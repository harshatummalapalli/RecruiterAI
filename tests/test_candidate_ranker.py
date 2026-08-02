from backend.models.candidate import Candidate
from backend.models.search_intent import (
    CompanyPreferences,
    Experience,
    Location,
    PreviousBackground,
    Role,
    SearchIntent,
    Skills,
    Titles,
)
from backend.services.candidate_ranker import CandidateRanker


def test_rank_scores_candidates_using_intent_signals() -> None:
    intent = SearchIntent(
        role=Role(title="Machine Learning Engineer"),
        location=Location(countries=["US"], cities=["New York"]),
        experience=Experience(minimum_years=5),
        titles=Titles(include_titles=["Machine Learning Engineer"], exclude_titles=["Manager"]),
        skills=Skills(required_skills=["Python", "PyTorch"], preferred_skills=["AWS"]),
        previous_background=PreviousBackground(preferred_companies=["OpenAI"]),
        company_preferences=CompanyPreferences(exclude_current_companies=["Big Tech"]),
    )

    candidates = [
        Candidate(
            name="Alice",
            title="Machine Learning Engineer",
            company="OpenAI",
            location="New York, US",
            provider_score=0.9,
            raw_data={"skills": ["Python", "PyTorch", "AWS"]},
        ),
        Candidate(
            name="Bob",
            title="Manager",
            company="Big Tech",
            location="Remote",
            provider_score=0.8,
            raw_data={"skills": ["Python"]},
        ),
        Candidate(
            name="Carol",
            title="Data Scientist",
            company="Acme",
            location="London",
            provider_score=0.7,
            raw_data={"skills": ["Python"]},
        ),
    ]

    ranked = CandidateRanker().rank(candidates, intent)

    assert ranked[0].name == "Alice"
    assert ranked[0].final_score == 6.9
    assert ranked[1].name == "Carol"
    assert ranked[1].final_score == 0.7
    assert ranked[2].name == "Bob"
    assert ranked[2].final_score == -4.2
