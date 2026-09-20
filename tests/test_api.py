import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import backend.api as api_module
from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.errors import ConfigurationError, ProviderError
from backend.models.candidate import Candidate
from backend.models.search_intent import Role, SearchIntent
from backend.providers.base import BaseLLMProvider, BaseProvider
from backend.services.candidate_ranker import CandidateRanker
from backend.services.capability_mapper import CapabilityMapper
from backend.services.candidate_merger import CandidateMerger
from backend.services.jd_parser import JDParser
from backend.services.match_explainer import MatchExplainer
from backend.services.query_expansion import QueryExpansionService
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_planner import SearchPlanner
from backend.exporters.excel import ExcelExporter
from backend.models.provider_capabilities import ProviderCapabilities
from backend.providers.registry import ProviderRegistry


def _login(client: TestClient) -> None:
    """Give a TestClient a valid session cookie directly, without going through
    Google — most tests only care that the pipeline runs once past the
    authentication gate, not that Google verification itself works (that's
    covered by the dedicated auth tests below). Requires SESSION_SECRET_KEY
    to be set, which the autouse fixture in conftest.py handles for every test."""
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value())


class FakeParser(BaseLLMProvider):
    def parse_job_description(self, job_description: str) -> SearchIntent:
        from backend.models.search_intent import (
            AIFocus,
            CompanyPreferences,
            Experience,
            Location,
            PreviousBackground,
            Ranking,
            Role,
            Skills,
            Titles,
        )

        return SearchIntent(
            role=Role(title="Software Engineer"),
            location=Location(countries=["US"], cities=["Hyderabad"]),
            experience=Experience(minimum_years=3),
            titles=Titles(include_titles=["Software Engineer"]),
            skills=Skills(required_skills=["Python"], preferred_skills=["FastAPI"]),
            previous_background=PreviousBackground(preferred_companies=["OpenAI"]),
            ai_focus=AIFocus(),
            company_preferences=CompanyPreferences(),
            ranking=Ranking(),
        )


class FakeProvider(BaseProvider):
    def search(self, plan):
        return [
            Candidate(
                name="Alice",
                title="Software Engineer",
                company="OpenAI",
                location="US",
                provider_score=0.95,
                final_score=9.5,
                raw_data={"skills": ["Python", "FastAPI"], "years_experience": 5},
            )
        ]


class OptionAwareProvider(BaseProvider):
    def __init__(self) -> None:
        self.seen_options = []

    def search(self, plan):
        return []

    def search_with_options(self, plan, options=None):
        self.seen_options.append(options or {})
        return [
            Candidate(
                name="Bob",
                title="Backend Engineer",
                company="Acme",
                location="US",
                provider_score=0.88,
                final_score=8.8,
                raw_data={"skills": ["Python"], "years_experience": 6},
            )
        ]

class PlanCapturingProvider(BaseProvider):
    def __init__(self) -> None:
        self.seen_plans = []
        self.seen_options = []

    def search(self, plan):
        return self.search_with_options(plan)

    def search_with_options(self, plan, options=None):
        self.seen_plans.append(plan)
        self.seen_options.append(options or {})
        return [
            Candidate(
                name="Priya Rao",
                title="Software Engineer",
                company="Acme India",
                location="Hyderabad, India",
                provider_score=0.9,
                final_score=9.0,
                raw_data={"skills": ["Python"], "years_experience": 4},
            )
        ]


class FailingProvider(BaseProvider):
    def search(self, plan):
        raise ProviderError("Provider response failed")


class FailingParser(BaseLLMProvider):
    def parse_job_description(self, job_description: str) -> SearchIntent:
        raise ConfigurationError("OPENAI_API_KEY is missing")


def build_test_app(search_store=None) -> TestClient:
    ProviderRegistry._providers.clear()
    ProviderRegistry.register("mock", FakeProvider())

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=search_store,
    )
    return TestClient(app)


def test_health_endpoint() -> None:
    client = build_test_app()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_providers_endpoint_reports_configuration_status() -> None:
    client = build_test_app()
    _login(client)
    response = client.get("/providers")

    assert response.status_code == 200
    assert response.json()["providers"] == ["configured"]


def test_parse_jd_endpoint_returns_search_intent() -> None:
    client = build_test_app()
    _login(client)
    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})

    assert response.status_code == 200
    assert response.json()["role"]["title"] == "Software Engineer"
    assert response.json()["skills"]["required_skills"] == ["Python"]


def test_create_app_uses_openai_provider_by_default() -> None:
    class StubOpenAIProvider(BaseLLMProvider):
        def parse_job_description(self, job_description: str) -> SearchIntent:
            return SearchIntent(role=Role(title="Senior AI Engineer"))

    original_provider = api_module.OpenAIProvider
    api_module.OpenAIProvider = StubOpenAIProvider
    try:
        app = create_app()
        client = TestClient(app)
        _login(client)
        response = client.post(
            "/parse-jd",
            json={"jd_text": "We are looking for a Senior AI Engineer with Python, FastAPI, Azure, OpenAI, RAG and Kubernetes."},
        )
    finally:
        api_module.OpenAIProvider = original_provider

    assert response.status_code == 200
    assert response.json()["role"]["title"] == "Senior AI Engineer"


def test_search_endpoint_returns_structured_result() -> None:
    client = build_test_app()
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "platform"
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["name"] == "Alice"
    assert payload["explanations"][0]["relevance_tier"] == "direct"
    # Structured evidence (career history, education, contact, company
    # context) is index-aligned with candidates/explanations, not left for
    # the frontend to re-derive from raw_data.
    assert payload["evidence"][0]["current_company"] == "OpenAI"
    assert payload["evidence"][0]["role_alignment"]["title_relevance"] == "direct"


def test_decision_and_note_survive_a_reload_of_the_same_search(tmp_path) -> None:
    # Regression test for the "decisions/notes lost on refresh" bug: PATCH
    # /search/{id}/candidate always persisted them (search_store.py never
    # had a bug), but neither POST /search nor GET /search/{id} ever
    # returned recruiter_decisions/notes in the response body, so the
    # frontend had nothing to rehydrate its local state from on reload.
    from backend.services.search_store import SearchStore

    client = build_test_app(search_store=SearchStore(storage_dir=tmp_path))
    _login(client)

    created = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"}).json()
    search_id = created["search_id"]
    candidate_id = created["candidates"][0].get("profile_url") or created["candidates"][0]["name"]
    # Not yet decided/noted anywhere.
    assert created["recruiter_decisions"] == {}
    assert created["notes"] == {}

    patch_response = client.patch(
        f"/search/{search_id}/candidate",
        json={"candidate_id": candidate_id, "decision": "shortlist", "note": "Strong RAG background."},
    )
    assert patch_response.status_code == 200

    # Simulates a browser refresh: a fresh GET, no new search/LLM/provider call.
    reloaded = client.get(f"/search/{search_id}")
    assert reloaded.status_code == 200
    payload = reloaded.json()

    assert payload["recruiter_decisions"] == {candidate_id: "shortlist"}
    assert len(payload["notes"][candidate_id]) == 1
    assert payload["notes"][candidate_id][0]["text"] == "Strong RAG background."


def test_rerunning_the_same_search_id_carries_forward_existing_decisions(tmp_path) -> None:
    # "Run Search Again" (edit brief, re-search with the same search_id)
    # must not look like it wiped out decisions already made.
    from backend.services.search_store import SearchStore

    client = build_test_app(search_store=SearchStore(storage_dir=tmp_path))
    _login(client)

    first = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock", "search_id": "fixed-id"}).json()
    candidate_id = first["candidates"][0].get("profile_url") or first["candidates"][0]["name"]
    client.patch(f"/search/{first['search_id']}/candidate", json={"candidate_id": candidate_id, "decision": "maybe"})

    rerun = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock", "search_id": "fixed-id"}).json()

    assert rerun["search_id"] == "fixed-id"
    assert rerun["recruiter_decisions"] == {candidate_id: "maybe"}


def test_search_endpoint_returns_real_empty_state_when_provider_finds_no_candidates() -> None:
    class EmptyResultsProvider(BaseProvider):
        def search(self, plan):
            return []

    ProviderRegistry._providers.clear()
    ProviderRegistry.register("mock", EmptyResultsProvider())
    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 0
    assert payload["candidates"] == []


def test_search_endpoint_returns_recruiter_friendly_error_without_provider_configuration() -> None:
    ProviderRegistry._providers.clear()
    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 503
    assert response.json()["detail"] == "No sourcing provider is currently configured."


def test_search_endpoint_passes_provider_options() -> None:
    ProviderRegistry._providers.clear()
    provider = OptionAwareProvider()
    ProviderRegistry.register("options", provider)

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
    )
    client = TestClient(app)
    _login(client)
    response = client.post(
        "/search",
        json={
            "jd_text": "Need a Python engineer",
            "provider": "options",
            "page_size": 7,
            "max_pages": 2,
            "autocomplete": True,
        },
    )

    assert response.status_code == 200
    # OptionAwareProvider returns a single candidate, which is below the
    # discovery target pool size, so the title-expansion query also runs —
    # both calls must receive the same provider options.
    assert provider.seen_options == [{"page_size": 7, "max_pages": 2, "autocomplete": True}] * 2


def test_parse_jd_endpoint_returns_recruiter_friendly_error_for_configuration_failures() -> None:
    ProviderRegistry._providers.clear()
    app = create_app(
        jd_parser=JDParser(provider=FailingParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to prepare the search brief right now."


def test_search_endpoint_returns_recruiter_friendly_error_for_provider_failures() -> None:
    ProviderRegistry._providers.clear()
    ProviderRegistry.register("mock", FailingProvider())
    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The sourcing provider could not complete this search. Please try again."


def test_export_endpoint_returns_excel_file() -> None:
    client = build_test_app()
    _login(client)
    response = client.post("/export", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    actual_path = Path(tempfile.gettempdir()) / "recruiterai-api" / "results.xlsx"
    assert actual_path.exists()
    actual_path.unlink(missing_ok=True)


def test_search_endpoint_preserves_city_and_experience_filters_through_to_provider(tmp_path) -> None:
    # Regression test for the location pipeline bug: CapabilityMapper's
    # hardcoded supported_filters whitelist used to silently strip cities
    # (and exclude_titles/minimum_years/etc.) from every search before it
    # ever reached the provider, even though the provider genuinely
    # supports filtering on them.
    from backend.services.search_store import SearchStore

    ProviderRegistry._providers.clear()
    provider = PlanCapturingProvider()
    ProviderRegistry.register("mock", provider)

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=SearchStore(storage_dir=tmp_path),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer in Hyderabad", "provider": "mock"})

    assert response.status_code == 200
    sent_plan = provider.seen_plans[0]
    assert sent_plan.searches[0].cities == ["Hyderabad"]
    assert sent_plan.searches[0].minimum_years == 3


def test_search_endpoint_uses_provided_intent_without_reparsing_via_llm(tmp_path) -> None:
    # The recruiter's edited Search Brief must be authoritative: /search must
    # not re-parse jd_text (or a re-serialized version of it) through the LLM
    # when a structured `intent` is supplied. A parser that raises if it's
    # ever invoked proves no second LLM call happens.
    from backend.services.search_store import SearchStore

    class ExplodingParser(BaseLLMProvider):
        def parse_job_description(self, job_description: str) -> SearchIntent:
            raise AssertionError("jd_parser.parse() must not be called when request.intent is provided")

    ProviderRegistry._providers.clear()
    provider = PlanCapturingProvider()
    ProviderRegistry.register("mock", provider)

    app = create_app(
        jd_parser=JDParser(provider=ExplodingParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=SearchStore(storage_dir=tmp_path),
    )
    client = TestClient(app)
    _login(client)

    structured_intent = {
        "role": {"title": "Principal Distributed Systems Engineer"},
        "location": {"countries": ["United States"], "cities": ["New York"], "work_mode": "hybrid"},
        "experience": {"minimum_years": 5, "maximum_years": None},
        "titles": {"include_titles": [], "exclude_titles": []},
        "skills": {"required_skills": ["Python"], "preferred_skills": []},
        "previous_background": {"preferred_companies": []},
        "ai_focus": {},
        "company_preferences": {},
        "ranking": {},
    }

    response = client.post(
        "/search",
        json={
            "jd_text": "this prose must be ignored for parsing purposes",
            "intent": structured_intent,
            "provider": "mock",
        },
    )

    assert response.status_code == 200
    # seen_plans[0] is the primary natural-language sub-plan (no title
    # filter by design); seen_plans[1] is the title-expansion sub-plan,
    # which is where the recruiter-provided title actually lands.
    primary_plan = provider.seen_plans[0]
    assert primary_plan.searches[0].countries == ["United States"]
    assert primary_plan.searches[0].cities == ["New York"]
    assert primary_plan.searches[0].minimum_years == 5
    assert primary_plan.searches[0].maximum_years is None

    expansion_plan = provider.seen_plans[1]
    assert expansion_plan.searches[0].include_titles == ["Principal Distributed Systems Engineer"]


def test_search_endpoint_location_override_from_search_brief_is_authoritative(tmp_path) -> None:
    # The recruiter's already-resolved Search Brief location must win over
    # whatever the JD-text re-parse guesses — including replacing a city
    # the parser found with the exact one the recruiter locked in, and
    # carrying zip/radius through even though the parser has no concept of them.
    from backend.services.search_store import SearchStore

    ProviderRegistry._providers.clear()
    provider = PlanCapturingProvider()
    ProviderRegistry.register("mock", provider)

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=SearchStore(storage_dir=tmp_path),
    )
    client = TestClient(app)
    _login(client)
    response = client.post(
        "/search",
        json={
            "jd_text": "Need a Python engineer in Hyderabad",
            "provider": "mock",
            "location": {
                "search_geography": "radius",
                "countries": ["India"],
                "cities": ["Gachibowli"],
                "zip_codes": ["500032"],
                "radius_miles": 15,
                "work_mode": "hybrid",
            },
        },
    )

    assert response.status_code == 200
    sent_plan = provider.seen_plans[0]
    # City/country are genuinely supported — they must reach the provider
    # exactly as the recruiter resolved them.
    assert sent_plan.searches[0].cities == ["Gachibowli"]
    assert sent_plan.searches[0].countries == ["India"]
    # zip_codes has no CrustData filter field at all; radius_miles was given
    # without a radius_place anchor, so it can't be enforced either; work_mode
    # is Remote/Hybrid/Onsite, which only exists on job_search. All three must
    # be cleared before dispatch (never sent as a false promise), with a
    # graceful-degradation warning explaining why.
    assert sent_plan.searches[0].zip_codes == []
    assert sent_plan.searches[0].radius_miles is None

    payload = response.json()
    warning_text = " ".join(payload["warnings"])
    assert "search radius" in warning_text
    assert "postal/zip code" in warning_text
    assert "work mode" in warning_text


def test_search_endpoint_persists_and_reloads_without_rerunning_pipeline(tmp_path) -> None:
    from backend.services.search_store import SearchStore

    ProviderRegistry._providers.clear()
    provider = PlanCapturingProvider()
    ProviderRegistry.register("mock", provider)

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=SearchStore(storage_dir=tmp_path),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})
    assert response.status_code == 200
    search_id = response.json()["search_id"]
    assert search_id

    # PlanCapturingProvider returns a single candidate for the primary query,
    # which is below the discovery target pool size, so the title-expansion
    # query also runs — two calls for the initial search.
    assert len(provider.seen_plans) == 2

    reload_response = client.get(f"/search/{search_id}")
    assert reload_response.status_code == 200
    assert reload_response.json()["search_id"] == search_id
    assert reload_response.json()["candidates"][0]["name"] == "Priya Rao"
    # Reloading must not call the provider again.
    assert len(provider.seen_plans) == 2


def test_get_search_returns_404_for_unknown_search_id() -> None:
    client = build_test_app()
    _login(client)
    response = client.get("/search/does-not-exist")
    assert response.status_code == 404


def test_patch_candidate_persists_decision_and_note(tmp_path) -> None:
    from backend.services.search_store import SearchStore

    ProviderRegistry._providers.clear()
    ProviderRegistry.register("mock", PlanCapturingProvider())

    app = create_app(
        jd_parser=JDParser(provider=FakeParser()),
        search_planner=SearchPlanner(),
        query_expander=QueryExpansionService(),
        capability_mapper=CapabilityMapper(),
        provider_registry=ProviderRegistry,
        candidate_merger=CandidateMerger(),
        candidate_ranker=CandidateRanker(),
        match_explainer=MatchExplainer(),
        search_diagnostics=SearchDiagnostics(),
        excel_exporter=ExcelExporter(),
        search_store=SearchStore(storage_dir=tmp_path),
    )
    client = TestClient(app)
    _login(client)
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})
    search_id = response.json()["search_id"]
    candidate_id = response.json()["candidates"][0]["candidate_id"] or "candidate-1"

    patch_response = client.patch(
        f"/search/{search_id}/candidate",
        json={"candidate_id": candidate_id, "decision": "shortlist", "note": "Strong fit"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["recruiter_decisions"][candidate_id] == "shortlist"
    assert patch_response.json()["notes"][candidate_id][0]["text"] == "Strong fit"


def test_auth_google_endpoint_sets_session_cookie_for_allowed_domain(monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "verify_google_id_token",
        lambda credential: {"email": "recruiter@example.com", "email_verified": True},
    )
    client = build_test_app()

    response = client.post("/auth/google", json={"credential": "fake-token"})

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "email": "recruiter@example.com"}
    assert "recruiterai_session" in response.cookies


def test_auth_google_endpoint_rejects_wrong_domain(monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "verify_google_id_token",
        lambda credential: {"email": "someone@gmail.com", "email_verified": True},
    )
    client = build_test_app()

    response = client.post("/auth/google", json={"credential": "fake-token"})

    assert response.status_code == 403
    assert "recruiterai_session" not in response.cookies


def test_protected_endpoint_rejects_without_session() -> None:
    client = build_test_app()

    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})

    assert response.status_code == 401


def test_protected_endpoint_accepts_with_valid_session() -> None:
    client = build_test_app()
    _login(client)

    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})

    assert response.status_code == 200


def test_auth_logout_clears_session(monkeypatch) -> None:
    # Goes through the real /auth/google flow (not the _login() shortcut) so the
    # session cookie is set via an actual Set-Cookie response header — this is
    # what makes httpx's cookie jar correctly apply the logout deletion.
    monkeypatch.setattr(
        api_module,
        "verify_google_id_token",
        lambda credential: {"email": "recruiter@example.com", "email_verified": True},
    )
    client = build_test_app()
    assert client.post("/auth/google", json={"credential": "fake-token"}).status_code == 200
    assert client.get("/auth/me").status_code == 200

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200

    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})
    assert response.status_code == 401
