# Wires backend/services/requirement_semantics.py into the REAL
# requirement_judge path. career_signals.py's predicates already have their
# own unit tests (tests/test_career_signals.py) — these tests prove the
# recognizer correctly classifies requirement SENTENCES, and that
# RequirementJudge answers a recognized one deterministically (never asking
# the LLM), while an unrecognized one still goes through the existing LLM
# path completely unchanged.

import json
from types import SimpleNamespace
from typing import Dict, List

from backend.models.candidate import Candidate
from backend.models.search_intent import Role, SearchIntent, Titles
from backend.services.requirement_judge import RequirementJudge
from backend.services.requirement_semantics import SemanticRequirement, evaluate, recognize_requirement


def _intent(*core: str) -> SearchIntent:
    return SearchIntent(role=Role(title="Recruiter"), titles=Titles(include_titles=["Recruiter"]), core_signals=list(core))


def _candidate(events_current: List[Dict], events_past: List[Dict], candidate_id="c1") -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        name="Test Candidate",
        title=(events_current[0]["title"] if events_current else None),
        raw_data={"experience": {"employment_details": {"current": events_current, "past": events_past}}},
    )


def _event(title, headcount=None, industries=None, start=None, end=None):
    e = {"title": title, "name": f"Company for {title}", "start_date": start, "end_date": end}
    if headcount is not None:
        e["company_headcount_latest"] = headcount
    if industries is not None:
        e["company_industries"] = industries
    return e


class _CountingClient:
    """Records every payload it was actually asked, so tests can prove the
    deterministic pre-pass kept a recognized requirement OUT of it."""

    def __init__(self, results: List[Dict]):
        self._results = results
        self.calls: List[Dict] = []
        self.responses = self

    def create(self, **kwargs):
        payload = json.loads(kwargs["input"][1]["content"])
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        if "claims" in payload:
            claims = payload["claims"]
            return SimpleNamespace(output_text=json.dumps({"results": [{"i": c["i"], "supports": True} for c in claims]}), usage=usage)
        self.calls.append(payload)
        return SimpleNamespace(output_text=json.dumps({"results": self._results}), usage=usage)


# ---------------------------------------------------------------------------
# recognize_requirement(): classification of free-text requirement sentences
# ---------------------------------------------------------------------------

def test_recognizes_current_startup_language():
    r = recognize_requirement("currently works at a startup")
    assert r == SemanticRequirement(text="currently works at a startup", family="company_size", scope="current", operator="matches", value="small")


def test_recognizes_historical_startup_language():
    r = recognize_requirement("worked at startups earlier in their career")
    assert r == SemanticRequirement(text="worked at startups earlier in their career", family="company_size", scope="career", operator="matches", value="small")


def test_recognizes_current_enterprise_language():
    r = recognize_requirement("currently works at a large enterprise")
    assert r == SemanticRequirement(text="currently works at a large enterprise", family="company_size", scope="current", operator="matches", value="large")


def test_recognizes_historical_enterprise_language():
    r = recognize_requirement("worked at an enterprise company")
    assert r == SemanticRequirement(text="worked at an enterprise company", family="company_size", scope="career", operator="matches", value="large")


def test_recognizes_both_bands():
    r = recognize_requirement("worked across startups and large enterprises")
    assert r == SemanticRequirement(text="worked across startups and large enterprises", family="company_size", scope="career", operator="worked_across", values=("small", "large"))


def test_recognizes_current_tech():
    r = recognize_requirement("currently works at a technology company")
    assert r == SemanticRequirement(text="currently works at a technology company", family="industry", scope="current", operator="matches", value="technology")


def test_recognizes_historical_tech():
    r = recognize_requirement("worked at a technology company")
    assert r == SemanticRequirement(text="worked at a technology company", family="industry", scope="career", operator="matches", value="technology")


def test_recognizes_tech_duration():
    r = recognize_requirement("worked in technology for 3+ years")
    assert r == SemanticRequirement(text="worked in technology for 3+ years", family="industry", scope="career", operator="duration_at_least", value="technology", min_years=3.0)


def test_recognizes_current_leadership():
    r = recognize_requirement("currently a recruiting leader")
    assert r == SemanticRequirement(text="currently a recruiting leader", family="career_state", scope="current", operator="currently_leadership")


def test_recognizes_historical_progression():
    r = recognize_requirement("has progressed from recruiter to leadership")
    assert r == SemanticRequirement(text="has progressed from recruiter to leadership", family="career_progression", scope="career", operator="historical_leadership_progression")


def test_ambiguous_wording_is_not_recognized_and_not_silently_scoped():
    # Task 5's explicit example: this must NOT be transformed into
    # "currently works at a startup" — it stays unrecognized and falls
    # through to the existing LLM path.
    assert recognize_requirement("Experience working with startups") is None


def test_unrelated_requirement_is_not_recognized():
    assert recognize_requirement("Proficiency in Python") is None
    assert recognize_requirement("") is None


def test_current_vs_historical_industry_are_represented_distinctly():
    current = recognize_requirement("currently works at a technology company")
    historical = recognize_requirement("worked at a technology company")
    assert current.family == historical.family == "industry"
    assert current.operator == historical.operator == "matches"
    assert current.value == historical.value == "technology"
    assert current.scope == "current"
    assert historical.scope == "career"
    assert current.scope != historical.scope


def test_current_vs_historical_career_state_are_represented_as_different_families():
    # Not merely a scope difference: "currently a leader" (career_state) and
    # "historical progression" (career_progression) are two distinct
    # families with two distinct operators, per the task's own examples.
    current = recognize_requirement("currently a recruiting leader")
    historical = recognize_requirement("has progressed from recruiter to leadership")
    assert current.family == "career_state"
    assert current.operator == "currently_leadership"
    assert historical.family == "career_progression"
    assert historical.operator == "historical_leadership_progression"
    assert current.family != historical.family
    assert current.operator != historical.operator


def test_company_size_operators_are_represented_distinctly():
    single_band = recognize_requirement("currently works at a startup")
    both_bands = recognize_requirement("worked across startups and large enterprises")
    assert single_band.family == both_bands.family == "company_size"
    assert single_band.operator == "matches"
    assert single_band.value == "small"
    assert single_band.values is None
    assert both_bands.operator == "worked_across"
    assert both_bands.values == ("small", "large")
    assert both_bands.value is None
    assert single_band.operator != both_bands.operator


# ---------------------------------------------------------------------------
# evaluate(): the 15 minimum cases, against realistic employment events
# ---------------------------------------------------------------------------

def test_1_current_startup():
    c = _candidate([_event("Recruiter", headcount=150, end=None)], [])
    j = evaluate(recognize_requirement("currently works at a startup"), "core", c)
    assert j["verdict"] == "met" and "150" in j["quote"]


def test_2_historical_startup():
    c = _candidate([_event("Manager", headcount=20000, end=None)], [_event("Recruiter", headcount=150, end="2018-01-01")])
    j = evaluate(recognize_requirement("worked at startups"), "core", c)
    assert j["verdict"] == "met"


def test_3_current_enterprise():
    c = _candidate([_event("Recruiter", headcount=22000, end=None)], [])
    j = evaluate(recognize_requirement("currently works at a large enterprise"), "core", c)
    assert j["verdict"] == "met"


def test_4_historical_enterprise():
    c = _candidate([_event("Recruiter", headcount=50, end=None)], [_event("Recruiter", headcount=9000, end="2015-01-01")])
    j = evaluate(recognize_requirement("worked at an enterprise company"), "core", c)
    assert j["verdict"] == "met"


def test_5_startup_and_enterprise_progression():
    c = _candidate([_event("Manager", headcount=9000, end=None)], [_event("Recruiter", headcount=80, end="2016-01-01")])
    j = evaluate(recognize_requirement("worked across startups and large enterprises"), "core", c)
    assert j["verdict"] == "met"
    assert "80" in j["quote"] and "9,000" in j["quote"]


def test_6_unknown_headcount_does_not_satisfy():
    c = _candidate([_event("Recruiter", headcount=0, end=None)], [_event("Recruiter", headcount=None, end="2016-01-01")])
    j = evaluate(recognize_requirement("currently works at a startup"), "core", c)
    assert j["verdict"] == "not_evidenced" and j["quote"] == ""


def test_7_current_tech():
    c = _candidate([_event("Recruiter", industries=["Software Development"], end=None)], [])
    j = evaluate(recognize_requirement("currently works at a technology company"), "core", c)
    assert j["verdict"] == "met"


def test_8_historical_tech_but_current_non_tech():
    c = _candidate(
        [_event("Recruiter", industries=["Legal Services"], end=None)],
        [_event("Recruiter", industries=["Technology, Information and Internet"], end="2020-01-01")],
    )
    j_current = evaluate(recognize_requirement("currently works at a technology company"), "core", c)
    j_any = evaluate(recognize_requirement("worked at a technology company"), "core", c)
    assert j_current["verdict"] == "not_evidenced"
    assert j_any["verdict"] == "met"


def test_9_historical_tech():
    c = _candidate([_event("Recruiter", industries=["Healthcare"], end=None)], [_event("Recruiter", industries=["Software"], end="2019-01-01")])
    j = evaluate(recognize_requirement("worked at a technology company"), "core", c)
    assert j["verdict"] == "met"


def test_10_tech_duration():
    c = _candidate(
        [_event("Recruiter", industries=["Healthcare"], end=None)],
        [
            _event("Recruiter", industries=["Software Development"], end="2020-01-01"),
        ],
    )
    c.raw_data["experience"]["employment_details"]["past"][0]["duration_years"] = 4.0
    j = evaluate(recognize_requirement("worked in technology for 3+ years"), "core", c)
    assert j["verdict"] == "met"
    assert "4" in j["quote"]


def test_11_mixed_industry_career():
    c = _candidate(
        [_event("Recruiter", industries=["Healthcare"], end=None)],
        [
            _event("Recruiter", industries=["Software Development"], end="2020-01-01"),
            _event("Recruiter", industries=["Legal Services"], end="2015-01-01"),
        ],
    )
    assert evaluate(recognize_requirement("worked at a technology company"), "core", c)["verdict"] == "met"
    assert evaluate(recognize_requirement("currently works at a technology company"), "core", c)["verdict"] == "not_evidenced"


def test_12_historical_leadership_progression():
    c = _candidate(
        [_event("Recruiting Manager", end=None, start="2020-01-01")],
        [_event("Recruiter", end="2020-01-01", start="2016-01-01")],
    )
    j = evaluate(recognize_requirement("has progressed from recruiter to leadership"), "core", c)
    assert j["verdict"] == "met"
    assert "Recruiter" in j["quote"] and "Recruiting Manager" in j["quote"]


def test_13_current_recruiting_leadership():
    c = _candidate([_event("Recruiting Manager", end=None)], [_event("Recruiter", end="2019-01-01")])
    j = evaluate(recognize_requirement("currently a recruiting leader"), "core", c)
    assert j["verdict"] == "met"


def test_14_historical_leadership_but_current_ic():
    c = _candidate(
        [_event("Executive Recruiter", end=None, start="2019-06-01")],
        [
            _event("Recruiter", end="2004-07-01", start="1996-01-01"),
            _event("Director of Talent Acquisition", end="2019-06-01", start="2018-03-01"),
        ],
    )
    hist = evaluate(recognize_requirement("has progressed from recruiter to leadership"), "core", c)
    cur = evaluate(recognize_requirement("currently a recruiting leader"), "core", c)
    assert hist["verdict"] == "met"
    assert cur["verdict"] == "not_evidenced"


def test_15_executive_recruiter_remains_ic_shaped_for_progression():
    from backend.services.career_signals import is_ic_title, is_leadership_title
    assert is_ic_title("Executive Recruiter") is True
    assert is_leadership_title("Executive Recruiter") is False


# ---------------------------------------------------------------------------
# Real requirement_judge integration: LLM is never asked about a recognized
# requirement; it's still asked about everything else, unchanged.
# ---------------------------------------------------------------------------

def test_all_recognized_requirements_never_call_the_llm_at_all():
    intent = _intent("currently works at a technology company", "currently a recruiting leader")
    candidate = _candidate([_event("Recruiting Manager", industries=["Software Development"], end=None)], [_event("Recruiter", end="2019-01-01")])
    client = _CountingClient(results=[])

    judgments = RequirementJudge(client=client).judge(candidate, intent)

    assert client.calls == []  # the LLM was never invoked
    assert [j["verdict"] for j in judgments] == ["met", "met"]
    assert all(j.get("deterministic") for j in judgments)


def test_mixed_requirements_only_send_the_unrecognized_one_to_the_llm():
    intent = _intent("currently works at a technology company", "Proficiency in Python")
    candidate = _candidate([_event("Recruiting Manager", industries=["Software Development"], end=None)], [])
    client = _CountingClient(results=[{"r": 1, "verdict": "met", "p": 0, "quote": "x", "term": "x"}])
    # A passage the LLM can cite, so the ordinary path has something to verify against.
    candidate.raw_data["basic_profile"] = {"headline": "x"}

    judgments = RequirementJudge(client=client).judge(candidate, intent)

    assert len(client.calls) == 1  # exactly one LLM call, for the non-recognized requirement only
    sent_requirement_indices = {r["r"] for r in client.calls[0]["requirements"]}
    assert sent_requirement_indices == {1}  # only "Proficiency in Python" (index 1) was sent
    assert judgments[0]["deterministic"] is True
    assert judgments[0]["verdict"] == "met"


def test_deterministic_judgments_are_exempt_from_the_review_pass():
    intent = _intent("currently a recruiting leader")
    candidate = _candidate([_event("Recruiting Manager", end=None)], [_event("Recruiter", end="2019-01-01")])

    class _FailIfCalled:
        responses = None

        def __getattr__(self, item):
            raise AssertionError("The LLM must never be called for an all-deterministic requirement set")

    judgments = RequirementJudge(client=_FailIfCalled()).judge(candidate, intent)
    assert judgments[0]["verdict"] == "met"


# ---------------------------------------------------------------------------
# Natural-language requirements flowing end-to-end through the real path
# ---------------------------------------------------------------------------

def test_nl_1_currently_works_at_a_startup_end_to_end():
    intent = _intent("currently works at a startup")
    candidate = _candidate([_event("Recruiter", headcount=45, end=None)], [_event("Recruiter", headcount=30000, end="2018-01-01")])
    judgments = RequirementJudge(client=_CountingClient([])).judge(candidate, intent)
    assert judgments[0]["verdict"] == "met"  # current employer is the known-small one


def test_nl_2_worked_at_a_technology_company_end_to_end():
    intent = _intent("worked at a technology company")
    candidate = _candidate(
        [_event("Talent Acquisition Lead", industries=["Law Practice", "Legal Services"], end=None)],
        [_event("Senior Manager Talent Acquisition", industries=["Technology, Information and Internet"], end="2022-04-01")],
    )
    judgments = RequirementJudge(client=_CountingClient([])).judge(candidate, intent)
    assert judgments[0]["verdict"] == "met"  # the real Harsha/Epiq pattern: past employer is enough for the unscoped form


def test_nl_3_currently_a_recruiting_leader_end_to_end_false_case():
    intent = _intent("currently a recruiting leader")
    candidate = _candidate(
        [_event("Executive Recruiter", end=None, start="2019-06-01")],
        [_event("Director of Talent Acquisition", end="2019-06-01", start="2018-03-01")],
    )
    judgments = RequirementJudge(client=_CountingClient([])).judge(candidate, intent)
    assert judgments[0]["verdict"] == "not_evidenced"  # reached leadership before, but not currently
