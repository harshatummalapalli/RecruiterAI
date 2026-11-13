import json
import hashlib
import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.auth import (
    SESSION_COOKIE_NAME,
    check_domain_allowed,
    create_session_cookie_value,
    get_session_email,
    is_email_permitted,
    is_super_admin,
    require_admin,
    require_session,
    verify_google_id_token,
)
from backend.providers.crustdata import fetch_credit_balance as get_crustdata_credit_balance
from backend.bootstrap import bootstrap
from backend.config import (
    get_discovery_max_pages,
    get_discovery_page_size,
    get_session_cookie_secure,
    get_session_max_age_seconds,
    get_unipile_webhook_secret,
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
from backend.services.candidate_evidence_builder import rehydrate_response_evidence
from backend.services.capability_mapper import CapabilityMapper
from backend.providers.harvest import HarvestEnrichmentService
from backend.services import candidate_presentation as presentation_rules
from backend.services import role_lifecycle
from backend.services.crustdata_capabilities import supported_search_query_filters
from backend.services.intake_session import IntakeSessionManager, list_draft_summaries
from backend.services.intent_change import meaningful_changes
from backend.services.role_feedback import Guidance, build_guidance
from backend.services.role_runtime import (
    RoleError,
    RoleRuntime,
    RoleScheduler,
    apply_candidate_update,
    derived_fields,
    draft_summary,
    is_archived,
    search_summary,
    sidebar_label,
)
from backend.services.search_boundary import BoundaryValidationError, validate_search_boundary
from backend.services.confirmation import (
    ConfirmationEdits,
    ConfirmationRefused,
    ConfirmationStore,
    brief_summary,
    build_snapshot,
    location_override_for_search,
    search_intent_from_snapshot,
)
from backend.services.search_translator import build_confirmed_hiring_intent, to_search_intent
from backend.bridge.intake_service import ConfirmationNotReady, IntakeReadError
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
# required_skills/preferred_skills are deliberately excluded too: the
# CrustDataProvider payload builder (_build_filter_conditions) has never
# actually turned either field into a filter condition — this account's
# plan is separately confirmed to deny "skills" as a response field at all
# (see crustdata.py's DEFAULT_FIELDS comment) — so declaring them
# "supported" here was a silent lie: nothing warned if either field were
# ever populated, it would just vanish before reaching the provider.
# Which recruiter-intent filters are genuinely hard-filterable on CrustData is
# now DERIVED from the tested capability model (the single source of truth),
# not hardcoded here — a field becomes a hard filter only when the model vouches
# for it. Skill/technology requirements are deliberately absent: they reach
# CrustData only through the natural-language query (see search_translator.py /
# search_planner.py), and the mapper warns if required_skills/preferred_skills
# are ever populated rather than dropping them in silence.
CRUSTDATA_SUPPORTED_FILTERS = supported_search_query_filters()

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
    # The id of a confirmed brief (POST /intake/{id}/confirmations). When the server requires confirmation (the
    # default), this is the ONLY accepted source of the search intent: the browser is never trusted to supply it.
    confirmation_id: Optional[str] = None
    # The recruiter's already-parsed-and-edited Search Brief. When present,
    # this is authoritative and the search pipeline uses it directly instead
    # of re-parsing `jd_text` through the LLM a second time — a second pass
    # over serialized prose is lossy (drops confidence scores, risks
    # re-splitting/mis-reading list fields, and can re-derive numeric bounds
    # like years of experience incorrectly) and non-deterministic. `jd_text`
    # is still accepted/stored for display and for backward-compatible
    # callers that don't send a structured intent.
    intent: Optional[SearchIntent] = None
    campaign_duration_days: Optional[int] = 1


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
    # Which confirmed brief this search ran from (posted title, candidate identity). Lets the workspace name the
    # role correctly after a reload without any browser state.
    confirmed_brief: Optional[Dict[str, Any]] = None
    # Multi-search roles. All absent (None / empty) for a search stored before roles existed, which keeps behaving as
    # it always did: every candidate is shown.
    role: Optional[Dict[str, Any]] = None
    presentation: Optional[Dict[str, Dict[str, Any]]] = None
    availability: Optional[Dict[str, Any]] = None
    calibration: Optional[Dict[str, Any]] = None
    feedback: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    new_candidates: int = 0
    retrieval_exhausted: bool = False
    # New engine: ask for a structured reason on Maybe/Reject, and reveal the next
    # already-read candidate from the held pool when one is rejected. Default off so
    # legacy/role searches are unchanged.
    feedback_capture: bool = False
    reserve_available: int = 0
    pool_candidate_count: int = 0
    pool_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    initial_validation_pending: bool = False
    # The result of the last pool-first refine (matched / dropped / exhausted), so the
    # UI can say "N of your read pool match" and offer a wider search when none do.
    refine_outcome: Optional[Dict[str, Any]] = None
    # Per-candidate outreach state for THIS recruiter (they own this search), keyed
    # by candidate_id, then by channel: {candidate_id: {"linkedin": {state, kind, at},
    # "email": {state, subject, at}}}. Populated from the persisted record; it lets
    # the card show "Invited"/"Emailed" without a per-candidate fetch. See the
    # /search/{id}/outreach/* endpoints and backend/services/outreach.py (step 3).
    outreach: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # RUN: the autonomous campaign opened on the recruiter's one Go-validation.
    # None when no campaign is running. {status, budget, used, rounds, window_hours,
    # ...} — the UI reads this (with reserve_available) to badge "N new matches
    # waiting" instead of the system auto-pausing or re-asking for a validation.
    campaign: Optional[Dict[str, Any]] = None


class WorkspaceUpdateRequest(BaseModel):
    arranged: bool


class CandidateUpdateRequest(BaseModel):
    candidate_id: str
    decision: Optional[str] = None
    note: Optional[str] = None
    # Optional, for Maybe and Reject only: a structured reason and a short note. See backend/services/role_feedback.py.
    feedback_reason: Optional[str] = None
    feedback_note: Optional[str] = None


class OutreachDraftRequest(BaseModel):
    """Ask for an AI draft for one candidate on one channel. `inmail` only applies
    to LinkedIn (InMail vs a connection note)."""
    candidate_id: str
    channel: str  # "linkedin" | "email"
    inmail: bool = False
    tone: Optional[str] = None  # "warm" | "direct" | None
    reply_to: Optional[str] = None  # the candidate's inbound message, to draft a reply to it


class OutreachSendRequest(BaseModel):
    """Send a (recruiter-reviewed) outreach message. The candidate is identified
    only by id within the owned search; the account is resolved server-side from
    the session, never from the client."""
    candidate_id: str
    channel: str  # "linkedin" | "email"
    body: str
    subject: Optional[str] = None
    inmail: bool = False


class SequenceRequest(BaseModel):
    """Enroll/stop a candidate in the one built-in follow-up flow."""
    candidate_id: str


class CampaignStartRequest(BaseModel):
    """Open a paced, budget-capped campaign on a search (the recruiter's Go)."""
    window_hours: int = 72
    budget: int = 100


class RefineRequest(BaseModel):
    """Structured refine deltas (new engine). Every field is typed and capability-
    grounded — no free text is interpreted. All optional; only what the recruiter
    changed is sent. See recruiter/agents/calibration/refine.refine_model."""
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    work_mode: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    exclude_companies_current: Optional[List[str]] = None
    exclude_companies_ever: Optional[List[str]] = None
    only_companies: Optional[List[str]] = None
    exclude_titles: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    retier: Optional[Dict[str, str]] = None
    when: Optional[Dict[str, str]] = None
    add_requirements: Optional[List[Dict[str, Any]]] = None
    dealbreakers: Optional[List[str]] = None


class ShowMoreRequest(BaseModel):
    # True for the quiet "N new candidates" notice: show only what the background search found.
    only_new: bool = False


class RoleActionRequest(BaseModel):
    action: str  # "pause" | "resume"


class CalibrationRequest(BaseModel):
    dismiss: List[str] = Field(default_factory=list)


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
    # Onsite/hybrid multi-city (Phase 2 §2.6): several named cities that REPLACE
    # the single city + radius. Must be mirrored here or the browser's cities are
    # silently dropped and a multi-city hybrid role fails state/city/radius checks.
    cities: List[str] = Field(default_factory=list)
    remote_scope: Optional[str] = None
    remote_states: List[str] = Field(default_factory=list)
    remote_cities: List[str] = Field(default_factory=list)
    # Company targeting (new engine): include = ever worked at ANY of these (OR),
    # exclude = not currently at these (the hiring company is always excluded too).
    # Consumed by the bridge's assemble -> CompanyRules; ignored on the legacy path.
    include_companies: List[str] = Field(default_factory=list)
    exclude_companies: List[str] = Field(default_factory=list)
    # Scope for each company list: "current" (current employer only) or "ever" (anywhere
    # in their history). Defaults preserve prior behaviour (include=ever, exclude=current).
    include_companies_scope: str = "ever"
    exclude_companies_scope: str = "current"
    # Experience is now a first-step recruiter input (min required, max optional),
    # instead of only being read from the JD — so a JD that omits it never forces
    # an unanswerable clarification. Consumed by the bridge; ignored by legacy.
    min_years: Optional[int] = None
    max_years: Optional[int] = None


class IntakeStartRequest(BaseModel):
    raw_input: str
    # Required: the boundary is recruiter-owned, and the server (not the
    # browser) validates it. See backend/services/search_boundary.py.
    boundary: SearchBoundaryRequest
    # The role title exactly as the recruiter typed it. Optional; when given it
    # is the posted title, verbatim, and is never rewritten or replaced.
    posted_title: Optional[str] = None
    # Optional hiring-manager / client brief. When present it is read alongside
    # the JD and reconciled against it (feature A); absent, intake is unchanged.
    hm_notes: Optional[str] = None


class ConfirmationRequest(BaseModel):
    edits: ConfirmationEdits = Field(default_factory=ConfirmationEdits)


class IntakeAnswerRequest(BaseModel):
    issue_id: str
    value: str
    label: str


class IntegrationConnectRequest(BaseModel):
    channel: str  # linkedin | email | whatsapp


class IntegrationDisconnectRequest(BaseModel):
    channel: str


# The sidebar lists at most this many roles, and an unsearched brief only while it is recent.
# Completed searches and drafts each get their OWN budget, rather than competing for one shared, recency-sorted
# slot list — a burst of drafts (real or test-generated) can then never push a completed search out of view; it
# can only push out an OLDER draft. Searches get the much larger budget: they represent committed work, drafts
# are transient by nature. See the forensic audit this resolves for why a shared budget was the actual bug.
SIDEBAR_SEARCH_LIMIT = 200
SIDEBAR_DRAFT_LIMIT = 20
DRAFT_VISIBLE_SECONDS = 14 * 24 * 3600


class _SummaryCache:
    """Sidebar summaries keyed by file version, so listing many large search records only re-reads the ones that
    changed."""

    def __init__(self) -> None:
        self._items: Dict[Path, tuple] = {}

    def get(self, store: SearchStore, path: Path, model_confirmations: Any = None) -> Optional[Dict[str, Any]]:
        try:
            stat = path.stat()
        except OSError:
            return None
        version = (stat.st_mtime_ns, stat.st_size)
        cached = self._items.get(path)
        if cached and cached[0] == version:
            return cached[1]
        record = store.load(path.stem)
        if not record:
            return None
        summary = search_summary(record)
        confirmation_id = (record.get("confirmed_brief") or {}).get("confirmation_id")
        if model_confirmations is not None and confirmation_id:
            try:
                model = model_confirmations.load(confirmation_id)
                if model is not None:
                    summary["title"] = model.posted_title or model.identity or summary["title"]
                    summary["company"] = summary.get("company") or model.hiring_company or ""
                    if not summary.get("place"):
                        location = model.location
                        summary["place"] = (f"Remote · {', '.join(location.countries)}"
                                             if location.work_mode == "remote" and location.countries
                                             else ", ".join(location.cities or location.states or location.countries))
            except Exception:  # malformed/missing old confirmations do not hide the search card
                logger.debug("Could not resolve campaign label | search_id=%s", path.stem, exc_info=True)
        entry = {"summary": summary, "session_id": (record.get("confirmed_brief") or {}).get("session_id"),
                 "owner_email": record.get("owner_email")}
        self._items[path] = (version, entry)
        return entry


def _engine_boundary(validated, req) -> Dict[str, Any]:
    """The boundary dict handed to the new engine: the NORMALIZED geo from
    validate_search_boundary (preserving the old app's canonicalization + onsite/
    remote rules) plus the fields the legacy SearchBoundary doesn't carry — company
    include/exclude and the first-step min/max years."""
    import dataclasses
    data = dataclasses.asdict(validated)
    data["include_companies"] = list(req.include_companies or [])
    data["exclude_companies"] = list(req.exclude_companies or [])
    data["include_companies_scope"] = getattr(req, "include_companies_scope", "ever") or "ever"
    data["exclude_companies_scope"] = getattr(req, "exclude_companies_scope", "current") or "current"
    data["min_years"] = req.min_years
    data["max_years"] = req.max_years
    return data


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
    confirmation_store: Optional[ConfirmationStore] = None,
    require_confirmation: Optional[bool] = None,
    role_clock: Optional[Callable[[], datetime]] = None,
    intake_service: Optional[Any] = None,
    outreach_service: Optional[Any] = None,
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
    confirmation_store = confirmation_store or ConfirmationStore()
    # New 7-agent engine (opt-in). Off by default -> every route stays legacy, so
    # production is unchanged until RECRUITER_NEW_ENGINE is set. When on, the
    # intake/search routes below run through backend.bridge.IntakeService instead.
    if intake_service is None and os.environ.get("RECRUITER_NEW_ENGINE", "").strip().lower() in ("1", "true", "yes"):
        from backend.bridge import build_intake_service
        intake_service = build_intake_service(org=os.environ.get("ALLOWED_EMAIL_DOMAIN") or "default")
    if require_confirmation is None:
        require_confirmation = os.environ.get("RECRUITERAI_REQUIRE_CONFIRMATION", "true").strip().lower() not in ("0", "false", "no")
    # Retrieval parity: the browser has never sent the model-written search sentence, so it has never reached the
    # provider. Sending it now would change which candidates are retrieved, which is a separate decision. Off by
    # default; the sentence is still stored in the confirmed snapshot.
    send_confirmed_sentence = os.environ.get("RECRUITERAI_SEND_CONFIRMED_SEARCH_SENTENCE", "false").strip().lower() in ("1", "true", "yes")
    harvest_enrichment_service = harvest_enrichment_service or HarvestEnrichmentService()
    requirement_judge = requirement_judge or RequirementJudge()
    # Outreach (Unipile) — per-recruiter connected accounts + hosted-auth connect
    # flow. Always available; the actual Unipile calls no-op until UNIPILE_API_KEY
    # is set on the server (connecting an account then fails friendly, not crashes).
    if outreach_service is None:
        from backend.providers.unipile import UnipileClient
        from backend.services.connected_accounts import ConnectedAccountStore
        from backend.services.outreach import OutreachService, PendingConnectStore
        outreach_service = OutreachService(UnipileClient(), ConnectedAccountStore(), PendingConnectStore())
    search_summary_cache = _SummaryCache()
    clock = role_clock or (lambda: datetime.now(timezone.utc))

    # --- Per-user isolation (owner scoping) -------------------------------------
    # Every search and intake session belongs to the recruiter who created it.
    # Google OAuth already proves a verified identity; these helpers make each
    # recruiter see and act on ONLY their own work. The super admin sees all.
    def _session_owner(request: Request) -> Optional[str]:
        """The lowercased login email that owns anything created in this session, or None."""
        email = get_session_email(request)
        return email.lower() if email else None

    def _can_access(record: Dict[str, Any], request: Request) -> bool:
        """True if the caller may see/act on this record.

        * The super admin sees everything.
        * A record WITH an owner is visible only to that owner.
        * A record with NO owner is legacy data from before per-user scoping. An
          IDENTIFIED non-admin recruiter never sees it — that was exactly the
          cross-account leak (a second signed-in Gmail seeing the admin's role). It
          stays reachable to the admin, and to a session carrying no identity at all
          (an old opaque cookie from before login emails were stored, or a test
          client), which only ever had the old shared view anyway. Those cookies
          expire and re-login stamps an email, closing even that transitional window.
        """
        if is_super_admin(request):
            return True
        owner = (record.get("owner_email") or "").strip().lower()
        caller = _session_owner(request)
        if not owner:
            return caller is None
        return bool(caller) and owner == caller

    def _claim_owner(store: SearchStore, record_id: str, owner: Optional[str]) -> None:
        """Stamp `owner` onto a freshly created record, once. No-op without an owner
        (e.g. the dev auth bypass, where is_super_admin already grants full access)
        or if the record already has one. Relies on the store's sticky-owner save to
        then carry the owner through every later background rebuild."""
        if not owner:
            return

        def mutate(rec: Dict[str, Any]) -> None:
            if not rec.get("owner_email"):
                rec["owner_email"] = owner

        store.update(record_id, mutate)

    def _intake_store() -> SearchStore:
        """The file store backing intake sessions for whichever engine is live."""
        if intake_service is not None:
            return intake_service._sessions
        return intake_session_manager._store

    def require_owned_search(search_id: str, request: Request) -> None:
        """Route guard for /search/{search_id}/*. A 404 (not 403 — the search is
        invisible, not merely forbidden, so IDs can't be probed) when the caller does
        not own it. A search_id that does not exist passes through unchanged, so the
        handler's own 404 and the creation path are untouched."""
        record = search_store.load(search_id)
        if record is not None and not _can_access(record, request):
            raise HTTPException(status_code=404, detail="Search not found.")

    def require_owned_session(session_id: str, request: Request) -> None:
        """Route guard for /intake/{session_id}/* — same contract as above."""
        record = _intake_store().load(session_id)
        if record is not None and not _can_access(record, request):
            raise HTTPException(status_code=404, detail="Intake session not found.")

    def _build_plan(intent: SearchIntent, location: Optional[LocationOverride]) -> tuple:
        """Location override, radius handling, search plan, query expansion and provider capability mapping: everything
        between "the confirmed intent" and "queries the provider can run". Shared by every way a search starts."""
        # Location fidelity fix: the recruiter's Search Brief has already resolved location (search geography, exact
        # cities, zip, radius) with far more care than a second OpenAI pass over serialized prose ever could. When it
        # is given, it is authoritative: it REPLACES whatever the JD parse guessed, rather than only filling gaps, so
        # an intentional "Global" (no constraint) choice isn't silently overridden by a stray guess.
        if location is not None:
            intent.location.countries = list(location.countries)
            intent.location.states = list(location.states)
            intent.location.cities = list(location.cities)
            intent.location.zip_codes = list(location.zip_codes)
            intent.location.radius_miles = location.radius_miles
            intent.location.radius_place = location.radius_place
            intent.location.radius_unit = location.radius_unit or "mi"
            intent.location.work_mode = location.work_mode
            if location.employment_type:
                intent.role.employment_type = location.employment_type
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
        return intent, mapped_plan, friendly_warnings

    def _confirmed_intent(snapshot: Dict[str, Any]) -> tuple:
        intent = search_intent_from_snapshot(snapshot)
        if not send_confirmed_sentence:
            intent.natural_language_search_query = None
        return intent, LocationOverride(**location_override_for_search(intent, snapshot["boundary"]))

    def start_cycle(search_id: str, snapshot: Dict[str, Any], cycle: Dict[str, Any], guidance: Guidance, provider_name: Optional[str] = None) -> None:
        """Runs ONE retrieval cycle for a role, on the same background pipeline as any search. The role's record must
        already exist. Campaign retrieval sizing remains backend-owned at the established 50-profile page."""
        if intake_service is not None and not isinstance(snapshot, dict):
            def run_engine_cycle() -> None:
                try:
                    feedback_record = search_store.load(search_id) or {}
                    result = intake_service.run_search(snapshot.model_id, search_id,
                                                       provider=provider_name or "crustdata",
                                                       cursor=cycle.get("cursor"),
                                                       feedback_record=feedback_record,
                                                       admit_all_relevant=cycle.get("n", 1) > 1,
                                                       surface_all=cycle.get("n", 1) > 1)
                    pool = result.pop("pool", {})
                    with search_store.lock:
                        record = search_store.load(search_id) or {}
                        current = record.get("response") or {}
                        stored_pool = ((record.get("internal_diagnostics") or {}).get("pool") or {})
                        old_ids = {e.get("candidate_id") for e in (stored_pool.get("judged") or []) + (stored_pool.get("reserve") or [])}
                        old_ids.update(c.get("candidate_id") for c in current.get("candidates") or [])
                        keep = [i for i, c in enumerate(result.get("candidates") or [])
                                if c.get("candidate_id") not in old_ids]
                        new_candidates = [(result.get("candidates") or [])[i] for i in keep]
                        for field in ("candidates", "explanations", "evidence"):
                            current[field] = list(current.get(field) or []) + [
                                (result.get(field) or [])[i] for i in keep if i < len(result.get(field) or [])
                            ]
                        current["candidate_count"] = len(current.get("candidates") or [])
                        current["diagnostics"] = result.get("diagnostics") or current.get("diagnostics") or {}
                        current["status"] = "complete"
                        current["recruiter_decisions"] = record.get("recruiter_decisions", {})
                        current["notes"] = record.get("notes", {})

                        diagnostics = record.setdefault("internal_diagnostics", {})
                        old_pool = diagnostics.setdefault("pool", {"judged": [], "reserve": [], "counts": {}})
                        known = {e.get("candidate_id") for e in (old_pool.get("judged") or []) + (old_pool.get("reserve") or [])}
                        for state in ("judged", "reserve"):
                            additions = [e for e in pool.get(state, []) if e.get("candidate_id") not in known]
                            old_pool.setdefault(state, []).extend(additions)
                            known.update(e.get("candidate_id") for e in additions)
                        old_pool["counts"] = {
                            "judged": len(old_pool.get("judged") or []),
                            "reserve": len(old_pool.get("reserve") or []),
                            "shown": len(current.get("candidates") or []),
                            "total": len(old_pool.get("judged") or []) + len(old_pool.get("reserve") or []),
                        }
                        visible_ids = {c.get("candidate_id") for c in current.get("candidates") or []}
                        current["reserve_available"] = sum(1 for e in old_pool.get("judged") or []
                            if not e.get("shown") and e.get("candidate_id") not in visible_ids)
                        current["candidate_states"] = {**(current.get("candidate_states") or {}),
                            **{(current.get("candidates") or [])[i].get("candidate_id"): "review_ready" for i in keep}}
                        presentation = record.setdefault("presentation", {})
                        batch_number = presentation_rules.next_batch_number(record)
                        for candidate in new_candidates:
                            candidate_id = candidate.get("candidate_id")
                            if candidate_id:
                                presentation[candidate_id] = {
                                    "state": presentation_rules.PRESENTED, "source": "daily",
                                    "seen": True, "batch": batch_number,
                                }

                        diag = result.get("diagnostics") or {}
                        pulled = int(diag.get("pulled") or 0)
                        credits = float(diag.get("credits_used") if diag.get("credits_used") is not None
                                        else (diag.get("est_credits") or (pulled * 0.03)))
                        record.setdefault("cycles", []).append({
                            "n": cycle["n"], "kind": cycle["kind"], "at": datetime.now(timezone.utc).isoformat(),
                            "retrieved": pulled, "credits_used": credits,
                            "new_candidates": len(keep), "cursor_used": bool(cycle.get("cursor")),
                            "confirmation_id": snapshot.model_id,
                        })
                        next_cursor = diag.get("next_cursor")
                        record["retrieval"] = {"next_cursor": next_cursor, "exhausted": not bool(next_cursor),
                                                "cycle": cycle["n"]}
                        if keep and not record.get("campaign_initial_ids"):
                            record["campaign_initial_ids"] = [
                                current["candidates"][len(current["candidates"]) - len(keep) + offset].get("candidate_id")
                                for offset in range(min(5, len(keep)))
                            ]
                            record["role"]["reserve_analysis_state"] = None
                        record["status"] = "complete"
                        record["updated_at"] = datetime.now(timezone.utc).isoformat()
                        record["response"] = current
                        search_store.save(search_id, record)
                except Exception:
                    logger.exception("[SEARCH] New-engine campaign cycle failed | search_id=%s", search_id)
                    def failed(record: Dict[str, Any]) -> None:
                        record["status"] = "error"
                        response = record.setdefault("response", {})
                        response["status"] = "error"
                        response.setdefault("warnings", []).append("The next campaign search could not be completed.")
                        record["updated_at"] = datetime.now(timezone.utc).isoformat()
                    search_store.update(search_id, failed)

            def mark_engine_running(record: Dict[str, Any]) -> None:
                record["status"] = STATUS_RUNNING
                record.setdefault("response", {})["status"] = STATUS_RUNNING
                record["updated_at"] = datetime.now(timezone.utc).isoformat()
            search_store.update(search_id, mark_engine_running)
            threading.Thread(target=run_engine_cycle, daemon=True,
                             name=f"engine-campaign-{search_id}-{cycle['n']}").start()
            logger.info("[SEARCH] New-engine campaign cycle started | search_id=%s kind=%s n=%s", search_id, cycle["kind"], cycle["n"])
            return
        # Every cycle of a role searches with the provider the role was started with.
        provider_name = provider_name or (search_store.load(search_id) or {}).get("provider") or "crustdata"
        provider = provider_registry.get(provider_name)
        intent, location = _confirmed_intent(snapshot)
        intent, mapped_plan, friendly_warnings = _build_plan(intent, location)
        if cycle["kind"] in ("more", "resume", "daily"):
            # A cursor belongs to the query that produced it: continue the primary natural-language query only.
            primary = [query for query in mapped_plan.searches if query.query_name == "natural_language"]
            if primary:
                mapped_plan = SearchPlan(searches=primary, strategy=mapped_plan.strategy, reasoning=mapped_plan.reasoning, confidence_score=mapped_plan.confidence_score)
        options = {
            "page_size": get_discovery_page_size(),
            "max_pages": get_discovery_max_pages(),
            "autocomplete": True,
            "cursor": cycle.get("cursor"),
        }
        options = {key: value for key, value in options.items() if value is not None}

        def mark_running(record: Dict[str, Any]) -> None:
            record["status"] = STATUS_RUNNING
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            record.pop("error_message", None)
            record.setdefault("response", {})["status"] = STATUS_RUNNING

        existing_record = search_store.update(search_id, mark_running)
        if existing_record is None:
            raise KeyError(search_id)
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
                jd_text=snapshot["raw_input"],
                location_override=location.model_dump(),
                friendly_warnings=friendly_warnings,
                debug=False,
                existing_record=existing_record,
                target_pool_size=MAX_WORKSPACE_CANDIDATES,
                cycle=cycle,
                guidance=guidance,
            ),
            daemon=True,
            name=f"search-{search_id}",
        ).start()
        logger.info("[SEARCH] Cycle started | search_id=%s kind=%s n=%s cursor=%s", search_id, cycle["kind"], cycle["n"], bool(cycle.get("cursor")))

    role_runtime = RoleRuntime(search_store, confirmation_store, start_cycle, clock,
                               getattr(intake_service, "_confirmations", None))
    app.state.role_runtime = role_runtime
    if os.environ.get("RECRUITERAI_ROLE_SCHEDULER", "true").strip().lower() not in ("0", "false", "no"):
        role_scheduler = RoleScheduler(role_runtime)
        # Started with the server, not at import, so building the app (tests, tools) never starts background work.
        app.router.on_startup.append(role_scheduler.start)
        app.router.on_shutdown.append(role_scheduler.stop)

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
        if not is_email_permitted(claims.get("email")):
            logger.warning("[AUTH] Rejected a verified sign-in that is not on the access allowlist")
            raise HTTPException(status_code=403, detail="Your account isn't on the access list yet. Please ask your administrator for access.")
        response.set_cookie(
            SESSION_COOKIE_NAME,
            create_session_cookie_value(claims.get("email")),
            httponly=True,
            samesite="lax",
            secure=get_session_cookie_secure(),
            max_age=get_session_max_age_seconds(),
        )
        logger.info("[AUTH] Recruiter signed in")
        return {"authenticated": True, "email": claims.get("email")}

    @app.get("/auth/me", dependencies=[Depends(require_session)])
    def auth_me(request: Request) -> Dict[str, bool]:
        # is_admin drives admin-only UI (the live credit meter). Ordinary
        # recruiters simply never receive it, so they never see a gated surface.
        return {"authenticated": True, "is_admin": is_super_admin(request)}

    @app.get("/credits", dependencies=[Depends(require_admin)])
    def credits() -> Dict[str, Any]:
        # Live CrustData balance for the super admin's meter. CrustData's
        # /user/credits is itself free (no credits consumed). person_search costs
        # 0.03 credits/result, so a search's spend ≈ results * 0.03.
        balance = get_crustdata_credit_balance()
        return {"credits": balance, "cost_per_result": 0.03}

    @app.post("/auth/logout")
    def auth_logout(response: Response) -> Dict[str, bool]:
        response.delete_cookie(SESSION_COOKIE_NAME)
        return {"authenticated": False}

    @app.get("/providers", dependencies=[Depends(require_session)])
    def providers() -> Dict[str, List[str]]:
        return {"providers": provider_registry.available()}

    # --- Outreach integrations (Settings → Connect LinkedIn / Email / WhatsApp) ---
    # Per-recruiter: every account binds to the authenticated owner_email and is
    # resolved from the session, never from client input. The connect page runs on
    # our white-label host (UNIPILE_HOSTED_AUTH_DOMAIN), so no vendor is exposed.
    def _connect_result_page(ok: bool, message: str, channel: Optional[str] = None) -> HTMLResponse:
        # Our-branded callback page. It tells the opener (the Settings tab) the
        # result and closes; a plain "return" link is the fallback if it can't close.
        import html as _html
        safe = _html.escape(message)
        payload = json.dumps({"type": "recruiterai:integration", "ok": ok, "channel": channel})
        body = f"""<!doctype html><html><head><meta charset="utf-8"><title>RecruiterAI</title>
<style>body{{font-family:-apple-system,Segoe UI,Inter,sans-serif;background:#fbfbfd;color:#18223a;
display:grid;place-items:center;height:100vh;margin:0}}.card{{max-width:360px;text-align:center;padding:28px}}
.badge{{width:44px;height:44px;border-radius:50%;margin:0 auto 14px;display:grid;place-items:center;font-size:22px;
background:{('#ecfaf1' if ok else '#fdecec')};color:{('#15803d' if ok else '#b91c1c')}}}
p{{color:#46506a;font-size:14px}} a{{color:#16203a;font-weight:600}}</style></head>
<body><div class="card"><div class="badge">{('✓' if ok else '!')}</div>
<p>{safe}</p><p><a href="#" onclick="window.close();return false;">You can close this tab</a></p></div>
<script>try{{if(window.opener)window.opener.postMessage({payload},"*");}}catch(e){{}}
setTimeout(function(){{try{{window.close();}}catch(e){{}}}},1200);</script></body></html>"""
        return HTMLResponse(content=body)

    @app.get("/integrations", dependencies=[Depends(require_session)])
    def list_integrations(http_request: Request) -> Dict[str, Any]:
        owner = _session_owner(http_request)
        return {"integrations": outreach_service.list_integrations(owner or "")}

    @app.post("/integrations/connect", dependencies=[Depends(require_session)])
    def integrations_connect(request: IntegrationConnectRequest, http_request: Request) -> Dict[str, str]:
        from backend.providers.unipile import UnipileError, UnipileNotConfiguredError
        from backend.services.outreach import OutreachConnectError
        owner = _session_owner(http_request)
        if not owner:
            raise HTTPException(status_code=401, detail="Sign in to connect an account.")
        callback = str(http_request.base_url).rstrip("/") + "/integrations/callback"
        try:
            link = outreach_service.begin_connect(owner, request.channel, callback_url=callback)
        except OutreachConnectError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except UnipileNotConfiguredError:
            raise HTTPException(status_code=503, detail="Account connections aren't enabled yet.")
        except UnipileError:
            logger.exception("[INTEGRATIONS] begin_connect failed | owner=%s channel=%s", owner, request.channel)
            raise HTTPException(status_code=502, detail="Couldn't start the connection. Please try again.")
        return {"link": link}

    @app.get("/integrations/callback")
    def integrations_callback(
        account_id: Optional[str] = None,
        provider: Optional[str] = None,
        state: Optional[str] = None,
        error_title: Optional[str] = None,
    ) -> HTMLResponse:
        # Unipile's redirect target. No session dependency — the binding is proven
        # by the single-use `state` token (tied to the recruiter who started it),
        # which the browser's session cookie can't be relied upon here.
        from backend.services.outreach import OutreachConnectError
        if error_title or not (account_id and state):
            return _connect_result_page(False, error_title or "The connection was cancelled.")
        try:
            _owner, channel = outreach_service.complete_connect(state, account_id, provider or "")
        except OutreachConnectError as exc:
            return _connect_result_page(False, str(exc))
        except Exception:
            logger.exception("[INTEGRATIONS] complete_connect failed")
            return _connect_result_page(False, "We couldn't finish connecting that account.")
        label = {"linkedin": "LinkedIn", "email": "email", "whatsapp": "WhatsApp"}.get(channel, channel)
        return _connect_result_page(True, f"Connected your {label}. Returning to RecruiterAI…", channel)

    @app.post("/integrations/disconnect", dependencies=[Depends(require_session)])
    def integrations_disconnect(request: IntegrationDisconnectRequest, http_request: Request) -> Dict[str, bool]:
        owner = _session_owner(http_request)
        if not owner:
            raise HTTPException(status_code=401, detail="Sign in first.")
        return {"disconnected": outreach_service.disconnect(owner, request.channel)}

    # --- Reply inbox (Phase 1, step 4) -------------------------------------
    # One application-wide Unipile webhook; each event is routed to its owning
    # recruiter (account_id -> owner) before any record is touched, so a reply
    # only ever flips state on the recruiter who sent the outreach.
    @app.post("/integrations/webhook/register", dependencies=[Depends(require_admin)])
    def integrations_webhook_register(http_request: Request) -> Dict[str, Any]:
        from backend.providers.unipile import UnipileError
        from backend.services.outreach import OutreachActionError
        try:
            return outreach_service.ensure_reply_webhook(public_base_url=str(http_request.base_url))
        except OutreachActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except UnipileError:
            logger.exception("[OUTREACH] webhook registration failed")
            raise HTTPException(status_code=502, detail="Couldn't register the reply webhook.")

    def _apply_reply(interp: Dict[str, Any]) -> int:
        """Flip outreach state on every one of this owner's searches where a sent
        outreach's target matches the event's sender. Precedence: `replied` wins
        over everything but an existing `replied`; `connected` only upgrades an
        `invited` (never downgrades a messaged/replied thread)."""
        owner = (interp["owner_email"] or "").lower()
        channel = interp["channel"]
        ids = {i for i in interp["identifiers"] if i}
        state = interp["state"]
        preview = (interp.get("preview") or "").strip()[:500] or None
        if not ids:
            return 0
        updated = 0
        for path in Path(search_store.storage_dir).glob("*.json"):
            record = search_store.load(path.stem)
            if not record or (record.get("owner_email") or "").lower() != owner:
                continue
            outreach = record.get("outreach") or {}
            hits = [cid for cid, chans in outreach.items()
                    if isinstance(chans.get(channel), dict) and str(chans[channel].get("target_id") or "") in ids]
            if not hits:
                continue

            def apply(rec: Dict[str, Any], hits=hits) -> None:
                now = datetime.now(timezone.utc).isoformat()
                for cid in hits:
                    entry = ((rec.get("outreach") or {}).get(cid) or {}).get(channel)
                    if not isinstance(entry, dict):
                        continue
                    current = entry.get("state")
                    if state == "replied" and current != "replied":
                        entry["state"] = "replied"
                        entry["replied_at"] = now
                        if preview:
                            entry["reply_preview"] = preview
                        # A reply ends any active follow-up sequence (goal met).
                        seq = ((rec.get("outreach") or {}).get(cid) or {}).get("sequence")
                        if isinstance(seq, dict) and seq.get("status") == "active":
                            seq["status"] = "done"
                    elif state == "connected" and current == "invited":
                        entry["state"] = "connected"
                        entry["connected_at"] = now
                rec["updated_at"] = now

            if search_store.update(path.stem, apply) is not None:
                updated += len(hits)
        return updated

    @app.post("/integrations/webhook")
    async def integrations_webhook(http_request: Request, token: Optional[str] = None) -> Dict[str, Any]:
        # No session: this is Unipile calling us. We authenticate by the token we
        # put in the webhook URL at registration (= UNIPILE_WEBHOOK_SECRET). When a
        # secret is configured it MUST match; always 200 otherwise so Unipile does
        # not retry a payload we simply had no candidate match for.
        secret = (get_unipile_webhook_secret() or "").strip()
        if secret and token != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook token.")
        if not secret:
            logger.warning("[OUTREACH] webhook called with no UNIPILE_WEBHOOK_SECRET configured — accepting (dev only)")
        try:
            event = await http_request.json()
        except Exception:
            return {"ok": True, "updated": 0}
        try:
            interp = outreach_service.interpret_event(event)
            updated = _apply_reply(interp) if interp else 0
        except Exception:
            logger.exception("[OUTREACH] webhook handling failed")
            return {"ok": True, "updated": 0}
        if updated:
            logger.info("[OUTREACH] reply webhook | type=%s updated=%s", (event or {}).get("type"), updated)
        return {"ok": True, "updated": updated}

    # --- RUN: campaign tick (a cron on the server calls this every ~2h) -----
    @app.post("/campaigns/tick")
    def campaigns_tick(token: Optional[str] = None) -> Dict[str, Any]:
        # Token-gated (CAMPAIGN_TICK_SECRET), not session-auth — it's the server's
        # own scheduler calling in. Processes each ACTIVE, due campaign one paced
        # round: enrich the next budgeted batch of reserve matches toward the target.
        secret = (os.environ.get("CAMPAIGN_TICK_SECRET") or "").strip()
        if not secret or token != secret:
            raise HTTPException(status_code=401, detail="Invalid tick token.")
        if intake_service is None:
            return {"ok": True, "processed": 0, "enriched": 0, "note": "engine off"}
        MAX_PER_TICK = 20   # protect the small box — cap campaigns worked per tick
        processed = enriched_total = 0
        for path in Path(search_store.storage_dir).glob("*.json"):
            if processed >= MAX_PER_TICK:
                break
            record = search_store.load(path.stem)
            if not record or not isinstance(record.get("campaign"), dict):
                continue
            if not intake_service.campaign_due(record):
                continue
            # The round does real Harvest + Claude work (slow); run it on the loaded
            # copy OUTSIDE the store lock, then persist only the campaign/pool/response
            # so a recruiter decision made meanwhile (recruiter_decisions) is not lost.
            try:
                result = intake_service.campaign_round(record)
            except Exception:
                logger.exception("[CAMPAIGN] round failed | search_id=%s", path.stem)
                continue

            def persist(fresh: Dict[str, Any], src=record) -> None:
                fresh["campaign"] = src.get("campaign")
                if src.get("internal_diagnostics") is not None:
                    fresh["internal_diagnostics"] = src["internal_diagnostics"]
                if src.get("response") is not None:
                    fresh["response"] = src["response"]
                fresh["updated_at"] = datetime.now(timezone.utc).isoformat()

            search_store.update(path.stem, persist)
            processed += 1
            enriched_total += int(result.get("enriched", 0) or 0)
        logger.info("[CAMPAIGN] tick | processed=%s enriched=%s", processed, enriched_total)
        return {"ok": True, "processed": processed, "enriched": enriched_total}

    @app.post("/parse-jd", dependencies=[Depends(require_session)])
    def parse_jd(request: ParseRequest) -> SearchIntent:
        if intake_service is not None:
            return JSONResponse(intake_service.parse_jd(request.jd_text))
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

    def _validated_boundary(body: SearchBoundaryRequest) -> SearchBoundary:
        try:
            return validate_search_boundary(
                SearchBoundary(
                    hiring_company=body.hiring_company,
                    country=body.country,
                    work_mode=body.work_mode,
                    state=body.state,
                    city=body.city,
                    radius_miles=body.radius_miles,
                    cities=list(body.cities),
                    remote_scope=body.remote_scope,
                    remote_states=list(body.remote_states),
                    remote_cities=list(body.remote_cities),
                )
            )
        except BoundaryValidationError as exc:
            raise HTTPException(status_code=422, detail={"message": "The search boundary is incomplete.", "errors": exc.errors})

    @app.post("/intake/start", dependencies=[Depends(require_session)])
    def intake_start(request: IntakeStartRequest, http_request: Request) -> Dict[str, Any]:
        owner_email = _session_owner(http_request)
        boundary = _validated_boundary(request.boundary)
        if not (request.raw_input or "").strip():
            raise HTTPException(status_code=422, detail={"message": "Describe the role first.", "errors": ["Paste a job description or describe the role."]})
        if intake_service is not None:
            # The role read (LLM, ~30s) runs on a background thread so this request
            # returns at once with an 'understanding' placeholder; the frontend
            # polls GET /intake/{id} until the brief is ready (same pattern as
            # /search). No 30s held connection to time out on OCI.
            started = intake_service.begin(
                request.raw_input, _engine_boundary(boundary, request.boundary),
                posted_title=request.posted_title, hm_notes=request.hm_notes)
            session_id = started["session_id"]
            # Claim ownership before the background read thread starts (no race): the
            # session already exists on disk from begin(), and the store's sticky-owner
            # save then carries owner_email through read_into() and every later write.
            _claim_owner(_intake_store(), session_id, owner_email)

            def _read_role() -> None:
                try:
                    intake_service.read_into(session_id)
                except Exception:
                    logger.exception("[INTAKE] Background role read failed | session_id=%s", session_id)

            threading.Thread(target=_read_role, daemon=True, name=f"intake-read-{session_id}").start()
            return started
        try:
            record = intake_session_manager.start(request.raw_input, boundary=boundary, posted_title=request.posted_title)
        except ConfigurationError as exc:
            logger.warning("Intake reasoning is unavailable", exc_info=exc)
            _raise_recruiter_friendly_error("Unable to understand this role right now.")
        except RecruiterAIError as exc:
            logger.exception("Intake reasoning failed")
            _raise_recruiter_friendly_error("Please contact your administrator.")
        _claim_owner(intake_session_manager._store, record.session_id, owner_email)
        return {"session_id": record.session_id, "result": record.result, "boundary": record.boundary}

    @app.post("/intake/{session_id}/answer", dependencies=[Depends(require_session), Depends(require_owned_session)])
    def intake_answer(session_id: str, request: IntakeAnswerRequest) -> Dict[str, Any]:
        if intake_service is not None:
            try:
                return intake_service.answer(session_id, request.issue_id, request.value, request.label)
            except KeyError:
                raise HTTPException(status_code=404, detail="Intake session not found.")
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

    def _gate_search_request(request: SearchRequest) -> tuple[SearchRequest, Optional[Dict[str, Any]]]:
        """The deterministic guardrail. With confirmation required, a search runs only from a valid confirmed
        snapshot; the browser's own intent, location or description are never used."""
        if request.confirmation_id:
            snapshot = confirmation_store.load(request.confirmation_id)
            if snapshot is None:
                raise HTTPException(status_code=422, detail="This confirmation is not valid. Confirm the brief again before searching.")
            if request.intent is not None or request.location is not None:
                raise HTTPException(status_code=422, detail="A confirmed search cannot also carry its own intent or location.")
            intent = search_intent_from_snapshot(snapshot)
            if not send_confirmed_sentence:
                intent.natural_language_search_query = None
            override = LocationOverride(**location_override_for_search(intent, snapshot["boundary"]))
            return request.model_copy(update={"intent": intent, "location": override, "jd_text": snapshot["raw_input"]}), snapshot
        if require_confirmation:
            raise HTTPException(status_code=409, detail="Confirm the brief before searching.")
        return request, None

    @app.post("/intake/{session_id}/confirmations", dependencies=[Depends(require_session), Depends(require_owned_session)])
    def intake_confirmations(session_id: str, request: ConfirmationRequest) -> Dict[str, Any]:
        """The recruiter presses Search. The server checks the gate, builds the executable intent itself, applies the
        whitelisted edits, and stores an immutable snapshot that /search then runs from."""
        if intake_service is not None:
            try:
                return intake_service.confirm(session_id, request.edits.model_dump())
            except KeyError:
                raise HTTPException(status_code=404, detail="Intake session not found.")
            except ConfirmationNotReady as exc:
                raise HTTPException(status_code=409, detail={"message": "This brief is not ready to search.", "reasons": exc.reasons})
        record = intake_session_manager.get(session_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        try:
            payload = build_snapshot(record, request.edits, query_expander)
        except ConfirmationRefused as exc:
            raise HTTPException(status_code=409, detail={"message": "This brief is not ready to search.", "reasons": exc.reasons})
        snapshot = confirmation_store.create(payload)
        return {**brief_summary(snapshot), "search_intent": snapshot["search_intent"], "edits": snapshot["edits"]}

    @app.get("/intake/{session_id}", dependencies=[Depends(require_session), Depends(require_owned_session)])
    def intake_get(session_id: str) -> Dict[str, Any]:
        """Everything needed to resume a brief after a reload. Read only: no model call."""
        if intake_service is not None:
            try:
                data = intake_service.get(session_id)
            except IntakeReadError:
                _raise_recruiter_friendly_error("Unable to understand this role right now. Please try again.", status_code=502)
            if data is None:
                raise HTTPException(status_code=404, detail="Intake session not found.")
            return data
        record = intake_session_manager.get(session_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        return {
            "session_id": record.session_id,
            "result": record.result,
            "boundary": record.boundary,
            "posted_title_input": record.posted_title_input,
        }

    @app.patch("/intake/{session_id}/boundary", dependencies=[Depends(require_session), Depends(require_owned_session)])
    def intake_update_boundary(session_id: str, request: SearchBoundaryRequest) -> Dict[str, Any]:
        """The recruiter edits the Search Boundary. Deterministic: validated and re-applied to the pinned reading with
        no model call."""
        boundary = _validated_boundary(request)
        if intake_service is not None:
            try:
                return intake_service.update_boundary(session_id, _engine_boundary(boundary, request))
            except KeyError:
                raise HTTPException(status_code=404, detail="Intake session not found.")
        try:
            record = intake_session_manager.update_boundary(session_id, boundary)
        except KeyError:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"session_id": record.session_id, "result": record.result, "boundary": record.boundary}

    @app.post("/intake/{session_id}/confirm", dependencies=[Depends(require_session), Depends(require_owned_session)])
    def intake_confirm(session_id: str) -> SearchIntent:
        if intake_service is not None:
            try:
                return JSONResponse(intake_service.search_intent_preview(session_id))
            except KeyError:
                raise HTTPException(status_code=404, detail="Intake session not found.")
            except ConfirmationNotReady as exc:
                raise HTTPException(status_code=409, detail={"message": "This brief is not ready to search.", "reasons": exc.reasons})
        record = intake_session_manager.get(session_id)
        if record is None or record.result is None:
            raise HTTPException(status_code=404, detail="Intake session not found.")
        try:
            return to_search_intent(build_confirmed_hiring_intent(record.result, boundary=record.boundary), query_expander=query_expander)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/intake/{session_id}/preview", dependencies=[Depends(require_session), Depends(require_owned_session)])
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

    def _search_response(record: Dict[str, Any]) -> SearchResponse:
        # record["response"] is the snapshot from whenever the search last ran — recruiter_decisions/notes are updated
        # separately (PATCH, below) and live at the top level of the record, not inside that snapshot, so they must be
        # merged in here rather than trusted to already be present on it.
        response_data = dict(record["response"])
        # Backfills presentation-only fields (career/photo/open-to-work) from
        # already-stored raw CrustData/Harvest data on a search persisted
        # before those fields existed on CandidateEvidence. No network call,
        # no change to role_alignment/requirement_judgments/ranking/admission
        # — see candidate_evidence_builder.rehydrate_response_evidence.
        response_data["evidence"] = rehydrate_response_evidence(
            response_data.get("candidates") or [],
            response_data.get("evidence") or [],
            record.get("harvest_evidence"),
        )
        response_data["recruiter_decisions"] = record.get("recruiter_decisions", {})
        response_data["notes"] = record.get("notes", {})
        response_data["workspace_arranged"] = bool(record.get("workspace_arranged", False))
        response_data["confirmed_brief"] = record.get("confirmed_brief")
        response_data["status"] = record.get("status", response_data.get("status", "complete"))
        response_data["outreach"] = record.get("outreach", {})
        response_data["campaign"] = record.get("campaign")
        response_data.update(derived_fields(record, clock()))
        return SearchResponse(**response_data)

    def _restore_stored_ranked_candidates(search_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Promote already-enriched reserve rows after first-batch validation.

        This is a local, idempotent restore from the stored ranking pool. It makes
        older campaign records show the same rich candidate cards without another
        provider or Harvest call. Raw, un-enriched reserve entries are untouched.
        """
        if intake_service is None or not record.get("role"):
            return record
        first_ids = role_lifecycle.initial_validation_ids(record)
        decisions = record.get("recruiter_decisions") or {}
        if not first_ids or any(decisions.get(cid) not in ("shortlist", "maybe", "reject") for cid in first_ids):
            return record
        pool = ((record.get("internal_diagnostics") or {}).get("pool") or {})
        response_ids = {candidate.get("candidate_id") for candidate in (record.get("response") or {}).get("candidates") or []}
        held = [entry for entry in pool.get("judged") or []
                if entry.get("candidate_id") and not entry.get("shown") and entry.get("candidate_id") not in response_ids]
        if not held:
            return record

        restored: Dict[str, Any] = {}
        def apply(current: Dict[str, Any]) -> None:
            ids = intake_service.reveal_batch(current, len(held))
            if not ids:
                return
            presentation = current.setdefault("presentation", {})
            batch = presentation_rules.next_batch_number(current)
            for candidate_id in ids:
                presentation[candidate_id] = {
                    "state": presentation_rules.PRESENTED, "source": "validated-pool",
                    "seen": True, "batch": batch,
                }
            current["campaign_initial_ids"] = first_ids
            pool_now = ((current.get("internal_diagnostics") or {}).get("pool") or {})
            visible = {candidate.get("candidate_id") for candidate in (current.get("response") or {}).get("candidates") or []}
            pool_now.setdefault("counts", {})["shown"] = len(visible)
            current["response"]["reserve_available"] = sum(
                1 for entry in pool_now.get("judged") or []
                if not entry.get("shown") and entry.get("candidate_id") not in visible
            )
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            restored["ids"] = ids

        updated = search_store.update(search_id, apply)
        return updated or record

    @app.get("/searches", dependencies=[Depends(require_session)])
    def list_searches(request: Request) -> Dict[str, Any]:
        """The workspace sidebar: every role, plus briefs that have not been searched yet. Newest activity first
        within each group — but completed searches and drafts are two separate lists with two separate budgets
        (SIDEBAR_SEARCH_LIMIT, SIDEBAR_DRAFT_LIMIT), not one shared, recency-sorted list. A flood of drafts (a
        recruiter's own, or test-generated ones sharing the default storage path) can only ever crowd out an
        OLDER DRAFT — never a completed search. Completed searches are listed first, by identity (search_id),
        never merged or de-duplicated by title."""
        searches: List[Dict[str, Any]] = []
        used_sessions: set = set()
        now = clock()
        for path in Path(search_store.storage_dir).glob("*.json"):
            summary = search_summary_cache.get(search_store, path,
                                               getattr(intake_service, "_confirmations", None))
            if summary is None:
                continue
            # Per-user isolation: a recruiter's sidebar lists only their own roles; the
            # super admin sees every one. Unowned legacy records are admin-only.
            if not _can_access({"owner_email": summary.get("owner_email")}, request):
                continue
            # `archived` is time-dependent (explicit Close + the 14-day idle rule), so it
            # is computed here against the live clock rather than cached in the summary.
            item = {**summary["summary"], "archived": is_archived(summary["summary"], now)}
            searches.append(item)
            if summary["session_id"]:
                used_sessions.add(summary["session_id"])
        searches.sort(key=lambda item: item.get("updated_at") or "", reverse=True)

        cutoff = datetime.now(timezone.utc).timestamp() - DRAFT_VISIBLE_SECONDS
        drafts: List[Dict[str, Any]] = []
        for draft in list_draft_summaries(intake_session_manager):
            if draft["session_id"] in used_sessions or not draft.get("boundary"):
                continue
            if not _can_access({"owner_email": draft.get("owner_email")}, request):
                continue
            updated = datetime.fromisoformat(draft["updated_at"]).timestamp()
            if updated >= cutoff:
                drafts.append(draft_summary(draft))
        drafts.sort(key=lambda item: item.get("updated_at") or "", reverse=True)

        items = searches[:SIDEBAR_SEARCH_LIMIT] + drafts[:SIDEBAR_DRAFT_LIMIT]
        return {"searches": items}

    @app.get("/search/{search_id}", response_model=SearchResponse, dependencies=[Depends(require_session), Depends(require_owned_search)])
    def get_search(search_id: str) -> SearchResponse:
        role_runtime.tick_record(search_id)
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        record = _restore_stored_ranked_candidates(search_id, record)
        logger.info("[SEARCH] Reloaded persisted search | search_id=%s — no OpenAI or CrustData calls made", search_id)
        return _search_response(record)

    @app.patch("/search/{search_id}/workspace", dependencies=[Depends(require_session), Depends(require_owned_search)])
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

    def _maybe_start_feedback_pool_analysis(search_id: str) -> None:
        """After a clear first-batch signal, deep-read the held 40 from the paid pull.

        The CrustData search is not repeated here. The cheap admission screen,
        Harvest and Judge are run against the already stored reserve profiles.
        """
        if intake_service is None:
            return
        trigger: Dict[str, Any] = {}

        def claim(record: Dict[str, Any]) -> None:
            role = record.get("role") or {}
            first_ids = role_lifecycle.initial_validation_ids(record)
            decisions = record.get("recruiter_decisions") or {}
            decided = [decisions.get(cid) for cid in first_ids if decisions.get(cid) in ("shortlist", "maybe", "reject")]
            if not first_ids or len(decided) < len(first_ids) or role.get("status") != role_lifecycle.SEARCHING:
                return
            record["campaign_initial_ids"] = first_ids
            shortlist = decided.count("shortlist")
            maybe = decided.count("maybe")
            # Positive validation, per spec: 3 Shortlist, OR 2 Shortlist + 1 Maybe.
            # Only a positive validation unlocks surfacing every closely-aligned reserve
            # profile without re-admitting 10 or validating a second five. Anything short
            # of that is a refine signal — the recruiter adjusts the brief and re-validates
            # (via Refine), it does not dump the whole reserve.
            positive_validation = shortlist >= 3 or (shortlist >= 2 and maybe >= 1)
            if not positive_validation:
                return
            feedback_hash = hashlib.sha256(json.dumps({
                "decisions": decisions,
                "feedback_events": record.get("feedback_events") or [],
            }, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            if role.get("reserve_analysis_state") == "running" or role.get("reserve_analysis_feedback_hash") == feedback_hash:
                return
            pool = ((record.get("internal_diagnostics") or {}).get("pool") or {})
            reserve = list(pool.get("reserve") or [])
            if not reserve:
                return
            role["reserve_analysis_state"] = "running"
            role["reserve_analysis_signal"] = "positive"
            role["reserve_analysis_feedback_hash"] = feedback_hash
            record["role"] = role
            # RUN auto-start: the one Go-validation opens the campaign. From here the
            # search flows on its own — this first positive-validation pass is the
            # campaign's first round; the 2h cron (/campaigns/tick) paces the rest and
            # STEER (refine) course-corrects it. Idempotent, so a refine mid-campaign
            # won't restart it. The deep-reads this pass spends are counted against the
            # budget in `persist` below, so the budget cap is a single running total.
            intake_service.start_campaign(record)
            trigger.update({"confirmation_id": (record.get("confirmed_brief") or {}).get("confirmation_id"),
                            "reserve": reserve, "signal": role["reserve_analysis_signal"],
                            "feedback_record": record, "feedback_hash": feedback_hash})

        search_store.update(search_id, claim)
        if not trigger:
            return

        def analyze() -> None:
            try:
                result = intake_service.analyze_reserve(trigger["confirmation_id"], trigger["reserve"],
                                                       feedback_record=trigger.get("feedback_record"))
                new_pool = result.pop("pool", {})
                def persist(record: Dict[str, Any]) -> None:
                    response = record.get("response") or {}
                    diag = record.setdefault("internal_diagnostics", {})
                    pool = diag.setdefault("pool", {"judged": [], "reserve": [], "counts": {}})
                    known = {e.get("candidate_id") for e in pool.get("judged") or []}
                    analyzed = [e for e in new_pool.get("judged") or [] if e.get("candidate_id") not in known]
                    pool["judged"] = list(pool.get("judged") or []) + analyzed
                    pool["reserve"] = list(new_pool.get("reserve") or [])
                    existing_ids = {c.get("candidate_id") for c in response.get("candidates") or []}
                    additions = [i for i, c in enumerate(result.get("candidates") or [])
                                 if c.get("candidate_id") not in existing_ids]
                    for field in ("candidates", "explanations", "evidence"):
                        response[field] = list(response.get(field) or []) + [
                            (result.get(field) or [])[i] for i in additions if i < len(result.get(field) or [])
                        ]
                    response["candidate_count"] = len(response.get("candidates") or [])
                    response["candidate_states"] = {**(response.get("candidate_states") or {}),
                        **{(result.get("candidates") or [])[i].get("candidate_id"): "review_ready" for i in additions}}
                    pool["counts"] = {"judged": len(pool.get("judged") or []),
                        "reserve": len(pool.get("reserve") or []), "shown": response["candidate_count"],
                        "total": len(pool.get("judged") or []) + len(pool.get("reserve") or [])}
                    response["reserve_available"] = sum(1 for e in pool.get("judged") or []
                        if not e.get("shown") and e.get("candidate_id") not in existing_ids)
                    revealed_ids = intake_service.reveal_batch(record, 500)
                    presentation = record.setdefault("presentation", {})
                    batch_number = presentation_rules.next_batch_number(record)
                    for candidate_id in additions + revealed_ids:
                        presentation[candidate_id] = {
                            "state": presentation_rules.PRESENTED, "source": "validated-pool",
                            "seen": True, "batch": batch_number,
                        }
                    # Initial admitted candidates held behind the first-five
                    # validation and feedback-qualified reserve candidates now
                    # share one rich response. Keep evidence arrays aligned.
                    rows = list(zip(response.get("candidates") or [], response.get("explanations") or [],
                                    response.get("evidence") or []))
                    rows.sort(key=lambda row: -(row[0].get("final_score") or 0.0))
                    response["candidates"] = [row[0] for row in rows]
                    response["explanations"] = [row[1] for row in rows]
                    response["evidence"] = [row[2] for row in rows]
                    response["candidate_count"] = len(rows)
                    pool["counts"]["shown"] = len(rows)
                    visible_ids = {candidate.get("candidate_id") for candidate in response.get("candidates") or []}
                    response["reserve_available"] = sum(
                        1 for entry in pool.get("judged") or []
                        if not entry.get("shown") and entry.get("candidate_id") not in visible_ids
                    )
                    response["status"] = "complete"
                    record["response"] = response
                    record["role"]["reserve_analysis_state"] = "complete"
                    record["role"]["reserve_analysis_signal"] = trigger["signal"]
                    record["role"]["reserve_analysis_added"] = len(additions)
                    record["role"]["reserve_analysis_feedback_hash"] = trigger["feedback_hash"]
                    # Count this pass's deep-reads against the campaign budget so the
                    # cap is one running total across the Go-pass and every cron round.
                    campaign = record.get("campaign")
                    if isinstance(campaign, dict) and campaign.get("status") == "active":
                        campaign["used"] = int(campaign.get("used") or 0) + len(additions)
                        campaign["rounds"] = int(campaign.get("rounds") or 0) + 1
                        campaign["last_round_at"] = datetime.now(timezone.utc).isoformat()
                        if campaign["used"] >= int(campaign.get("budget") or 0):
                            campaign["status"] = "done"; campaign["done_reason"] = "budget"
                        record["campaign"] = campaign
                    record["updated_at"] = datetime.now(timezone.utc).isoformat()
                search_store.update(search_id, persist)
                # If the recruiter refined feedback while this pass was running,
                # screen any remaining reserve under the newest decisions too.
                _maybe_start_feedback_pool_analysis(search_id)
            except Exception:
                logger.exception("[SEARCH] Feedback pool analysis failed | search_id=%s", search_id)
                def failed(record: Dict[str, Any]) -> None:
                    role = record.get("role") or {}
                    role["reserve_analysis_state"] = "failed"
                    record["role"] = role
                    record["updated_at"] = datetime.now(timezone.utc).isoformat()
                search_store.update(search_id, failed)

        threading.Thread(target=analyze, daemon=True, name=f"feedback-pool-{search_id}").start()

    @app.patch("/search/{search_id}/candidate", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def update_candidate(search_id: str, update: CandidateUpdateRequest) -> SearchResponse:
        failure: List[RoleError] = []

        def apply(record: Dict[str, Any]) -> None:
            try:
                apply_candidate_update(
                    record,
                    search_id=search_id,
                    candidate_id=update.candidate_id,
                    decision=update.decision,
                    note=update.note,
                    feedback_reason=update.feedback_reason,
                    feedback_note=update.feedback_note,
                    now=clock(),
                )
            except RoleError as error:
                failure.append(error)

        # update() is atomic with respect to the running search's own progress saves, so a decision recorded
        # mid-search is never overwritten by the pipeline's next write (and vice versa).
        record = search_store.update(search_id, apply)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        if failure:
            raise HTTPException(status_code=failure[0].status_code, detail=failure[0].message)
        logger.info("[SEARCH] Recruiter decision/note persisted | search_id=%s candidate_id=%s", search_id, update.candidate_id)
        if intake_service is not None:
            _maybe_start_feedback_pool_analysis(search_id)
            record = search_store.load(search_id) or record
        return _search_response(record)

    @app.post("/search/{search_id}/reveal", response_model=SearchResponse, dependencies=[Depends(require_session), Depends(require_owned_search)])
    def reveal_candidate(search_id: str) -> SearchResponse:
        # Pool-first reveal (new engine): bring the next already-read profile forward
        # from the held pool — no new search, no credits. A no-op (returns the search
        # unchanged) when the free pool is exhausted; reaching wider is a separate,
        # credit-gated step (the refine flow).
        if intake_service is None:
            raise HTTPException(status_code=404, detail="Reveal is not available for this search.")
        current = search_store.load(search_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        first_ids = role_lifecycle.initial_validation_ids(current)
        decisions = current.get("recruiter_decisions") or {}
        if first_ids and any(decisions.get(cid) not in ("shortlist", "maybe", "reject") for cid in first_ids):
            raise HTTPException(status_code=409, detail="Please validate all five initial candidates before viewing more.")
        outcome = {"revealed": False}

        def apply(record: Dict[str, Any]) -> None:
            ids = intake_service.reveal_batch(record, 1)
            outcome["revealed"] = bool(ids)
            for candidate_id in ids:
                record.setdefault("presentation", {})[candidate_id] = {
                    "state": presentation_rules.PRESENTED, "source": "pool-reveal", "seen": False,
                }
            if ids:
                record["updated_at"] = datetime.now(timezone.utc).isoformat()

        record = search_store.update(search_id, apply)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Pool-first reveal | search_id=%s revealed=%s", search_id, outcome["revealed"])
        return _search_response(record)

    # --- Outreach on a candidate (Phase 1, step 3) -------------------------
    # Both are scoped to an owned search (require_owned_search), so the candidate
    # and the evidence to draft from come from the recruiter's own record, and the
    # sending account is resolved from the session owner — never from the client.
    def _find_candidate(record: Dict[str, Any], candidate_id: str) -> tuple:
        response = record.get("response") or {}
        candidates = response.get("candidates") or []
        evidence = response.get("evidence") or []
        for index, candidate in enumerate(candidates):
            if candidate.get("candidate_id") == candidate_id:
                return candidate, (evidence[index] if index < len(evidence) else {})
        return None, None

    def _candidate_email(candidate: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> Optional[str]:
        return candidate.get("email") or ((evidence or {}).get("contact") or {}).get("email")

    @app.post("/search/{search_id}/outreach/draft", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def outreach_draft(search_id: str, request: OutreachDraftRequest, http_request: Request) -> Dict[str, Any]:
        from backend.services.outreach_draft import draft_outreach, fallback_draft
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        candidate, evidence = _find_candidate(record, request.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found in this search.")
        owner = _session_owner(http_request) or ""
        role = record.get("confirmed_brief") or record.get("role") or {}
        channel = (request.channel or "").strip().lower()
        sender = outreach_service.sender_name(owner, channel)
        try:
            return draft_outreach(channel, candidate=candidate, evidence=evidence, role=role,
                                  recruiter_name=sender, inmail=request.inmail, tone=request.tone, reply_to=request.reply_to)
        except Exception:
            logger.exception("[OUTREACH] draft generation failed | search_id=%s channel=%s", search_id, channel)
            return fallback_draft(channel, candidate=candidate, role=role, recruiter_name=sender, inmail=request.inmail)

    @app.get("/integrations/outreach/limits", dependencies=[Depends(require_session)])
    def outreach_limits(http_request: Request) -> Dict[str, Any]:
        owner = _session_owner(http_request) or ""
        return {"limits": outreach_service.usage(owner)}

    @app.get("/integrations/outreach/inbox", dependencies=[Depends(require_session)])
    def outreach_inbox(http_request: Request) -> Dict[str, Any]:
        """Every candidate THIS recruiter has reached out to, across all their
        searches — the replies & outreach view. Owner-scoped by reading only this
        recruiter's own search records; replies float to the top."""
        from backend.services.sequence import next_due as _sequence_due
        owner = (_session_owner(http_request) or "").lower()
        rows: List[Dict[str, Any]] = []
        for path in Path(search_store.storage_dir).glob("*.json"):
            record = search_store.load(path.stem)
            if not record or (record.get("owner_email") or "").lower() != owner:
                continue
            outreach = record.get("outreach") or {}
            if not outreach:
                continue
            response = record.get("response") or {}
            cand_by_id = {c.get("candidate_id"): c for c in (response.get("candidates") or [])}
            brief = record.get("confirmed_brief") or {}
            role_title = brief.get("posted_title") or ((record.get("role") or {}).get("label") or {}).get("title") or "Untitled role"
            for candidate_id, channels in outreach.items():
                if not isinstance(channels, dict):
                    continue
                chan = {k: v for k, v in channels.items() if isinstance(v, dict) and v.get("state")}
                if not chan:
                    continue
                cand = cand_by_id.get(candidate_id) or {}
                times = [v[key] for v in chan.values() for key in ("replied_at", "connected_at", "at") if v.get(key)]
                replied = any(v.get("state") == "replied" for v in chan.values())
                seq = channels.get("sequence") if isinstance(channels.get("sequence"), dict) else None
                rows.append({
                    "search_id": path.stem,
                    "candidate_id": candidate_id,
                    "name": cand.get("name") or "Candidate",
                    "profile_url": cand.get("profile_url"),
                    "role_title": role_title,
                    "channels": chan,
                    "sequence": seq,
                    "sequence_due": (_sequence_due(seq, channels) if seq else None),
                    "last_activity": max(times) if times else None,
                    "replied": replied,
                })
        rows.sort(key=lambda r: r.get("last_activity") or "", reverse=True)  # most recent first
        rows.sort(key=lambda r: 0 if r["replied"] else 1)                    # stable: replies on top
        return {"inbox": rows, "counts": {"total": len(rows), "replied": sum(1 for r in rows if r["replied"])}}

    @app.post("/search/{search_id}/outreach/send", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def outreach_send(search_id: str, request: OutreachSendRequest, http_request: Request) -> Dict[str, Any]:
        from backend.providers.unipile import UnipileAPIError, UnipileError, UnipileNotConfiguredError
        from backend.services.outreach import OutreachActionError, OutreachLimitError, send_category
        owner = _session_owner(http_request)
        if not owner:
            raise HTTPException(status_code=401, detail="Sign in first.")
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        candidate, evidence = _find_candidate(record, request.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found in this search.")
        channel = (request.channel or "").strip().lower()
        category = send_category(channel, inmail=request.inmail)
        try:
            outreach_service.check_limit(owner, category)
        except OutreachLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        try:
            if channel == "linkedin":
                if request.inmail:
                    result = outreach_service.message_linkedin(owner, profile_url=candidate.get("profile_url"), text=request.body, inmail=True)
                else:
                    result = outreach_service.connect_linkedin(owner, profile_url=candidate.get("profile_url"), note=request.body)
            elif channel == "email":
                result = outreach_service.email_candidate(
                    owner, to_email=_candidate_email(candidate, evidence),
                    subject=request.subject, body=request.body, display_name=candidate.get("name"),
                )
            else:
                raise HTTPException(status_code=400, detail="Unknown outreach channel.")
        except OutreachActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except UnipileNotConfiguredError:
            raise HTTPException(status_code=503, detail="Outreach isn't enabled yet.")
        except UnipileAPIError as exc:
            raise HTTPException(status_code=502, detail=(exc.detail or exc.title or "That message was rejected by the provider."))
        except UnipileError:
            logger.exception("[OUTREACH] send failed | search_id=%s channel=%s", search_id, channel)
            raise HTTPException(status_code=502, detail="Couldn't send that right now. Please try again.")

        def apply(rec: Dict[str, Any]) -> None:
            from backend.services.sequence import advance_on_send
            entry = rec.setdefault("outreach", {}).setdefault(request.candidate_id, {})
            entry[channel] = result
            # If this candidate is mid-sequence, a send advances it (approve-each:
            # the human just sent the step, we only record the progress).
            seq = entry.get("sequence")
            if isinstance(seq, dict) and seq.get("status") == "active":
                advance_on_send(seq, channel, request.inmail)

        updated = search_store.update(search_id, apply)
        outreach_service.record_send(owner, category)  # count only a send that actually went out
        logger.info("[OUTREACH] sent | search_id=%s candidate=%s channel=%s state=%s", search_id, request.candidate_id, channel, result.get("state"))
        entry = ((updated or {}).get("outreach") or {}).get(request.candidate_id, {})
        return {"candidate_id": request.candidate_id, "channel": channel, "outreach": result,
                "sequence": entry.get("sequence"), "limits": outreach_service.usage(owner)}

    @app.post("/search/{search_id}/outreach/sequence/enroll", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def outreach_sequence_enroll(search_id: str, request: SequenceRequest) -> Dict[str, Any]:
        from backend.services.sequence import new_enrollment, next_due
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        candidate, _ = _find_candidate(record, request.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found in this search.")

        def apply(rec: Dict[str, Any]) -> None:
            entry = rec.setdefault("outreach", {}).setdefault(request.candidate_id, {})
            seq = entry.get("sequence")
            if not (isinstance(seq, dict) and seq.get("status") == "active"):
                entry["sequence"] = new_enrollment()

        updated = search_store.update(search_id, apply) or record
        entry = (updated.get("outreach") or {}).get(request.candidate_id, {})
        seq = entry.get("sequence")
        return {"sequence": seq, "due": next_due(seq, entry)}

    @app.post("/search/{search_id}/outreach/sequence/stop", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def outreach_sequence_stop(search_id: str, request: SequenceRequest) -> Dict[str, Any]:
        def apply(rec: Dict[str, Any]) -> None:
            seq = ((rec.get("outreach") or {}).get(request.candidate_id) or {}).get("sequence")
            if isinstance(seq, dict) and seq.get("status") == "active":
                seq["status"] = "stopped"

        updated = search_store.update(search_id, apply)
        if updated is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        seq = ((updated.get("outreach") or {}).get(request.candidate_id) or {}).get("sequence")
        return {"sequence": seq}

    @app.post("/search/{search_id}/campaign/start", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def campaign_start(search_id: str, request: CampaignStartRequest) -> Dict[str, Any]:
        if intake_service is None:
            raise HTTPException(status_code=400, detail="Campaigns need the new engine.")
        record = search_store.load(search_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        # Go: open the campaign and run the first paced batch now so the recruiter
        # sees results immediately; the cron continues subsequent rounds. Heavy work
        # on the loaded copy outside the store lock, then persist campaign/pool/response.
        intake_service.start_campaign(record, window_hours=request.window_hours, budget=request.budget)
        result = intake_service.campaign_round(record)

        def persist(fresh: Dict[str, Any]) -> None:
            fresh["campaign"] = record.get("campaign")
            if record.get("internal_diagnostics") is not None:
                fresh["internal_diagnostics"] = record["internal_diagnostics"]
            if record.get("response") is not None:
                fresh["response"] = record["response"]
            fresh["updated_at"] = datetime.now(timezone.utc).isoformat()

        search_store.update(search_id, persist)
        logger.info("[CAMPAIGN] started | search_id=%s round=%s", search_id, result)
        return {"campaign": record.get("campaign"), "round": result}

    @app.post("/search/{search_id}/refine", response_model=SearchResponse, dependencies=[Depends(require_session), Depends(require_owned_search)])
    def refine_search(search_id: str, request: RefineRequest) -> SearchResponse:
        # Pool-first refine (new engine): re-check + re-rank the already-read pool
        # against the recruiter's structured deltas — free, instant, no new search.
        # When nothing in the read pool matches, the view is kept and `refine_outcome`
        # reports exhausted so the UI can offer a (credit-gated) wider search.
        if intake_service is None:
            raise HTTPException(status_code=404, detail="Refine is not available for this search.")
        outcome: Dict[str, Any] = {}

        def apply(record: Dict[str, Any]) -> None:
            outcome.update(intake_service.refine(record, request.model_dump(exclude_none=True)))

        record = search_store.update(search_id, apply)
        if record is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        logger.info("[SEARCH] Pool-first refine | search_id=%s matched=%s dropped=%s exhausted=%s",
                    search_id, outcome.get("matched"), outcome.get("dropped"), outcome.get("exhausted"))
        return _search_response(record)

    @app.post("/search/{search_id}/more", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def show_more(search_id: str, request: Optional[ShowMoreRequest] = None) -> Dict[str, Any]:
        current = search_store.load(search_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Search not found.")
        # A cycle already in flight is refused outright — this must come before the validation gate, so "still working"
        # is never masked by a "please validate first" reply while a retrieval is running.
        if current.get("status") == STATUS_RUNNING:
            raise HTTPException(status_code=409, detail="RecruiterAI is still working on this search.")
        first_ids = role_lifecycle.initial_validation_ids(current)
        decisions = current.get("recruiter_decisions") or {}
        if first_ids and any(decisions.get(cid) not in ("shortlist", "maybe", "reject") for cid in first_ids):
            return {"presented": 0, "cycle_started": False, "exhausted": False,
                    "message": "Please validate all five initial candidates before viewing more."}
        """"Show me more”: reveal only stored profiles; campaign scheduler owns all new paid retrieval."""
        # "Review new" (only_new) is a different request: it surfaces the quietly-added daily candidates, not the next
        # slice of the campaign pool, so it skips the pool reveal and uses the quiet-filtered reveal below.
        if intake_service is not None and not (request and request.only_new):
            record = current
            if (record.get("internal_diagnostics") or {}).get("pool"):
                if record.get("status") == STATUS_RUNNING:
                    raise HTTPException(status_code=409, detail="RecruiterAI is still working on this search.")
                outcome: Dict[str, Any] = {}
                def reveal_stored(record_to_update: Dict[str, Any]) -> None:
                    ids = intake_service.reveal_batch(record_to_update, presentation_rules.MORE_BATCH)
                    # Each reveal is its own presentation batch, so the workspace can still tell the recruiter
                    # which set a candidate was shown in (parity with the cursor-cycle reveal path).
                    batch_number = presentation_rules.next_batch_number(record_to_update)
                    for candidate_id in ids:
                        record_to_update.setdefault("presentation", {})[candidate_id] = {
                            "state": presentation_rules.PRESENTED, "source": "pool-reveal", "seen": False,
                            "batch": batch_number,
                        }
                    if ids:
                        record_to_update["updated_at"] = datetime.now(timezone.utc).isoformat()
                    outcome["ids"] = ids
                record = search_store.update(search_id, reveal_stored)
                if record is None:
                    raise HTTPException(status_code=404, detail="Search not found.")
                ids = outcome.get("ids") or []
                if ids:
                    return {"presented": len(ids), "cycle_started": False, "exhausted": False,
                            "message": f"Revealed {len(ids)} already-assessed candidates from this campaign pool."}
        try:
            outcome = role_runtime.show_more(search_id, only_new=bool(request and request.only_new))
        except RoleError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message)
        return outcome

    @app.post("/search/{search_id}/role", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def role_action(search_id: str, request: RoleActionRequest) -> SearchResponse:
        try:
            record = role_runtime.set_role_action(search_id, request.action)
        except RoleError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message)
        return _search_response(record)

    @app.post("/search/{search_id}/calibration", dependencies=[Depends(require_session), Depends(require_owned_search)])
    def calibration_correction(search_id: str, request: CalibrationRequest) -> SearchResponse:
        try:
            record = role_runtime.calibrate(search_id, request.dismiss)
        except RoleError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message)
        return _search_response(record)

    def _search_role(request: SearchRequest, snapshot: Dict[str, Any], confirmed_brief: Dict[str, Any], search_id: str, owner_email: Optional[str] = None) -> SearchResponse:
        """A search from a confirmed brief is a ROLE. The first time it is confirmed it starts (Day 0). Confirming a
        changed brief on the same role is a meaningful change when it alters what is searched: the role is extended
        by a day (within its limit) and a fresh retrieval runs. A confirmation that changes nothing searched re-runs
        nothing."""
        now = clock()
        with search_store.lock:
            existing = search_store.load(search_id) or {}
            existing_role = existing.get("role")
            if existing_role and existing.get("status") == STATUS_RUNNING:
                raise HTTPException(status_code=409, detail="RecruiterAI is still working on this search.")

            has_inventory = bool((existing.get("response") or {}).get("candidates"))
            restart = not existing_role or existing.get("status") in ("error", "interrupted") or not has_inventory
            changed: List[str] = []
            if not restart:
                previous = confirmation_store.load((existing.get("confirmed_brief") or {}).get("confirmation_id") or "")
                changed = meaningful_changes(previous["search_intent"], snapshot["search_intent"]) if previous else ["the brief"]
                if not changed:
                    existing["confirmed_brief"] = confirmed_brief
                    existing["updated_at"] = now.isoformat()
                    search_store.save(search_id, existing)
                    logger.info("[SEARCH] Confirmation changes nothing that is searched; no new retrieval | search_id=%s", search_id)
                    return _search_response(existing)

            record = dict(existing)
            record.update(
                {
                    "search_id": search_id,
                    "status": STATUS_RUNNING,
                    "owner_email": existing.get("owner_email") or owner_email,
                    "created_at": existing.get("created_at", now.isoformat()),
                    "updated_at": now.isoformat(),
                    "jd_text": snapshot["raw_input"],
                    "confirmed_brief": confirmed_brief,
                    "recruiter_decisions": existing.get("recruiter_decisions", {}),
                    "notes": existing.get("notes", {}),
                    "harvest_evidence": existing.get("harvest_evidence", {}),
                    "internal_diagnostics": existing.get("internal_diagnostics", {}) if not restart else {},
                    "feedback_events": existing.get("feedback_events", []),
                    "provider": request.provider,
                }
            )
            if restart:
                duration_days = request.campaign_duration_days if request.campaign_duration_days in (1, 3) else 1
                role = existing_role or role_lifecycle.new_role(now, label=sidebar_label(snapshot), duration_days=duration_days)
                role["label"] = sidebar_label(snapshot)
                record.update(
                    {
                        "role": role,
                        "presentation": {},
                        "cycles": [],
                        "retrieval": None,
                        "availability": None,
                        "candidate_states": {},
                        "response": {
                            "provider": "platform", "search_id": search_id, "candidate_count": 0, "candidates": [], "explanations": [],
                            "evidence": [], "diagnostics": {}, "warnings": [], "debug": None, "status": STATUS_RUNNING,
                            "candidate_states": {}, "progress": {"admitted": 0, "surfaced": 0, "building_context": 0, "review_ready": 0},
                        },
                    }
                )
                record.pop("calibration", None)
                cycle = {"kind": "initial", "n": 1, "cursor": None, "dedupe": "all", "present": presentation_rules.INITIAL_BATCH, "confirmation_id": snapshot["confirmation_id"]}
            else:
                role = record["role"]
                role["label"] = sidebar_label(snapshot)
                role_lifecycle.extend_for_change(role, now, changed)
                # Candidates held in reserve under the old brief are not offered as if they were found under the new one;
                # any that the new retrieval finds again are refreshed and offered again.
                for entry in (record.get("presentation") or {}).values():
                    if entry.get("state") == presentation_rules.RESERVE:
                        entry["stale"] = True
                cycle = {"kind": "change", "n": len(record.get("cycles") or []) + 1, "cursor": None, "dedupe": "presented", "present": presentation_rules.MORE_BATCH, "confirmation_id": snapshot["confirmation_id"]}
            search_store.save(search_id, record)
            start_cycle(search_id, snapshot, cycle, build_guidance(record) if not restart else Guidance(), provider_name=request.provider)
            return _search_response(search_store.load(search_id) or record)

    @app.post("/search", response_model=SearchResponse, dependencies=[Depends(require_session)])
    def search(request: SearchRequest, http_request: Request) -> SearchResponse:
        owner_email = _session_owner(http_request)
        # POST /search carries the id in the BODY, not the path, so the route guard
        # can't run here — enforce ownership inline: a caller may only (re)run a search
        # whose id either is new or is already theirs. Hijacking another recruiter's
        # campaign by posting their id is a 404, same as any other cross-user access.
        if request.search_id:
            existing_owned = search_store.load(request.search_id)
            if existing_owned is not None and not _can_access(existing_owned, http_request):
                raise HTTPException(status_code=404, detail="Search not found.")
        if intake_service is not None:
            if not request.confirmation_id:
                raise HTTPException(status_code=409, detail="Confirm the brief before searching.")
            search_id = request.search_id or str(uuid.uuid4())
            provider_name = request.provider or "crustdata"
            confirmation_id = request.confirmation_id
            model = intake_service._confirmations.load(confirmation_id)
            if model is None:
                raise HTTPException(status_code=409, detail="Confirm the brief again before searching.")
            existing = search_store.load(search_id) or {}
            now = datetime.now(timezone.utc).isoformat()
            duration_days = request.campaign_duration_days if request.campaign_duration_days in (1, 3) else 1
            now_dt = datetime.now(timezone.utc)
            existing_role = existing.get("role")
            if existing_role:
                role_lifecycle.tick(existing_role, now_dt)
            if existing_role and role_lifecycle.campaign_budget_exhausted(existing):
                raise HTTPException(status_code=409, detail="This campaign has used its credit allowance. Start a new search to begin another campaign.")
            if existing_role and existing_role.get("status") == role_lifecycle.PAUSED and not role_lifecycle.resume(existing_role, now_dt):
                raise HTTPException(status_code=409, detail="This campaign window has ended. Start a new search to begin another campaign.")
            role = existing_role or role_lifecycle.new_role(now_dt, duration_days=duration_days)
            cycle_number = len(existing.get("cycles") or []) + 1
            cycle_kind = "change" if existing_role else "initial"
            role["last_auto_search_at"] = now
            role["label"] = {
                "title": model.posted_title or model.identity or "Untitled role",
                "company": model.hiring_company or "",
                "place": f"Remote · {', '.join(model.location.countries)}" if model.location.work_mode == "remote" and model.location.countries else ", ".join(model.location.cities or model.location.states or model.location.countries),
            }

            # The CrustData pull + Judge ranking take 30-90s, so — exactly like the
            # legacy Progressive Candidate Workspace — POST /search returns at once
            # with status="running" and the work runs on a background thread. The
            # frontend already polls GET /search/{id} until it leaves "running".
            running: Dict[str, Any] = {
                "provider": provider_name, "search_id": search_id, "candidate_count": 0,
                "candidates": [], "explanations": [], "evidence": [], "diagnostics": {},
                "warnings": [], "debug": None, "status": STATUS_RUNNING, "candidate_states": {},
                "progress": {"admitted": 0, "surfaced": 0, "building_context": 0, "review_ready": 0},
                "recruiter_decisions": existing.get("recruiter_decisions", {}),
                "notes": existing.get("notes", {}),
            }
            search_store.save(search_id, {
                "search_id": search_id, "status": STATUS_RUNNING,
                "owner_email": existing.get("owner_email") or owner_email,
                "created_at": existing.get("created_at", now), "updated_at": now,
                "response": running, "recruiter_decisions": existing.get("recruiter_decisions", {}),
                "notes": existing.get("notes", {}), "candidate_states": {},
                "confirmed_brief": existing.get("confirmed_brief"), "harvest_evidence": {},
                "internal_diagnostics": {}, "role": role, "cycles": list(existing.get("cycles") or []),
                "retrieval": None, "campaign_initial_ids": [], "campaign_label": role["label"],
            })

            def _save_progress(partial: Dict[str, Any]) -> None:
                # Persist each mid-flight snapshot so polls show "Reading profiles:
                # N of M" climbing instead of a frozen running state for minutes.
                def persist_progress(prior: Dict[str, Any]) -> None:
                    snapshot = {**partial,
                                "recruiter_decisions": prior.get("recruiter_decisions", {}),
                                "notes": prior.get("notes", {})}
                    prior.update({
                        "search_id": search_id, "status": STATUS_RUNNING,
                        "created_at": prior.get("created_at", now),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "response": snapshot, "candidate_states": {},
                        "harvest_evidence": prior.get("harvest_evidence", {}),
                    })
                search_store.update(search_id, persist_progress)

            def _run_engine_search() -> None:
                pool = None
                try:
                    resp = intake_service.run_search(
                        confirmation_id, search_id, provider=provider_name,
                        on_progress=_save_progress,
                        feedback_record=existing if existing_role else None,
                        admit_all_relevant=bool(existing_role),
                        surface_all=bool(existing_role),
                    )
                    # The held pool rides out on the response; lift it off before the
                    # snapshot is stored so it is persisted (internal, admin-only) but
                    # never serialized into the polled SearchResponse.
                    pool = resp.pop("pool", None)
                    status = "complete"
                except KeyError:
                    resp = {**running, "status": "error",
                            "warnings": ["This confirmation is no longer valid. Confirm the brief again before searching."]}
                    status = "error"
                except Exception:
                    logger.exception("[SEARCH] New-engine background search failed | search_id=%s", search_id)
                    resp = {**running, "status": "error",
                            "warnings": ["The search could not be completed. Please try again."]}
                    status = "error"
                ended = datetime.now(timezone.utc).isoformat()
                prior = search_store.load(search_id) or {}
                diagnostics = resp.get("diagnostics") or {}
                pulled = int(diagnostics.get("pulled") or 0)
                credits = float(diagnostics.get("credits_used") if diagnostics.get("credits_used") is not None
                                else (diagnostics.get("est_credits") or pulled * 0.03))
                initial_candidates = resp.get("candidates") or []
                campaign_ids = [c.get("candidate_id") for c in initial_candidates[:5] if c.get("candidate_id")]
                campaign_ids = prior.get("campaign_initial_ids") or campaign_ids
                old_role = prior.get("role") or role
                if old_role.get("status") == role_lifecycle.SEARCHING:
                    old_role["last_auto_search_at"] = ended
                next_cursor = diagnostics.get("next_cursor")
                search_store.save(search_id, {
                    "search_id": search_id, "status": status,
                    "created_at": prior.get("created_at", now), "updated_at": ended,
                    "response": resp, "recruiter_decisions": prior.get("recruiter_decisions", {}),
                    "notes": prior.get("notes", {}), "candidate_states": prior.get("candidate_states", {}),
                    "feedback_events": prior.get("feedback_events", []),
                    "confirmed_brief": resp.get("confirmed_brief") or prior.get("confirmed_brief"),
                    "harvest_evidence": {}, "internal_diagnostics": {"pool": pool} if pool else {},
                    "role": old_role, "campaign_label": old_role.get("label") or role.get("label"),
                    "campaign_initial_ids": campaign_ids,
                    "cycles": list(prior.get("cycles") or []) + [{"n": cycle_number, "kind": cycle_kind, "at": ended, "retrieved": pulled,
                                "credits_used": credits, "new_candidates": len(initial_candidates),
                                "cursor_used": False, "confirmation_id": confirmation_id}],
                    "retrieval": {"next_cursor": next_cursor, "exhausted": not bool(next_cursor), "cycle": cycle_number},
                    "presentation": {c.get("candidate_id"): {"state": "presented", "source": "initial", "seen": True}
                                      for c in initial_candidates if c.get("candidate_id")},
                })

            threading.Thread(target=_run_engine_search, daemon=True,
                             name=f"engine-search-{search_id}").start()
            logger.info("[SEARCH] New-engine background search started | search_id=%s", search_id)
            return SearchResponse(**running)
        request, confirmed_snapshot = _gate_search_request(request)
        confirmed_brief = brief_summary(confirmed_snapshot) if confirmed_snapshot else None
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
            if confirmed_snapshot is not None:
                return _search_role(request, confirmed_snapshot, confirmed_brief, search_id, owner_email)

            intent = _resolve_search_intent(request, jd_parser)
            if not isinstance(intent, SearchIntent):
                raise ParsingError("JD parser returned an invalid SearchIntent")

            intent, mapped_plan, friendly_warnings = _build_plan(intent, request.location)

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
                    "owner_email": existing_record.get("owner_email") or owner_email,
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
                    "confirmed_brief": confirmed_brief,
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
                confirmed_brief=confirmed_brief,
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
        request, _ = _gate_search_request(request)
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
