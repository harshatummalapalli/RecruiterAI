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


def test_rank_gives_a_convergence_bonus_to_candidates_found_by_multiple_queries() -> None:
    # A candidate independently surfaced by both the natural-language and
    # title-expansion queries is stronger evidence than either alone.
    intent = SearchIntent()

    single_source = Candidate(name="Single", provider_score=1.0, raw_data={"matched_queries": ["natural_language"]})
    both_sources = Candidate(name="Both", provider_score=1.0, raw_data={"matched_queries": ["natural_language", "title_expansion"]})

    ranked = CandidateRanker().rank([single_source, both_sources], intent)

    both = next(c for c in ranked if c.name == "Both")
    single = next(c for c in ranked if c.name == "Single")
    assert both.final_score > single.final_score


def test_rank_never_scores_skills_when_crustdata_did_not_return_them() -> None:
    # This account's CrustData plan never returns a "skills" field on
    # person_search — raw_data has no "skills" key in practice. Required
    # skills must not silently score as matched or missing based on
    # something that was never actually evidence.
    intent = SearchIntent(skills=Skills(required_skills=["Python"], preferred_skills=["Go"]))
    candidate = Candidate(name="NoSkillData", provider_score=1.0, raw_data={})

    ranked = CandidateRanker().rank([candidate], intent)

    # No skill weight was added or subtracted — the score is exactly the
    # provider score plus/minus only the signals that actually had evidence.
    assert ranked[0].final_score == 1.0
