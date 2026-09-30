# The role_context family (Role Context Evidence Spike release) — the one
# family that needs Harvest role descriptions, not CrustData employment
# fields, since CrustData never returns role descriptions at all (see
# career_signals.py's own findings). Proves the key distinction the release
# is built around: "works at a technology company" (industry family) does
# NOT prove "has recruited technical talent" (role_context family) — they
# are answered from entirely different evidence.

from typing import Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Role, SearchIntent, Titles
from backend.services.requirement_judge import RequirementJudge
from backend.services.requirement_semantics import evaluate, recognize_requirement


def _harvest(*entries: Dict) -> HarvestEvidence:
    """entries: {"position":..., "companyName":..., "description":...}"""
    return HarvestEvidence(success=True, raw={"element": {"experience": list(entries)}})


def _role(position: str, company: str, description: Optional[str] = None) -> Dict:
    e = {"position": position, "companyName": company}
    if description is not None:
        e["description"] = description
    return e


def _candidate(current_title: Optional[str] = None, current_industries: Optional[List[str]] = None, skills: Optional[List[str]] = None) -> Candidate:
    raw = {"experience": {"employment_details": {"current": [], "past": []}}}
    if current_industries is not None:
        raw["experience"]["employment_details"]["current"] = [{"title": current_title, "company_industries": current_industries, "end_date": None}]
    return Candidate(candidate_id="c1", name="Test Candidate", title=current_title, raw_data=raw)


class _FailIfCalled:
    class _Responses:
        def create(self, **kwargs):
            raise AssertionError(f"Unexpected LLM call: {kwargs.get('input')}")
    responses = _Responses()


def _intent(*core: str) -> SearchIntent:
    return SearchIntent(role=Role(title="Recruiter"), titles=Titles(include_titles=["Recruiter"]), core_signals=list(core))


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------

def test_recognizes_software_engineering_recruiting():
    r = recognize_requirement("has recruited software engineers")
    assert r.family == "role_context" and r.operator == "evidence_matches" and r.value == "software engineering recruiting" and r.scope == "career"


def test_recognizes_ai_ml_recruiting():
    r = recognize_requirement("has hired AI/ML teams")
    assert r.family == "role_context" and r.value == "AI/ML recruiting"


def test_recognizes_technical_talent_generic_bucket():
    r = recognize_requirement("has recruited technical talent")
    assert r.family == "role_context" and r.value == "technical recruiting"


def test_recognizes_engineering_leaders():
    r = recognize_requirement("has hired engineering leaders")
    assert r.family == "role_context" and r.value == "technical recruiting"


def test_does_not_recognize_bare_industry_or_title_language():
    # Explicitly listed in the spec as must-NOT-auto-become-role_context.
    assert recognize_requirement("works in technology") is None
    assert recognize_requirement("works at a SaaS company") is None
    assert recognize_requirement("technology recruiter") is None
    assert recognize_requirement("technical recruiter") is None


# ---------------------------------------------------------------------------
# Phase 6 minimum cases 1-10
# ---------------------------------------------------------------------------

def test_1_description_explicitly_mentions_software_engineering_hiring():
    h = _harvest(_role("Recruiter", "Acme", "Led full-cycle recruiting for software engineers and backend engineers across three product teams."))
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert j["verdict"] == "met"
    assert "Acme" in j["quote"]


def test_2_description_explicitly_mentions_ai_ml_hiring():
    h = _harvest(_role("Talent Acquisition Lead", "Epiq", "Leading enterprise-scale technical hiring with a focus on AI/ML, backend, and infrastructure roles."))
    j = evaluate(recognize_requirement("has hired AI/ML teams"), "core", _candidate(), h)
    assert j["verdict"] == "met"
    assert "Epiq" in j["quote"]


def test_3_description_does_not_mention_requested_activity():
    h = _harvest(_role("Recruiter", "Acme", "Managed full-cycle recruiting for sales and customer success roles."))
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert j["verdict"] == "not_evidenced"
    assert j["quote"] == ""
    assert j["evidence_state"] == "not_evidenced"  # a real description WAS checked


def test_4_tech_industry_but_description_silent_on_technical_hiring_not_met():
    # The real regression pattern found live in this session (Louise C. /
    # Nikhil Madaan / Andrew Ezra): current employer classified technology,
    # deterministic industry-family check would say True, but the role
    # description itself says nothing about technical hiring — role_context
    # must NOT borrow the industry family's answer.
    candidate = _candidate(current_title="Talent Acquisition Lead", current_industries=["Technology, Information and Internet"])
    h = _harvest(_role("Talent Acquisition Lead", "TechCo", "Manage full-cycle recruiting for the finance, legal, and people operations teams."))
    industry_req = recognize_requirement("currently works at a technology company")
    role_context_req = recognize_requirement("has recruited software engineers")
    industry_judgment = evaluate(industry_req, "core", candidate, h)
    role_context_judgment = evaluate(role_context_req, "core", candidate, h)
    assert industry_judgment["verdict"] == "met"  # industry family: legitimately true
    assert role_context_judgment["verdict"] == "not_evidenced"  # role_context: correctly NOT borrowed from industry


def test_5_software_skills_without_supporting_description_not_met():
    # Global skills must never substitute for event-scoped evidence — the
    # description here is about client relationship management, not hiring
    # software engineers, even though the candidate's own skills/experience
    # is engineering-adjacent.
    h = _harvest(_role("Account Manager", "Acme", "Built relationships with enterprise software clients and managed contract renewals."))
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert j["verdict"] == "not_evidenced"
    assert j["evidence_state"] == "not_evidenced"  # a real description was checked; it just isn't hiring-related


def test_6_technical_recruiter_title_without_description_not_automatically_met():
    h = _harvest(_role("Technical Recruiter", "Acme", None))  # no description at all
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(current_title="Technical Recruiter"), h)
    assert j["verdict"] == "not_evidenced"
    assert j["evidence_state"] == "unknown"  # nothing was actually checked, so nothing can be concluded


def test_7_current_and_historical_descriptions_remain_event_scoped():
    h = _harvest(
        _role("Recruiter", "CurrentCo", "Recruiting for sales and marketing roles only."),
        _role("Technical Recruiter", "PastCo", "Recruited software engineers and backend engineers for a Series B startup."),
    )
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert j["verdict"] == "met"
    assert "PastCo" in j["quote"] and "CurrentCo" not in j["quote"]


def test_8_unrecognized_ambiguous_role_context_sentence_falls_to_llm():
    # Deliberately vague wording the recognizer must not force a verdict on.
    assert recognize_requirement("has a strong technical background") is None
    assert recognize_requirement("experience with engineering teams") is None


def test_9_recognized_role_context_requirement_bypasses_the_llm():
    intent = _intent("has recruited software engineers")
    candidate = _candidate()
    harvest = _harvest(_role("Recruiter", "Acme", "Recruited software engineers and backend engineers."))
    judgments = RequirementJudge(client=_FailIfCalled()).judge(candidate, intent, harvest_evidence=harvest)
    assert judgments[0]["verdict"] == "met"
    assert judgments[0]["deterministic"] is True


def test_10_evidence_references_the_actual_employment_event():
    h = _harvest(_role("Lead Recruiter", "SpecificCo", "Recruited software engineers and platform engineers for the core infra team."))
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert "Lead Recruiter" in j["quote"] and "SpecificCo" in j["quote"]
    assert "Lead Recruiter at SpecificCo" in j["evidence_detail"]
    assert j["evidence_type"] == "demonstrated_work" and j["strength"] == "strong"


# ---------------------------------------------------------------------------
# Additional: no fabricated summaries; no Harvest data at all; mixed with
# other recognized families in one requirement set.
# ---------------------------------------------------------------------------

def test_no_fabricated_summary_quote_is_ever_generated():
    h = _harvest(_role("Recruiter", "Acme", "Recruited software engineers for the platform team."))
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), h)
    assert "strong technical recruiting background" not in j["quote"].lower()
    assert "Recruited software engineers for the platform team" in j["quote"]


def test_no_harvest_evidence_at_all_is_not_evidenced_not_a_crash():
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), harvest_evidence=None)
    assert j["verdict"] == "not_evidenced"
    assert j["evidence_state"] == "unknown"  # no Harvest data at all — nothing was checked


def test_failed_harvest_is_treated_as_no_evidence():
    failed = HarvestEvidence(success=False, error="timeout")
    j = evaluate(recognize_requirement("has recruited software engineers"), "core", _candidate(), failed)
    assert j["verdict"] == "not_evidenced"
    assert j["evidence_state"] == "unknown"


def test_mixed_role_context_and_company_size_requirements_both_deterministic():
    intent = _intent("has recruited software engineers", "currently works at a startup")
    candidate = Candidate(
        candidate_id="c2", name="Mixed",
        raw_data={"experience": {"employment_details": {"current": [{"title": "Recruiter", "company_headcount_latest": 90, "end_date": None}], "past": []}}},
    )
    harvest = _harvest(_role("Recruiter", "Acme", "Recruited software engineers and backend engineers."))
    judgments = RequirementJudge(client=_FailIfCalled()).judge(candidate, intent, harvest_evidence=harvest)
    assert judgments[0]["verdict"] == "met"  # role_context
    assert judgments[1]["verdict"] == "met"  # company_size, unaffected


# ---------------------------------------------------------------------------
# Role Context Evidence Availability — met / not_evidenced / unknown
# ---------------------------------------------------------------------------

_SWE_REQ = "has recruited software engineers"


def _j(*entries: Dict) -> Dict:
    h = _harvest(*entries)
    return evaluate(recognize_requirement(_SWE_REQ), "core", _candidate(), h)


def test_state_1_description_with_matching_evidence_is_met():
    j = _j(_role("Recruiter", "Acme", "Recruited software engineers and backend engineers."))
    assert j["verdict"] == "met" and j["evidence_state"] == "met"
    assert "Acme" in j["quote"]


def test_state_2_description_without_matching_evidence_is_not_evidenced():
    j = _j(_role("Recruiter", "Acme", "Recruited sales and marketing staff."))
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "not_evidenced"
    assert j["quote"] == ""


def test_state_3_missing_description_key_is_unknown():
    j = _j(_role("Recruiter", "Acme", None))
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "unknown"
    assert j["quote"] == ""
    # Never implies the candidate didn't do the work.
    assert "did not" not in j["evidence_detail"].lower()
    assert "no evidence" not in j["evidence_detail"].lower()


def test_state_4_empty_string_description_is_unknown():
    entry = _role("Recruiter", "Acme")
    entry["description"] = "   "  # present key, blank text
    j = _j(entry)
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "unknown"


def test_state_5_multiple_events_one_matching_is_met():
    j = _j(
        _role("Recruiter", "RoleA", "Recruited sales staff."),  # described, no match
        _role("Recruiter", "RoleB", None),  # missing description
        _role("Recruiter", "RoleC", "Recruited software engineers for the platform team."),  # matches
    )
    assert j["verdict"] == "met" and j["evidence_state"] == "met"
    assert "RoleC" in j["quote"]


def test_state_6_multiple_events_described_none_matching_is_not_evidenced():
    j = _j(
        _role("Recruiter", "RoleA", "Recruited sales staff."),
        _role("Recruiter", "RoleB", "Recruited marketing staff."),
    )
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "not_evidenced"


def test_state_7_multiple_events_all_missing_descriptions_is_unknown():
    j = _j(
        _role("Recruiter", "RoleA", None),
        _role("Recruiter", "RoleB", None),
    )
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "unknown"


def test_state_8_one_missing_one_non_matching_is_not_evidenced_not_unknown():
    # A single relevant, checked description is enough to make this a real
    # "checked and didn't match" — one other event's missing description
    # must never downgrade that to "unknown" or, worse, hide the fact that
    # something real WAS checked.
    j = _j(
        _role("Recruiter", "RoleA", None),
        _role("Recruiter", "RoleB", "Recruited sales and marketing staff."),
    )
    assert j["verdict"] == "not_evidenced" and j["evidence_state"] == "not_evidenced"


def test_state_9_mixed_harvest_event_quality_does_not_let_a_missing_description_override_a_real_match():
    # Order matters not at all: the missing-description event comes FIRST,
    # ahead of the one that actually demonstrates the requirement.
    j = _j(
        _role("Coordinator", "RoleA", None),
        _role("Recruiter", "RoleB", "Handled scheduling only."),
        _role("Technical Recruiter", "RoleC", "Recruited software engineers and platform engineers."),
    )
    assert j["verdict"] == "met" and j["evidence_state"] == "met"
    assert "RoleC" in j["quote"]


def test_state_10_recognized_role_context_llm_bypass_is_unchanged():
    intent = _intent(_SWE_REQ)
    harvest = _harvest(_role("Recruiter", "Acme", "Recruited software engineers."))
    judgments = RequirementJudge(client=_FailIfCalled()).judge(_candidate(), intent, harvest_evidence=harvest)
    assert judgments[0]["verdict"] == "met"
    assert judgments[0]["deterministic"] is True


def test_state_11_existing_three_families_are_unaffected_by_the_evidence_state_addition():
    from backend.services.requirement_semantics import evaluate as _evaluate, recognize_requirement as _recognize

    size_candidate = Candidate(candidate_id="c3", name="Size", raw_data={"experience": {"employment_details": {"current": [{"title": "Recruiter", "company_headcount_latest": 150, "end_date": None}], "past": []}}})
    j_size = _evaluate(_recognize("currently works at a startup"), "core", size_candidate)
    assert j_size["verdict"] == "met"
    assert j_size["evidence_state"] == "met"  # defaults to mirroring verdict, unaffected by the role_context change

    unknown_headcount_candidate = Candidate(candidate_id="c4", name="Unknown", raw_data={"experience": {"employment_details": {"current": [{"title": "Recruiter", "company_headcount_latest": 0, "end_date": None}], "past": []}}})
    j_unknown = _evaluate(_recognize("currently works at a startup"), "core", unknown_headcount_candidate)
    # company_size's own "unknown headcount" semantics (career_signals.py)
    # are explicitly out of scope for this release — still verdict=
    # not_evidenced, still evidence_state defaults to mirror it exactly as
    # before this release, not a new three-way distinction for this family.
    assert j_unknown["verdict"] == "not_evidenced"
    assert j_unknown["evidence_state"] == "not_evidenced"
