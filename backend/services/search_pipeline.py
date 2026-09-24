"""Progressive Candidate Workspace — the CrustData -> Harvest -> rerank
portion of a search, extracted from backend/api.py's POST /search so it can
run on a background thread instead of blocking the HTTP request.

Intent resolution and search-plan building stay synchronous in api.py (fast,
no network calls, and where existing error handling for a bad request
already lives); everything here is the slow, network-bound part, plus the
progressive persistence that lets GET /search/{id} reflect a running search.

Candidate lifecycle (system-driven, three states only):
    SURFACED -> BUILDING_CONTEXT -> REVIEW_READY
This is deliberately separate from the recruiter's own decision
(recruiter_decisions: shortlist/reject, unchanged, untouched by this
module) — see the product spec's "lifecycle != recruiter decision".

Search-level status:
    running -> complete
    running -> error            (an unhandled exception during the pipeline)
    running -> interrupted      (only via reconcile_interrupted_searches, at
                                  process startup — never set mid-search)

Identity: every candidate is addressed by CrustData's own
`candidate_id` (see _candidate_key) — never profile_url, never array
position. CandidateMerger already prefers this same field as its primary
dedup key for the identical reason (exact, always present).
"""

import dataclasses
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan
from backend.providers.base import BaseProvider
from backend.providers.harvest import HarvestEnrichmentService
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.candidate_merger import CandidateMerger
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_store import SearchStore

logger = logging.getLogger(__name__)

# Candidate lifecycle — exactly these three, per product decision. Never
# combined with recruiter_decisions.
SURFACED = "surfaced"
BUILDING_CONTEXT = "building_context"
REVIEW_READY = "review_ready"

# Search-level status.
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_INTERRUPTED = "interrupted"
STATUS_ERROR = "error"

# Recruiter-facing workspace hard cap. Deliberately a SEPARATE knob from
# HARVEST_ENRICHMENT_TOP_N (backend/config.py) — workspace admission and
# enrichment budget are independent decisions (see product spec, "Harvest
# budget" section): a candidate can be admitted into the workspace and
# still never receive Harvest enrichment.
MAX_WORKSPACE_CANDIDATES = 25

# Minimum merged/deduplicated candidate count before the supplementary
# title-expansion query is skipped (Phase 3, moved here unchanged from
# backend/api.py) — a separate tuning knob from MAX_WORKSPACE_CANDIDATES
# above even though both are currently 25: this one governs when a SECOND
# CrustData query is worth its cost, not how many candidates the recruiter
# workspace admits.
DISCOVERY_TARGET_POOL_SIZE = 25


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_key(candidate: Candidate) -> str:
    """The one stable identity used for lifecycle/decisions/notes. Never
    profile_url, never array position — see module docstring."""
    return candidate.candidate_id or ""


def run_adaptive_discovery(
    provider: BaseProvider,
    mapped_plan: SearchPlan,
    options: Dict[str, Any],
    candidate_merger: CandidateMerger,
    target_pool_size: int,
) -> tuple:
    """Run the primary natural-language query alone first; only run the
    supplementary title-expansion query if the primary didn't reach the
    target pool size. Returns the raw candidates from whichever queries
    actually ran, plus a SearchPlan reflecting only those queries. Moved
    here unchanged from backend/api.py (Progressive Candidate Workspace) —
    behavior is identical, only the module changed."""
    primary_queries = [q for q in mapped_plan.searches if q.query_name == "natural_language"]
    other_queries = [q for q in mapped_plan.searches if q.query_name != "natural_language"]

    def run(searches: List[Any]) -> List[Any]:
        sub_plan = SearchPlan(searches=searches, strategy=mapped_plan.strategy, reasoning=mapped_plan.reasoning, confidence_score=mapped_plan.confidence_score)
        if hasattr(provider, "search_with_options"):
            return provider.search_with_options(sub_plan, options=options)
        return provider.search(sub_plan)

    if not primary_queries:
        candidates = run(mapped_plan.searches)
        return candidates, mapped_plan

    candidates = run(primary_queries)
    executed_searches = list(primary_queries)

    if other_queries:
        unique_so_far = len(candidate_merger.merge(candidates))
        if unique_so_far < target_pool_size:
            candidates = candidates + run(other_queries)
            executed_searches = executed_searches + other_queries

    executed_plan = SearchPlan(
        searches=executed_searches,
        strategy=mapped_plan.strategy,
        reasoning=mapped_plan.reasoning,
        confidence_score=mapped_plan.confidence_score,
    )
    return candidates, executed_plan


def reconcile_interrupted_searches(search_store: SearchStore) -> int:
    """Called once at process startup. A background search thread cannot
    survive a process restart (deploy, crash) — any record still marked
    "running" at startup is therefore unambiguously orphaned, not actually
    in progress. Flips it to "interrupted" so a polling frontend gets a
    definitive terminal state instead of polling forever. Returns the
    number of records reconciled."""
    storage_dir = Path(search_store.storage_dir)
    if not storage_dir.exists():
        return 0

    reconciled = 0
    for path in storage_dir.glob("*.json"):
        record = search_store.load(path.stem)
        if not record or record.get("status") != STATUS_RUNNING:
            continue
        record["status"] = STATUS_INTERRUPTED
        record["updated_at"] = _now_iso()
        response = record.get("response")
        if isinstance(response, dict):
            response["status"] = STATUS_INTERRUPTED
        search_store.save(path.stem, record)
        reconciled += 1
        logger.warning("Marked orphaned running search as interrupted | search_id=%s", path.stem)
    return reconciled


def run_search_pipeline(
    *,
    search_id: str,
    intent: SearchIntent,
    mapped_plan: SearchPlan,
    options: Dict[str, Any],
    provider: BaseProvider,
    candidate_merger: CandidateMerger,
    candidate_ranker: CandidateRanker,
    harvest_enrichment_service: HarvestEnrichmentService,
    match_explainer: MatchExplainer,
    search_diagnostics: SearchDiagnostics,
    search_store: SearchStore,
    jd_text: str,
    location_override: Optional[Dict[str, Any]],
    friendly_warnings: List[str],
    debug: bool,
    existing_record: Dict[str, Any],
    target_pool_size: int = MAX_WORKSPACE_CANDIDATES,
) -> None:
    """The slow half of a search — CrustData discovery through final rerank —
    designed to run on a background thread. Persists progressively via
    search_store so GET /search/{search_id} can reflect a running search at
    any point (see module docstring for the exact milestones)."""
    started_at = time.perf_counter()
    created_at = existing_record.get("created_at") or _now_iso()
    existing_harvest_raw = existing_record.get("harvest_evidence", {})
    existing_harvest = {
        candidate_id: HarvestEvidence(**payload) for candidate_id, payload in existing_harvest_raw.items()
    }
    recruiter_decisions = existing_record.get("recruiter_decisions", {})
    notes = existing_record.get("notes", {})
    harvest_by_id: Dict[str, HarvestEvidence] = {}

    def _persist(
        *,
        status: str,
        candidates: List[Candidate],
        explanations: List[Optional[Dict[str, Any]]],
        evidence: List[Optional[Dict[str, Any]]],
        candidate_states: Dict[str, str],
        diagnostics: Optional[Dict[str, Any]] = None,
        debug_payload: Optional[Dict[str, Any]] = None,
        internal_diagnostics: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        progress = {"admitted": len(candidates), "surfaced": 0, "building_context": 0, "review_ready": 0}
        for state in candidate_states.values():
            if state in progress:
                progress[state] += 1

        response: Dict[str, Any] = {
            "provider": "platform",
            "search_id": search_id,
            "candidate_count": len(candidates),
            "candidates": [candidate.model_dump() for candidate in candidates],
            "explanations": [entry or {} for entry in explanations],
            "evidence": [entry or {} for entry in evidence],
            "diagnostics": diagnostics or {},
            "warnings": friendly_warnings,
            "debug": debug_payload,
            "recruiter_decisions": recruiter_decisions,
            "notes": notes,
            "status": status,
            "candidate_states": dict(candidate_states),
            "progress": progress,
        }
        record: Dict[str, Any] = {
            "search_id": search_id,
            "status": status,
            "created_at": created_at,
            "updated_at": _now_iso(),
            "jd_text": jd_text,
            "location_override": location_override,
            "response": response,
            "recruiter_decisions": recruiter_decisions,
            "notes": notes,
            "candidate_states": dict(candidate_states),
            "harvest_evidence": {
                **existing_harvest_raw,
                **{candidate_id: dataclasses.asdict(ev) for candidate_id, ev in harvest_by_id.items()},
            },
            "internal_diagnostics": internal_diagnostics or {},
        }
        if error_message:
            record["error_message"] = error_message
        search_store.save(search_id, record)

    admitted: List[Candidate] = []
    explanations: List[Optional[Dict[str, Any]]] = []
    evidence: List[Optional[Dict[str, Any]]] = []
    candidate_states: Dict[str, str] = {}

    try:
        # --- Discovery + merge (unchanged provider/merge logic) ---
        raw_candidates, executed_plan = run_adaptive_discovery(
            provider=provider,
            mapped_plan=mapped_plan,
            options=options,
            candidate_merger=candidate_merger,
            target_pool_size=DISCOVERY_TARGET_POOL_SIZE,
        )
        logger.info("[SEARCH] Candidates Returned | search_id=%s count=%s queries_run=%s", search_id, len(raw_candidates), len(executed_plan.searches))
        merged_candidates = candidate_merger.merge(raw_candidates)
        logger.info("[SEARCH] Candidate merge complete | search_id=%s unique=%s", search_id, len(merged_candidates))

        # --- Baseline ranking (existing formula, unchanged) ---
        ranked_candidates = candidate_ranker.rank(merged_candidates, intent)
        logger.info("[SEARCH] Baseline ranking complete | search_id=%s count=%s", search_id, len(ranked_candidates))

        # --- Admission: top N by the EXISTING baseline rank. No new score
        # threshold — per product decision, a positional cut on the
        # already-validated ranking, nothing else. ---
        admitted = ranked_candidates[:target_pool_size]

        # CrustData always provides candidate_id in practice (CandidateMerger
        # already relies on it as its primary dedup key for the same reason),
        # but a provider adapter is free to omit it — assign a synthetic,
        # stable id right here so every identity-keyed structure below
        # (candidate_states, explanations/evidence lookup, and the
        # candidate_id the frontend ultimately receives) always has a real,
        # non-empty, consistent value to key on. Never profile_url, never
        # array position after a later reorder — this is set once, up front.
        for index, candidate in enumerate(admitted):
            if not candidate.candidate_id:
                candidate.candidate_id = f"admitted-{search_id}-{index}"

        id_to_index = {_candidate_key(c): i for i, c in enumerate(admitted)}

        # Every admitted candidate gets a REAL explanation/evidence pair
        # immediately (CrustData-only at this point — no network call,
        # identical computation build_candidate_evidence/match_explainer
        # already do). Harvest only upgrades a subset of these later; it is
        # never a prerequisite for a candidate to have usable evidence.
        explanations = [None] * len(admitted)
        evidence = [None] * len(admitted)
        for index, candidate in enumerate(admitted):
            explanation_obj = match_explainer.explain(candidate, intent)
            evidence_obj = build_candidate_evidence(candidate, intent)
            explanations[index] = explanation_obj.model_dump()
            evidence[index] = dataclasses.asdict(evidence_obj)
            candidate_states[_candidate_key(candidate)] = SURFACED

        _persist(status=STATUS_RUNNING, candidates=admitted, explanations=explanations, evidence=evidence, candidate_states=candidate_states)
        logger.info("[SEARCH] Admitted into workspace | search_id=%s admitted=%s", search_id, len(admitted))

        # --- Enrichment budget (HARVEST_ENRICHMENT_TOP_N, unchanged=15) is
        # a slice of the ADMITTED workspace, never the full discovery pool. ---
        harvest_slice = admitted[: harvest_enrichment_service.top_n]
        harvest_slice_ids = {_candidate_key(c) for c in harvest_slice if _candidate_key(c)}
        for candidate_id in harvest_slice_ids:
            candidate_states[candidate_id] = BUILDING_CONTEXT
        # Candidates outside the enrichment budget already have complete
        # (CrustData-only) evidence from the loop above — reviewable now,
        # never silently held back just because they missed the Harvest cut.
        for candidate in admitted:
            candidate_id = _candidate_key(candidate)
            if candidate_id and candidate_id not in harvest_slice_ids:
                candidate_states[candidate_id] = REVIEW_READY

        _persist(status=STATUS_RUNNING, candidates=admitted, explanations=explanations, evidence=evidence, candidate_states=candidate_states)

        def _promote_after_harvest(candidate: Candidate, harvest_evidence_obj: HarvestEvidence) -> None:
            candidate_id = _candidate_key(candidate)
            index = id_to_index.get(candidate_id)
            if index is None:
                return
            explanation_obj = match_explainer.explain(candidate, intent, harvest_evidence=harvest_evidence_obj)
            evidence_obj = build_candidate_evidence(candidate, intent, harvest_evidence=harvest_evidence_obj)
            explanations[index] = explanation_obj.model_dump()
            evidence[index] = dataclasses.asdict(evidence_obj)
            candidate_states[candidate_id] = REVIEW_READY
            _persist(status=STATUS_RUNNING, candidates=admitted, explanations=explanations, evidence=evidence, candidate_states=candidate_states)

        # --- Harvest, progressively. Reuses HarvestEnrichmentService's own
        # fetch logic (_fetch_one — same network call, same error handling,
        # same idempotency, same concurrency setting) unchanged; only the
        # orchestration loop is inlined here (instead of inside
        # enrich_top_n, which only returns once the whole batch is done) so
        # each candidate can be promoted the moment ITS fetch resolves,
        # exactly as the product spec asks for ("as_completed... so
        # candidates transition individually"). ---
        to_fetch: List[Candidate] = []
        for candidate in harvest_slice:
            candidate_id = _candidate_key(candidate)
            cached = existing_harvest.get(candidate_id) if candidate_id else None
            if cached is not None and cached.success:
                harvest_by_id[candidate_id] = cached
                _promote_after_harvest(candidate, cached)
            elif candidate_id:
                to_fetch.append(candidate)

        if to_fetch and harvest_enrichment_service._client.is_configured():
            concurrency = max(1, harvest_enrichment_service.concurrency)
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                future_to_candidate = {pool.submit(harvest_enrichment_service._fetch_one, c): c for c in to_fetch}
                for future in as_completed(future_to_candidate):
                    candidate = future_to_candidate[future]
                    candidate_id = _candidate_key(candidate)
                    try:
                        harvest_evidence_obj = future.result()
                    except Exception:  # noqa: BLE001 - one candidate's Harvest
                        # call must never take down the whole search. _fetch_one
                        # already converts every KNOWN failure mode (timeout,
                        # HTTP error, malformed response, not configured) into
                        # a graceful HarvestEvidence(success=False, ...); this
                        # is the backstop for anything unexpected it doesn't
                        # already handle — same degrade-and-continue contract.
                        logger.exception("Unexpected Harvest failure for one candidate | search_id=%s candidate_id=%s", search_id, candidate_id)
                        harvest_evidence_obj = HarvestEvidence(success=False, error="unexpected_error", fetched_at=_now_iso())
                    harvest_by_id[candidate_id] = harvest_evidence_obj
                    _promote_after_harvest(candidate, harvest_evidence_obj)
        elif to_fetch:
            # Harvest not configured at all — every to_fetch candidate
            # degrades to CrustData-only evidence, exactly like a Harvest
            # failure does (see HarvestEnrichmentService's own docstring:
            # "zero network calls... discovery unaffected").
            for candidate in to_fetch:
                _promote_after_harvest(candidate, HarvestEvidence(success=False, error="not_configured", fetched_at=_now_iso()))

        logger.info(
            "[SEARCH] Harvest enrichment complete | search_id=%s attempted=%s succeeded=%s",
            search_id,
            len(harvest_by_id),
            sum(1 for e in harvest_by_id.values() if e.success),
        )

        # --- Single deliberate rerank — the EXISTING formula
        # (rerank_top_n), invoked exactly once, after the whole Harvest
        # batch has settled. Never per-candidate — this is what prevents
        # the list from continuously reshuffling. ---
        admitted = candidate_ranker.rerank_top_n(admitted, intent, harvest_by_id, top_n=harvest_enrichment_service.top_n)
        reordered_explanations = [explanations[id_to_index[_candidate_key(c)]] for c in admitted]
        reordered_evidence = [evidence[id_to_index[_candidate_key(c)]] for c in admitted]
        explanations, evidence = reordered_explanations, reordered_evidence

        diagnostics_report = search_diagnostics.analyze(executed_plan, admitted)
        diagnostics_dict = {
            "total_queries": diagnostics_report.total_queries,
            "total_candidates": diagnostics_report.total_candidates,
            "candidates_per_query": diagnostics_report.candidates_per_query,
            "duplicate_candidates": diagnostics_report.duplicate_candidates,
            "average_provider_score": diagnostics_report.average_provider_score,
            "average_final_score": diagnostics_report.average_final_score,
            "top_job_titles": diagnostics_report.top_job_titles,
            "top_companies": diagnostics_report.top_companies,
            "query_execution_summary": diagnostics_report.query_execution_summary,
        }

        execution_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
        debug_payload = None
        if debug:
            final_provider_payload = provider.debug_payloads(executed_plan, options) if hasattr(provider, "debug_payloads") else None
            debug_payload = {
                "search_id": search_id,
                "execution_time_ms": execution_time_ms,
                "jd_text": jd_text,
                "location_override": location_override,
                "generated_provider_query": [q.model_dump() for q in executed_plan.searches],
                "final_provider_payload": final_provider_payload,
                "candidates_returned": len(raw_candidates),
                "candidates_after_merge": len(merged_candidates),
                "candidates_ranked": len(ranked_candidates),
            }

        _persist(
            status=STATUS_COMPLETE,
            candidates=admitted,
            explanations=explanations,
            evidence=evidence,
            candidate_states=candidate_states,
            diagnostics=diagnostics_dict,
            debug_payload=debug_payload,
            internal_diagnostics={"total_search_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1)},
        )
        logger.info("[SEARCH] Execution complete | search_id=%s execution_time_ms=%s", search_id, execution_time_ms)

    except Exception as exc:  # noqa: BLE001 - a background thread has no caller to raise to
        logger.exception("Search pipeline failed in background | search_id=%s", search_id)
        _persist(
            status=STATUS_ERROR,
            candidates=admitted,
            explanations=explanations,
            evidence=evidence,
            candidate_states=candidate_states,
            error_message=str(exc),
        )
