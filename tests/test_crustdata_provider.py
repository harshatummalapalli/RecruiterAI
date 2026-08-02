import json

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
        assert request.headers["x-api-version"] == "2025-11-01"
        payload = json.loads(request.read().decode("utf-8"))
        if payload.get("search", {}).get("query") == "Machine Learning Engineer Python PyTorch":
            request_names.append("Primary")
        elif payload.get("search", {}).get("query") == "ML Engineer Python PyTorch":
            request_names.append("Alternate 1")
        assert payload["filters"]
        assert payload["limit"] == 10
        assert payload["fields"] == ["crustdata_person_id", "basic_profile", "experience", "social_handles"]
        return httpx.Response(
            200,
            json={
                "profiles": [
                    {
                        "crustdata_person_id": "crust-001",
                        "score": 0.91,
                        "basic_profile": {
                            "name": "Alicia Chen",
                            "headline": "Senior Machine Learning Engineer",
                            "location": {"raw": "New York, US"},
                        },
                        "experience": {
                            "employment_details": {
                                "current": [{"title": "Senior Machine Learning Engineer", "name": "OpenAI"}]
                            }
                        },
                        "social_handles": {
                            "professional_network_identifier": {"profile_url": "https://example.com/candidates/alicia-chen"}
                        },
                    }
                ],
                "next_cursor": None,
                "total_count": 1,
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
    assert candidates[0].provider_score == 0.91


def test_build_payload_maps_richer_search_query_to_crustdata_filters() -> None:
    provider = CrustDataProvider()
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="Primary",
                include_titles=["Software Engineer"],
                exclude_titles=["Manager", "Director"],
                required_skills=["Python"],
                preferred_skills=["AWS"],
                countries=["US"],
                cities=["New York"],
                work_mode="hybrid",
                minimum_years=5,
                maximum_years=10,
                preferred_companies=["OpenAI"],
                exclude_current_companies=["Google"],
                preferred_company_types=["startup"],
            )
        ]
    )

    payload = provider._build_payload(plan.searches[0])
    filters = payload["filters"]

    assert filters["op"] == "and"
    assert any(
        condition == {"field": "experience.employment_details.current.title", "type": "(.)", "value": "Software Engineer"}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "experience.employment_details.title", "type": "not_in", "value": ["Manager", "Director"]}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "years_of_experience_raw", "type": "=>", "value": 5}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "years_of_experience_raw", "type": "=<", "value": 10}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "experience.employment_details.company_name", "type": "in", "value": ["OpenAI"]}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "experience.employment_details.current.company_name", "type": "not_in", "value": ["Google"]}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "experience.employment_details.current.company_type", "type": "in", "value": ["startup"]}
        for condition in filters["conditions"]
    )
    assert payload["search"]["query"] == "Software Engineer Python AWS"


def test_search_with_options_paginates_and_uses_page_size(monkeypatch) -> None:
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode("utf-8"))
        seen_payloads.append(payload)
        if len(seen_payloads) == 1:
            return httpx.Response(200, json={"profiles": [{"crustdata_person_id": "crust-001"}], "next_cursor": "cursor-2"})
        return httpx.Response(200, json={"profiles": [{"crustdata_person_id": "crust-002"}]})

    provider = CrustDataProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    plan = SearchPlan(searches=[SearchQuery(query_name="Primary", include_titles=["Software Engineer"], required_skills=["Python"])])

    candidates = provider.search_with_options(plan, options={"page_size": 7, "max_pages": 2})

    assert len(candidates) == 2
    assert [payload["limit"] for payload in seen_payloads] == [7, 7]
    assert seen_payloads[1]["cursor"] == "cursor-2"
    assert [candidate.candidate_id for candidate in candidates] == ["crust-001", "crust-002"]


def test_search_with_options_retries_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    sleep_calls: list[float] = []
    monkeypatch.setattr("backend.providers.crustdata.time.sleep", lambda seconds: sleep_calls.append(seconds))

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"profiles": [{"crustdata_person_id": "crust-003"}]})

    provider = CrustDataProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    plan = SearchPlan(searches=[SearchQuery(query_name="Primary", include_titles=["Software Engineer"])])

    candidates = provider.search_with_options(plan, options={"max_retries": 1, "retry_backoff_base": 0.25})

    assert len(candidates) == 1
    assert sleep_calls == [0.25]


def test_build_payload_includes_autocomplete_when_requested() -> None:
    provider = CrustDataProvider()
    payload = provider._build_payload(SearchQuery(include_titles=["Software Engineer"], required_skills=["Python"]), options={"autocomplete": True})

    assert payload["autocomplete"] is True
    assert payload["search"]["query"] == "Software Engineer Python"


def test_candidate_normalizes_missing_raw_data_to_empty_dict() -> None:
    candidate = Candidate(raw_data=None)

    assert candidate.raw_data == {}
