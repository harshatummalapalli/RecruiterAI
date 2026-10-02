"""Shadow-mode tests — categorization, default-off, and failure isolation.
No network, no CrustData."""
from __future__ import annotations

import json
from pathlib import Path

from backend.models.structured_intent import parse_structured_intent, StructuredHiringIntent, RoleArchetype, LocationReq, Radius
from backend.services.search_compiler import compile_intent
from backend.services import search_compiler_shadow as shadow

GOLDEN = Path(__file__).parent / "fixtures" / "structured_intent"

LEGACY_EPIQ_TREE = {"op": "and", "conditions": [
    {"field": "basic_profile.location.country", "type": "in", "value": ["India"]},
    {"field": "basic_profile.location.state", "type": "in", "value": ["Telangana"]},
    {"field": "basic_profile.location.city", "type": "in", "value": ["Hyderabad"]},
    {"field": "basic_profile.location", "type": "geo_distance", "value": {"location": "Hyderabad, Telangana", "distance": 10, "unit": "mi"}},
    {"field": "years_of_experience_raw", "type": "=>", "value": 7},
    {"field": "experience.employment_details.current.company_name", "type": "in", "value": ["Arete", "QuisLex"]},
    {"field": "experience.employment_details.current.title", "type": "(!)", "value": "Director"},
]}


def _compiled(name):
    return compile_intent(parse_structured_intent((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8")))


def test_categorize_divergence_epiq_flags_the_known_enforcement_changes():
    cats = {c["category"] for c in shadow.categorize_divergence(LEGACY_EPIQ_TREE, _compiled("epiq_product_owner"))}
    assert "company_hard_filter_removed" in cats
    assert "radius_removed" in cats
    assert "seniority_moved_to_admission" in cats
    assert "role_family_added" in cats
    assert "downstream_verification_added" in cats


def test_city_normalization_is_representation_with_no_impact():
    intent = StructuredHiringIntent(
        role_archetype=RoleArchetype(value="title_defined", confidence=0.9, rationale="x"),
        role_family=["Software Engineer"],
        location=LocationReq(entries=["Bangalore, Karnataka, India"]))
    plan = compile_intent(intent)
    norm = [c for c in shadow.categorize_divergence({"op": "and", "conditions": []}, plan)
            if c["category"] == "provider_surface_normalization"]
    assert norm and norm[0]["kind"] == "representation" and norm[0]["impact"] == "none"
    assert "Bangalore -> Bengaluru" in norm[0]["detail"]


def test_disabled_by_default_returns_none_and_does_not_extract(monkeypatch):
    monkeypatch.delenv("SEARCH_COMPILER_SHADOW_ENABLED", raising=False)
    called = {"n": 0}
    import backend.services.structured_intent_extractor as ex
    monkeypatch.setattr(ex, "extract_structured_intent", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    assert shadow.run_shadow("s1", "jd", None) is None
    assert called["n"] == 0  # the LLM extraction was never invoked when disabled


def test_enabled_failure_is_isolated_never_raises(monkeypatch):
    monkeypatch.setenv("SEARCH_COMPILER_SHADOW_ENABLED", "true")
    import backend.services.structured_intent_extractor as ex
    def boom(*a, **k):
        raise RuntimeError("extractor exploded")
    monkeypatch.setattr(ex, "extract_structured_intent", boom)
    # must swallow the error and return None, not propagate
    assert shadow.run_shadow("s2", "jd", None) is None


def test_compiled_result_is_never_populated_in_the_record(monkeypatch):
    monkeypatch.setenv("SEARCH_COMPILER_SHADOW_ENABLED", "true")
    import backend.services.structured_intent_extractor as ex
    monkeypatch.setattr(ex, "extract_structured_intent",
                        lambda *a, **k: parse_structured_intent((GOLDEN / "epiq_product_owner.expected.json").read_text(encoding="utf-8")))

    class _Plan:
        searches = []
    rec = shadow.run_shadow("s3", "jd", _Plan())
    assert rec is not None
    assert rec["compiled_search_result"] is None
    assert rec["legacy_search_result"] == "untouched"
    assert rec["extraction_model"] == "gpt-6.1-sol"
    assert "divergence" in rec and "semantic_diff" in rec
