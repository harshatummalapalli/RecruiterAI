"""Bridge translation — engine objects -> dayzero.partners frontend contract."""

import json

from backend.bridge.translate import to_intake_result, to_search_intent, to_search_response
from recruiter.agents.intake.model import Question
from recruiter.agents.ranking.model import RankedCandidate, RankingResult
from recruiter.agents.search.model import SearchResult
from recruiter.candidates import CandidateRecord
from recruiter.role_model import (
    ARCHITECT,
    JD,
    CapabilityGroup,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def _model() -> RoleModel:
    return RoleModel(
        identity="eDiscovery Operations Analyst",
        seniority=Seniority(8, 12, Provenance(JD, "8-12 yrs")),
        role_level=ARCHITECT,
        location=Location(countries=("India",), states=("Karnataka",), cities=("Bengaluru", "Pune"),
                          work_mode="hybrid"),
        requirements=(
            Requirement("eDiscovery operations", "core", Provenance(JD, "EDRM lifecycle"), hard=True),
            Requirement("Windows/MS Office", "supporting", Provenance(JD)),
        ),
        capability_groups=(CapabilityGroup("eDiscovery", ("Relativity", "Nuix", "EDRM"), "eDiscovery", "x"),),
        companies=CompanyRules(exclude_current=("Epiq",), prefer_ever=("KLDiscovery",)),
        exclude_titles=("VP", "Director"),
        industries=("Legal Services",),
        posted_title="Operations Analyst – eDiscovery",
        posted_title_source="jd",
        employment_type="full-time",
        hiring_company="Epiq",
        limitations=("work mode not filterable",),
    )


def test_search_intent_maps_core_fields_and_is_json_safe():
    si = to_search_intent(_model())
    assert si["role"]["title"] == "eDiscovery Operations Analyst"
    assert si["location"]["cities"] == ["Bengaluru", "Pune"] and si["location"]["work_mode"] == "hybrid"
    assert si["experience"] == {"minimum_years": 8, "maximum_years": 12, "confidence_score": None}
    assert si["titles"]["exclude_titles"] == ["VP", "Director"]
    assert si["company_preferences"]["exclude_current_companies"] == ["Epiq"]
    assert si["company_preferences"]["preferred_companies_ever"] == ["KLDiscovery"]
    assert si["must_have_keyword_groups"] == [["Relativity", "Nuix", "EDRM"]]
    assert "eDiscovery" in si["natural_language_search_query"]
    json.dumps(si)  # must serialize


def test_intake_result_maps_brief_and_marks_status():
    qs = (Question(id="capability", prompt="Require eDiscovery?", kind="capability_confirm",
                   options=("keep", "remove")),)
    result = to_intake_result("JD text", _model(), qs, status="ready")
    ru = result["role_understanding"]
    assert ru["primary_candidate_identity"]["value"] == "eDiscovery Operations Analyst"
    assert ru["posted_title"] == "Operations Analyst – eDiscovery"
    assert ru["core_capabilities"][0]["value"] == "eDiscovery operations"
    assert ru["technologies_mentioned"] == [{"category": "eDiscovery", "items": ["Relativity", "Nuix", "EDRM"]}]
    assert ru["explicit_constraints"]["experience_minimum_years"] == 8
    assert ru["explicit_constraints"]["locations"] == [
        {"city": "Bengaluru", "state": "Karnataka", "country": "India"},
        {"city": "Pune", "state": "Karnataka", "country": "India"},
    ]
    # brain-only fields present but empty (Phase-2 trim targets)
    assert ru["role_interpretation"] == {"value": None, "evidence": None, "source": None}
    # the one hard requirement rides final_search_intent
    assert result["decision"]["final_search_intent"]["hard_requirements"] == ["eDiscovery operations"]
    assert result["decision"]["issues"][0]["question"] == "Require eDiscovery?"
    assert result["status"] == "ready"
    json.dumps(result)  # must serialize


def test_search_response_maps_candidates_and_diagnostics():
    rec = CandidateRecord("c1", name="Asha", title="eDiscovery Analyst", company="KLDiscovery",
                          location="Pune, India", profile_url="http://x", provider_score=0.8,
                          matched_queries=("natural_language",), raw={"basic_profile": {"headline": "Relativity"}})
    ranking = RankingResult(ranked=(), shown=(RankedCandidate(rec, 0.91, "Strong Relativity match."),),
                            admitted=25, judged=5, judge_failures=0, experience_excluded=2)
    search = SearchResult(candidates=(rec,), pulled=50, geo_dropped=1, est_credits=1.5, excluded_dropped=3)
    resp = to_search_response("crustdata", "s-1", _model(), search, ranking)
    assert resp["candidate_count"] == 1 and resp["search_id"] == "s-1"
    c = resp["candidates"][0]
    assert c["name"] == "Asha" and c["final_score"] == 0.91 and c["raw_data"]["basic_profile"]["headline"] == "Relativity"
    assert resp["explanations"][0]["why_this_candidate"] == "Strong Relativity match."
    assert resp["diagnostics"]["pulled"] == 50 and resp["diagnostics"]["excluded_dropped"] == 3
    assert resp["diagnostics"]["experience_excluded"] == 2 and resp["status"] == "complete"
    # rich evidence now built via the keeper candidate_evidence_builder
    ev = resp["evidence"][0]
    assert ev["current_company"] == "KLDiscovery" and "Relativity" in ev["headline"]
    assert "past_roles" in ev and "education" in ev and "role_alignment" in ev
    json.dumps(resp)
