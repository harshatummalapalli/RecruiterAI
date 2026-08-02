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
from backend.services.search_planner import SearchPlanner


def test_build_creates_multiple_deterministic_queries():
    intent = SearchIntent(
        role=Role(title="Machine Learning Engineer", seniority="senior", employment_type="full_time"),
        location=Location(countries=["US"], cities=["New York"], work_mode="hybrid"),
        experience=Experience(minimum_years=5, maximum_years=10),
        titles=Titles(include_titles=["ML Engineer"], exclude_titles=["Manager"]),
        skills=Skills(required_skills=["Python", "PyTorch"], preferred_skills=["LLM"], required_weight=0.9, preferred_weight=0.1),
        previous_background=PreviousBackground(preferred_technologies=["LangChain"], preferred_companies=["OpenAI"]),
        ai_focus=AIFocus(llm=True, rag=True, agentic_ai=False, mcp=True, semantic_kernel=False),
        company_preferences=CompanyPreferences(exclude_current_companies=["Big Tech"], preferred_company_types=["startup"]),
        ranking=Ranking(must_have=["Python"], nice_to_have=["LLM"], bonus=["MLOps"]),
        confidence_score=88,
    )

    plan = SearchPlanner().build(intent)

    assert len(plan.searches) == 2
    assert [query.query_name for query in plan.searches] == ["Primary", "Alternate 1"]
    assert plan.searches[0].include_titles == ["Machine Learning Engineer"]
    assert plan.searches[1].include_titles == ["ML Engineer"]
    assert plan.searches[0].exclude_titles == ["Manager"]
    assert plan.searches[0].required_skills == ["Python", "PyTorch"]
    assert plan.searches[0].preferred_skills == ["LLM"]
    assert plan.searches[0].countries == ["US"]
    assert plan.searches[0].cities == ["New York"]
    assert plan.searches[0].work_mode == "hybrid"
    assert plan.searches[0].minimum_years == 5
    assert plan.searches[0].maximum_years == 10
    assert plan.searches[0].preferred_companies == ["OpenAI"]
    assert plan.searches[0].exclude_current_companies == ["Big Tech"]
    assert plan.searches[0].preferred_company_types == ["startup"]
    assert plan.searches[0].must_have == ["Python"]
    assert plan.searches[0].nice_to_have == ["LLM"]
    assert plan.searches[0].bonus == ["MLOps"]
    assert plan.strategy == "multi_query"
    assert plan.reasoning == "Deterministic mapping from SearchIntent to multiple title-based SearchQuery variants"
    assert plan.confidence_score == 88
