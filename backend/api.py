import json
import logging
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.auth import (
    SESSION_COOKIE_NAME,
    check_domain_allowed,
    create_session_cookie_value,
    require_session,
    verify_google_id_token,
)
from backend.bootstrap import bootstrap
from backend.config import (
    get_discovery_max_pages,
    get_discovery_page_size,
    get_session_cookie_secure,
    get_session_max_age_seconds,
)
from backend.errors import ConfigurationError, ParsingError, ProviderError, RecruiterAIError, RankingError
from backend.models.intake import IntakeResult, SearchBoundary
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
from backend.providers.harvest import HarvestEnrichmentService
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_translator import build_confirmed_hiring_intent, to_search_intent
from backend.services.jd_parser import JDParser
from backend.services.match_explainer import MatchExplainer
from backend.services.query_expansion import QueryExpansionService
from backend.services.requirement_judge import RequirementJudge
from backend.services.search_diagnostics import SearchDiagnostics
from backend.services.search_pipeline import (
    MAX_WORKSPACE_CANDIDATES,
    STATUS_RUNNING,
    reconcile_interrupted_searches,
    run_search_pipeline,
)
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

# Fields CrustData's /person/search API can actually filter on for this
# account, verified through live API calls (see the V0.1 discovery
# architecture notes) rather than assumed from general documentation.
# zip_codes and work_mode are deliberately excluded: CrustData has no
# ZIP/postal filter field at all (confirmed via a live 400 rejection), and
# Remote/Hybrid/Onsite exists only on job_search, never person_search.
# radius_place/radius_miles ARE supported (via geo_distance) provided a
# place-name/ZIP-text anchor is given, not a raw postal filter.
CRUSTDATA_SUPPORTED_FILTERS = [
    "include_titles",
    "exclude_titles",
    "required_skills",
    "preferred_skills",
    "countries",
    "states",
    "cities",
    "radius_place",
    "radius_miles",
    "employment_type",
    "minimum_years",
    "maximum_years",
    "preferred_companies",
    "exclude_current_companies",
    "preferred_company_types",
]

FRIENDLY_UNSUPPORTED_FILTER_LABELS = {
    "zip_codes": "postal/zip code",
    "work_mode": "work mode (remote/hybrid/onsite)",
}



def _raise_recruiter_friendly_error(detail: str, status_code: int = 503) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _apply_radius_degradation(intent: SearchIntent) -> Optional[str]:
    """Radius search needs an anchor place (CrustData's geo_distance has no
    concept of a bare distance) — if the recruiter set a radius without one,
    it can't be enforced. Never silently drop it: clear it and say so,
    rather than pretending it was applied."""
    if intent.location.radius_miles is not None and not intent.location.radius_place:
        intent.location.radius_miles = None
        return "A search radius needs a place to search around, so it was not applied. Results may include candidates outside that distance."
    return None


def _friendly_capability_warnings(raw_warnings: List[str]) -> List[str]:
    """Turn "dropped unsupported filter 'X'" internal warnings into the
    recruiter-facing phrasing requested for graceful degradation."""
    friendly: List[str] = []
    seen_fields: set = set()
    for raw in raw_warnings:
        for field_name, label in FRIENDLY_UNSUPPORTED_FILTER_LABELS.items():
            if f"'{field_name}'" in raw and field_name not in seen_fields:
                seen_fields.add(field_name)
                friendly.append(f"This search cannot filter by {label}, so results may include other arrangements.")
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
    states: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    zip_codes: List[str] = Field(default_factory=list)
    radius_miles: Optional[float] = None
    # Free-form place name (or ZIP text) CrustData's geo_distance geocodes
    # server-side — never sent as a zip_code filter field, which CrustData
    # doesn't have.
    radius_place: Optional[str] = None
    radius_unit: str = "mi"
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None


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
    search_id: str
    candidate_count: int
    candidates: List[Dict[str, Any]]
    explanations: List[Dict[str, Any]]
    # Structured CandidateEvidence per candidate (career history, education,
    # contact, company context) — index-aligned with `candidates`/
    # `explanations`. Lets the frontend render a rich candidate record
    # without reimplementing raw-provider-response parsing in JS.
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None
    # Recruiter-authored state for this search, keyed by the same candidate
    # id the frontend already sends to PATCH /search/{id}/candidate. Root
    # cause of the "decisions/notes lost on refresh" bug: this data was
    # persisted (see update_candidate below) but never returned by either
    # POST /search or GET /search/{id}, so the frontend had nothing to
    # rehydrate its local state from. Always populated from the persisted
    # record at response-build time, never fabricated.
    recruiter_decisions: Dict[str, str] = Field(default_factory=dict)
    notes: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    # Progressive Candidate Workspace — search-level status and per-candidate
    # lifecycle. `status` defaults to "complete" so a record persisted before
    # this field existed still validates. `candidate_states` is keyed by the
    # same stable candidate_id used everywhere else (never profile_url/
    # array position) — see backend/services/search_pipeline.py.
    status: str = "complete"
    candidate_states: Dict[str, str] = Field(default_factory=dict)
    progress: Dict[str, int] = Field(default_factory=dict)
    # True once the recruiter has accepted the one-time grouping of this
    # search's candidates by evidence. Presentation state only: it never
    # touches evidence, ranking or admission.
    workspace_arranged: bool = False


class WorkspaceUpdateRequest(BaseModel):
    arranged: bool


class CandidateUpdateRequest(BaseModel):
    candidate_id: str
    decision: Optional[str] = None
    note: Optional[str] = None


class ExportResponse(BaseModel):
    filename: str
    path: str


class GoogleLoginRequest(BaseModel):
    credential: str


class SearchBoundaryRequest(BaseModel):
    """The recruiter-confirmed search boundary from the intake form — see
    backend/models/intake.py's SearchBoundary for the authoritative
    contract (this is just its pydantic request-body mirror)."""

    hiring_company: str
    country: str
    work_mode: str
    state: Optional[str] = None
    city: Optional[str] = None
    radius_miles: Optional[float] = None
    remote_scope: Optional[str] = None
    remote_states: List[str] = Field(default_factory=list)
    remote_cities: List[str] = Field(default_factory=list)


class IntakeStartRequest(BaseModel):
    raw_input: str
    # Optional for backward compatibility with any caller that doesn't send
    # one (e.g. existing tests) — the intake flow behaves exactly as before
    # when omitted.
    boundary: Optional[SearchBoundaryRequest] = None


class IntakeAnswerRequest(BaseModel):
    issue_id: str
    value: str
    label: str


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
    intake_session_manager: Optional[IntakeSessionManager] = None,
    harvest_enrichment_service: Optional[HarvestEnrichmentService] = None,
    requirement_judge: Optional[RequirementJudge] = None,
) -> FastAPI:
    app = FastAPI(title="RecruiterAI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://140.245.235.18",
            "https://hire.dayzero.partners",
        ],
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
    intake_session_manager = intake_session_manager or IntakeSessionManager()
    harvest_enrichment_service = harvest_enrichment_service or HarvestEnrichmentService()
    requirement_judge = requirement_judge or RequirementJudge()

    # A background search thread cannot survive a process restart — any
    # record still marked "running" from a previous process instance is
    # unambiguously orphaned. Reconcile once at startup so a polling
    # frontend never waits on a search that will never finish.
    reconcile_interrupted_searches(search_store)

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/google")
    def auth_google(request: GoogleLoginRequest, response: Response) -> Dict[str, Any]:
        claims = verify_google_id_token(request.credential)
        check_domain_allowed(claims)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            create_session_cookie_value(),
            httponly=True,
            samesite="lax",
            secure=get_session_cookie_secure(),
            max_age=get_session_max_age_seconds(),
        )
        logger.info("[AUTH] Recruiter signed in")
        return {"authenticated": True, "email": claims.get("email")}

    @app.get("/auth/me", dependencies=[Depends(require_session)])
    def auth_me() -> Dict[str, bool]:
        return {"authenticated": True}

    @app.post("/auth/logout")
    def auth_logout(response: Response) -> Dict[str, bool]:
        response.delete_cookie(SESSION_COOKIE_NAME)
        return {"authenticated": False}

    @app.get("/providers", dependencies=[Depends(require_session)])
    def providers() -> Dict[str, List[str]]:
        return {"providers": provider_registry.available()}

    @app.post("/parse-jd", dependencies=[Depends(require_session)])
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

    @app.post("/intake/start", dependencies=[Depends(require_session)])
    def intake_start(request: IntakeStartRequest) -> Dict[str, Any]:
        boundary = (
            SearchBoundary(
                hiring_company=request.boundary.hiring_company,
                country=request.boundary.country,
                work_mode=request.boundary.work_mode,
                state=request.boundary.state,
                city=request.boundary.city,
                radius_miles=request.boundary.radius_miles,
                remote_scope=request.boundary.remote_scope,
                remote_states=list(request.boundary.remote_states),
                remote_cities=list(request.boundary.remote_cities),
            )
            if request.boundary is not None
            else None
        )
        try:
            record = intake_session_manager.start(request.raw_input, boundary=boundary)
        except ConfigurationError as exc:
            logger.warning("Intake reasoning is unavailable", exc_info=exc)
            _raise_recruiter_friendly_error("Unable to understand this role right now.")
        except RecruiterAIError as exc:
            logger.exception("Intake reasoning failed")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        return {"session_id": record.session_id, "result": record.result}

    @app.post("/intake/{session_id}/answer", dependencies=[Depends(require_session)])
    def intake_answer(session_id: str, request: IntakeAnswerRequest) -> Dict[str, Any]:
        try:
            record = intake_session_manager.answer(session_id, request.issue_id, request.value, request.label)
        except KeyError:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ConfigurationError as exc:
            logger.warning("Intake reasoning is unavailable", exc_info=exc)
            _raise_recruiter_friendly_error("Unable to update this role's understanding right now.")
        except RecruiterAIError as exc:
            logger.exception("Intake reasoning failed")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        return {"session_id": record.session_id, "result": record.result}

    @app.post("/intake/{session_id}/confirm", dependencies=[Depends(require_session)])
    def intake_confirm(session_id: str) -> SearchIntent:
        record = intake_session_manager.get(session_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        try:
            return to_search_intent(build_confirmed_hiring_intent(record.result, boundary=record.boundary), query_expander=query_expander)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/intake/{session_id}/preview", dependencies=[Depends(require_session)])
    def intake_preview(session_id: str, provider: str = "crustdata") -> Dict[str, Any]:
        """Zero-cost debug contract (no CrustData credits spent): Confirmed
        Hiring Intent -> SearchPlan -> the exact provider payload(s) that
        would be sent, all built without calling the provider's search API.
        Lets every role type in the regression matrix be inspected end to
        end without paying for a live search."""
        record = intake_session_manager.get(session_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        try:
            confirmed = build_confirmed_hiring_intent(record.result, boundary=record.boundary)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        search_intent = to_search_intent(confirmed, query_expander=query_expander)
        plan = search_planner.build(search_intent)
        expanded_plan = query_expander.expand(plan)
        capabilities = ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS)
        mapped_plan, capability_warnings = capability_mapper.map(expanded_plan, capabilities)

        try:
            provider_instance = provider_registry.get(provider)
        except KeyError:
            raise HTTPException(status_code=503, detail="No sourcing provider is currently configured.")
        if not hasattr(provider_instance, "debug_payloads"):
            raise HTTPException(status_code=503, detail="This provider does not support a zero-cost preview.")

        return {
            "confirmed_hiring_intent": confirmed,
            "search_intent": search_intent,
            "search_plan": [query.model_dump() for query in mapped_plan.searches],
            "provider_payloads": provider_instance.debug_payloads(mapped_plan, options={"page_size": 25}),
            "capability_warnings": capability_warnings,
        }

    @app.get("/search/{search_id}", response_model=SearchResponse, dependencies=[Depends(require_session)])
    def get_search(search_id: str) -> SearchResponse:
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Reloaded persisted search | search_id=%s — no OpenAI or CrustData calls made", search_id)
        # record["response"] is the snapshot from whenever the search last
        # ran — recruiter_decisions/notes are updated separately (PATCH,
        # below) and live at the top level of the record, not inside that
        # snapshot, so they must be merged in here rather than trusted to
        # already be present on it.
        response_data = dict(record["response"])
        response_data["recruiter_decisions"] = record.get("recruiter_decisions", {})
        response_data["notes"] = record.get("notes", {})
        response_data["workspace_arranged"] = bool(record.get("workspace_arranged", False))
        return SearchResponse(**response_data)

    @app.patch("/search/{search_id}/workspace", dependencies=[Depends(require_session)])
    def update_workspace(search_id: str, update: WorkspaceUpdateRequest) -> Dict[str, Any]:
        # The recruiter's one-time "group by evidence" choice. Atomic with the
        # running pipeline's own saves, like the candidate PATCH below.
        def apply(record: Dict[str, Any]) -> None:
            record["workspace_arranged"] = update.arranged

        record = search_store.update(search_id, apply)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Workspace arranged flag persisted | search_id=%s arranged=%s", search_id, update.arranged)
        return {"workspace_arranged": bool(record.get("workspace_arranged", False))}

    @app.patch("/search/{search_id}/candidate", dependencies=[Depends(require_session)])
    def update_candidate(search_id: str, update: CandidateUpdateRequest) -> Dict[str, Any]:
        def apply(record: Dict[str, Any]) -> None:
            if update.decision is not None:
                record.setdefault("recruiter_decisions", {})[update.candidate_id] = update.decision
            if update.note:
                record.setdefault("notes", {}).setdefault(update.candidate_id, []).append(
                    {"text": update.note, "created_at": datetime.now(timezone.utc).isoformat()}
                )

        # update() is atomic with respect to the running search's own progress
        # saves, so a shortlist recorded mid-search is never overwritten by the
        # pipeline's next write (and vice versa).
        record = search_store.update(search_id, apply)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Recruiter decision/note persisted | search_id=%s candidate_id=%s", search_id, update.candidate_id)
        return {"recruiter_decisions": record.get("recruiter_decisions", {}), "notes": record.get("notes", {})}

    @app.post("/search", response_model=SearchResponse, dependencies=[Depends(require_session)])
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
                intent.location.states = list(request.location.states)
                intent.location.cities = list(request.location.cities)
                intent.location.zip_codes = list(request.location.zip_codes)
                intent.location.radius_miles = request.location.radius_miles
                intent.location.radius_place = request.location.radius_place
                intent.location.radius_unit = request.location.radius_unit or "mi"
                intent.location.work_mode = request.location.work_mode
                if request.location.employment_type:
                    intent.role.employment_type = request.location.employment_type
                logger.info(
                    "[SEARCH] Location override applied from Search Brief | countries=%s states=%s cities=%s zip_codes=%s radius_place=%s radius_miles=%s work_mode=%s",
                    intent.location.countries,
                    intent.location.states,
                    intent.location.cities,
                    intent.location.zip_codes,
                    intent.location.radius_place,
                    intent.location.radius_miles,
                    intent.location.work_mode,
                )

            radius_degradation_warning = _apply_radius_degradation(intent)

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
            if radius_degradation_warning:
                friendly_warnings.append(radius_degradation_warning)
            for raw_warning in capability_warnings:
                logger.warning("[SEARCH] Constraint dropped for this provider | %s", raw_warning)
            logger.info("Capability mapping complete (%s constraint(s) dropped)", len(capability_warnings))

            # Retrieval sizing is backend-owned (Phase 3) — the frontend no
            # longer sends page_size/max_pages at all; a caller MAY still
            # override them explicitly (e.g. a future debug tool), but the
            # recruiter-facing product always gets the configured default.
            options = {
                "page_size": request.page_size if request.page_size is not None else get_discovery_page_size(),
                "max_pages": request.max_pages if request.max_pages is not None else get_discovery_max_pages(),
                "max_retries": request.max_retries,
                "retry_backoff_base": request.retry_backoff_base,
                "autocomplete": request.autocomplete,
                "cursor": request.cursor,
            }
            options = {key: value for key, value in options.items() if value is not None}

            # Everything from here on (CrustData discovery, baseline ranking,
            # workspace admission, Harvest enrichment, rerank) is the slow,
            # network-bound part of a search — it now runs on a background
            # thread (Progressive Candidate Workspace) instead of blocking
            # this request. See backend/services/search_pipeline.py.
            existing_record = search_store.load(search_id) or {}

            # An immediate "running" record so a poll that lands before the
            # background thread's first save still gets a coherent response
            # instead of a 404, and so GET /search/{id} always has something
            # to read.
            search_store.save(
                search_id,
                {
                    "search_id": search_id,
                    "status": STATUS_RUNNING,
                    "created_at": existing_record.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "jd_text": request.jd_text,
                    "location_override": request.location.model_dump() if request.location else None,
                    "response": {
                        "provider": "platform",
                        "search_id": search_id,
                        "candidate_count": 0,
                        "candidates": [],
                        "explanations": [],
                        "evidence": [],
                        "diagnostics": {},
                        "warnings": friendly_warnings,
                        "debug": None,
                        "recruiter_decisions": existing_record.get("recruiter_decisions", {}),
                        "notes": existing_record.get("notes", {}),
                        "status": STATUS_RUNNING,
                        "candidate_states": {},
                        "progress": {"admitted": 0, "surfaced": 0, "building_context": 0, "review_ready": 0},
                    },
                    "recruiter_decisions": existing_record.get("recruiter_decisions", {}),
                    "notes": existing_record.get("notes", {}),
                    "candidate_states": {},
                    "harvest_evidence": existing_record.get("harvest_evidence", {}),
                    "internal_diagnostics": {},
                },
            )

            threading.Thread(
                target=run_search_pipeline,
                kwargs=dict(
                    search_id=search_id,
                    intent=intent,
                    mapped_plan=mapped_plan,
                    options=options,
                    provider=provider,
                    candidate_merger=candidate_merger,
                    candidate_ranker=candidate_ranker,
                    harvest_enrichment_service=harvest_enrichment_service,
                    requirement_judge=requirement_judge,
                    match_explainer=match_explainer,
                    search_diagnostics=search_diagnostics,
                    search_store=search_store,
                    jd_text=request.jd_text,
                    location_override=request.location.model_dump() if request.location else None,
                    friendly_warnings=friendly_warnings,
                    debug=request.debug,
                    existing_record=existing_record,
                    target_pool_size=MAX_WORKSPACE_CANDIDATES,
                ),
                daemon=True,
                name=f"search-{search_id}",
            ).start()

            logger.info("[SEARCH] Background pipeline started | search_id=%s", search_id)

            return SearchResponse(
                provider="platform",
                search_id=search_id,
                candidate_count=0,
                candidates=[],
                explanations=[],
                evidence=[],
                recruiter_decisions=existing_record.get("recruiter_decisions", {}),
                notes=existing_record.get("notes", {}),
                diagnostics={},
                warnings=friendly_warnings,
                debug=None,
                status=STATUS_RUNNING,
                candidate_states={},
                progress={"admitted": 0, "surfaced": 0, "building_context": 0, "review_ready": 0},
            )
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

    @app.post("/export", dependencies=[Depends(require_session)])
    def export(request: SearchRequest) -> FileResponse:
        try:
            provider = provider_registry.get(request.provider)
        except KeyError as exc:
            raise HTTPException(status_code=503, detail="No sourcing provider is currently configured.") from exc

        intent = _resolve_search_intent(request, jd_parser)
        if request.location is not None:
            intent.location.countries = list(request.location.countries)
            intent.location.states = list(request.location.states)
            intent.location.cities = list(request.location.cities)
            intent.location.zip_codes = list(request.location.zip_codes)
            intent.location.radius_miles = request.location.radius_miles
            intent.location.radius_place = request.location.radius_place
            intent.location.radius_unit = request.location.radius_unit or "mi"
            intent.location.work_mode = request.location.work_mode
            if request.location.employment_type:
                intent.role.employment_type = request.location.employment_type
        _apply_radius_degradation(intent)
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
