"""Release 1 (evidence engine): verified requirement judging, years derived
from role dates, freshness tie-break, deduped evidence, restored diagnostics,
and the false-warning / wording fixes."""

import json
from datetime import date
from types import SimpleNamespace
from typing import Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence, PastRole
from backend.models.intake import ContradictionFinding, IntakeDecision, IntakeResult, RoleUnderstanding, SearchBoundary
from backend.models.search_intent import Experience, Role, SearchIntent, Skills, Titles
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.base import BaseProvider
from backend.providers.harvest import HarvestClient, HarvestEnrichmentService
from backend.services.candidate_evidence_builder import (
    _classify_seniority,
    _derive_experience_years,
    build_candidate_evidence,
)
from backend.services.candidate_merger import CandidateMerger
from backend.services.candidate_ranker import CandidateRanker
from backend.services.intake_reasoning import MISSING_LOCATION_WARNING, apply_search_boundary
from backend.services.match_explainer import MatchExplainer
from backend.services.requirement_judge import JudgeOutcome, RequirementJudge
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_pipeline import REVIEW_READY, STATUS_COMPLETE, run_search_pipeline
from backend.services.search_store import SearchStore


def _intent(core: Optional[List[str]] = None, minimum_years: Optional[int] = None) -> SearchIntent:
    return SearchIntent(
        role=Role(title="Backend Engineer", seniority="Mid-level"),
        titles=Titles(include_titles=["Backend Engineer"]),
        skills=Skills(required_skills=[]),
        experience=Experience(minimum_years=minimum_years),
        core_signals=core or [],
    )


def _candidate(cid="c1", name="Ada", description="Built REST APIs in Python.", updated="2026-09-20T00:00:00+00:00", **extra):
    raw = {
        "basic_profile": {"headline": "Backend Engineer"},
        "experience": {"employment_details": {"current": [], "past": []}},
        "metadata": {"updated_at": updated},
    }
    raw.update(extra)
    return Candidate(candidate_id=cid, name=name, title="Backend Engineer", company="Acme", raw_data=raw)


def _harvest_with(description: str) -> HarvestEvidence:
    return HarvestEvidence(
        success=True,
        raw={
            "element": {
                "experience": [{"position": "Backend Engineer", "companyName": "Acme", "description": description}],
                "skills": [{"name": "Python"}],
            }
        },
    )


class _FakeClient:
    """Stands in for the OpenAI client. First call: the canned verdicts.
    Second (review) call: approves every claim unless told otherwise."""

    def __init__(self, results: List[Dict], raises: bool = False) -> None:
        self._results = results
        self._raises = raises
        self.calls = 0
        self.responses = self

    def create(self, **kwargs):
        self.calls += 1
        if self._raises:
            raise RuntimeError("model unavailable")
        system = kwargs["input"][0]["content"]
        if "claims" in json.loads(kwargs["input"][1]["content"]):
            claims = json.loads(kwargs["input"][1]["content"])["claims"]
            return SimpleNamespace(output_text=json.dumps({"results": [{"i": c["i"], "supports": True} for c in claims]}), usage=None)
        return SimpleNamespace(output_text=json.dumps({"results": self._results}), usage=None)


# --- requirement judge: no verified quote, no credit ------------------------------------------------------------

def test_judge_accepts_a_quote_that_really_appears_in_the_cited_passage() -> None:
    intent = _intent(core=["Experience designing REST APIs"])
    harvest = _harvest_with("Built REST APIs enabling data exchange across enterprise systems.")
    probe = RequirementJudge(client=_FakeClient([]))
    # Find which passage number carries the role description.
    evidence = build_candidate_evidence(_candidate(), intent, harvest_evidence=harvest)
    sources = evidence.labeled_text_sources()
    index = next(i for i, s in enumerate(sources) if "REST APIs" in s.text)
    offset = 1 if evidence.derived_experience_years is not None else 0

    judge = RequirementJudge(client=_FakeClient([{"r": 0, "verdict": "met", "p": index + offset, "quote": "Built REST APIs enabling data exchange", "term": "REST APIs"}]))
    judgments = judge.judge(_candidate(), intent, harvest_evidence=harvest)

    assert judgments[0]["verdict"] == "met"
    assert judgments[0]["quote"] == "Built REST APIs enabling data exchange"
    assert judgments[0]["source"] == "harvest: employment description"
    assert probe.is_available()


def test_judge_discards_a_fabricated_or_paraphrased_quote() -> None:
    intent = _intent(core=["Working experience with relational databases"])
    harvest = _harvest_with("Contributed to system design discussions.")
    judge = RequirementJudge(client=_FakeClient([{"r": 0, "verdict": "met", "p": 0, "quote": "Managed PostgreSQL schemas and migrations", "term": "PostgreSQL"}]))

    judgments = judge.judge(_candidate(), intent, harvest_evidence=harvest)

    assert judgments[0]["verdict"] == "not_evidenced"
    assert "quote" not in judgments[0]


def test_judge_discards_a_quote_cited_against_the_wrong_passage() -> None:
    intent = _intent(core=["Python"])
    harvest = _harvest_with("Built REST APIs in Go.")
    judge = RequirementJudge(client=_FakeClient([{"r": 0, "verdict": "met", "p": 99, "quote": "Built REST APIs", "term": "REST"}]))
    assert judge.judge(_candidate(), intent, harvest_evidence=harvest)[0]["verdict"] == "not_evidenced"


def test_judge_failure_returns_none_so_the_caller_falls_back() -> None:
    judge = RequirementJudge(client=_FakeClient([], raises=True))
    assert judge.judge(_candidate(), _intent(core=["Python"])) is None


def test_judge_does_nothing_without_requirements() -> None:
    client = _FakeClient([])
    assert RequirementJudge(client=client).judge(_candidate(), _intent(core=[])) is None
    assert client.calls == 0


def test_judged_alignment_uses_only_verified_judgments_not_term_matching() -> None:
    # The sentence contains the generic word "design"; the candidate's text
    # contains it too, so the OLD term matcher would have matched. With a judge
    # verdict of not_evidenced, alignment must show it as unmatched.
    intent = _intent(core=["Working experience with relational databases, including schema design"])
    candidate = _candidate()
    candidate.raw_data["__requirement_judgments"] = [
        {"tier": "core", "signal_text": intent.core_signals[0], "verdict": "not_evidenced"}
    ]
    harvest = _harvest_with("Contributed to backend performance improvements and system design discussions.")

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)
    assert evidence.role_alignment.matched_signals == []
    assert [s.signal_text for s in evidence.role_alignment.unmatched_signals] == intent.core_signals

    legacy = build_candidate_evidence(_candidate(), intent, harvest_evidence=harvest)
    assert legacy.role_alignment.matched_signals  # the false positive the judge exists to remove


def test_verified_judgment_flows_into_recruiter_facing_evidence() -> None:
    intent = _intent(core=["Experience designing REST APIs"])
    candidate = _candidate()
    candidate.raw_data["__requirement_judgments"] = [
        {
            "tier": "core", "signal_text": intent.core_signals[0], "verdict": "met",
            "quote": "Built REST APIs enabling data exchange", "term": "REST APIs",
            "source": "harvest: employment description", "evidence_detail": "Backend Engineer at Acme",
            "evidence_type": "demonstrated_work", "strength": "strong",
        }
    ]
    explanation = MatchExplainer().explain(candidate, intent)
    assert any("Built REST APIs enabling data exchange" in line for line in explanation.strong_evidence)


# --- years from dates ---------------------------------------------------------------------------------

def test_years_are_derived_from_dates_with_overlaps_merged_and_open_roles_skipped() -> None:
    roles = [
        PastRole(title="A", company="X", start_date="2020-01-01T00:00:00", end_date="2022-01-01T00:00:00"),
        PastRole(title="B", company="Y", start_date="2021-01-01T00:00:00", end_date="2023-01-01T00:00:00"),  # overlaps A
        PastRole(title="C", company="Z", start_date="2019-01-01T00:00:00", end_date=None),  # skipped: no end
    ]
    years = _derive_experience_years({}, roles, today=date(2026, 1, 1))
    assert years == 3.0  # 2020-01 -> 2023-01, not 4.0


def test_current_role_runs_to_today() -> None:
    assert _derive_experience_years({"start_date": "2025-01-01T00:00:00"}, [], today=date(2026, 1, 1)) == 1.0


def test_no_dates_means_no_derived_years() -> None:
    assert _derive_experience_years({}, [PastRole(title="A", company="X")]) is None


def test_seniority_compares_derived_years_to_the_asked_minimum_not_the_provider_label() -> None:
    candidate = _candidate()
    candidate.raw_data["experience"]["employment_details"]["current"] = [
        {"start_date": "2020-01-01T00:00:00", "seniority_level": "Entry Level"}
    ]
    evidence = build_candidate_evidence(candidate, _intent(minimum_years=3), None)
    assert evidence.current_seniority == "Entry Level"
    assert evidence.derived_experience_years and evidence.derived_experience_years > 3
    aligned, basis = _classify_seniority(evidence, "Mid-level", 3)
    assert aligned is True and "professional experience are visible in dated roles" in basis
    # Total experience is NOT backend-specific experience, and must say so.
    assert "not independently verified" in basis


# --- ranking, wording and dedupe ---------------------------------------------------------------------

def test_exact_score_ties_break_by_freshest_profile_not_by_name() -> None:
    older = _candidate("1", "Aaron", updated="2026-01-01T00:00:00+00:00")
    newer = _candidate("2", "Zed", updated="2026-09-01T00:00:00+00:00")
    ranked = CandidateRanker().rank([older, newer], _intent())
    assert older.final_score == newer.final_score
    assert [c.name for c in ranked] == ["Zed", "Aaron"]


def test_title_relevance_text_has_no_python_list_syntax() -> None:
    evidence = build_candidate_evidence(_candidate(), _intent(), None)
    basis = evidence.role_alignment.title_relevance_basis
    assert "[" not in basis and "]" not in basis


def test_repeated_evidence_sentence_is_shown_once() -> None:
    intent = _intent(core=["Backend services", "High volume systems"])
    candidate = _candidate()
    quote = "Designed scalable backend services for high volume systems"
    candidate.raw_data["__requirement_judgments"] = [
        {"tier": "core", "signal_text": s, "verdict": "met", "quote": quote, "term": "backend services",
         "source": "harvest: employment description", "evidence_detail": "Engineer at Acme",
         "evidence_type": "demonstrated_work", "strength": "strong"}
        for s in intent.core_signals
    ]
    lines = MatchExplainer().explain(candidate, intent).strong_evidence
    assert len(lines) == 1


# --- warnings ---------------------------------------------------------------------------------------

def test_boundary_removes_the_false_no_location_warning() -> None:
    result = IntakeResult(
        raw_input="x",
        role_understanding=RoleUnderstanding(),
        decision=IntakeDecision(warnings=[MISSING_LOCATION_WARNING, "Some other real warning"]),
        contradictions=[ContradictionFinding(category="missing_location", warning=MISSING_LOCATION_WARNING, evidence=[])],
    )
    boundary = SearchBoundary(hiring_company="Epiq", country="Canada", work_mode="hybrid", state="Ontario", city="Toronto", radius_miles=25)
    apply_search_boundary(result, boundary)
    assert result.decision.warnings == ["Some other real warning"]
    assert result.contradictions == []


def test_friendly_warnings_do_not_use_provider_vocabulary() -> None:
    from backend.api import _friendly_capability_warnings

    text = " ".join(_friendly_capability_warnings(["dropped unsupported filter 'work_mode'"]))
    assert "provider" not in text.lower() and "work mode" in text


# --- Harvest: one retry for a malformed read ---------------------------------------------------------

def test_malformed_harvest_read_is_retried_once() -> None:
    calls = {"n": 0}

    class Flaky:
        def is_configured(self):
            return True

        def fetch_profile(self, url, **kwargs):
            calls["n"] += 1
            return {"element": {"about": "ok"}} if calls["n"] == 2 else {"unexpected": True}

    service = HarvestEnrichmentService(client=Flaky())
    result = service._fetch_one(Candidate(candidate_id="c9", profile_url="https://www.linkedin.com/in/x"))
    assert result.success is True and calls["n"] == 2


# --- pipeline: judge wiring, funnel, restored diagnostics --------------------------------------------

class _Provider(BaseProvider):
    def __init__(self, n):
        self.n = n

    def search(self, plan):
        return self.search_with_options(plan)

    def search_with_options(self, plan, options=None):
        if "natural_language" not in [q.query_name for q in plan.searches]:
            return []
        return [
            Candidate(
                candidate_id=f"p{i}", name=f"Person {i}", title="Backend Engineer", company="Acme",
                profile_url=f"https://www.linkedin.com/in/p{i}",
                raw_data={"basic_profile": {"headline": "Backend Engineer"}, "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"},
                          "__response_metadata": {"total_count": 725313}},
            )
            for i in range(self.n)
        ]


class _HarvestOK(HarvestClient):
    def is_configured(self):
        return True

    def fetch_profile(self, url, **kwargs):
        return {"element": {"experience": [{"position": "Engineer", "companyName": "Acme", "description": "Built REST APIs enabling data exchange."}]}, "cost": 0.0064}


class _AlwaysMetJudge(RequirementJudge):
    def __init__(self):
        super().__init__(client=object())
        self.seen = 0

    def judge_detailed(self, candidate, intent, harvest_evidence=None):
        self.seen += 1
        return JudgeOutcome(
            judgments=[{"tier": "core", "signal_text": intent.core_signals[0], "verdict": "not_evidenced"}],
            requirements=1, calls=1, input_tokens=1000, output_tokens=200, latency_ms=50.0,
        )


def _run_pipeline(tmp_path, n, judge, top_n=25):
    intent = _intent(core=["Experience designing REST APIs"])
    intent.location.countries = ["Canada"]
    store = SearchStore(storage_dir=tmp_path)
    run_search_pipeline(
        search_id="r1", intent=intent,
        mapped_plan=SearchPlan(searches=[SearchQuery(query_name="natural_language", natural_language_query="x")]),
        options={}, provider=_Provider(n), candidate_merger=CandidateMerger(), candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=HarvestEnrichmentService(client=_HarvestOK(), top_n=top_n),
        match_explainer=MatchExplainer(), search_diagnostics=SearchDiagnostics(), search_store=store,
        jd_text="jd", location_override=None, friendly_warnings=[], debug=False, existing_record={},
        requirement_judge=judge,
    )
    return store.load("r1")


def test_pipeline_judges_every_read_candidate_and_reads_all_25(tmp_path) -> None:
    judge = _AlwaysMetJudge()
    record = _run_pipeline(tmp_path, 30, judge)
    assert record["status"] == STATUS_COMPLETE
    assert judge.seen == 25  # every admitted candidate, not just a top slice
    assert len(record["harvest_evidence"]) == 25
    assert all(state == REVIEW_READY for state in record["response"]["candidate_states"].values())
    assert all(c["raw_data"].get("__requirement_judgments") for c in record["response"]["candidates"])


def test_pipeline_records_an_honest_funnel_and_restores_diagnostics(tmp_path) -> None:
    record = _run_pipeline(tmp_path, 30, _AlwaysMetJudge())
    funnel = record["response"]["diagnostics"]["funnel"]
    assert funnel == {
        "in_scope": 725313, "has_location_scope": True, "retrieved": 30, "selected": 25,
        "read_in_depth": 25, "presented": 25,
    }
    internal = record["internal_diagnostics"]
    assert internal["crustdata"]["merged_unique_count"] == 30
    assert internal["harvest"]["attempted"] == 25 and internal["harvest"]["successful"] == 25
    assert internal["harvest"]["total_cost"] > 0
    judge = internal["requirement_judge"]
    assert judge["enabled"] is True and judge["candidates_judged"] == 25 and judge["openai_calls"] == 25
    assert judge["requirements_judged"] == 25 and judge["input_tokens"] == 25000 and judge["estimated_cost_usd"] > 0
    assert internal["harvest"]["retried"] == 0
    assert internal["evidence_coverage"]["candidates"] == 25
    assert internal["admission"]["final_candidate_count"] == 25


def test_pipeline_without_a_judge_keeps_the_deterministic_engine(tmp_path) -> None:
    record = _run_pipeline(tmp_path, 5, None)
    assert record["status"] == STATUS_COMPLETE
    assert record["internal_diagnostics"]["requirement_judge"]["enabled"] is False
    assert not any(c["raw_data"].get("__requirement_judgments") for c in record["response"]["candidates"])


# --- Review Ready gating and recruiter-facing language ---------------------------------------------------

def test_candidate_is_not_review_ready_until_read_and_judged(tmp_path) -> None:
    observed = []
    store = SearchStore(storage_dir=tmp_path)

    class Watching(_AlwaysMetJudge):
        def judge_detailed(self, candidate, intent, harvest_evidence=None):
            state = store.load("r1")["response"]["candidate_states"][candidate.candidate_id]
            observed.append((state, harvest_evidence.success if harvest_evidence else None))
            return super().judge_detailed(candidate, intent, harvest_evidence)

    intent = _intent(core=["Experience designing REST APIs"])
    run_search_pipeline(
        search_id="r1", intent=intent,
        mapped_plan=SearchPlan(searches=[SearchQuery(query_name="natural_language", natural_language_query="x")]),
        options={}, provider=_Provider(6), candidate_merger=CandidateMerger(), candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=HarvestEnrichmentService(client=_HarvestOK(), top_n=25),
        match_explainer=MatchExplainer(), search_diagnostics=SearchDiagnostics(), search_store=store,
        jd_text="jd", location_override=None, friendly_warnings=[], debug=False, existing_record={},
        requirement_judge=Watching(),
    )
    # While being judged, every candidate was still BUILDING_CONTEXT, and its profile had already been read.
    assert len(observed) == 6
    assert all(state == "building_context" and read_ok is True for state, read_ok in observed)
    final = store.load("r1")["response"]["candidate_states"]
    assert set(final.values()) == {REVIEW_READY}


_FORBIDDEN = ("provider", "crustdata", "harvest", "openai", "gpt", "judge", "natural_language", "enrich")


def test_no_internal_provider_language_reaches_recruiter_facing_text(tmp_path) -> None:
    record = _run_pipeline(tmp_path, 8, _AlwaysMetJudge())
    response = record["response"]
    texts = list(response["warnings"])
    for explanation in response["explanations"]:
        texts += [explanation["why_this_candidate"], *explanation["strong_evidence"], *explanation["potential_concerns"], *explanation["what_we_dont_know"]]
    for evidence in response["evidence"]:
        texts += [note["note"] for note in evidence["uncertainty"]]
        alignment = evidence["role_alignment"]
        texts += [alignment["title_relevance_basis"], alignment["seniority_alignment_basis"]]
    leaks = [(word, text) for text in texts for word in _FORBIDDEN if word in text.lower()]
    assert leaks == []


# --- concurrency: found by the real Toronto run ------------------------------------------------------

def test_readers_never_see_a_half_written_record_while_the_pipeline_is_saving(tmp_path) -> None:
    import threading

    store = SearchStore(storage_dir=tmp_path)
    big = {"response": {"candidates": [{"raw_data": "x" * 200_000} for _ in range(5)]}, "status": "running"}
    stop = threading.Event()
    failures = []

    def writer():
        for i in range(60):
            big["n"] = i
            store.save("s1", big)
        stop.set()

    store.save("s1", big)
    thread = threading.Thread(target=writer)
    thread.start()
    while not stop.is_set():
        if store.load("s1") is None:
            failures.append(1)
    thread.join()
    assert failures == []  # a torn read used to return None -> "search not found" -> polling stopped


def test_a_decision_made_mid_search_is_not_overwritten_by_pipeline_progress_saves(tmp_path) -> None:
    store = SearchStore(storage_dir=tmp_path)
    decided = []

    class DecidingMidRun(_AlwaysMetJudge):
        def judge_detailed(self, candidate, intent, harvest_evidence=None):
            if not decided:  # the recruiter shortlists the first candidate that is judged, while the search is running
                decided.append(candidate.candidate_id)
                store.update("r1", lambda r: r.setdefault("recruiter_decisions", {}).__setitem__(candidate.candidate_id, "shortlist"))
            return super().judge_detailed(candidate, intent, harvest_evidence)

    intent = _intent(core=["Experience designing REST APIs"])
    run_search_pipeline(
        search_id="r1", intent=intent,
        mapped_plan=SearchPlan(searches=[SearchQuery(query_name="natural_language", natural_language_query="x")]),
        options={}, provider=_Provider(8), candidate_merger=CandidateMerger(), candidate_ranker=CandidateRanker(),
        harvest_enrichment_service=HarvestEnrichmentService(client=_HarvestOK(), top_n=25),
        match_explainer=MatchExplainer(), search_diagnostics=SearchDiagnostics(), search_store=store,
        jd_text="jd", location_override=None, friendly_warnings=[], debug=False, existing_record={},
        requirement_judge=DecidingMidRun(),
    )
    record = store.load("r1")
    assert record["status"] == STATUS_COMPLETE
    assert record["recruiter_decisions"] == {decided[0]: "shortlist"}
    assert record["response"]["recruiter_decisions"] == {decided[0]: "shortlist"}


def test_unevidenced_core_requirements_are_reported_as_unknowns_only_when_the_judge_ran() -> None:
    intent = _intent(core=["Experience with PostgreSQL", "Experience with REST APIs"])
    judged = _candidate()
    judged.raw_data["__requirement_judgments"] = [
        {"tier": "core", "signal_text": intent.core_signals[0], "verdict": "not_evidenced"},
        {"tier": "core", "signal_text": intent.core_signals[1], "verdict": "met", "quote": "Built REST APIs",
         "term": "REST APIs", "source": "harvest: employment description", "evidence_detail": "Engineer at Acme",
         "evidence_type": "demonstrated_work", "strength": "strong"},
    ]
    unknowns = MatchExplainer().explain(judged, intent).what_we_dont_know
    gap = [u for u in unknowns if u.startswith("No evidence found on the profile for these core requirements")]
    assert len(gap) == 1 and "PostgreSQL" in gap[0] and "REST APIs" not in gap[0]

    # Without a judge, "unmatched" only means "no keyword hit": it must not be presented as a gap.
    unjudged = MatchExplainer().explain(_candidate(), intent).what_we_dont_know
    assert not any("No evidence found" in u for u in unjudged)
