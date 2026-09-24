"""Evidence evaluation for the experiment: reads the top-25 of each strategy's
captured results with the EXISTING Harvest + requirement-judge machinery and
scores each candidate against the SAME confirmed requirements. Nothing here is
ground truth and nothing feeds back into ranking or admission."""

import dataclasses
import glob
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from pydantic import TypeAdapter

from backend.experiments.crustdata_retrieval import run as exp
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.providers.crustdata import CrustDataProvider
from backend.providers.harvest import HarvestEnrichmentService
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer
from backend.services.requirement_judge import RequirementJudge

DEPTH = 25


def _cached_harvest() -> Dict[str, HarvestEvidence]:
    """Successful Harvest reads already paid for in earlier searches (local, production copies, experiments)."""
    cache: Dict[str, HarvestEvidence] = {}
    patterns = [str(exp.ROOT / "output" / "searches" / "*.json"), str(exp.SCRATCH / "prod_searches" / "searches" / "*.json"), str(exp.SCRATCH / "*.json"), str(exp.SCRATCH / "p*_search_store" / "*.json")]
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            store = data.get("harvest_evidence") if isinstance(data, dict) else None
            if isinstance(store, dict):
                for cid, payload in store.items():
                    if isinstance(payload, dict) and payload.get("success") and payload.get("raw"):
                        cache[cid] = HarvestEvidence(**payload)
    return cache


def _load_candidates(role_key: str, strategy: str, provider: CrustDataProvider):
    data = exp._load(f"retrieval_{role_key}_{strategy}.json")
    candidates = provider._parse_candidates({"profiles": data["raw_items"]}, query_name="natural_language" if strategy == "nl" else "structured")
    return data, candidates  # candidates are in provider order


def plan() -> Dict[str, Any]:
    provider = CrustDataProvider()
    cache = _cached_harvest()
    need, cached = 0, 0
    per_role: Dict[str, Any] = {}
    for role in exp._load("manifest.json")["roles"]:
        ids = set()
        for strategy in ("nl", "structured"):
            _, cands = _load_candidates(role["role_key"], strategy, provider)
            ids |= {c.candidate_id for c in cands[:DEPTH]}
        hit = sum(1 for i in ids if i in cache)
        per_role[role["role_key"]] = {"candidates": len(ids), "already_in_harvest_cache": hit}
        need += len(ids) - hit
        cached += hit
    out = {"top_n_per_strategy": DEPTH, "per_role": per_role, "harvest_reads_needed": need, "reused_from_cache": cached, "estimated_harvest_usd": round(need * 0.0064, 2)}
    print(json.dumps(out, indent=1))
    return out


def evaluate() -> None:
    provider = CrustDataProvider()
    manifest = exp._load("manifest.json")
    cache = _cached_harvest()
    judge = RequirementJudge()
    explainer, ranker = MatchExplainer(), CandidateRanker()
    harvest_store: Dict[str, Any] = {}
    stats = {"harvest_calls": 0, "harvest_cost_usd": 0.0, "judge_calls": 0, "judge_input_tokens": 0, "judge_output_tokens": 0, "judge_failed": 0}

    for role in manifest["roles"]:
        intent = TypeAdapter(SearchIntent).validate_python(role["intent"])
        loaded = {s: _load_candidates(role["role_key"], s, provider) for s in ("nl", "structured")}
        wanted: Dict[str, Any] = {}
        for _, cands in loaded.values():
            for c in cands[:DEPTH]:
                wanted.setdefault(c.candidate_id, c)
        need = [c for cid, c in wanted.items() if cid not in cache]
        if need:
            service = HarvestEnrichmentService(top_n=len(need), concurrency=3)
            fetched = service.enrich_top_n(need, existing={})
            stats["harvest_calls"] += len(fetched)
            stats["harvest_cost_usd"] += sum(e.cost or 0.0 for e in fetched.values())
            cache.update({cid: e for cid, e in fetched.items() if e.success})
            harvest_by_id = {cid: e for cid, e in fetched.items()}
        else:
            harvest_by_id = {}
        for cid in wanted:
            if cid in cache:
                harvest_by_id[cid] = cache[cid]
        harvest_store.update({cid: dataclasses.asdict(e) for cid, e in harvest_by_id.items() if e.success})

        def judge_one(candidate):
            harvest = harvest_by_id.get(candidate.candidate_id)
            outcome = judge.judge_detailed(candidate, intent, harvest if harvest and harvest.success else None)
            return candidate.candidate_id, outcome

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = dict(pool.map(judge_one, list(wanted.values())))
        for outcome in outcomes.values():
            stats["judge_calls"] += outcome.calls
            stats["judge_input_tokens"] += outcome.input_tokens
            stats["judge_output_tokens"] += outcome.output_tokens
            stats["judge_failed"] += 1 if outcome.failed else 0

        role_rows: List[Dict[str, Any]] = []
        for strategy, (data, cands) in loaded.items():
            for position, candidate in enumerate(cands[:DEPTH], start=1):
                harvest = harvest_by_id.get(candidate.candidate_id)
                harvest = harvest if harvest and harvest.success else None
                outcome = outcomes[candidate.candidate_id]
                if outcome.judgments is not None and not outcome.failed:
                    candidate.raw_data["__requirement_judgments"] = outcome.judgments
                evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)
                explanation = explainer.explain(candidate, intent, harvest_evidence=harvest)
                alignment = evidence.role_alignment
                real = [s for s in alignment.matched_signals if s.source != "career dates"]
                score = sum(ranker.score_components(evidence, candidate.provider_score).values())
                role_rows.append(
                    {
                        "role_key": role["role_key"], "strategy": strategy, "provider_position": position, "candidate_id": candidate.candidate_id,
                        "current_title": candidate.title, "current_company": candidate.company, "harvest_read": harvest is not None,
                        "judged": bool(outcome.judgments) and not outcome.failed,
                        "met": {t: sum(1 for s in alignment.matched_signals if s.tier == t) for t in ("core", "supporting", "differentiator")},
                        "requirement_totals": {"core": len(intent.core_signals), "supporting": len(intent.supporting_signals), "differentiator": len(intent.differentiator_signals)},
                        "met_excluding_career_dates": len(real),
                        "demonstrated_evidence": sum(1 for s in real if s.strength == "strong"),
                        "listed_only_evidence": sum(1 for s in real if s.strength != "strong"),
                        "core_met_excluding_dates": sum(1 for s in real if s.tier == "core"),
                        "level_fit": alignment.level_fit, "experience_floor": alignment.experience_floor,
                        "derived_experience_years": evidence.derived_experience_years,
                        "concerns": explanation.potential_concerns,
                        "unproven_core": [s.signal_text for s in alignment.unmatched_signals if s.tier == "core"],
                        "title_relevance": alignment.title_relevance,
                        "existing_release1_score_descriptive_only": round(score, 2),
                        "fit": data["rows"][position - 1]["fit"],
                        "quotes": [{"tier": s.tier, "requirement": s.signal_text, "source": s.source, "quote": s.evidence_text[:200]} for s in real],
                    }
                )
        exp._dump(f"evaluation_{role['role_key']}.json", role_rows)
        print(f"{role['role_key']}: evaluated {len(wanted)} unique candidates, harvest reads this role={len(need)}")
    exp._dump("harvest_evaluation_cache.json", harvest_store)
    stats["judge_estimated_usd"] = round((stats["judge_input_tokens"] * 0.15 + stats["judge_output_tokens"] * 0.60) / 1_000_000, 4)
    exp._dump("evaluation_stats.json", stats)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    import sys

    {"plan": plan, "evaluate": evaluate}[sys.argv[1]]()
