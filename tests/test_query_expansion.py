from backend.models.search_plan import SearchPlan, SearchQuery
from backend.services.query_expansion import QueryExpansionService


def test_expand_query_uses_knowledge_files_and_deduplicates_values() -> None:
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="Primary",
                include_titles=["Machine Learning Engineer"],
                exclude_titles=["Software Engineer"],
                required_skills=["Python", "PyTorch"],
                preferred_skills=["LLM"],
                must_have=["AWS"],
                nice_to_have=["MLOps"],
                bonus=["Python"],
                work_mode="senior",
            )
        ],
        strategy="multi_query",
    )

    expanded_plan = QueryExpansionService().expand(plan)

    query = expanded_plan.searches[0]

    assert query.include_titles == ["Machine Learning Engineer", "ML Engineer", "Applied Scientist"]
    assert query.exclude_titles == ["Software Engineer", "Engineer", "Application Developer"]
    assert query.required_skills == ["Python", "PyTorch", "Python 3", "PySpark", "Torch", "Deep Learning"]
    assert query.preferred_skills == ["LLM", "Large Language Models"]
    assert query.must_have == ["AWS", "Amazon Web Services"]
    assert query.nice_to_have == ["MLOps", "Machine Learning Operations"]
    assert query.bonus == ["Python", "Python 3", "PySpark"]
    assert query.work_mode == "lead"


def test_expand_query_keeps_existing_plan_shape() -> None:
    plan = SearchPlan(searches=[SearchQuery(query_name="Secondary", include_titles=["Data Scientist"])])

    expanded_plan = QueryExpansionService().expand(plan)

    assert expanded_plan.strategy is None
    assert len(expanded_plan.searches) == 1
    assert expanded_plan.searches[0].query_name == "Secondary"
    assert expanded_plan.searches[0].include_titles == ["Data Scientist", "Research Scientist", "Analytics Scientist"]
