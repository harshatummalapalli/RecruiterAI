import json
import logging
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.bootstrap import bootstrap
from backend.errors import ConfigurationError, ParsingError, ProviderError, RecruiterAIError, RankingError
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
from backend.services.search_store import SearchStore
from backend.exporters.excel import ExcelExporter

_STANDARD_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())


class _StructuredFormatter(logging.Formatter):
    """Appends any `extra=` fields on a log record as JSON. Plain
    `logging.basicConfig()` silently drops `extra=` — it's never included in
    the default format string — so structured fields like search_id,
    execution_time_ms, or CrustData credit usage would otherwise never
    actually reach the log output despite being attached to the record."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_KEYS and key != "message"
        }
        if not extra_fields:
            return base
        try:
            extra_json = json.dumps(extra_fields, default=str)
        except (TypeError, ValueError):
            extra_json = str(extra_fields)
        return f"{base} | {extra_json}"


_log_handler = logging.StreamHandler()
_log_handler.setFormatter(_StructuredFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler], force=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fields CrustData's /person/search API has no way to filter on today. Kept
# here (not guessed at request time) so Constraint mapping and Debug Mode
# agree on exactly what gets dropped and why. See docs/LOCATION_PIPELINE.md.
CRUSTDATA_SUPPORTED_FILTERS = [
    "include_titles",
    "exclude_titles",
    "required_skills",
    "preferred_skills",
    "countries",
    "cities",
    "minimum_years",
    "maximum_years",
    "preferred_companies",
    "exclude_current_companies",
    "preferred_company_types",
]

FRIENDLY_UNSUPPORTED_FILTER_LABELS = {
    "zip_codes": "postal/zip code",
    "radius_miles": "search radius",
    "work_mode": "work mode (remote/hybrid/onsite)",
    "must_have": "ranking hint (must-have)",
    "nice_to_have": "ranking hint (nice-to-have)",
    "bonus": "ranking hint (bonus)",
}


def _raise_recruiter_friendly_error(detail: str, status_code: int = 503) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _friendly_capability_warnings(raw_warnings: List[str]) -> List[str]:
    """Turn "dropped unsupported filter 'X'" internal warnings into the
    recruiter-facing phrasing requested for graceful degradation."""
    friendly: List[str] = []
    seen_fields: set = set()
    for raw in raw_warnings:
        for field_name, label in FRIENDLY_UNSUPPORTED_FILTER_LABELS.items():
            if f"'{field_name}'" in raw and field_name not in seen_fields:
                seen_fields.add(field_name)
                friendly.append(f"Current provider cannot filter by {label}. The search may include broader results.")
    return friendly


class ParseRequest(BaseModel):
    jd_text: str


def _resolve_search_intent(request: "SearchRequest", jd_parser: JDParser) -> SearchIntent:
    """Use the recruiter's already-edited Search Brief when the caller sends
    one; only fall back to an LLM parse of `jd_text` for backward-compatible
    callers that don't. This is what keeps the Search Brief -> Search step
    from re-parsing the JD (or a re-serialized version of it) a second time."""
    if request.intent is not None:
        logger.info("Using recruiter-provided Search Brief directly (no second LLM parse)")
        return request.intent
    logger.info("No structured Search Brief provided — parsing job description via LLM")
    return jd_parser.parse(request.jd_text)


class LocationOverride(BaseModel):
    """The recruiter's already-resolved Search Brief location — sent
    directly so the backend never has to re-derive location from a second,
    lossy OpenAI pass over serialized prose. When present, this is
    authoritative for location; when absent, location falls back to
    whatever the JD parse produces (backward compatible)."""

    search_geography: Optional[str] = None
    countries: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    zip_codes: List[str] = Field(default_factory=list)
    radius_miles: Optional[float] = None
    work_mode: Optional[str] = None


class SearchRequest(ParseRequest):
    provider: str
    page_size: Optional[int] = None
    max_pages: Optional[int] = None
    max_retries: Optional[int] = None
    retry_backoff_base: Optional[float] = None
    autocomplete: Optional[bool] = None
    cursor: Optional[str] = None
    location: Optional[LocationOverride] = None
    debug: Optional[bool] = None
    search_id: Optional[str] = None
    # The recruiter's already-parsed-and-edited Search Brief. When present,
    # this is authoritative and the search pipeline uses it directly instead
    # of re-parsing `jd_text` through the LLM a second time — a second pass
    # over serialized prose is lossy (drops confidence scores, risks
    # re-splitting/mis-reading list fields, and can re-derive numeric bounds
    # like years of experience incorrectly) and non-deterministic. `jd_text`
    # is still accepted/stored for display and for backward-compatible
    # callers that don't send a structured intent.
    intent: Optional[SearchIntent] = None


class SearchResponse(BaseModel):
    provider: str
    demo: bool = False
    search_id: str
    candidate_count: int
    candidates: List[Dict[str, Any]]
    explanations: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None


class CandidateUpdateRequest(BaseModel):
    candidate_id: str
    decision: Optional[str] = None
    note: Optional[str] = None


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
    search_store: Optional[SearchStore] = None,
) -> FastAPI:
    app = FastAPI(title="RecruiterAI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    search_store = search_store or SearchStore()

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
        except ConfigurationError as exc:
            logger.warning("Search brief preparation is unavailable", exc_info=exc)
            _raise_recruiter_friendly_error("Unable to prepare the search brief right now.")
        except ProviderError as exc:
            logger.warning("Search brief preparation could not continue", exc_info=exc)
            _raise_recruiter_friendly_error("Unable to prepare the search brief right now.")
        except RecruiterAIError as exc:
            logger.exception("JD parsing failed")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        except Exception as exc:
            logger.exception("Unexpected JD parsing error")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        return intent

    @app.get("/search/{search_id}", response_model=SearchResponse)
    def get_search(search_id: str) -> SearchResponse:
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Reloaded persisted search | search_id=%s — no OpenAI or CrustData calls made", search_id)
        return SearchResponse(**record["response"])

    @app.patch("/search/{search_id}/candidate")
    def update_candidate(search_id: str, update: CandidateUpdateRequest) -> Dict[str, Any]:
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        if update.decision is not None:
            record.setdefault("recruiter_decisions", {})[update.candidate_id] = update.decision
        if update.note:
            record.setdefault("notes", {}).setdefault(update.candidate_id, []).append(
                {"text": update.note, "created_at": datetime.now(timezone.utc).isoformat()}
            )
        search_store.save(search_id, record)
        logger.info("[SEARCH] Recruiter decision/note persisted | search_id=%s candidate_id=%s", search_id, update.candidate_id)
        return {"recruiter_decisions": record.get("recruiter_decisions", {}), "notes": record.get("notes", {})}

    @app.post("/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        search_id = request.search_id or str(uuid.uuid4())
        started_at = time.perf_counter()
        logger.info(
            "[SEARCH] Search Brief received | search_id=%s provider=%s jd_chars=%s has_location_override=%s",
            search_id,
            request.provider,
            len(request.jd_text),
            request.location is not None,
        )

        try:
            provider = provider_registry.get(request.provider)
        except KeyError as exc:
            logger.warning("Unknown sourcing provider requested: %s", request.provider)
            _raise_recruiter_friendly_error("No sourcing provider is currently configured.")

        try:
            intent = _resolve_search_intent(request, jd_parser)
            if not isinstance(intent, SearchIntent):
                raise ParsingError("JD parser returned an invalid SearchIntent")

            # Location fidelity fix: the recruiter's Search Brief has already
            # resolved location (search geography, exact cities, zip, radius)
            # with far more care than a second OpenAI pass over serialized
            # prose ever could. When the frontend sends it, it is
            # authoritative — it REPLACES whatever the JD parse guessed,
            # rather than only filling gaps, so an intentional "Global" (no
            # constraint) choice isn't silently overridden by a stray guess.
            if request.location is not None:
                intent.location.countries = list(request.location.countries)
                intent.location.cities = list(request.location.cities)
                intent.location.zip_codes = list(request.location.zip_codes)
                intent.location.radius_miles = request.location.radius_miles
                intent.location.work_mode = request.location.work_mode
                logger.info(
                    "[SEARCH] Location override applied from Search Brief | countries=%s cities=%s zip_codes=%s radius_miles=%s work_mode=%s",
                    intent.location.countries,
                    intent.location.cities,
                    intent.location.zip_codes,
                    intent.location.radius_miles,
                    intent.location.work_mode,
                )

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
            capabilities = ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS)
            mapped_plan, capability_warnings = capability_mapper.map(expanded_plan, capabilities)
            if not isinstance(mapped_plan, SearchPlan):
                raise RankingError("Capability mapping returned an invalid plan")
            friendly_warnings = _friendly_capability_warnings(capability_warnings)
            for raw_warning in capability_warnings:
                logger.warning("[SEARCH] Constraint dropped for this provider | %s", raw_warning)
            logger.info("Capability mapping complete (%s constraint(s) dropped)", len(capability_warnings))

            options = {
                "page_size": request.page_size,
                "max_pages": request.max_pages,
                "max_retries": request.max_retries,
                "retry_backoff_base": request.retry_backoff_base,
                "autocomplete": request.autocomplete,
                "cursor": request.cursor,
            }
            options = {key: value for key, value in options.items() if value is not None}
            logger.info(
                "[SEARCH] Provider Request dispatched | provider=%s queries=%s options=%s",
                request.provider,
                len(mapped_plan.searches),
                options,
            )
            if hasattr(provider, "search_with_options"):
                candidates = provider.search_with_options(mapped_plan, options=options)
            else:
                candidates = provider.search(mapped_plan)
            if not isinstance(candidates, list):
                raise ProviderError("Provider returned an invalid candidate list")
            logger.info("[SEARCH] Candidates Returned | provider=%s count=%s", request.provider, len(candidates))
            if not candidates:
                logger.info("No candidates were returned for this search — this is a real empty result, not an error.")

            logger.info("Merging candidates")
            merged_candidates = candidate_merger.merge(candidates)
            logger.info("Candidate merge complete (%s unique)", len(merged_candidates))

            ranked_candidates = candidate_ranker.rank(merged_candidates, intent)
            logger.info("[SEARCH] Ranking Completed | count=%s", len(ranked_candidates))

            logger.info("Generating explanations")
            explanations = [match_explainer.explain(candidate, intent).model_dump() for candidate in ranked_candidates]
            logger.info("Explanations generated")

            logger.info("Generating diagnostics")
            diagnostics = search_diagnostics.analyze(mapped_plan, ranked_candidates)
            logger.info("Diagnostics generated")

            execution_time_ms = round((time.perf_counter() - started_at) * 1000, 2)

            debug_payload: Optional[Dict[str, Any]] = None
            if request.debug:
                final_provider_payload = (
                    provider.debug_payloads(mapped_plan, options) if hasattr(provider, "debug_payloads") else None
                )
                debug_payload = {
                    "search_id": search_id,
                    "execution_time_ms": execution_time_ms,
                    "jd_text": request.jd_text,
                    "location_override": request.location.model_dump() if request.location else None,
                    "generated_provider_query": [q.model_dump() for q in mapped_plan.searches],
                    "final_provider_payload": final_provider_payload,
                    "capability_warnings": capability_warnings,
                    "candidates_returned": len(candidates),
                    "candidates_after_merge": len(merged_candidates),
                    "candidates_ranked": len(ranked_candidates),
                }

            response = SearchResponse(
                provider="platform",
                search_id=search_id,
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
                warnings=friendly_warnings,
                debug=debug_payload,
            )

            existing_record = search_store.load(search_id) or {}
            search_store.save(
                search_id,
                {
                    "search_id": search_id,
                    "created_at": existing_record.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "jd_text": request.jd_text,
                    "location_override": request.location.model_dump() if request.location else None,
                    "response": response.model_dump(),
                    "recruiter_decisions": existing_record.get("recruiter_decisions", {}),
                    "notes": existing_record.get("notes", {}),
                },
            )

            logger.info(
                "[SEARCH] Execution summary",
                extra={
                    "search_id": search_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_time_ms": execution_time_ms,
                    "queries_dispatched": len(mapped_plan.searches),
                    "candidates_returned": len(ranked_candidates),
                    "validation_rules_fired": len(capability_warnings),
                    "final_search_constraints": {
                        "countries": intent.location.countries,
                        "cities": intent.location.cities,
                        "zip_codes": intent.location.zip_codes,
                        "radius_miles": intent.location.radius_miles,
                        "work_mode": intent.location.work_mode,
                        "required_skills": intent.skills.required_skills,
                        "minimum_years": intent.experience.minimum_years,
                        "maximum_years": intent.experience.maximum_years,
                    },
                },
            )

            return response
        except HTTPException:
            raise
        except ConfigurationError as exc:
            logger.warning("Sourcing is unavailable — check the provider API key configuration", exc_info=exc)
            _raise_recruiter_friendly_error("Sourcing is currently unavailable. Please check the provider configuration and try again.")
        except ProviderError as exc:
            logger.warning("Sourcing request failed", exc_info=exc)
            _raise_recruiter_friendly_error("The sourcing provider could not complete this search. Please try again.", status_code=502)
        except RecruiterAIError as exc:
            logger.exception("Search pipeline failed")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        except Exception as exc:
            logger.exception("Unexpected search pipeline error")
            _raise_recruiter_friendly_error("Please contact your administrator.")

    @app.post("/export")
    def export(request: SearchRequest) -> FileResponse:
        try:
            provider = provider_registry.get(request.provider)
        except KeyError as exc:
            raise HTTPException(status_code=503, detail="No sourcing provider is currently configured.") from exc

        intent = _resolve_search_intent(request, jd_parser)
        if request.location is not None:
            intent.location.countries = list(request.location.countries)
            intent.location.cities = list(request.location.cities)
            intent.location.zip_codes = list(request.location.zip_codes)
            intent.location.radius_miles = request.location.radius_miles
            intent.location.work_mode = request.location.work_mode
        plan = search_planner.build(intent)
        expanded_plan = query_expander.expand(plan)

        capabilities = ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS)
        mapped_plan, _ = capability_mapper.map(expanded_plan, capabilities)

        options = {
            "page_size": request.page_size,
            "max_pages": request.max_pages,
            "max_retries": request.max_retries,
            "retry_backoff_base": request.retry_backoff_base,
            "autocomplete": request.autocomplete,
            "cursor": request.cursor,
        }
        options = {key: value for key, value in options.items() if value is not None}
        if hasattr(provider, "search_with_options"):
            candidates = provider.search_with_options(mapped_plan, options=options)
        else:
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
