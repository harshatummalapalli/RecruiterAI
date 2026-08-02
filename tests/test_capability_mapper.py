from backend.models.provider_capabilities import ProviderCapabilities
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.services.capability_mapper import CapabilityMapper


def test_mapper_drops_unsupported_filters_and_returns_warnings() -> None:
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="Primary",
                include_titles=["Machine Learning Engineer"],
                exclude_titles=["Manager"],
                required_skills=["Python"],
                preferred_skills=["PyTorch"],
                countries=["US"],
                cities=["New York"],
                work_mode="hybrid",
                minimum_years=5,
                maximum_years=10,
                preferred_companies=["OpenAI"],
                exclude_current_companies=["Big Tech"],
                preferred_company_types=["startup"],
                must_have=["AWS"],
                nice_to_have=["LLM"],
                bonus=["MLOps"],
            )
        ],
        strategy="multi_query",
    )

    capabilities = ProviderCapabilities(
        supported_filters=[
            "include_titles",
            "required_skills",
            "countries",
            "preferred_companies",
        ]
    )

    mapped_plan, warnings = CapabilityMapper().map(plan, capabilities)

    assert len(mapped_plan.searches) == 1
    assert mapped_plan.searches[0].include_titles == ["Machine Learning Engineer"]
    assert mapped_plan.searches[0].required_skills == ["Python"]
    assert mapped_plan.searches[0].countries == ["US"]
    assert mapped_plan.searches[0].preferred_companies == ["OpenAI"]

    assert mapped_plan.searches[0].exclude_titles == []
    assert mapped_plan.searches[0].preferred_skills == []
    assert mapped_plan.searches[0].cities == []
    assert mapped_plan.searches[0].work_mode is None
    assert mapped_plan.searches[0].minimum_years is None
    assert mapped_plan.searches[0].maximum_years is None
    assert mapped_plan.searches[0].exclude_current_companies == []
    assert mapped_plan.searches[0].preferred_company_types == []
    assert mapped_plan.searches[0].must_have == []
    assert mapped_plan.searches[0].nice_to_have == []
    assert mapped_plan.searches[0].bonus == []

    assert any("exclude_titles" in warning for warning in warnings)
    assert any("preferred_skills" in warning for warning in warnings)
    assert any("work_mode" in warning for warning in warnings)
    assert any("Primary" in warning for warning in warnings)


def test_mapper_leaves_supported_filters_unchanged() -> None:
    plan = SearchPlan(searches=[SearchQuery(query_name="Secondary", include_titles=["Data Scientist"])] )
    capabilities = ProviderCapabilities(supported_filters=["include_titles"])

    mapped_plan, warnings = CapabilityMapper().map(plan, capabilities)

    assert mapped_plan.searches[0].include_titles == ["Data Scientist"]
    assert warnings == []
