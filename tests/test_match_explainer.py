from backend.models.candidate import Candidate
from backend.models.search_intent import (
    CompanyPreferences,
    Experience,
    Location,
    PreviousBackground,
    Ranking,
    Role,
    SearchIntent,
    Skills,
    Titles,
)
from backend.services.match_explainer import MatchExplainer


def test_explainer_builds_structured_match_summary() -> None:
    candidate = Candidate(
        name="Alicia",
        title="Machine Learning Engineer",
        company="OpenAI",
        location="US",
        provider_score=0.91,
        final_score=9.1,
        raw_data={"skills": ["Python", "PyTorch"], "years_experience": 6},
    )
    intent = SearchIntent(
        role=Role(title="Machine Learning Engineer"),
        location=Location(countries=["US"], cities=["New York"]),
        experience=Experience(minimum_years=5, maximum_years=10),
        titles=Titles(include_titles=["Machine Learning Engineer"]),
        skills=Skills(required_skills=["Python"], preferred_skills=["PyTorch"]),
        previous_background=PreviousBackground(preferred_companies=["OpenAI"]),
        company_preferences=CompanyPreferences(),
        ranking=Ranking(),
    )

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.final_score == 9.1
    assert explanation.matched_required_skills == ["Python"]
    assert explanation.missing_required_skills == []
    assert explanation.matched_preferred_skills == ["PyTorch"]
    assert explanation.missing_preferred_skills == []
    assert explanation.title_match is True
    assert explanation.location_match is True
    assert explanation.company_match is True
    assert explanation.experience_match is True
    assert explanation.matched_titles == ["Machine Learning Engineer"]
    assert explanation.matched_skills == ["Python", "PyTorch"]
    assert explanation.missing_skills == []
    assert explanation.matched_location == "US"
    assert explanation.matched_experience == "6 years"
    assert explanation.potential_risks == []
    assert "title matches" in explanation.summary


def test_explainer_reports_missing_matches() -> None:
    candidate = Candidate(
        title="Data Scientist",
        company="Acme",
        location="CA",
        final_score=6.0,
        raw_data={"skills": ["SQL"], "years_experience": 2},
    )
    intent = SearchIntent(
        titles=Titles(include_titles=["Machine Learning Engineer"]),
        location=Location(countries=["US"]),
        experience=Experience(minimum_years=5),
        skills=Skills(required_skills=["Python"], preferred_skills=["PyTorch"]),
        previous_background=PreviousBackground(preferred_companies=["OpenAI"]),
    )

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.matched_required_skills == []
    assert explanation.missing_required_skills == ["Python"]
    assert explanation.matched_preferred_skills == []
    assert explanation.missing_preferred_skills == ["PyTorch"]
    assert explanation.title_match is False
    assert explanation.location_match is False
    assert explanation.company_match is False
    assert explanation.experience_match is False
    assert explanation.matched_titles == []
    assert explanation.matched_skills == []
    assert explanation.missing_skills == ["Python"]
    assert explanation.matched_location is None
    assert explanation.matched_experience == "Requires at least 5 years of experience"
    assert explanation.potential_risks == ["Experience is below the requested range"]


def test_explainer_treats_missing_experience_data_as_insufficient_evidence_not_a_mismatch() -> None:
    # Regression test: a candidate with no years_experience data at all must
    # never be treated the same as one confirmed to fall outside the
    # requested range. Missing evidence is not negative evidence.
    candidate = Candidate(
        name="Jordan",
        title="Machine Learning Engineer",
        company="OpenAI",
        location="US",
        raw_data={},  # no years_experience key at all
    )
    intent = SearchIntent(
        titles=Titles(include_titles=["Machine Learning Engineer"]),
        location=Location(countries=["US"]),
        experience=Experience(minimum_years=5),
    )

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.experience_match is None
    assert explanation.matched_experience is None
    assert explanation.missing_experience is None
    # No "risk" is raised purely from missing data.
    assert explanation.potential_risks == []
    assert "could not be verified from the available data" in explanation.summary
    assert "does not satisfy" not in explanation.summary
