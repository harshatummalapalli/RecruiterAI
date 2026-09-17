from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.providers.base import BaseProvider
from backend.providers.registry import ProviderRegistry
from backend.services.candidate_ranker import CandidateRanker
from backend.services.capability_mapper import CapabilityMapper
from backend.services.candidate_merger import CandidateMerger
from backend.services.jd_parser import JDParser
from backend.services.match_explainer import MatchExplainer
from backend.services.query_expansion import QueryExpansionService
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_planner import SearchPlanner


class FakeProvider(BaseProvider):
    def search(self, plan):
        return [
            Candidate(
                name="Alice",
                title="Senior AI Engineer",
                company="OpenAI",
                location="US",
                provider_score=0.95,
                raw_data={"skills": ["Python", "FastAPI"], "years_experience": 5},
            )
        ]


class FakeParser:
    def parse_job_description(self, job_description: str) -> SearchIntent:
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

        return SearchIntent(
            role=Role(title="Senior AI Engineer"),
            location=Location(countries=["US"]),
            experience=Experience(minimum_years=3),
            titles=Titles(include_titles=["Senior AI Engineer"]),
            skills=Skills(required_skills=["Python", "FastAPI"], preferred_skills=["Azure"]),
            previous_background=PreviousBackground(preferred_companies=["OpenAI"]),
            ai_focus=AIFocus(rag=True, llm=True),
            company_preferences=CompanyPreferences(),
            ranking=Ranking(),
        )


def test_search_endpoint_runs_full_pipeline_with_mock_provider() -> None:
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
        excel_exporter=None,
    )
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value())
    response = client.post(
        "/search",
        json={"jd_text": "We are looking for a Senior AI Engineer with Python, FastAPI, Azure, OpenAI, RAG and Kubernetes.", "provider": "mock"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "platform"
    assert payload["candidate_count"] == 1
    assert payload["diagnostics"]["total_queries"] >= 1
