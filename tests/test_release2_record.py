"""Release 2 (candidate record): the display data the record needs (photo, open-to-work, career with descriptions,
education fallback, the three review-first lines) is built from what the providers actually returned, never guessed,
and never touches ranking."""

from typing import Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Experience, Role, SearchIntent, Titles
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer

CORE = ["Proficiency in Python", "Experience with REST APIs", "Experience with Kafka"]


def intent() -> SearchIntent:
    return SearchIntent(role=Role(title="Backend Engineer", seniority="Senior"), titles=Titles(include_titles=["Backend Engineer"]),
                        experience=Experience(minimum_years=5), core_signals=list(CORE))


def candidate(photo: Optional[str] = "https://crustdata.example/p.jpg", education=None, judgments=None, past=None) -> Candidate:
    raw: Dict = {
        "basic_profile": {"headline": "Backend Engineer", "profile_picture_permalink": photo},
        "experience": {"employment_details": {
            "current": [{"title": "Backend Engineer", "name": "Acme", "start_date": "2023-02-01T00:00:00"}],
            "past": past if past is not None else [{"title": "Developer", "name": "Beta", "start_date": "2019-07-01T00:00:00", "end_date": "2023-01-01T00:00:00"}]}},
        "education": {"schools": education or []},
    }
    if judgments is not None:
        raw["__requirement_judgments"] = judgments
    return Candidate(candidate_id="c1", name="Ada", title="Backend Engineer", company="Acme", raw_data=raw)


def harvest(open_to_work=None, photo=None, experience=None, education=None) -> HarvestEvidence:
    element: Dict = {"experience": experience or [], "education": education or []}
    if open_to_work is not None:
        element["openToWork"] = open_to_work
    if photo:
        element["photo"] = photo
    return HarvestEvidence(success=True, raw={"element": element})


def met(text, strength="strong", source="harvest: employment description", quote="Built it."):
    return {"tier": "core", "signal_text": text, "verdict": "met", "quote": quote, "term": "x", "source": source,
            "evidence_detail": "Engineer at Acme", "evidence_type": "demonstrated_work", "strength": strength}


def missing(text):
    return {"tier": "core", "signal_text": text, "verdict": "not_evidenced"}


# --- photo and open-to-work -------------------------------------------------------------------------------------------
def test_photo_prefers_the_search_providers_image_and_falls_back_to_the_profile_read() -> None:
    assert build_candidate_evidence(candidate(), intent(), harvest(photo="https://li.example/h.jpg")).photo_url == "https://crustdata.example/p.jpg"
    assert build_candidate_evidence(candidate(photo=None), intent(), harvest(photo="https://li.example/h.jpg")).photo_url == "https://li.example/h.jpg"
    assert build_candidate_evidence(candidate(photo=None), intent()).photo_url is None
    assert build_candidate_evidence(candidate(photo="not-a-url"), intent()).photo_url is None      # never a broken value


def test_open_to_work_is_only_known_when_the_profile_read_says_so() -> None:
    assert build_candidate_evidence(candidate(), intent(), harvest(open_to_work=True)).open_to_work is True
    assert build_candidate_evidence(candidate(), intent(), harvest(open_to_work=False)).open_to_work is False
    assert build_candidate_evidence(candidate(), intent()).open_to_work is None                     # unknown is not "no"


def test_open_to_work_and_photo_never_change_the_score() -> None:
    ranker = CandidateRanker()
    plain, decorated = candidate(photo=None), candidate()
    plain.candidate_id, decorated.candidate_id = "a", "b"
    ranker.rerank_top_n(ranker.rank([plain, decorated], intent()), intent(), {"a": harvest(), "b": harvest(open_to_work=True, photo="https://x.example/y.jpg")}, top_n=2)
    assert plain.final_score == decorated.final_score


# --- career -------------------------------------------------------------------------------------------------------------
def test_career_uses_the_profile_read_with_descriptions_and_marks_the_current_role() -> None:
    experience = [
        {"position": "Backend Engineer", "companyName": "Acme", "startDate": {"text": "Feb 2023"}, "endDate": {"text": "Present"}, "duration": "1 yr 8 mos", "description": "- Built REST APIs."},
        {"position": "Developer", "companyName": "Beta", "startDate": {"text": "Jul 2019"}, "endDate": {"text": "Jan 2023"}, "description": None},
    ]
    career = build_candidate_evidence(candidate(), intent(), harvest(experience=experience)).career
    assert [(c.title, c.company, c.current) for c in career] == [("Backend Engineer", "Acme", True), ("Developer", "Beta", False)]
    assert career[0].description == "- Built REST APIs." and career[0].end is None and career[1].end == "Jan 2023"
    assert career[1].description is None                                       # no description is shown as none, not invented


def test_career_falls_back_to_search_data_with_display_dates_and_no_descriptions() -> None:
    career = build_candidate_evidence(candidate(), intent()).career
    assert [(c.title, c.start, c.end, c.current) for c in career] == [
        ("Backend Engineer", "Feb 2023", None, True), ("Developer", "Jul 2019", "Jan 2023", False)]
    assert all(c.description is None for c in career)


def test_education_comes_from_search_data_and_only_falls_back_to_the_profile_read() -> None:
    profile_edu = [{"schoolName": "Read U", "degree": "BSc", "fieldOfStudy": "CS", "startDate": {"year": 2014}, "endDate": {"year": 2018}}]
    fallback = build_candidate_evidence(candidate(), intent(), harvest(education=profile_edu)).education
    assert [(e.institution, e.degree, e.end_date) for e in fallback] == [("Read U", "BSc", "2018")]
    own = build_candidate_evidence(candidate(education=[{"school": "Search U", "degree": "MSc", "end_year": 2020}]), intent(), harvest(education=profile_edu)).education
    assert [e.institution for e in own] == ["Search U"]


# --- the three review-first lines -----------------------------------------------------------------------------------------
def explain(judgments) -> List[str]:
    return MatchExplainer().explain(candidate(judgments=judgments), intent(), harvest_evidence=harvest()).review_first


def test_review_first_lines_name_what_is_proven_what_is_not_and_what_to_watch() -> None:
    lines = explain([met(CORE[0]), met(CORE[1]), missing(CORE[2])])
    assert len(lines) == 3
    assert lines[0].startswith("Evidence for 2 of 3 core requirements.") and "Proficiency in Python" in lines[0] and "REST APIs" in lines[0]
    assert lines[1] == "Not evidenced on the profile: Experience with Kafka."
    assert lines[2].startswith("Watch:") or lines[2] == "Nothing flagged."


def test_review_first_only_credits_demonstrated_work_in_its_first_line_and_never_invents() -> None:
    lines = explain([met(CORE[0], strength="supporting", source="harvest: skill"), met(CORE[1]), met(CORE[2])])
    assert "Shown in described work: Experience with REST APIs; Experience with Kafka." in lines[0]
    assert "Proficiency in Python" not in lines[0].split("Shown in described work:")[1]          # a listed skill is not "described work"
    assert lines[1] == "Every core requirement has evidence on the profile."


def test_review_first_is_empty_when_no_judge_ran() -> None:
    assert MatchExplainer().explain(candidate(), intent()).review_first == []


def test_review_first_watch_line_carries_level_concerns() -> None:
    staff = candidate(judgments=[met(CORE[0]), met(CORE[1]), met(CORE[2])])
    staff.title = "Staff Backend Engineer"
    lines = MatchExplainer().explain(staff, intent(), harvest_evidence=harvest()).review_first
    assert lines[2].startswith("Watch:") and "level above" in lines[2]
