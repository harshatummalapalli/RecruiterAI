import httpx

from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.crustdata import CrustDataProvider


def test_search_returns_candidate_objects_from_search_plan(monkeypatch) -> None:
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="Primary",
                include_titles=["Machine Learning Engineer"],
                required_skills=["Python", "PyTorch"],
                countries=["US"],
                cities=["New York"],
                minimum_years=5,
            ),
            SearchQuery(
                query_name="Alternate 1",
                include_titles=["ML Engineer"],
                required_skills=["Python", "PyTorch"],
                countries=["US"],
                cities=["New York"],
                minimum_years=5,
            ),
        ],
        strategy="multi_query",
        reasoning="Deterministic mapping from SearchIntent to multiple SearchQuery variants",
        confidence_score=88,
    )

    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")

    request_names: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        payload = request.read().decode("utf-8")
        if "Primary" in payload:
            request_names.append("Primary")
        elif "Alternate 1" in payload:
            request_names.append("Alternate 1")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "crust-001",
                        "name": "Alicia Chen",
                        "title": "Senior Machine Learning Engineer",
                        "company": "OpenAI",
                        "location": "New York, US",
                        "score": 0.97,
                        "profile_url": "https://example.com/candidates/alicia-chen",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CrustDataProvider(client=client)
    candidates = provider.search(plan)

    assert isinstance(candidates, list)
    assert len(candidates) == 2
    assert request_names == ["Primary", "Alternate 1"]
    assert all(isinstance(candidate, Candidate) for candidate in candidates)
    assert candidates[0].name == "Alicia Chen"
    assert candidates[0].title == "Senior Machine Learning Engineer"
    assert candidates[0].company == "OpenAI"
    assert candidates[0].location == "New York, US"
    assert candidates[0].provider_score == 0.97
