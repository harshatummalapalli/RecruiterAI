import json

import httpx

from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.crustdata import CrustDataProvider


def test_search_returns_candidate_objects_from_search_plan(monkeypatch) -> None:
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="natural_language",
                natural_language_query="Senior ML engineer with strong Python and PyTorch experience.",
                countries=["US"],
                cities=["New York"],
                minimum_years=5,
            ),
            SearchQuery(
                query_name="title_expansion",
                include_titles=["Machine Learning Engineer", "ML Engineer"],
                countries=["US"],
                cities=["New York"],
                minimum_years=5,
            ),
        ],
        strategy="primary_natural_language_plus_title_expansion",
        confidence_score=88,
    )

    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")

    request_names: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-api-version"] == "2025-11-01"
        payload = json.loads(request.read().decode("utf-8"))
        if payload.get("search", {}).get("query") == "Senior ML engineer with strong Python and PyTorch experience.":
            request_names.append("natural_language")
        elif "search" not in payload:
            request_names.append("title_expansion")
        assert payload["filters"]
        assert payload["limit"] == 25
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
    assert request_names == ["natural_language", "title_expansion"]
    assert all(isinstance(candidate, Candidate) for candidate in candidates)
    assert candidates[0].name == "Alicia Chen"
    assert candidates[0].title == "Senior Machine Learning Engineer"
    assert candidates[0].company == "OpenAI"
    assert candidates[0].location == "New York, US"
    assert candidates[0].provider_score == 0.91
    # Each candidate is tagged with the query that found it (source
    # tracking for merge-time convergence detection).
    assert candidates[0].raw_data["matched_queries"] == ["natural_language"]
    assert candidates[1].raw_data["matched_queries"] == ["title_expansion"]


def test_build_payload_single_title_uses_plain_fuzzy_match() -> None:
    provider = CrustDataProvider()
    payload = provider._build_payload(SearchQuery(include_titles=["Software Engineer"]))
    filters = payload["filters"]

    assert {"field": "experience.employment_details.current.title", "type": "(.)", "value": "Software Engineer"} in filters["conditions"]


def test_build_payload_multi_title_uses_structural_or_not_pipe_string() -> None:
    # Regression test: joining titles into "A|B|C" with the "(.)" fuzzy
    # operator was confirmed live to fuzzy-match the literal joined string
    # (returning near-zero results), not to behave as OR.
    provider = CrustDataProvider()
    payload = provider._build_payload(
        SearchQuery(include_titles=["Senior Backend Engineer", "Senior Software Engineer", "Backend Developer"])
    )
    filters = payload["filters"]

    title_or = next(c for c in filters["conditions"] if c.get("op") == "or")
    assert title_or == {
        "op": "or",
        "conditions": [
            {"field": "experience.employment_details.current.title", "type": "(.)", "value": "Senior Backend Engineer"},
            {"field": "experience.employment_details.current.title", "type": "(.)", "value": "Senior Software Engineer"},
            {"field": "experience.employment_details.current.title", "type": "(.)", "value": "Backend Developer"},
        ],
    }
    # No condition anywhere joins values with a pipe character.
    assert not any("|" in str(condition.get("value", "")) for condition in filters["conditions"])


def test_build_payload_maps_richer_search_query_to_crustdata_filters() -> None:
    provider = CrustDataProvider()
    plan = SearchPlan(
        searches=[
            SearchQuery(
                query_name="Primary",
                include_titles=["Software Engineer"],
                exclude_titles=["Manager", "Director"],
                natural_language_query="Backend engineer with Python experience.",
                countries=["US"],
                states=["New York"],
                cities=["New York"],
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
    # Exclusions are fuzzy-NOT ("(!)") on CURRENT title only — never
    # `not_in`/`!=` (exact-match only, confirmed live to be unsafe for real
    # compound executive titles like "Co-Founder & CTO") and never the
    # unscoped `experience.employment_details.title` field, which would also
    # match PAST roles.
    assert {"field": "experience.employment_details.current.title", "type": "(!)", "value": "Manager"} in filters["conditions"]
    assert {"field": "experience.employment_details.current.title", "type": "(!)", "value": "Director"} in filters["conditions"]
    assert not any(condition.get("type") in ("not_in", "!=") and "title" in str(condition.get("field", "")) for condition in filters["conditions"])
    assert any(
        condition == {"field": "basic_profile.location.state", "type": "in", "value": ["New York"]}
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
    assert payload["search"]["query"] == "Backend engineer with Python experience."
    assert payload["search"]["mode"] == "hybrid"


def test_build_payload_title_exclusion_only_scopes_current_title_not_past() -> None:
    # A candidate whose CURRENT title is "Principal Software Engineer" but
    # who was a Founder/CTO in the past must remain eligible — the exclusion
    # is built only against experience.employment_details.current.title,
    # never the unscoped/past title field, so their history can't disqualify
    # them.
    provider = CrustDataProvider()
    payload = provider._build_payload(SearchQuery(exclude_titles=["Founder", "CTO"]))
    filters = payload["filters"]

    for condition in filters["conditions"]:
        if condition.get("type") == "(!)":
            assert condition["field"] == "experience.employment_details.current.title"
    assert not any(condition.get("field") == "experience.employment_details.past.title" for condition in filters["conditions"])
    assert not any(condition.get("field") == "experience.employment_details.title" for condition in filters["conditions"])


def test_build_payload_geo_distance_radius() -> None:
    provider = CrustDataProvider()
    payload = provider._build_payload(
        SearchQuery(radius_place="New York, NY", radius_miles=25, radius_unit="mi")
    )
    filters = payload["filters"]

    assert {
        "field": "basic_profile.location",
        "type": "geo_distance",
        "value": {"location": "New York, NY", "distance": 25, "unit": "mi"},
    } in filters["conditions"]


def test_build_payload_never_sends_zip_code_filter() -> None:
    # CrustData has no zip_code filter field at all (confirmed live: a 400
    # "Unknown filter column" rejection). SearchQuery has no zip filter
    # field for the provider to accidentally send — radius_place carries a
    # ZIP-shaped string only as free-form geo_distance location text.
    provider = CrustDataProvider()
    payload = provider._build_payload(SearchQuery(radius_place="10001", radius_miles=10))
    filters = payload["filters"]

    assert not any("zip" in str(condition.get("field", "")).lower() for condition in filters["conditions"])
    geo_condition = next(c for c in filters["conditions"] if c.get("type") == "geo_distance")
    assert geo_condition["value"]["location"] == "10001"


def test_build_payload_employment_type_only_forwards_known_values() -> None:
    provider = CrustDataProvider()

    valid_payload = provider._build_payload(SearchQuery(employment_type="Full-time"))
    assert any(
        condition == {"field": "experience.employment_details.current.employment_type", "type": "in", "value": ["Full-time"]}
        for condition in valid_payload["filters"]["conditions"]
    )

    invalid_payload = provider._build_payload(SearchQuery(employment_type="Freelance", minimum_years=5))
    assert not any("employment_type" in str(condition.get("field", "")) for condition in invalid_payload["filters"]["conditions"])


def test_build_payload_treats_maximum_years_zero_as_no_maximum() -> None:
    # maximum_years=0 is the JD parser's "not specified" placeholder, not a
    # real upper bound of zero years. It must never combine with
    # minimum_years=5 into a self-contradicting AND filter that guarantees
    # zero results.
    provider = CrustDataProvider()
    payload = provider._build_payload(
        SearchQuery(include_titles=["Software Engineer"], minimum_years=5, maximum_years=0)
    )
    filters = payload["filters"]

    assert any(
        condition == {"field": "years_of_experience_raw", "type": "=>", "value": 5}
        for condition in filters["conditions"]
    )
    assert not any(condition["field"] == "years_of_experience_raw" and condition["type"] == "=<" for condition in filters["conditions"])


def test_build_payload_keeps_explicit_maximum_years() -> None:
    provider = CrustDataProvider()
    payload = provider._build_payload(
        SearchQuery(include_titles=["Software Engineer"], minimum_years=5, maximum_years=8)
    )
    filters = payload["filters"]

    assert any(
        condition == {"field": "years_of_experience_raw", "type": "=>", "value": 5}
        for condition in filters["conditions"]
    )
    assert any(
        condition == {"field": "years_of_experience_raw", "type": "=<", "value": 8}
        for condition in filters["conditions"]
    )


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
    plan = SearchPlan(searches=[SearchQuery(query_name="Primary", include_titles=["Software Engineer"])])

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


def test_build_payload_never_forwards_autocomplete_to_crustdata() -> None:
    # CrustData's /person/search API rejects an "autocomplete" field outright
    # (400 invalid_request, extra_forbidden) — the generic `autocomplete`
    # request option must never reach the actual CrustData payload.
    provider = CrustDataProvider()
    payload = provider._build_payload(
        SearchQuery(include_titles=["Software Engineer"], natural_language_query="Backend engineer."),
        options={"autocomplete": True},
    )

    assert "autocomplete" not in payload
    assert payload["search"]["query"] == "Backend engineer."


def test_build_payload_no_search_block_without_natural_language_query() -> None:
    # A query with only structural filters (e.g. the title-expansion query)
    # must not get a fabricated "search" block from title/skill keywords —
    # that was the old behavior this replaces.
    provider = CrustDataProvider()
    payload = provider._build_payload(SearchQuery(include_titles=["Software Engineer"], required_skills=["Python"]))

    assert "search" not in payload


def test_candidate_normalizes_missing_raw_data_to_empty_dict() -> None:
    candidate = Candidate(raw_data=None)

    assert candidate.raw_data == {}
