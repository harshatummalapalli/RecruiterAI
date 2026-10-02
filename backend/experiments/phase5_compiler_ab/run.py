"""Phase 5 — live behavioral A/B: legacy translator vs deterministic compiler.

Only the provider SEARCH PLAN differs between arms. Both arms run through the
exact same run_search_pipeline (same legacy SearchIntent for ranking/judge/
admission, same Harvest/Judge/admission/N->50->25). The compiled arm retrieves
via the Phase-3 compiled filter tree (posted raw); the legacy arm retrieves via
the existing translator plan.

Credit safety: every CrustData POST is ledgered (results * 0.03 estimate + the
body's credits_used when present). Hard cap enforced before each role.
Nothing in production is changed. Run: python -m backend.experiments.phase5_compiler_ab.run
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.provider_capabilities import ProviderCapabilities
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.services.capability_mapper import CapabilityMapper
from backend.services.query_expansion import QueryExpansionService
from backend.services.search_planner import SearchPlanner
from backend.services.candidate_merger import CandidateMerger
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_store import SearchStore
from backend.providers.harvest import HarvestEnrichmentService
from backend.providers.crustdata import CrustDataProvider, DEFAULT_FIELDS
from backend.providers.openai import OpenAIProvider
from backend.services.requirement_judge import RequirementJudge
from backend.services.confirmation import search_intent_from_snapshot, location_override_for_search
from backend.services.search_pipeline import run_search_pipeline, MAX_WORKSPACE_CANDIDATES
from backend.config import get_discovery_page_size, get_discovery_max_pages
from backend.api import _apply_radius_degradation, _friendly_capability_warnings, CRUSTDATA_SUPPORTED_FILTERS, LocationOverride
from backend.models.structured_intent import parse_structured_intent
from backend.services.search_compiler import compile_intent

CREDIT_CAP = 12.0
CREDITS_PER_RESULT = 0.03
PAGE_SIZE = get_discovery_page_size()
LEDGER: List[Dict[str, Any]] = []
OUT = Path("output/experiments/phase5_compiler_ab")
FIX = Path("tests/fixtures")


class _LedgerMixin:
    """Record every CrustData POST's returned count + credit signals."""
    arm_label = "?"

    def _search_api(self, payload, options=None):  # type: ignore[override]
        resp = super()._search_api(payload, options=options)  # type: ignore[misc]
        profiles = resp.get("profiles") or []
        LEDGER.append({
            "arm": self.arm_label,
            "returned": len(profiles),
            "total_count": resp.get("total_count"),
            "credits_used_body": resp.get("credits_used") or resp.get("credit_usage"),
            "est_credits": round(len(profiles) * CREDITS_PER_RESULT, 3),
        })
        return resp


class LegacyProvider(_LedgerMixin, CrustDataProvider):
    pass


class RawTreeProvider(_LedgerMixin, CrustDataProvider):
    """Posts a precompiled filter tree verbatim, ignoring the SearchQuery."""
    def __init__(self, tree: Dict[str, Any], *a, **k):
        super().__init__(*a, **k)
        self._tree = tree

    def _build_payload(self, search, options=None, cursor=None):
        options = options or {}
        return {"filters": self._tree, "limit": int(options.get("page_size") or PAGE_SIZE), "fields": DEFAULT_FIELDS}


def _services():
    return dict(candidate_merger=CandidateMerger(), candidate_ranker=CandidateRanker(),
                harvest_enrichment_service=HarvestEnrichmentService(), requirement_judge=RequirementJudge(),
                match_explainer=MatchExplainer(), search_diagnostics=SearchDiagnostics(), search_store=SearchStore())


def _build_legacy_plan(intent):
    _apply_radius_degradation(intent)
    plan = SearchPlanner().build(intent)
    expanded = QueryExpansionService().expand(plan)
    caps = ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS)
    mapped, warnings = CapabilityMapper().map(expanded, caps)
    return mapped, _friendly_capability_warnings(warnings)


def legacy_intent_epiq():
    snap = json.loads(Path("output/confirmations/22db28f4-00cf-408d-ac4e-590a6cc0b952.json").read_text(encoding="utf-8"))
    intent = search_intent_from_snapshot(snap); intent.natural_language_search_query = None
    loc = LocationOverride(**location_override_for_search(intent, snap["boundary"]))
    L = intent.location; L.countries = list(loc.countries); L.states = list(loc.states); L.cities = list(loc.cities)
    L.zip_codes = list(loc.zip_codes); L.radius_miles = loc.radius_miles; L.radius_place = loc.radius_place
    L.radius_unit = loc.radius_unit or "mi"; L.work_mode = loc.work_mode
    return intent, loc.model_dump(), snap["raw_input"]


def legacy_intent_python():
    brief = json.loads((FIX / "regression_set" / "python_backend_hyderabad.json").read_text(encoding="utf-8"))["raw_brief"]
    intent = OpenAIProvider().parse_job_description(brief)
    return intent, None, brief


def compiled_tree(name):
    si = parse_structured_intent((FIX / "structured_intent" / f"{name}.expected.json").read_text(encoding="utf-8"))
    return compile_intent(si).filter_tree


def _run(search_id, intent, mapped_plan, provider, jd_text, location_override):
    now = datetime.now(timezone.utc).isoformat()
    rec = {"search_id": search_id, "status": "running", "created_at": now, "updated_at": now, "jd_text": jd_text,
           "response": {}, "recruiter_decisions": {}, "notes": {}, "candidate_states": {}, "harvest_evidence": {}, "internal_diagnostics": {}}
    SearchStore().save(search_id, rec)
    run_search_pipeline(search_id=search_id, intent=intent, mapped_plan=mapped_plan,
                        options={"page_size": PAGE_SIZE, "max_pages": get_discovery_max_pages(), "autocomplete": True},
                        provider=provider, jd_text=jd_text, location_override=location_override, friendly_warnings=[],
                        debug=False, existing_record=rec, target_pool_size=MAX_WORKSPACE_CANDIDATES, cycle=None, guidance=None, **_services())
    return search_id


def _ledger_total():
    return round(sum(e["est_credits"] for e in LEDGER), 3)


def run_role(role, name, legacy_builder):
    print(f"\n{'#'*70}\nROLE: {role}\n{'#'*70}")
    intent, loc_override, jd = legacy_builder()
    legacy_plan, _ = _build_legacy_plan(intent)
    tree = compiled_tree(name)
    print(f"[plan] legacy queries: {[q.query_name for q in legacy_plan.searches]}")
    print(f"[plan] compiled tree top-level conditions: {len(tree['conditions'])}")

    worst = (len(legacy_plan.searches) + 1) * PAGE_SIZE * CREDITS_PER_RESULT
    if _ledger_total() + worst > CREDIT_CAP:
        print(f"[STOP] would exceed cap: spent={_ledger_total()} + worst={worst} > {CREDIT_CAP}. Not running {role}.")
        return None

    ids = {}
    LegacyProvider.arm_label = f"{role}:legacy"
    ids["legacy"] = _run(f"p5-{role}-legacy-{uuid.uuid4().hex[:8]}", intent, legacy_plan, LegacyProvider(), jd, loc_override)
    print(f"[ledger] after legacy: {_ledger_total()} cr")

    tp = RawTreeProvider(tree); tp.arm_label = f"{role}:compiled"
    ids["compiled"] = _run(f"p5-{role}-compiled-{uuid.uuid4().hex[:8]}", intent,
                           SearchPlan(searches=[SearchQuery(query_name="compiled")]), tp, jd, loc_override)
    print(f"[ledger] after compiled: {_ledger_total()} cr")
    return {"role": role, "name": name, "ids": ids, "legacy_plan": [q.model_dump() for q in legacy_plan.searches], "compiled_tree": tree}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for role, name, builder in [("epiq", "epiq_product_owner", legacy_intent_epiq),
                                ("python", "python_backend_hyderabad", legacy_intent_python)]:
        r = run_role(role, name, builder)
        if r:
            manifest.append(r)
    (OUT / "manifest.json").write_text(json.dumps({"manifest": manifest, "ledger": LEDGER, "total_credits": _ledger_total()}, indent=2), encoding="utf-8")
    print(f"\n==== DONE. total CrustData credits (est): {_ledger_total()} / cap {CREDIT_CAP} ====")
    print("LEDGER:", json.dumps(LEDGER, indent=0))
    print("manifest:", OUT / "manifest.json")


if __name__ == "__main__":
    main()
