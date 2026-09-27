from backend.models.search_intent import (
    AIFocus,
    CompanyPreferences,
    Experience,
    Location,
    PreviousBackground,
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


def test_confirmed_core_supporting_differentiator_signals_survive_the_fallback_when_no_sentence_is_given():
    # The real shape of the Senior AI Software Engineer (.NET + AI) confirmation this bugfix was diagnosed from:
    # candidate_identity is generic ("Senior Backend Engineer"), skills.required/preferred are empty (the
    # confirmed-intake path never populates them — search_translator.to_search_intent doesn't set SearchIntent.skills
    # at all), and the only place the real requirements live is core/supporting/differentiator_signals. This is
    # exactly the SearchIntent api._gate_search_request hands to the planner once
    # RECRUITERAI_SEND_CONFIRMED_SEARCH_SENTENCE=false has blanked the model's own sentence.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="senior"),
        location=Location(countries=["India"], work_mode="remote"),
        experience=Experience(minimum_years=5),
        core_signals=[
            "5+ years of professional experience",
            "Proficiency in C# .NET",
            "Experience in AI Engineering",
            "Experience deploying AI into production",
        ],
        supporting_signals=["Agentic AI frameworks"],
        differentiator_signals=["LangChain or LangGraph"],
        natural_language_search_query=None,
    )

    plan = SearchPlanner().build(intent)
    query_text = plan.searches[0].natural_language_query

    for requirement in ["C# .NET", "AI Engineering", "deploying AI into production", "Agentic AI frameworks", "LangChain or LangGraph"]:
        assert requirement in query_text, query_text

    # Not title/seniority-only: the pre-fix behavior for this exact shape was "senior Senior Backend Engineer" alone.
    assert query_text != "senior Senior Backend Engineer"
    assert len(query_text) > len("senior Senior Backend Engineer") + 40


def test_required_and_preferred_skills_still_reach_the_fallback_for_the_legacy_non_intake_shape():
    # The older /parse-jd path populates skills.required/preferred but never core/supporting/differentiator_signals —
    # the combined fallback must keep serving that shape exactly as before.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="Senior"),
        skills=Skills(required_skills=["Python"], preferred_skills=["Distributed Systems"]),
    )

    plan = SearchPlanner().build(intent)
    query_text = plan.searches[0].natural_language_query

    assert "Senior" in query_text
    assert "Python" in query_text
    assert "Distributed Systems" in query_text
    assert "PySpark" not in query_text
