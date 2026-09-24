"""The requirement judge's central invariant: a "met" verdict reaches a
recruiter only if its quote is verified to appear in the profile passage it
cites. Anything else is downgraded to NOT_EVIDENCED.

These tests pin the DETERMINISTIC gate with a scripted model. Whether the real
model judges meaning correctly (generic-word and related-but-insufficient
cases) is covered by the opt-in live tests at the bottom
(RUN_LIVE_JUDGE=1), because a scripted model cannot prove that."""

import json
import os
from types import SimpleNamespace
from typing import Dict, List

import pytest

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Experience, Role, SearchIntent, Skills, Titles
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.match_explainer import MatchExplainer
from backend.services.requirement_judge import CAREER_DATES_CAVEAT, RequirementJudge, build_passages

DB_REQ = "Working experience with relational databases, including schema design"
REST_REQ = "Experience designing and implementing REST APIs consumed by other teams"
PY_REQ = "Proficiency in Python"
YEARS_REQ = "3+ years of professional experience building backend services"


def _intent(*core: str) -> SearchIntent:
    return SearchIntent(
        role=Role(title="Backend Engineer", seniority="Mid-level"),
        titles=Titles(include_titles=["Backend Engineer"]),
        skills=Skills(required_skills=[]),
        experience=Experience(minimum_years=3),
        core_signals=list(core),
    )


def _candidate() -> Candidate:
    return Candidate(
        candidate_id="c1", name="Ada", title="Backend Engineer", company="Acme",
        raw_data={
            "basic_profile": {"headline": "Backend Engineer"},
            "experience": {"employment_details": {"current": [{"start_date": "2019-01-01T00:00:00"}], "past": []}},
            "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"},
        },
    )


def _harvest(*descriptions: str, skills: List[str] = ()) -> HarvestEvidence:
    return HarvestEvidence(
        success=True,
        raw={"element": {
            "experience": [{"position": "Engineer", "companyName": "Acme", "description": d} for d in descriptions],
            "skills": [{"name": s} for s in skills],
        }},
    )


class _Scripted:
    """A scripted model. First call returns the given verdicts. The review
    call approves every claim by default; `review` overrides that:
    a set of requirement snippets to reject, "omit" to affirm nothing, or
    "fail" to raise."""

    def __init__(self, results: List[Dict], review=None) -> None:
        self._results = results
        self._review = review
        self.review_calls = 0
        self.responses = self

    def create(self, **kwargs):
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        if "claims" in json.loads(kwargs["input"][1]["content"]):
            self.review_calls += 1
            if self._review == "fail":
                raise RuntimeError("review model unavailable")
            claims = json.loads(kwargs["input"][1]["content"])["claims"]
            if self._review == "omit":
                return SimpleNamespace(output_text=json.dumps({"results": []}), usage=usage)
            rejected = self._review or set()
            return SimpleNamespace(
                output_text=json.dumps({"results": [{"i": c["i"], "supports": not any(r in c["requirement"] for r in rejected)} for c in claims]}),
                usage=usage,
            )
        return SimpleNamespace(output_text=json.dumps({"results": self._results}), usage=usage)


def _index(passages, needle: str) -> int:
    return next(i for i, p in enumerate(passages) if needle.lower() in p.text.lower())


def _judge(results, intent, harvest, candidate=None, review=None):
    candidate = candidate or _candidate()
    return RequirementJudge(client=_Scripted(results, review)).judge(candidate, intent, harvest_evidence=harvest), candidate


def _explain(judgments, intent, harvest, candidate=None):
    candidate = candidate or _candidate()
    candidate.raw_data["__requirement_judgments"] = judgments
    return MatchExplainer().explain(candidate, intent, harvest_evidence=harvest), build_candidate_evidence(candidate, intent, harvest_evidence=harvest)


# 1 ----------------------------------------------------------------------------------------------------------
def test_verified_positive_evidence_reaches_the_recruiter_with_its_source() -> None:
    intent, harvest = _intent(REST_REQ), _harvest("Built REST APIs enabling data exchange across enterprise systems.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "REST APIs"), "quote": "Built REST APIs enabling data exchange", "term": "REST APIs"}], intent, harvest)

    explanation, evidence = _explain(judgments, intent, harvest)

    assert judgments[0]["verdict"] == "met" and judgments[0]["strength"] == "strong"
    assert any("Built REST APIs enabling data exchange" in line for line in explanation.strong_evidence)
    assert evidence.role_alignment.matched_signals[0].evidence_text == "Built REST APIs enabling data exchange"


# 2 / 3 / 7  related-but-insufficient and partial: never counted, never shown as evidence -----------------
def test_partly_met_is_recorded_but_never_counts_or_shows_as_strong_evidence() -> None:
    intent, harvest = _intent(REST_REQ), _harvest("Developed a proof of concept to showcase Spring Boot and Docker.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "partly", "p": _index(p, "Spring Boot"), "quote": "proof of concept to showcase Spring Boot", "term": "Spring Boot"}], intent, harvest)

    explanation, evidence = _explain(judgments, intent, harvest)

    assert judgments[0]["verdict"] == "partly"
    assert evidence.role_alignment.matched_signals == []
    assert [s.signal_text for s in evidence.role_alignment.unmatched_signals] == [REST_REQ]
    assert explanation.strong_evidence == []


def test_unknown_verdict_or_missing_result_is_not_evidenced() -> None:
    intent, harvest = _intent(PY_REQ, DB_REQ), _harvest("Wrote services in Python.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "definitely", "p": _index(p, "Python"), "quote": "Wrote services in Python", "term": "Python"}], intent, harvest)  # r=1 omitted
    assert [j["verdict"] for j in judgments] == ["not_evidenced", "not_evidenced"]


# 4 ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("quote", ["Managed PostgreSQL schemas and migrations", "Designed relational data models", "", "  "])
def test_a_quote_the_model_invents_never_becomes_evidence(quote: str) -> None:
    intent, harvest = _intent(DB_REQ), _harvest("Contributed to system design discussions.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "design discussions"), "quote": quote, "term": "PostgreSQL"}], intent, harvest)
    explanation, evidence = _explain(judgments, intent, harvest)

    assert judgments[0]["verdict"] == "not_evidenced" and "quote" not in judgments[0]
    assert evidence.role_alignment.matched_signals == []
    assert not any(quote.strip() and quote in line for line in explanation.strong_evidence)


# 5 ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "source, quote",
    [
        ("• Built REST APIs for partner teams.", "Built REST APIs for partner teams."),            # bullet dropped
        ("Built REST APIs for partner teams.", "  built   rest apis  for partner teams. "),            # case + whitespace
        ("Led the team’s “REST” rollout – on time.", "Led the team's \"REST\" rollout - on time."),  # curly quotes, en dash
        ("Built REST APIs.", "Built REST APIs."),                                             # non-breaking spaces
    ],
)
def test_harmless_formatting_differences_still_verify(source: str, quote: str) -> None:
    intent, harvest = _intent(REST_REQ), _harvest(source)
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "REST"), "quote": quote, "term": "REST"}], intent, harvest)
    assert judgments[0]["verdict"] == "met"


def test_a_changed_word_does_not_verify() -> None:
    intent, harvest = _intent(REST_REQ), _harvest("Built REST APIs for partner teams.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "REST"), "quote": "Built GraphQL APIs for partner teams.", "term": "GraphQL"}], intent, harvest)
    assert judgments[0]["verdict"] == "not_evidenced"


# 6 ----------------------------------------------------------------------------------------------------------
def test_missing_evidence_is_reported_as_not_evidenced() -> None:
    intent, harvest = _intent(DB_REQ), _harvest("Wrote unit tests.")
    judgments, _ = _judge([{"r": 0, "verdict": "not_evidenced", "p": None, "quote": "", "term": ""}], intent, harvest)
    _, evidence = _explain(judgments, intent, harvest)
    assert judgments[0]["verdict"] == "not_evidenced"
    assert [s.signal_text for s in evidence.role_alignment.unmatched_signals] == [DB_REQ]


# 8 ----------------------------------------------------------------------------------------------------------
def test_two_requirements_sharing_one_sentence_both_count_but_the_recruiter_sees_it_once() -> None:
    sentence = "Built REST APIs and Python services for high-volume systems."
    intent, harvest = _intent(REST_REQ, PY_REQ), _harvest(sentence)
    p = build_passages(_candidate(), intent, harvest)
    i = _index(p, "REST APIs")
    judgments, _ = _judge(
        [{"r": 0, "verdict": "met", "p": i, "quote": "Built REST APIs and Python services", "term": "REST APIs"},
         {"r": 1, "verdict": "met", "p": i, "quote": "Built REST APIs and Python services", "term": "Python"}],
        intent, harvest,
    )
    explanation, evidence = _explain(judgments, intent, harvest)
    assert len(evidence.role_alignment.matched_signals) == 2  # both requirements are credited
    assert len(explanation.strong_evidence) == 1  # but the same proof is not shown twice


# 9 ----------------------------------------------------------------------------------------------------------
def test_listed_skill_is_labelled_supporting_and_demonstrated_work_strong() -> None:
    intent = _intent(PY_REQ, REST_REQ)
    harvest = _harvest("Built REST APIs enabling partner data exchange.", skills=["Python (Programming Language)"])
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge(
        [{"r": 0, "verdict": "met", "p": _index(p, "Python (Programming"), "quote": "Python (Programming Language)", "term": "Python"},
         {"r": 1, "verdict": "met", "p": _index(p, "Built REST"), "quote": "Built REST APIs enabling partner data exchange", "term": "REST APIs"}],
        intent, harvest,
    )
    by_signal = {j["signal_text"]: j for j in judgments}
    assert by_signal[PY_REQ]["evidence_type"] == "named_skill" and by_signal[PY_REQ]["strength"] == "supporting"
    assert by_signal[REST_REQ]["evidence_type"] == "demonstrated_work" and by_signal[REST_REQ]["strength"] == "strong"


# 10 ---------------------------------------------------------------------------------------------------------
def test_conflicting_passages_a_quote_is_only_valid_against_the_passage_that_contains_it() -> None:
    # Two passages: one describes databases, one describes Java. The model
    # cites the Java passage for the database requirement while quoting the
    # database sentence. The sentence exists in the profile, but not where
    # the model said, so it is not accepted.
    intent = _intent(DB_REQ)
    harvest = _harvest("Designed relational data models and SQL queries.", "Wrote Java services for the billing team.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "Java services"), "quote": "Designed relational data models and SQL queries", "term": "SQL"}], intent, harvest)
    assert judgments[0]["verdict"] == "not_evidenced"

    correct, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "relational data models"), "quote": "Designed relational data models and SQL queries", "term": "SQL"}], intent, harvest)
    assert correct[0]["verdict"] == "met"


def test_unparseable_model_output_falls_back_instead_of_breaking() -> None:
    class Garbage:
        responses = None

        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            return SimpleNamespace(output_text="not json at all", usage=None)

    intent = _intent(PY_REQ)
    assert RequirementJudge(client=Garbage()).judge(_candidate(), intent, harvest_evidence=_harvest("Wrote Python.")) is None


# Second-pass review: a real-but-irrelevant quote must not survive ------------------------------------------
def test_review_pass_downgrades_a_real_quote_that_does_not_state_the_requirement() -> None:
    # The quote EXISTS in the profile (so the deterministic gate passes), but it is
    # about AWS infrastructure, not REST APIs: the failure seen live on a real profile.
    intent = _intent(REST_REQ, PY_REQ)
    harvest = _harvest("Designed backend systems and AWS infrastructure supporting a scalable application.", "Wrote Python services.")
    p = build_passages(_candidate(), intent, harvest)
    results = [
        {"r": 0, "verdict": "met", "p": _index(p, "AWS infrastructure"), "quote": "Designed backend systems and AWS infrastructure", "term": "AWS"},
        {"r": 1, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"},
    ]
    judgments, _ = _judge(results, intent, harvest, review={"REST APIs"})
    explanation, evidence = _explain(judgments, intent, harvest)

    assert [j["verdict"] for j in judgments] == ["partly", "met"]
    assert judgments[0]["review"] == "not_supported_by_quote_alone"
    assert [s.signal_text for s in evidence.role_alignment.matched_signals] == [PY_REQ]
    assert not any("AWS infrastructure" in line for line in explanation.strong_evidence)


def test_a_claim_the_reviewer_does_not_affirm_is_not_evidence() -> None:
    intent, harvest = _intent(PY_REQ), _harvest("Wrote Python services.")
    p = build_passages(_candidate(), intent, harvest)
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"}], intent, harvest, review="omit")
    assert judgments[0]["verdict"] == "partly"


def test_if_the_review_call_fails_first_pass_verdicts_stand_and_the_failure_is_recorded() -> None:
    intent, harvest = _intent(PY_REQ), _harvest("Wrote Python services.")
    p = build_passages(_candidate(), intent, harvest)
    client = _Scripted([{"r": 0, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"}], review="fail")
    outcome = RequirementJudge(client=client).judge_detailed(_candidate(), intent, harvest)
    assert outcome.judgments[0]["verdict"] == "met" and outcome.review_failed is True


def test_the_computed_career_dates_claim_is_not_sent_for_review() -> None:
    intent, harvest = _intent(YEARS_REQ), _harvest("Built services.")
    client = _Scripted([{"r": 0, "verdict": "met", "p": 0, "quote": "years of professional experience are visible in dated roles", "term": "experience"}])
    RequirementJudge(client=client).judge(_candidate(), intent, harvest_evidence=harvest)
    assert client.review_calls == 0


# An omitted answer is re-asked, not silently read as "not evidenced" -------------------------------------
def test_requirements_the_model_skipped_are_asked_again_once() -> None:
    intent, harvest = _intent(PY_REQ, REST_REQ), _harvest("Wrote Python services.", "Built REST APIs for partners.")
    p = build_passages(_candidate(), intent, harvest)
    answers = iter([
        [{"r": 0, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"}],   # r=1 skipped
        [{"r": 1, "verdict": "met", "p": _index(p, "Built REST"), "quote": "Built REST APIs for partners", "term": "REST APIs"}],
    ])
    asked = []

    class Partial(_Scripted):
        def create(self, **kwargs):
            if not "claims" in json.loads(kwargs["input"][1]["content"]):
                self._results = next(answers)
                asked.append([r["r"] for r in json.loads(kwargs["input"][1]["content"])["requirements"]])
            return super().create(**kwargs)

    outcome = RequirementJudge(client=Partial([])).judge_detailed(_candidate(), intent, harvest)

    assert [j["verdict"] for j in outcome.judgments] == ["met", "met"]
    assert asked == [[0, 1], [1]]  # the second call asked ONLY for the skipped requirement
    assert outcome.re_asked_missing == 1


# Experience: total vs discipline-specific ------------------------------------------------------------------
def test_a_years_requirement_is_credited_from_total_experience_and_says_so() -> None:
    intent, harvest = _intent(YEARS_REQ), _harvest("Built backend services.")
    p = build_passages(_candidate(), intent, harvest)
    assert p[0].label == "career dates" and CAREER_DATES_CAVEAT in p[0].text
    judgments, _ = _judge([{"r": 0, "verdict": "met", "p": 0, "quote": "years of professional experience are visible in dated roles", "term": "professional experience"}], intent, harvest)
    explanation, evidence = _explain(judgments, intent, harvest)

    line = explanation.strong_evidence[0]
    assert "professional experience are visible in dated roles" in line
    assert "not independently verified" in line
    assert "years of backend experience" not in line.lower()
    assert "not independently verified" in evidence.role_alignment.seniority_alignment_basis
    assert any("not independently verified" in note.note for note in evidence.uncertainty if note.field == "years_of_experience")


# ---------------------------------------------------------------------------------------------------------
# Opt-in LIVE regression anchors: real gpt-4o-mini on profile text distilled from
# the Toronto validation. Skipped unless RUN_LIVE_JUDGE=1 (spends a few cents).
# ---------------------------------------------------------------------------------------------------------
live = pytest.mark.skipif(os.environ.get("RUN_LIVE_JUDGE") != "1", reason="live OpenAI test; set RUN_LIVE_JUDGE=1")


def _live(intent, harvest):
    from backend.services.requirement_judge import RequirementJudge as Real

    return {j["signal_text"]: j for j in Real().judge(_candidate(), intent, harvest_evidence=harvest)}


@live
def test_live_generic_word_is_not_evidence() -> None:
    intent = _intent(DB_REQ, "Exposure to AI/ML systems or data-intensive applications")
    harvest = _harvest("Contributed to backend performance improvements and system design discussions.", "Built backend services using Python (Django) for data-driven applications.")
    result = _live(intent, harvest)
    assert result[DB_REQ]["verdict"] != "met"
    assert result["Exposure to AI/ML systems or data-intensive applications"]["verdict"] != "met"


@live
def test_live_related_tooling_is_not_full_evidence() -> None:
    intent = _intent(REST_REQ, "Familiarity with containerized deployment (Docker, and exposure to Kubernetes)")
    harvest = _harvest("Developed a proof of concept to showcase the simplicity and speed of Spring Boot and Docker")
    result = _live(intent, harvest)
    assert result[REST_REQ]["verdict"] != "met"


@live
def test_live_genuine_evidence_is_found_with_a_real_quote() -> None:
    intent = _intent(REST_REQ, DB_REQ)
    harvest = _harvest("Built REST APIs enabling data exchange across enterprise systems.", "Designed and optimized relational data models and SQL queries for performance.")
    result = _live(intent, harvest)
    assert result[REST_REQ]["verdict"] == "met" and result[DB_REQ]["verdict"] == "met"


# ---------------------------------------------------------------------------------------------------------
# Release 1.1: the reviewer judges each claim in its own call (batched calls flipped verdicts on real quotes)
# ---------------------------------------------------------------------------------------------------------
def test_each_met_claim_is_reviewed_in_its_own_call() -> None:
    intent, harvest = _intent(PY_REQ, REST_REQ), _harvest("Wrote Python services.", "Built REST APIs for partners.")
    p = build_passages(_candidate(), intent, harvest)
    payloads: List[List[int]] = []

    class Recording(_Scripted):
        def create(self, **kwargs):
            if kwargs["input"][0]["content"].startswith("You review whether a quote"):
                payloads.append([c["i"] for c in json.loads(kwargs["input"][1]["content"])["claims"]])
                self.review_calls += 1
                claims = json.loads(kwargs["input"][1]["content"])["claims"]
                return SimpleNamespace(output_text=json.dumps({"results": [{"i": c["i"], "supports": True} for c in claims]}), usage=None)
            return super().create(**kwargs)

    results = [
        {"r": 0, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"},
        {"r": 1, "verdict": "met", "p": _index(p, "Built REST"), "quote": "Built REST APIs for partners", "term": "REST APIs"},
    ]
    RequirementJudge(client=Recording(results)).judge_detailed(_candidate(), intent, harvest)
    assert sorted(payloads) == [[0], [1]]  # two claims -> two single-claim calls, never one shared call


def test_one_failed_review_call_leaves_only_that_claim_unreviewed() -> None:
    intent, harvest = _intent(PY_REQ, REST_REQ), _harvest("Wrote Python services.", "Built REST APIs for partners.")
    p = build_passages(_candidate(), intent, harvest)

    class FlakyReview(_Scripted):
        def create(self, **kwargs):
            if kwargs["input"][0]["content"].startswith("You review whether a quote"):
                claims = json.loads(kwargs["input"][1]["content"])["claims"]
                if claims[0]["requirement"] == PY_REQ:
                    raise RuntimeError("one review call failed")
                # the other claim is rejected by the reviewer
                return SimpleNamespace(output_text=json.dumps({"results": [{"i": claims[0]["i"], "supports": False}]}), usage=None)
            return super().create(**kwargs)

    results = [
        {"r": 0, "verdict": "met", "p": _index(p, "Wrote Python"), "quote": "Wrote Python services", "term": "Python"},
        {"r": 1, "verdict": "met", "p": _index(p, "Built REST"), "quote": "Built REST APIs for partners", "term": "REST APIs"},
    ]
    outcome = RequirementJudge(client=FlakyReview(results)).judge_detailed(_candidate(), intent, harvest)
    by_text = {j["signal_text"]: j["verdict"] for j in outcome.judgments}
    assert by_text[PY_REQ] == "met" and outcome.review_failed is True    # failed call: first-pass verdict stands, recorded
    assert by_text[REST_REQ] == "partly"                                   # the other claim was still reviewed and rejected


@live
def test_live_reviewer_rejects_generic_mentions_and_plans_but_keeps_real_evidence() -> None:
    """The semantic pattern behind the borderline live matches: a generic mention ("high-performance APIs"),
    or discussing/planning the work ("held meetings to ... design solutions such as APIs"), is not the
    requirement itself; a quote that names it (or a tool of its own kind) still is."""
    from openai import OpenAI

    from backend.config import get_openai_api_key
    from backend.services.requirement_judge import RequirementJudge as Real

    def reviewed(requirement: str, quote: str) -> str:
        judgment = {"tier": "core", "signal_text": requirement, "verdict": "met", "quote": quote, "source": "harvest: employment description"}
        outcome = SimpleNamespace(judgments=[judgment], calls=0, input_tokens=0, output_tokens=0, review_failed=False, downgraded_by_review=0)
        Real()._review(OpenAI(api_key=get_openai_api_key()), outcome)
        return judgment["verdict"]

    assert reviewed(REST_REQ, "Designed and developed scalable backend services in Go and Python, delivering high-performance APIs for education platforms.") == "partly"
    assert reviewed(REST_REQ, "I held meetings to assess technical requirements and design solutions such as APIs and front-end architecture.") == "partly"
    assert reviewed(REST_REQ, "Built REST APIs in Flask for partner integrations.") == "met"
    assert reviewed("Familiarity with containerized deployment", "Provided consulting on microservices, leveraging Docker for deployment and scaling.") == "met"
