"""Release 1.1: level fit is judged from titles against the target seniority,
separately from the experience floor (arithmetic on dated roles). Years alone
never place anyone above or below a level, and nothing here changes the score."""

from datetime import date, timedelta
from typing import List, Optional

import pytest

from backend.models.candidate import Candidate
from backend.models.search_intent import Experience, Role, SearchIntent
from backend.services.candidate_evidence_builder import _level_marker, build_candidate_evidence
from backend.services.candidate_ranker import CandidateRanker
from backend.services.match_explainer import MatchExplainer


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat() + "T00:00:00"


def _candidate(title: str, years: Optional[float], headline: Optional[str] = None, past_titles: List[str] = ()) -> Candidate:
    current = [{"start_date": _iso(int(years * 365.25))}] if years is not None else []
    past = [{"title": t, "name": "Prev", "start_date": "2010-01-01T00:00:00", "end_date": "2011-01-01T00:00:00"} for t in past_titles]
    return Candidate(
        candidate_id="c1", name="Ada", title=title, company="Acme",
        raw_data={
            "basic_profile": {"headline": headline if headline is not None else title},
            "experience": {"employment_details": {"current": current, "past": past}},
        },
    )


def _intent(seniority: Optional[str] = "Senior", minimum_years: Optional[int] = 5) -> SearchIntent:
    return SearchIntent(role=Role(title="Backend Engineer", seniority=seniority), experience=Experience(minimum_years=minimum_years))


def _alignment(candidate: Candidate, intent: Optional[SearchIntent] = None):
    return build_candidate_evidence(candidate, intent or _intent()).role_alignment


# --- the eight regression cases the level pass has to get right --------------------------------------------------------
def test_senior_target_senior_candidate_is_aligned() -> None:
    a = _alignment(_candidate("Senior Software Engineer", 7))
    assert a.level_fit == "aligned" and a.experience_floor is True
    assert "consistent with the target Senior role" in a.level_basis


def test_senior_target_staff_candidate_is_potentially_above() -> None:
    a = _alignment(_candidate("Staff Software Engineer", 13))
    assert a.level_fit == "above" and a.experience_floor is True   # floor met AND possibly above: two separate facts
    assert "may indicate a level above the target Senior role" in a.level_basis


def test_senior_target_principal_candidate_is_potentially_above() -> None:
    a = _alignment(_candidate("Principal Engineer", 15))
    assert a.level_fit == "above"


def test_senior_target_junior_candidate_is_potentially_below() -> None:
    a = _alignment(_candidate("Junior Software Engineer", 2))
    assert a.level_fit == "below" and a.experience_floor is False


def test_missing_seniority_on_the_search_yields_no_level_claim() -> None:
    a = _alignment(_candidate("Staff Software Engineer", 13), _intent(seniority=None))
    assert a.level_fit is None and a.level_basis == ""


def test_conflicting_title_and_headline_is_unclear_not_a_guess() -> None:
    a = _alignment(_candidate("Backend Engineer", 7, headline="Senior Software Engineer"), _intent(seniority="Mid-level", minimum_years=3))
    # title states no level (so it does not conflict); headline says senior against a mid target -> a headline-only signal
    assert a.level_fit == "above"
    b = _alignment(_candidate("Staff Engineer", 9, headline="Senior Software Engineer"), _intent(seniority="Senior"))
    assert b.level_fit == "unclear" and "point to different levels" in b.level_basis


def test_high_experience_with_a_title_that_states_no_level_is_not_called_above() -> None:
    a = _alignment(_candidate("Backend Engineer", 19))
    assert a.level_fit == "unclear"            # years alone never make someone "above"
    assert a.experience_floor is True
    assert "states no level" in a.level_basis


def test_low_experience_with_a_senior_title_is_aligned_on_level_but_fails_the_floor() -> None:
    a = _alignment(_candidate("Senior Software Engineer", 2))
    assert a.level_fit == "aligned" and a.experience_floor is False


# --- more of the general behaviour ---------------------------------------------------------------------------------
def test_no_level_in_the_title_and_years_below_the_ask_is_potentially_below() -> None:
    a = _alignment(_candidate("Software Engineer", 2.5))
    assert a.level_fit == "below" and a.experience_floor is False


def test_earlier_title_can_confirm_a_fit_but_never_contradict_one() -> None:
    confirmed = _alignment(_candidate("Software Engineer", 8, past_titles=["Senior Software Engineer"]))
    assert confirmed.level_fit == "aligned"
    not_contradicted = _alignment(_candidate("Software Engineer", 8, past_titles=["Staff Engineer"]))
    assert not_contradicted.level_fit == "unclear"   # a past Staff title must not flag someone as above


def test_numbered_levels_are_understood() -> None:
    assert _level_marker("Software Engineer II")[1] == "mid"
    assert _level_marker("Backend Engineer Level III")[1] == "senior"
    assert _level_marker("Backend Engineer") is None


def test_mid_level_target_reads_mid_title_as_aligned() -> None:
    a = _alignment(_candidate("Software Engineer II", 4), _intent(seniority="Mid-level", minimum_years=3))
    assert a.level_fit == "aligned"


def test_floor_and_level_are_reported_as_two_facts_in_the_explanation() -> None:
    explanation = MatchExplainer().explain(_candidate("Staff Software Engineer", 13), _intent())
    assert explanation.experience_floor is True and explanation.level_fit == "above"
    assert any(s.startswith("Experience floor met:") for s in [explanation.why_this_candidate.split(". ")[1] + "."] + [explanation.why_this_candidate])
    assert "Level alignment" not in explanation.why_this_candidate           # an above-target level is a concern, not a strength
    concern = next(c for c in explanation.potential_concerns if c.startswith("Level alignment"))
    assert "may indicate a level above the target Senior role" in concern and "consider" in concern
    assert "overqualified" not in " ".join(explanation.potential_concerns).lower()


def test_unclear_level_is_listed_as_something_we_do_not_know_and_not_a_concern() -> None:
    explanation = MatchExplainer().explain(_candidate("Backend Engineer", 7), _intent())
    assert explanation.level_fit == "unclear"
    assert any(n.startswith("Level alignment") and "states no level" in n for n in explanation.what_we_dont_know)
    assert not any("Level alignment" in c for c in explanation.potential_concerns)


def test_the_years_wording_stays_truthful_and_never_says_backend_years() -> None:
    explanation = MatchExplainer().explain(_candidate("Senior Software Engineer", 7), _intent())
    assert "years of professional experience are visible in dated roles" in explanation.why_this_candidate
    assert "not independently verified" in explanation.why_this_candidate
    assert "backend experience" not in explanation.why_this_candidate.lower()


def test_level_fit_does_not_change_the_score() -> None:
    """Release 1.1 exposes the level signal but deliberately leaves the ranking formula alone: a candidate whose title
    may be above the target scores exactly what an aligned one does."""
    ranker = CandidateRanker()
    staff = _candidate("Staff Software Engineer", 8)
    senior = _candidate("Senior Software Engineer", 8)
    staff.candidate_id, senior.candidate_id = "s1", "s2"
    ranker.rank([staff, senior], _intent())
    assert staff.final_score == pytest.approx(senior.final_score)
