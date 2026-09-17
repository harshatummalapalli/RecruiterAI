from backend.models.search_intent import (
    AIFocus,
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
from backend.services.search_planner import EXECUTIVE_TITLE_EXCLUSIONS, SearchPlanner


def test_build_creates_primary_natural_language_and_title_expansion_queries():
    intent = SearchIntent(
        role=Role(title="Machine Learning Engineer", seniority="senior", employment_type="full_time"),
        location=Location(countries=["US"], states=["New York"], cities=["New York"], work_mode="hybrid"),
        experience=Experience(minimum_years=5, maximum_years=10),
        titles=Titles(include_titles=["ML Engineer"], exclude_titles=["Manager"]),
        skills=Skills(required_skills=["Python", "PyTorch"], preferred_skills=["LLM"], required_weight=0.9, preferred_weight=0.1),
        previous_background=PreviousBackground(preferred_technologies=["LangChain"], preferred_companies=["OpenAI"]),
        ai_focus=AIFocus(llm=True, rag=True, agentic_ai=False, mcp=True, semantic_kernel=False),
        company_preferences=CompanyPreferences(exclude_current_companies=["Big Tech"], preferred_company_types=["startup"]),
        ranking=Ranking(must_have=["Python"], nice_to_have=["LLM"], bonus=["MLOps"]),
        confidence_score=88,
        natural_language_search_query="Senior ML engineer with strong Python and PyTorch experience.",
    )

    plan = SearchPlanner().build(intent)

    assert len(plan.searches) == 2
    assert [query.query_name for query in plan.searches] == ["natural_language", "title_expansion"]

    primary, expansion = plan.searches

    # Primary: natural-language driven, NEVER a title hard filter.
    assert primary.natural_language_query == "Senior ML engineer with strong Python and PyTorch experience."
    assert primary.include_titles == []
    assert primary.required_skills == ["Python", "PyTorch"]
    assert primary.preferred_skills == ["LLM"]

    # Title expansion: conservative title family, structural (list, not a
    # pipe string), no natural-language query of its own.
    assert expansion.include_titles == ["Machine Learning Engineer", "ML Engineer"]
    assert expansion.natural_language_query is None

    # Shared hard filters/exclusions apply to both queries.
    for query in plan.searches:
        assert query.countries == ["US"]
        assert query.states == ["New York"]
        assert query.cities == ["New York"]
        assert query.minimum_years == 5
        assert query.maximum_years == 10
        assert query.preferred_companies == ["OpenAI"]
        assert query.exclude_current_companies == ["Big Tech"]
        assert query.preferred_company_types == ["startup"]
        assert query.must_have == ["Python"]
        assert query.nice_to_have == ["LLM"]
        assert query.bonus == ["MLOps"]
        # Recruiter-specified exclusion plus the standing executive policy.
        assert "Manager" in query.exclude_titles
        for excluded in EXECUTIVE_TITLE_EXCLUSIONS:
            assert excluded in query.exclude_titles

    assert plan.confidence_score == 88


def test_build_normalizes_maximum_years_zero_to_no_maximum():
    # The JD parser's "not specified" placeholder for maximum_years is 0.
    # SearchQuery must normalize this to None so it never reaches the
    # provider as a real (and self-contradicting) upper bound.
    intent = SearchIntent(
        role=Role(title="Backend Engineer"),
        location=Location(countries=["United States"], cities=["New York"], work_mode="hybrid"),
        experience=Experience(minimum_years=5, maximum_years=0),
    )

    plan = SearchPlanner().build(intent)

    assert plan.searches[0].minimum_years == 5
    assert plan.searches[0].maximum_years is None


def test_build_falls_back_to_deterministic_natural_language_query_when_llm_omits_it():
    # No natural_language_search_query set (e.g. a non-LLM caller) — the
    # planner must still build a usable query from only what's on the
    # intent, never inventing a requirement that wasn't provided.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="Senior"),
        skills=Skills(required_skills=["Python"], preferred_skills=["Distributed Systems"]),
    )

    plan = SearchPlanner().build(intent)

    query_text = plan.searches[0].natural_language_query
    assert "Senior" in query_text
    assert "Python" in query_text
    assert "Distributed Systems" in query_text
    # Never invents a technology that wasn't on the intent.
    assert "PySpark" not in query_text
    assert "Kubernetes" not in query_text


def test_executive_exclusions_never_target_legitimate_senior_ic_titles():
    # "Principal Software Engineer" containing the ambiguous word "Principal"
    # must never become a rejection — only real leadership/executive titles
    # are excluded.
    protected_titles = [
        "Staff Engineer",
        "Principal Engineer",
        "Principal Software Engineer",
        "Principal Architect",
        "Lead Engineer",
        "Engineering Manager",
    ]
    for title in protected_titles:
        assert title not in EXECUTIVE_TITLE_EXCLUSIONS
        assert not any(title == excluded for excluded in EXECUTIVE_TITLE_EXCLUSIONS)


def test_build_omits_title_expansion_query_when_no_titles_available():
    intent = SearchIntent(skills=Skills(required_skills=["Python"]))

    plan = SearchPlanner().build(intent)

    assert len(plan.searches) == 1
    assert plan.searches[0].query_name == "natural_language"
