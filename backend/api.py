import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.bootstrap import bootstrap
from backend.errors import ParsingError, ProviderError, RecruiterAIError, RankingError
from backend.models.candidate import Candidate
from backend.models.match_explanation import MatchExplanation
from backend.models.provider_capabilities import ProviderCapabilities
from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan
from backend.providers.base import BaseLLMProvider, BaseProvider
from backend.providers.openai import OpenAIProvider
from backend.providers.registry import ProviderRegistry
from backend.services.candidate_merger import CandidateMerger
from backend.services.candidate_ranker import CandidateRanker
from backend.services.capability_mapper import CapabilityMapper
from backend.services.jd_parser import JDParser
from backend.services.match_explainer import MatchExplainer
from backend.services.query_expansion import QueryExpansionService
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_planner import SearchPlanner
from backend.exporters.excel import ExcelExporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ParseRequest(BaseModel):
    jd_text: str


class SearchRequest(ParseRequest):
    provider: str


class SearchResponse(BaseModel):
    provider: str
    candidate_count: int
    candidates: List[Dict[str, Any]]
    explanations: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]


class ExportResponse(BaseModel):
    filename: str
    path: str


def create_app(
    jd_parser: Optional[JDParser] = None,
    search_planner: Optional[SearchPlanner] = None,
    query_expander: Optional[QueryExpansionService] = None,
    capability_mapper: Optional[CapabilityMapper] = None,
    provider_registry: Optional[type[ProviderRegistry]] = None,
    candidate_merger: Optional[CandidateMerger] = None,
    candidate_ranker: Optional[CandidateRanker] = None,
    match_explainer: Optional[MatchExplainer] = None,
    search_diagnostics: Optional[SearchDiagnostics] = None,
    excel_exporter: Optional[ExcelExporter] = None,
) -> FastAPI:
    app = FastAPI(title="RecruiterAI API")

    bootstrap()

    jd_parser = jd_parser or JDParser(provider=OpenAIProvider())
    search_planner = search_planner or SearchPlanner()
    query_expander = query_expander or QueryExpansionService()
    capability_mapper = capability_mapper or CapabilityMapper()
    provider_registry = provider_registry or ProviderRegistry
    candidate_merger = candidate_merger or CandidateMerger()
    candidate_ranker = candidate_ranker or CandidateRanker()
    match_explainer = match_explainer or MatchExplainer()
    search_diagnostics = search_diagnostics or SearchDiagnostics()
    excel_exporter = excel_exporter or ExcelExporter()

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/providers")
    def providers() -> Dict[str, List[str]]:
        return {"providers": provider_registry.available()}

    @app.post("/parse-jd")
    def parse_jd(request: ParseRequest) -> SearchIntent:
        try:
            intent = jd_parser.parse(request.jd_text)
        except RecruiterAIError as exc:
            logger.exception("JD parsing failed")
            raise HTTPException(status_code=500, detail="JD parsing failed") from exc
        except Exception as exc:
            logger.exception("Unexpected JD parsing error")
            raise HTTPException(status_code=500, detail="JD parsing failed") from exc
        return intent

    @app.post("/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        try:
            provider = provider_registry.get(request.provider)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            logger.info("Parsing job description")
            intent = jd_parser.parse(request.jd_text)
            if not isinstance(intent, SearchIntent):
                raise ParsingError("JD parser returned an invalid SearchIntent")
            logger.info("JD parsed")

            logger.info("Building search plan")
            plan = search_planner.build(intent)
            if not isinstance(plan, SearchPlan):
                raise RankingError("Search planner returned an invalid plan")
            logger.info("Search plan created (%s queries)", len(plan.searches))

            logger.info("Expanding search queries")
            expanded_plan = query_expander.expand(plan)
            if not isinstance(expanded_plan, SearchPlan):
                raise RankingError("Query expansion returned an invalid plan")
            logger.info("Query expansion complete (%s searches)", len(expanded_plan.searches))

            logger.info("Mapping provider capabilities")
            capabilities = ProviderCapabilities(supported_filters=["include_titles", "required_skills", "countries", "preferred_companies"])
            mapped_plan, _ = capability_mapper.map(expanded_plan, capabilities)
            if not isinstance(mapped_plan, SearchPlan):
                raise RankingError("Capability mapping returned an invalid plan")
            logger.info("Capability mapping complete")

            logger.info("Executing provider: %s", request.provider)
            candidates = provider.search(mapped_plan)
            if not isinstance(candidates, list):
                raise ProviderError("Provider returned an invalid candidate list")
            logger.info("Provider returned %s candidates", len(candidates))

            logger.info("Merging candidates")
            merged_candidates = candidate_merger.merge(candidates)
            logger.info("Candidate merge complete (%s unique)", len(merged_candidates))

            logger.info("Ranking candidates")
            ranked_candidates = candidate_ranker.rank(merged_candidates, intent)
            logger.info("Candidate ranking complete")

            logger.info("Generating explanations")
            explanations = [match_explainer.explain(candidate, intent).model_dump() for candidate in ranked_candidates]
            logger.info("Explanations generated")

            logger.info("Generating diagnostics")
            diagnostics = search_diagnostics.analyze(mapped_plan, ranked_candidates)
            logger.info("Diagnostics generated")

            return SearchResponse(
                provider=request.provider,
                candidate_count=len(ranked_candidates),
                candidates=[candidate.model_dump() for candidate in ranked_candidates],
                explanations=explanations,
                diagnostics={
                    "total_queries": diagnostics.total_queries,
                    "total_candidates": diagnostics.total_candidates,
                    "candidates_per_query": diagnostics.candidates_per_query,
                    "duplicate_candidates": diagnostics.duplicate_candidates,
                    "average_provider_score": diagnostics.average_provider_score,
                    "average_final_score": diagnostics.average_final_score,
                    "top_job_titles": diagnostics.top_job_titles,
                    "top_companies": diagnostics.top_companies,
                    "query_execution_summary": diagnostics.query_execution_summary,
                },
            )
        except HTTPException:
            raise
        except RecruiterAIError as exc:
            logger.exception("Search pipeline failed")
            raise HTTPException(status_code=500, detail="Search pipeline failed") from exc
        except Exception as exc:
            logger.exception("Unexpected search pipeline error")
            raise HTTPException(status_code=500, detail="Search pipeline failed") from exc

    @app.post("/export")
    def export(request: SearchRequest) -> FileResponse:
        try:
            provider = provider_registry.get(request.provider)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        intent = jd_parser.parse(request.jd_text)
        plan = search_planner.build(intent)
        expanded_plan = query_expander.expand(plan)

        capabilities = ProviderCapabilities(supported_filters=["include_titles", "required_skills", "countries", "preferred_companies"])
        mapped_plan, _ = capability_mapper.map(expanded_plan, capabilities)

        candidates = provider.search(mapped_plan)
        merged_candidates = candidate_merger.merge(candidates)
        ranked_candidates = candidate_ranker.rank(merged_candidates, intent)

        temp_dir = Path(tempfile.gettempdir()) / "recruiterai-api"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / "results.xlsx"
        excel_exporter.export(ranked_candidates, str(output_path))
        return FileResponse(output_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="results.xlsx")

    return app


class NoOpParser(BaseLLMProvider):
    def parse_job_description(self, job_description: str) -> SearchIntent:
        return SearchIntent()


app = create_app()
