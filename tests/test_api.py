import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
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
            location=Location(countries=["US"]),
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


def build_test_app() -> TestClient:
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
    )
    return TestClient(app)


def test_health_endpoint() -> None:
    client = build_test_app()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_providers_endpoint_lists_registered_providers() -> None:
    client = build_test_app()
    response = client.get("/providers")

    assert response.status_code == 200
    assert response.json() == {"providers": ["mock"]}


def test_parse_jd_endpoint_returns_search_intent() -> None:
    client = build_test_app()
    response = client.post("/parse-jd", json={"jd_text": "Need a Python engineer"})

    assert response.status_code == 200
    assert response.json()["role"]["title"] == "Software Engineer"
    assert response.json()["skills"]["required_skills"] == ["Python"]


def test_search_endpoint_returns_structured_result() -> None:
    client = build_test_app()
    response = client.post("/search", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["name"] == "Alice"
    assert payload["explanations"][0]["title_match"] is True


def test_export_endpoint_returns_excel_file() -> None:
    client = build_test_app()
    response = client.post("/export", json={"jd_text": "Need a Python engineer", "provider": "mock"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    actual_path = Path(tempfile.gettempdir()) / "recruiterai-api" / "results.xlsx"
    assert actual_path.exists()
    actual_path.unlink(missing_ok=True)
