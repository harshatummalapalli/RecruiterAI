"""Phase 2 — Structured Hiring Intent schema + semantic goldens.

Deterministic and credit-free. The goldens encode the CORRECT semantic
representation of the two anchor briefs (the acceptance criterion is semantic
correctness, not merely valid JSON). The live LLM emission is reviewed
separately before Phase 3; this suite pins what "correct" means.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.models.structured_intent import StructuredHiringIntent, parse_structured_intent

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "structured_intent"
REGRESSION_DIR = Path(__file__).parent / "fixtures" / "regression_set"


def _golden(name: str) -> StructuredHiringIntent:
    return parse_structured_intent((GOLDEN_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))


def test_goldens_parse_and_validate() -> None:
    for name in ("python_backend_hyderabad", "epiq_product_owner"):
        intent = _golden(name)
        assert intent.role_family  # non-empty
        assert 0.0 <= intent.role_archetype.confidence <= 1.0


def test_python_brief_semantics() -> None:
    i = _golden("python_backend_hyderabad")
    assert i.role_archetype.value == "skill_defined"
    skills = {(s.name, s.relationship, s.strength) for s in i.skills}
    assert ("Python", "current", "required") in skills
    assert ("Java", "past", "required") in skills           # historical, not current
    # Django/FastAPI preserved as an OR group, required
    assert any(set(g.any_of) == {"Django", "FastAPI"} and g.strength == "required" for g in i.skill_any_of)
    assert i.experience.minimum_years == 5 and i.experience.maximum_years == 8
    # education options preserved EXACTLY, not broadened
    assert set(i.education.degrees) == {"B.Tech", "B.E", "M.Tech"}
    assert set(i.education.streams) == {"Computer Science", "Information Technology", "Data Science", "Artificial Intelligence"}
    assert i.company_scale.minimum_employees == 5000 and i.company_scale.relationship == "current"
    assert i.location.entries == ["Hyderabad, Telangana, India"]


def test_epiq_brief_semantics() -> None:
    i = _golden("epiq_product_owner")
    assert i.role_archetype.value in {"title_defined", "hybrid"}
    assert set(i.role_family) == {"Product Owner", "Product Manager", "Product Lead"}
    # The load-bearing lesson: target companies are PREFERRED, never required.
    assert i.companies, "target companies should be captured"
    assert all(c.strength == "preferred" for c in i.companies)
    # Epiq is excluded as a current employer.
    assert any(x.kind == "current_company" and x.value == "Epiq" for x in i.exclusions)
    # Capability signals are evidence, present and strength-tagged.
    assert any(e.name.startswith("product vision") for e in i.evidence_signals)
    assert i.experience.minimum_years == 7


def test_preference_not_upgraded_to_requirement() -> None:
    # Across both goldens, nothing marked preferred in the brief appears as required.
    epiq = _golden("epiq_product_owner")
    assert all(c.strength == "preferred" for c in epiq.companies)
    # stakeholder/quality/AIML/legal-tech were "valuable"/"a plus" -> preferred
    soft = {e.name for e in epiq.evidence_signals if e.strength == "preferred"}
    assert "stakeholder engagement" in soft and "legal technology domain" in soft


def test_no_provider_mechanics_leak_is_rejected() -> None:
    bad = {
        "role_archetype": {"value": "skill_defined", "confidence": 0.8, "rationale": "x"},
        "role_family": ["Software Engineer"],
        "skills": [{"name": "Python via current.description", "relationship": "current", "strength": "required"}],
    }
    with pytest.raises(Exception):
        parse_structured_intent(json.dumps(bad))


def test_role_family_matches_regression_fixture_title_family() -> None:
    """The structured intent's role_family must agree with the Phase-0 regression
    suite's expected_title_family — the two artifacts cannot drift apart."""
    for name in ("python_backend_hyderabad", "epiq_product_owner"):
        intent = _golden(name)
        reg = json.loads((REGRESSION_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert set(intent.role_family) == set(reg["expected_title_family"]), f"{name}: role_family drift"


def test_two_level_logic_only_no_nested_groups() -> None:
    # The schema has no construct for a group inside a group; skill_any_of is a
    # flat OR of names. This asserts the shape stays two-level.
    i = _golden("python_backend_hyderabad")
    for g in i.skill_any_of:
        assert all(isinstance(n, str) for n in g.any_of)
