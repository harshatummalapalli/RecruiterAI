"""Keeper-adapter translation (pure parts). Network/LLM calls are validated at
the gated live run; here we only check the ProviderQuery/RoleModel -> keeper
mappings. Skips cleanly if the legacy backend isn't importable."""

import pytest

pytest.importorskip("backend.models.search_plan")
pytest.importorskip("backend.models.search_intent")

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.ranking.judge_adapter import _to_intent
from recruiter.providers.crustdata_adapter import _to_record, _to_search_query
from recruiter.role_model import JD, Provenance, Requirement, RoleModel, Seniority, Location, ARCHITECT


def test_provider_query_maps_to_keeper_search_query():
    pq = ProviderQuery(
        natural_language="AI Architect based in India",
        countries=("India",), cities=("Pune",), min_years=12,
        exclude_current_companies=("Epiq",),
        must_have_keyword_groups=(("agentic", "LLM"),),
        employment_type="full-time",
    )
    sq = _to_search_query(pq)
    assert sq.natural_language_query == "AI Architect based in India"
    assert sq.countries == ["India"] and sq.cities == ["Pune"]
    assert sq.minimum_years == 12
    assert sq.exclude_current_companies == ["Epiq"]
    assert sq.must_have_keyword_groups == [["agentic", "LLM"]]
    assert sq.employment_type == "full-time"


def test_keeper_candidate_maps_to_record():
    from backend.models.candidate import Candidate

    c = Candidate(candidate_id="x", name="N", title="AI Architect", company="Acme",
                  location="Pune, India", raw_data={"matched_queries": ["natural_language", "title_expansion"]})
    rec = _to_record(c)
    assert rec.candidate_id == "x" and rec.title == "AI Architect"
    assert set(rec.matched_queries) == {"natural_language", "title_expansion"}


def test_role_model_maps_to_keeper_intent_signals():
    role = RoleModel(
        identity="AI Architect", seniority=Seniority(12, None, Provenance(JD)),
        role_level=ARCHITECT, location=Location(countries=("India",)),
        requirements=(
            Requirement("Agentic Systems", "core", Provenance(JD)),
            Requirement("RAG", "supporting", Provenance(JD)),
            Requirement("Azure", "differentiator", Provenance(JD)),
        ),
    )
    intent = _to_intent(role)
    assert intent.core_signals == ["Agentic Systems"]
    assert intent.supporting_signals == ["RAG"]
    assert intent.differentiator_signals == ["Azure"]
