"""Phase 5.2 — third live A/B role: recruiter-brief constraints beyond the JD.

Ordinary JD (role/years/location) + a recruiter/HM brief carrying target
companies, company size, education, radius, and an exclusion. Legacy path sees
JD only (it has no recruiter-brief channel); compiled path merges JD+brief ->
structured intent -> compiled tree. Same N->50->25, same downstream intent
(legacy jd-parse intent, for retrieval isolation); fair relevance is measured
credit-free afterwards by re-judging both sets against the common compiler
intent (see evaluate.py).

Run: python -m backend.experiments.phase5_compiler_ab.run_role3
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.openai import OpenAIProvider
from backend.services.structured_intent_extractor import extract_structured_intent
from backend.services.search_compiler import compile_intent
from backend.experiments.structured_playground import runner as raw_runner
from backend.experiments.phase5_compiler_ab.run import (
    LegacyProvider, RawTreeProvider, _services, _build_legacy_plan, _run, PAGE_SIZE, LEDGER, _ledger_total, CREDIT_CAP,
)

OUT = Path("output/experiments/phase5_compiler_ab")

JD = ("Software Engineer. We are hiring a Software Engineer with 4 to 9 years of experience to design, "
      "build and maintain backend services and APIs. Location: Hyderabad, India.")
RECRUITER_BRIEF = (
    "Prefer candidates who have worked at Flipkart, Walmart, or PhonePe at some point in their career. "
    "They must currently be at a company with at least 5000 employees. "
    "Require a B.Tech or B.E degree in Computer Science or Information Technology. "
    "Only consider candidates within 25 miles of Hyderabad. "
    "Do not consider anyone currently working at Infosys.")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Extracting compiled structured intent from JD + recruiter brief (gpt-6.1-sol)...")
    si = extract_structured_intent(JD, recruiter_brief=RECRUITER_BRIEF)
    plan = compile_intent(si)
    tree = plan.filter_tree
    print("STRUCTURED INTENT (recruiter-supplied highlights):")
    print("  companies:", [(c.name, c.relationship, c.strength) for c in si.companies])
    print("  company_scale:", si.company_scale)
    print("  education:", si.education)
    print("  radius:", si.location.radius if si.location else None)
    print("  exclusions:", [(x.kind, x.value) for x in si.exclusions])
    print("  compiled tree conditions:", len(tree["conditions"]))

    # Cheap pre-check to avoid spending a full run on an empty compiled pool.
    probe = raw_runner.run(tree, 1, context={"probe": "role3-compiled"})
    tc = probe.get("total_count_provider_reported")
    print(f"[pre-check] compiled tree total_count = {tc} (credits spent so far ~{_ledger_total()})")
    if not tc or tc < 5:
        print(f"[STOP] compiled pool too small ({tc}); not spending a full run. Recording and stopping.")
        (OUT / "manifest_role3.json").write_text(json.dumps({"jd": JD, "recruiter_brief": RECRUITER_BRIEF,
            "structured_intent": si.model_dump(exclude_none=True), "compiled_tree": tree,
            "compiled_total_count": tc, "status": "stopped_small_pool"}, indent=2), encoding="utf-8")
        return

    # Legacy sees JD ONLY (no recruiter-brief channel in the old path).
    legacy_intent = OpenAIProvider().parse_job_description(JD)
    legacy_plan, _ = _build_legacy_plan(legacy_intent)
    print("LEGACY plan queries:", [q.query_name for q in legacy_plan.searches])

    worst = (len(legacy_plan.searches) + 1) * PAGE_SIZE * 0.03
    if _ledger_total() + worst > CREDIT_CAP:
        print(f"[STOP] would exceed cap: {_ledger_total()}+{worst} > {CREDIT_CAP}"); return

    ids = {}
    LegacyProvider.arm_label = "role3:legacy"
    ids["legacy"] = _run(f"p5c-swe-legacy-{uuid.uuid4().hex[:8]}", legacy_intent, legacy_plan, LegacyProvider(), JD, None)
    print(f"[ledger] after legacy: {_ledger_total()} cr")
    tp = RawTreeProvider(tree); tp.arm_label = "role3:compiled"
    ids["compiled"] = _run(f"p5c-swe-compiled-{uuid.uuid4().hex[:8]}", legacy_intent,
                           SearchPlan(searches=[SearchQuery(query_name="compiled")]), tp, JD, None)
    print(f"[ledger] after compiled: {_ledger_total()} cr")

    (OUT / "manifest_role3.json").write_text(json.dumps({"jd": JD, "recruiter_brief": RECRUITER_BRIEF,
        "structured_intent": si.model_dump(exclude_none=True), "compiled_tree": tree, "compiled_total_count": tc,
        "ids": ids, "legacy_plan": [q.model_dump() for q in legacy_plan.searches], "ledger": LEDGER,
        "total_credits": _ledger_total(), "status": "ran"}, indent=2), encoding="utf-8")
    print(f"\nDONE. ids={ids} total_credits~{_ledger_total()}")


if __name__ == "__main__":
    main()
