"""Phase 4 — routing + execution-provenance acceptance tests.

Wiring + traceability only. No CrustData, no live retrieval, no change to Judge
scoring/thresholds. Green requires: downstream requirements reach the Judge
checklist as SEMANTIC text (no provider syntax), and the audit record is
deterministic, complete, and hashed.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.models.structured_intent import parse_structured_intent
from backend.models.structured_intent import _PROVIDER_LEAK_TOKENS
from backend.services.search_compiler import compile_intent
from backend.services import compiler_audit as audit

GOLDEN = Path(__file__).parent / "fixtures" / "structured_intent"
_JUDGE_TIERS = {"core", "supporting", "differentiator"}


def _plan(name):
    intent = parse_structured_intent((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))
    return intent, compile_intent(intent)


def test_downstream_requirements_reach_the_judge_checklist():
    _, plan = _plan("epiq_product_owner")
    checklist = audit.judge_checklist(plan)
    texts = {t for _, t in checklist}
    # The product capabilities the compiler routed downstream must be present.
    assert any("product vision" in t.lower() for t in texts)
    assert any("backlog" in t.lower() for t in texts)
    # Tiers are exactly what RequirementJudge already consumes.
    assert all(tier in _JUDGE_TIERS for tier, _ in checklist)
    # required->core, preferred->supporting mapping held.
    by_text = {t.lower(): tier for tier, t in checklist}
    assert by_text.get("product vision and strategy") == "core"
    assert by_text.get("stakeholder engagement") == "supporting"


def test_no_provider_syntax_leaks_into_the_judge_checklist():
    for name in ("epiq_product_owner", "python_backend_hyderabad"):
        _, plan = _plan(name)
        for _, text in audit.judge_checklist(plan):
            low = text.lower()
            for tok in _PROVIDER_LEAK_TOKENS:
                assert tok not in low, f"{name}: provider token {tok!r} leaked into judge text {text!r}"


def test_python_has_no_downstream_checklist_everything_is_provider_enforced():
    # Python brief has no evidence signals / preferred items -> judge checklist empty.
    _, plan = _plan("python_backend_hyderabad")
    assert audit.judge_checklist(plan) == []


def test_audit_record_is_deterministic_and_complete():
    intent, plan = _plan("epiq_product_owner")
    a = audit.build_audit_record(intent, plan, search_id="s1", confirmation_id="c1")
    b = audit.build_audit_record(intent, plan, search_id="s1", confirmation_id="c1")
    assert a == b, "audit record not deterministic"
    for key in ("search_id", "confirmation_id", "intent_hash", "plan_hash", "compiler_version",
                "capability_map_version", "taxonomy_version", "compiled_provider_plan",
                "requirements", "downstream_checklist", "warnings"):
        assert key in a, f"audit record missing {key}"
    # requirements are grouped by execution category
    reqs = a["requirements"]
    assert reqs["provider_enforced"], "expected provider-enforced requirements"
    assert reqs["admission_enforced"], "seniority should be admission-enforced"
    assert reqs["downstream_verified"], "evidence should be downstream-verified"
    assert reqs["context_only"], "preferred companies should be context-only"


def test_hashes_are_stable_and_change_with_intent():
    intent, plan = _plan("epiq_product_owner")
    assert audit.intent_hash(intent) == audit.intent_hash(intent)
    assert audit.plan_hash(plan) == audit.plan_hash(plan)
    other_i, other_p = _plan("python_backend_hyderabad")
    assert audit.intent_hash(intent) != audit.intent_hash(other_i)
    assert audit.plan_hash(plan) != audit.plan_hash(other_p)


def test_persist_audit_round_trips(tmp_path):
    intent, plan = _plan("epiq_product_owner")
    rec = audit.build_audit_record(intent, plan, search_id="searchX")
    p = audit.persist_audit(rec, str(tmp_path))
    assert Path(p).exists()
    assert json.loads(Path(p).read_text(encoding="utf-8")) == rec


def test_adapter_does_not_import_the_judge_or_any_provider():
    # Old production behavior untouched: the routing adapter is pure and does not
    # pull in RequirementJudge, CrustData, or Harvest (no scoring/threshold/
    # network coupling introduced).
    import backend.services.compiler_audit as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    # Importing the static capability-map version constant is fine; the concern is
    # coupling to the Judge, the network providers, or any LLM/HTTP call.
    for forbidden in ("requirement_judge", "providers.crustdata", "providers.harvest",
                      "httpx", "openai", "responses.create"):
        assert forbidden not in src, f"adapter unexpectedly references {forbidden!r}"
