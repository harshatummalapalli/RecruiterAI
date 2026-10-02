"""Phase 3 — deterministic compiler acceptance tests (credit-free, no LLM).

Recruiter meaning -> deterministic provider plan, executable and testable without
an LLM or provider call. Both anchors must compile to their expected filter trees
exactly, with the Phase-3 invariants holding.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.models.structured_intent import parse_structured_intent
from backend.services import crustdata_capabilities as cap
from backend.services.search_compiler import compile_intent, canonicalize, semantic_diff

GOLDEN = Path(__file__).parent / "fixtures" / "structured_intent"
REG = Path(__file__).parent / "fixtures" / "regression_set"
ANCHORS = ["python_backend_hyderabad", "epiq_product_owner"]


def _intent(name):
    return parse_structured_intent((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))


def _reg(name):
    return json.loads((REG / f"{name}.json").read_text(encoding="utf-8"))


def _leaves(tree, acc):
    if isinstance(tree, dict) and "op" in tree:
        for c in tree["conditions"]:
            _leaves(c, acc)
    elif isinstance(tree, dict):
        acc.append(tree)
    return acc


@pytest.mark.parametrize("name", ANCHORS)
def test_anchor_compiles_to_expected_filter_tree_exactly(name):
    plan = compile_intent(_intent(name))
    expected = _reg(name)["expected_filter_tree"]
    assert canonicalize(plan.filter_tree) == canonicalize(expected), f"{name}: compiled tree != expected"


@pytest.mark.parametrize("name", ANCHORS)
def test_no_disallowed_provider_field_in_tree(name):
    """Every hard-filter field must be verified-filterable per the capability map."""
    plan = compile_intent(_intent(name))
    for leaf in _leaves(plan.filter_tree, []):
        fs = cap.get(leaf["field"]).filter_status
        assert fs == cap.FILTER_VERIFIED, f"{name}: {leaf['field']} is {fs}, not a verified hard filter"


@pytest.mark.parametrize("name", ANCHORS)
def test_titles_only_from_approved_retrieval_family(name):
    plan = compile_intent(_intent(name))
    fam = {t.lower() for t in plan.retrieval_title_family}
    for leaf in _leaves(plan.filter_tree, []):
        if "current.title" in leaf["field"] and leaf["type"] == "(.)":
            assert leaf["value"].lower() in fam, f"{name}: title {leaf['value']!r} outside approved family"


@pytest.mark.parametrize("name", ANCHORS)
def test_compiler_is_deterministic(name):
    a = compile_intent(_intent(name)).filter_tree
    b = compile_intent(_intent(name)).filter_tree
    assert canonicalize(a) == canonicalize(b)


def test_required_constraints_are_not_silently_dropped_python():
    plan = compile_intent(_intent("python_backend_hyderabad"))
    routes = {c.source: c.route for c in plan.audit}
    for req in ("skill:Python", "skill:Java", "skill_any_of:Django|FastAPI", "education.degrees",
                "education.streams", "company_scale", "role_family", "experience", "location"):
        assert routes.get(req) == "provider_hard_filter", f"{req} not hard-filtered: {routes.get(req)}"


def test_preferred_companies_never_become_hard_filters_epiq():
    plan = compile_intent(_intent("epiq_product_owner"))
    # No company_name IN leaf anywhere (preferred -> context/evidence).
    for leaf in _leaves(plan.filter_tree, []):
        assert not (leaf["field"].endswith("company_name") and leaf["type"] == "in"), "preferred company leaked into a hard filter"
    company_routes = [c.route for c in plan.audit if c.source.startswith("company:")]
    assert company_routes and all(r == "context_or_evidence" for r in company_routes)


def test_andor_structure_preserved_python():
    plan = compile_intent(_intent("python_backend_hyderabad"))
    # Django/FastAPI OR group must survive as an OR with both terms present.
    or_groups = [c for c in plan.filter_tree["conditions"] if c.get("op") == "or"]
    vals = [{l["value"] for l in g["conditions"]} for g in or_groups]
    assert any({"Django", "FastAPI"} <= v for v in vals), "Django/FastAPI OR group lost"


def test_evidence_signals_route_to_judge_epiq():
    plan = compile_intent(_intent("epiq_product_owner"))
    ev = [c for c in plan.audit if c.source.startswith("evidence:")]
    assert ev and all(c.route == "downstream_evidence" for c in ev)
    assert any("product vision" in c.source for c in ev)


def test_seniority_routes_to_admission_not_a_filter_epiq():
    plan = compile_intent(_intent("epiq_product_owner"))
    sen = [c for c in plan.audit if c.source == "seniority"]
    assert sen and sen[0].route == "admission_level_fit"


def test_semantic_diff_surfaces_hard_to_contextual_company_change():
    """Shadow-mode: the old plan hard-filtered on current company; the new plan
    does not. The diff must make that visible."""
    new = compile_intent(_intent("epiq_product_owner")).filter_tree
    old = {"op": "and", "conditions": new["conditions"] + [
        {"field": "experience.employment_details.current.company_name", "type": "in",
         "value": ["Arete", "QuisLex", "UnitedLex"]}]}
    diff = semantic_diff(old, new)
    assert any("REMOVED" in d and "company_name" in d for d in diff), diff
