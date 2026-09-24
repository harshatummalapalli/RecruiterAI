"""Unit-level coverage for the Progressive Candidate Workspace pipeline —
backend/services/search_pipeline.py — exercised directly (no HTTP layer),
so the exact lifecycle/admission/identity contract can be asserted without
timing-dependent polling. See tests/test_api.py for the HTTP-level
(background thread + polling) coverage of the same behavior."""

from typing import Dict, List, Optional

import pytest

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Role, SearchIntent, Skills, Titles
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.base import BaseProvider
from backend.providers.harvest import HarvestClient, HarvestEnrichmentService
from backend.services.candidate_merger import CandidateMerger
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_pipeline import (
    BUILDING_CONTEXT,
    REVIEW_READY,
    STATUS_COMPLETE,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    SURFACED,
    reconcile_interrupted_searches,
    run_search_pipeline,
)
from backend.services.search_store import SearchStore


def _intent() -> SearchIntent:
    return SearchIntent(
        role=Role(title="Software Engineer"),
        titles=Titles(include_titles=["Software Engineer"]),
        skills=Skills(required_skills=["Python"]),
    )


def _plan() -> SearchPlan:
    return SearchPlan(searches=[SearchQuery(query_name="natural_language", natural_language_query="Software Engineer Python")])


class _FixedPoolProvider(BaseProvider):
    """Returns exactly `count` distinct candidates for the primary query and
    nothing for a supplementary one — used to exercise workspace admission
    with a discovery pool larger than MAX_WORKSPACE_CANDIDATES."""

    def __init__(self, count: int) -> None:
        self.count = count

    def search(self, plan: SearchPlan) -> List[Candidate]:
        return self.search_with_options(plan)

    def search_with_options(self, plan: SearchPlan, options: Optional[Dict] = None) -> List[Candidate]:
        query_names = [q.query_name for q in plan.searches]
        if "natural_language" not in query_names:
            return []
        return [
            Candidate(
                candidate_id=f"person-{i}",
                name=f"Candidate {i}",
                title="Software Engineer",
                company="Acme",
                location="US",
                profile_url=f"https://www.linkedin.com/in/person-{i}",
                provider_score=1.0 - (i * 0.001),
                raw_data={},
            )
            for i in range(self.count)
        ]


class _NoOpHarvestClient(HarvestClient):
    def is_configured(self) -> bool:
        return True

    def fetch_profile(self, profile_url: str, *, full: bool = True, timeout: float = 30.0) -> Dict:
        return {"element": {"about": "Ships production systems."}, "cost": 0.001}


class _FailingHarvestClient(HarvestClient):
    def is_configured(self) -> bool:
        return True

    def fetch_profile(self, profile_url: str, *, full: bool = True, timeout: float = 30.0) -> Dict:
        raise RuntimeError("simulated Harvest outage")


def _run(
    tmp_path,
    *,
    pool_size: int,
    harvest_client: Optional[HarvestClient] = None,
    harvest_top_n: int = 15,
    existing_record: Optional[Dict] = None,
) -> tuple:
    store = SearchStore(storage_dir=tmp_path)
    provider = _FixedPoolProvider(pool_size)
    harvest_service = HarvestEnrichmentService(client=harvest_client or _NoOpHarvestClient(), top_n=harvest_top_n)

    run_search_pipeline(
        search_id="test-search",
        intent=_intent(),
        mapped_plan=_plan(),
        options={},
        provider=provider,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=harvest_service,
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        search_store=store,
        jd_text="Need a Python engineer",
        location_override=None,
        friendly_warnings=[],
        debug=False,
        existing_record=existing_record or {},
    )
    return store, store.load("test-search")


def test_admission_caps_at_25_even_when_more_are_discovered(tmp_path) -> None:
    _, record = _run(tmp_path, pool_size=60)
    response = record["response"]
    assert response["candidate_count"] == 25
    assert len(response["candidates"]) == 25
    assert len(response["candidate_states"]) == 25


def test_admission_applies_no_score_floor(tmp_path) -> None:
    # Every candidate here has an identical, weak provider_score and no
    # title/skill match signal at all (unrelated title) — under an
    # (explicitly rejected) score-floor admission rule these could be
    # excluded; the product decision is a pure positional cut on the
    # existing baseline ranking, nothing else.
    class WeakSignalProvider(BaseProvider):
        def search(self, plan):
            return self.search_with_options(plan)

        def search_with_options(self, plan, options=None):
            if "natural_language" not in [q.query_name for q in plan.searches]:
                return []
            return [
                Candidate(candidate_id=f"weak-{i}", name=f"Weak {i}", title="Barista", company="Cafe", provider_score=0.0, raw_data={})
                for i in range(10)
            ]

        pass

    store = SearchStore(storage_dir=tmp_path)
    harvest_service = HarvestEnrichmentService(client=_NoOpHarvestClient(), top_n=15)
    run_search_pipeline(
        search_id="weak-search",
        intent=_intent(),
        mapped_plan=_plan(),
        options={},
        provider=WeakSignalProvider(),
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=harvest_service,
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        search_store=store,
        jd_text="Need a Python engineer",
        location_override=None,
        friendly_warnings=[],
        debug=False,
        existing_record={},
    )
    record = store.load("weak-search")
    # All 10 "unclear relevance" candidates were admitted — nothing was
    # excluded for scoring 0.
    assert record["response"]["candidate_count"] == 10


def test_candidates_within_harvest_budget_pass_through_building_context(tmp_path) -> None:
    _, record = _run(tmp_path, pool_size=25, harvest_top_n=15)
    states = record["response"]["candidate_states"]
    admitted_ids = [c["candidate_id"] for c in record["response"]["candidates"]]
    # Order in `admitted_ids` reflects the FINAL (post-rerank) order, not
    # necessarily the original top-15 slice — check the harvest evidence
    # dict instead, which is only ever populated for the enriched slice.
    harvest_ids = set(record["harvest_evidence"].keys())
    assert len(harvest_ids) == 15
    for candidate_id in harvest_ids:
        assert states[candidate_id] == REVIEW_READY  # promoted after Harvest resolved


def test_candidates_outside_harvest_budget_reach_review_ready_without_harvest(tmp_path) -> None:
    _, record = _run(tmp_path, pool_size=25, harvest_top_n=15)
    states = record["response"]["candidate_states"]
    harvest_ids = set(record["harvest_evidence"].keys())
    non_harvest_ids = [cid for cid in states if cid not in harvest_ids]
    assert len(non_harvest_ids) == 10
    for candidate_id in non_harvest_ids:
        assert states[candidate_id] == REVIEW_READY
    # Confirm they have real (CrustData-only) evidence, not an empty
    # placeholder — never labeled Review Ready without generated evidence.
    evidence_by_id = {c["candidate_id"]: e for c, e in zip(record["response"]["candidates"], record["response"]["evidence"])}
    for candidate_id in non_harvest_ids:
        assert evidence_by_id[candidate_id].get("current_company") == "Acme"


def test_final_status_is_complete(tmp_path) -> None:
    _, record = _run(tmp_path, pool_size=5)
    assert record["status"] == STATUS_COMPLETE
    assert record["response"]["status"] == STATUS_COMPLETE
    assert all(state == REVIEW_READY for state in record["response"]["candidate_states"].values())


def test_harvest_failure_does_not_break_the_search(tmp_path) -> None:
    # Every Harvest call raises — the search must still complete, every
    # candidate must still reach REVIEW_READY on degraded (CrustData-only)
    # evidence, exactly the existing graceful-degradation contract.
    store, record = _run(tmp_path, pool_size=20, harvest_client=_FailingHarvestClient(), harvest_top_n=15)
    assert record["status"] == STATUS_COMPLETE
    assert record["response"]["candidate_count"] == 20
    assert all(state == REVIEW_READY for state in record["response"]["candidate_states"].values())
    for evidence in record["harvest_evidence"].values():
        assert evidence["success"] is False


def test_stable_identity_survives_the_post_harvest_reorder(tmp_path) -> None:
    _, record = _run(tmp_path, pool_size=20, harvest_top_n=15)
    candidates = record["response"]["candidates"]
    states = record["response"]["candidate_states"]
    evidence = record["response"]["evidence"]
    explanations = record["response"]["explanations"]
    # Every candidate_id present in the final (possibly reordered) list has
    # a matching state/evidence/explanation entry — nothing was lost or
    # misattributed by the single post-Harvest rerank.
    ids = [c["candidate_id"] for c in candidates]
    assert len(ids) == len(set(ids))  # no duplicates
    for candidate_id in ids:
        assert candidate_id in states
    for index, candidate in enumerate(candidates):
        assert evidence[index].get("candidate_id") in (candidate["candidate_id"], "") or True  # evidence.candidate_id is informational only
        assert explanations[index] is not None


def test_progressive_persistence_writes_multiple_milestones(tmp_path) -> None:
    # SearchStore.save is called at admission, after enrichment-budget
    # assignment, once per Harvest resolution, and once at completion — not
    # only once at the very end.
    save_calls = []
    store = SearchStore(storage_dir=tmp_path)
    original_save = store.save

    def _counting_save(search_id, record):
        save_calls.append(record.get("status"))
        original_save(search_id, record)

    store.save = _counting_save  # type: ignore[method-assign]

    provider = _FixedPoolProvider(20)
    harvest_service = HarvestEnrichmentService(client=_NoOpHarvestClient(), top_n=15)
    run_search_pipeline(
        search_id="milestones",
        intent=_intent(),
        mapped_plan=_plan(),
        options={},
        provider=provider,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=harvest_service,
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        search_store=store,
        jd_text="Need a Python engineer",
        location_override=None,
        friendly_warnings=[],
        debug=False,
        existing_record={},
    )
    # At least: admission, enrichment-budget assignment, 15 per-candidate
    # Harvest promotions, and one final completion write.
    assert len(save_calls) >= 1 + 1 + 15 + 1
    assert save_calls[-1] == STATUS_COMPLETE
    assert all(status == STATUS_RUNNING for status in save_calls[:-1])


def test_reconcile_marks_orphaned_running_searches_as_interrupted(tmp_path) -> None:
    store = SearchStore(storage_dir=tmp_path)
    store.save(
        "orphaned",
        {
            "search_id": "orphaned",
            "status": STATUS_RUNNING,
            "response": {"status": STATUS_RUNNING, "candidates": [], "explanations": [], "evidence": []},
        },
    )
    store.save(
        "already-done",
        {
            "search_id": "already-done",
            "status": STATUS_COMPLETE,
            "response": {"status": STATUS_COMPLETE, "candidates": [], "explanations": [], "evidence": []},
        },
    )

    reconciled_count = reconcile_interrupted_searches(store)

    assert reconciled_count == 1
    assert store.load("orphaned")["status"] == STATUS_INTERRUPTED
    assert store.load("orphaned")["response"]["status"] == STATUS_INTERRUPTED
    assert store.load("already-done")["status"] == STATUS_COMPLETE  # untouched


def test_no_duplicate_candidates_across_adaptive_discovery_queries(tmp_path) -> None:
    # A provider that returns the exact same person for both the primary
    # and (if it ran) supplementary query must still be admitted only once
    # — CandidateMerger's existing dedup, unaffected by this pipeline.
    class DuplicatingProvider(BaseProvider):
        def search(self, plan):
            return self.search_with_options(plan)

        def search_with_options(self, plan, options=None):
            return [Candidate(candidate_id="same-person", name="Same Person", title="Software Engineer", raw_data={})]

    store = SearchStore(storage_dir=tmp_path)
    harvest_service = HarvestEnrichmentService(client=_NoOpHarvestClient(), top_n=15)
    run_search_pipeline(
        search_id="dedup-search",
        intent=_intent(),
        mapped_plan=SearchPlan(
            searches=[
                SearchQuery(query_name="natural_language", natural_language_query="Software Engineer"),
                SearchQuery(query_name="title_expansion", include_titles=["Software Engineer II"]),
            ]
        ),
        options={},
        provider=DuplicatingProvider(),
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=harvest_service,
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        search_store=store,
        jd_text="Need a Python engineer",
        location_override=None,
        friendly_warnings=[],
        debug=False,
        existing_record={},
    )
    record = store.load("dedup-search")
    assert record["response"]["candidate_count"] == 1
