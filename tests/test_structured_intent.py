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


_SENIORITY_WORDS = ("senior", "junior", "principal", "staff", "lead ", "sr.", "sr ")


def _all_skill_terms(i: StructuredHiringIntent):
    names = {s.name.lower() for s in i.skills}
    for g in i.skill_any_of:
        names |= {n.lower() for n in g.any_of}
    return names


def python_invariant_violations(i: StructuredHiringIntent) -> list:
    """The four invariants for the Python anchor. Shared by the golden test and
    the live gate. Returns a list of human-readable violations (empty == pass)."""
    v = []
    # Invariant 2 — no invention: brief states no seniority.
    if i.seniority is not None:
        v.append(f"invented seniority {i.seniority.value!r} (brief states none)")
    # Invariant 1 — no loss: all education options preserved.
    if i.education:
        if set(i.education.degrees) < {"B.Tech", "B.E", "M.Tech"}:
            v.append(f"dropped a degree option: {i.education.degrees}")
        if set(s.lower() for s in i.education.streams) < {"computer science", "information technology", "data science", "artificial intelligence"}:
            v.append(f"dropped a stream option (e.g. IT): {i.education.streams}")
    else:
        v.append("education missing entirely")
    # Invariant 1 — Django AND FastAPI both preserved.
    terms = _all_skill_terms(i)
    if "django" not in terms or "fastapi" not in terms:
        v.append(f"lost Django/FastAPI: {terms}")
    # Invariant 3 — temporal specificity + strength.
    def find(name):
        for s in i.skills:
            if s.name.lower() == name:
                return s
        return None
    py = find("python"); ja = find("java")
    if not py or py.relationship != "current" or py.strength != "required":
        v.append(f"Python must be current+required, got {py}")
    if not ja or ja.relationship != "past" or ja.strength != "required":
        v.append(f"Java must be past+required, got {ja}")
    for g in i.skill_any_of:
        if {n.lower() for n in g.any_of} == {"django", "fastapi"}:
            if g.relationship != "current" or g.strength != "required":
                v.append(f"Django/FastAPI must be current+required, got rel={g.relationship} str={g.strength}")
    if i.company_scale and (i.company_scale.relationship != "current" or i.company_scale.minimum_employees != 5000):
        v.append(f"company_scale must be current/5000, got {i.company_scale}")
    # Invariant 4 — semantic routing: tech must be skills, not evidence.
    ev = {e.name.lower() for e in i.evidence_signals}
    if ev & {"python", "java", "django", "fastapi"}:
        v.append(f"tech misrouted into evidence_signals: {ev}")
    return v


def epiq_invariant_violations(i: StructuredHiringIntent) -> list:
    """The four invariants for the Epiq anchor."""
    v = []
    # Invariant 2 — no invention: role_family must not bake in seniority.
    for t in i.role_family:
        if any(w in t.lower() for w in ("senior", "junior", "principal", "sr.")):
            v.append(f"role_family invented seniority: {t!r}")
    if i.role_archetype.value not in {"title_defined", "hybrid"}:
        v.append(f"archetype should be title_defined/hybrid, got {i.role_archetype.value}")
    # Invariant 1 — no loss: all 13 target companies preserved, all preferred.
    if len(i.companies) < 13:
        v.append(f"lost target companies: {len(i.companies)}/13")
    if any(c.strength != "preferred" for c in i.companies):
        v.append("a target company was not 'preferred' (no fake requirement/boost)")
    # Invariant 4 — semantic routing: product capabilities are evidence, not skills.
    skill_terms = _all_skill_terms(i)
    for cap in ("product vision", "backlog", "agile", "stakeholder", "fluency"):
        if any(cap in s for s in skill_terms):
            v.append(f"capability misrouted into skills: {cap!r}")
    if not any("product vision" in e.name.lower() for e in i.evidence_signals):
        v.append("product-vision capability not captured as an evidence signal")
    # Epiq exclusion preserved.
    if not any(x.kind == "current_company" and x.value == "Epiq" for x in i.exclusions):
        v.append("lost the exclude-current-Epiq constraint")
    return v


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
    # role_family is SOURCE only now (seniority stripped); the broad retrieval
    # family (PO/PM/Product Lead) is a Phase-3 compiler responsibility.
    assert set(i.role_family) == {"Product Owner"}
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


def test_role_family_matches_regression_fixture_source_role() -> None:
    """The structured intent's role_family (SOURCE) must agree with the Phase-0
    regression fixture's role_family — both are the role the recruiter expressed,
    NOT the broad retrieval family (which is retrieval_expectations.title_family,
    a Phase-3 compiler artifact)."""
    for name in ("python_backend_hyderabad", "epiq_product_owner"):
        intent = _golden(name)
        reg = json.loads((REGRESSION_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert set(intent.role_family) == set(reg["role_family"]), f"{name}: source role drift"
        # and the source role must sit within the approved retrieval family
        assert set(intent.role_family) <= set(reg["retrieval_expectations"]["title_family"])


def test_golden_python_satisfies_all_four_invariants() -> None:
    assert python_invariant_violations(_golden("python_backend_hyderabad")) == []


def test_golden_epiq_satisfies_all_four_invariants() -> None:
    assert epiq_invariant_violations(_golden("epiq_product_owner")) == []


def test_two_level_logic_only_no_nested_groups() -> None:
    # The schema has no construct for a group inside a group; skill_any_of is a
    # flat OR of names. This asserts the shape stays two-level.
    i = _golden("python_backend_hyderabad")
    for g in i.skill_any_of:
        assert all(isinstance(n, str) for n in g.any_of)
