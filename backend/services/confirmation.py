"""Confirmation: the moment a recruiter's brief becomes an executable search.

The browser is never trusted as the source of the executable search intent. When the recruiter presses Search, the
server checks the deterministic gate, builds the intent itself from the pinned understanding, the recruiter's
answers and the Search Boundary, applies the recruiter's edits through a whitelist, and stores an IMMUTABLE snapshot.
`/search` then reads that snapshot by id. The same confirmed inputs always give the same snapshot content hash.
"""

import dataclasses
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.models.intake import IntakeResult
from backend.models.search_intent import SearchIntent
from backend.services.query_expansion import QueryExpansionService
from backend.services.search_boundary import BoundaryValidationError, validate_search_boundary
from backend.services.search_store import SearchStore
from backend.services.search_translator import (
    _fallback_natural_language_query,
    _validated_employment_type,
    build_confirmed_hiring_intent,
    to_search_intent,
)

DEFAULT_CONFIRMATION_DIR = Path(__file__).resolve().parents[2] / "output" / "confirmations"
MAX_LIST_ITEMS = 50
MAX_TEXT_CHARS = 240


class ConfirmationRefused(ValueError):
    """The deterministic gate said no. `reasons` are recruiter-readable."""

    def __init__(self, reasons: List[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class ConfirmationEdits(BaseModel):
    """The ONLY things a recruiter may change between the brief and the search. Location, work mode and hiring
    company are the Search Boundary's, so they are deliberately not here. A field that is absent is not changed.
    Anything else is rejected outright rather than ignored, so a browser cannot smuggle a field in."""

    model_config = ConfigDict(extra="forbid")

    candidate_identity: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    include_titles: Optional[List[str]] = None
    exclude_titles: Optional[List[str]] = None
    minimum_years: Optional[int] = Field(default=None, ge=0, le=60)
    maximum_years: Optional[int] = Field(default=None, ge=0, le=60)
    core_signals: Optional[List[str]] = None
    supporting_signals: Optional[List[str]] = None
    differentiator_signals: Optional[List[str]] = None
    exclude_current_companies: Optional[List[str]] = None
    preferred_companies: Optional[List[str]] = None


def _clean_text(value: Optional[str]) -> str:
    return " ".join((value or "").split())[:MAX_TEXT_CHARS]


def _clean_list(values: Optional[List[str]]) -> List[str]:
    cleaned: List[str] = []
    for value in values or []:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:MAX_LIST_ITEMS]


def gate_reasons(record: Any) -> List[str]:
    """Why this intake session may not be searched yet. Empty means ready. Deterministic; the model has no say."""
    reasons: List[str] = []
    result: Optional[IntakeResult] = record.result
    if result is None:
        return ["The role has not been understood yet."]
    try:
        validate_search_boundary(record.boundary)
    except BoundaryValidationError as exc:
        reasons.extend(exc.errors)
    pending = result.pending_ask_issues
    if result.status != "ready" or pending:
        reasons.append(f"{len(pending) or 1} question{'s' if len(pending) > 1 else ''} still need{'s' if len(pending) == 1 else ''} your answer.")
    return reasons


def apply_edits(intent: SearchIntent, edits: ConfirmationEdits) -> Dict[str, Any]:
    """Applies the whitelisted edits to the server-built intent. Returns just the edits that were applied."""
    applied: Dict[str, Any] = {}
    provided = edits.model_fields_set
    requirements_changed = False

    if "candidate_identity" in provided and _clean_text(edits.candidate_identity):
        intent.role.title = _clean_text(edits.candidate_identity)
        applied["candidate_identity"] = intent.role.title
    if "seniority" in provided:
        intent.role.seniority = _clean_text(edits.seniority) or None
        applied["seniority"] = intent.role.seniority
    if "employment_type" in provided:
        intent.role.employment_type = _validated_employment_type(_clean_text(edits.employment_type)) if edits.employment_type else None
        applied["employment_type"] = intent.role.employment_type
    if "include_titles" in provided:
        intent.titles.include_titles = _clean_list(edits.include_titles)
        applied["include_titles"] = intent.titles.include_titles
    if "exclude_titles" in provided:
        intent.titles.exclude_titles = _clean_list(edits.exclude_titles)
        applied["exclude_titles"] = intent.titles.exclude_titles
    if "minimum_years" in provided or "maximum_years" in provided:
        if "minimum_years" in provided:
            intent.experience.minimum_years = edits.minimum_years
        if "maximum_years" in provided:
            intent.experience.maximum_years = edits.maximum_years
        applied["experience"] = {"minimum_years": intent.experience.minimum_years, "maximum_years": intent.experience.maximum_years}
    for name, attribute in (("core_signals", "core_signals"), ("supporting_signals", "supporting_signals"), ("differentiator_signals", "differentiator_signals")):
        if name in provided:
            setattr(intent, attribute, _clean_list(getattr(edits, name)))
            applied[name] = getattr(intent, attribute)
            requirements_changed = True
    if "exclude_current_companies" in provided:
        intent.company_preferences.exclude_current_companies = _clean_list(edits.exclude_current_companies)
        applied["exclude_current_companies"] = intent.company_preferences.exclude_current_companies
    if "preferred_companies" in provided:
        intent.previous_background.preferred_companies = _clean_list(edits.preferred_companies)
        applied["preferred_companies"] = intent.previous_background.preferred_companies

    if requirements_changed:
        # The model-written search sentence describes the requirements it was written from. Once the recruiter has
        # edited them, it is rebuilt deterministically from what is now on screen rather than left stale.
        intent.natural_language_search_query = _fallback_natural_language_query(
            intent.role.title or "", intent.role.seniority, intent.core_signals, intent.supporting_signals, intent.differentiator_signals
        )
    return applied


def content_hash(payload: Dict[str, Any]) -> str:
    """Identifies WHAT was confirmed (not when, not by which id). Same confirmed inputs, same hash."""
    material = {key: payload[key] for key in ("raw_input", "posted_title", "posted_title_source", "boundary", "search_intent")}
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def build_snapshot(record: Any, edits: ConfirmationEdits, query_expander: QueryExpansionService) -> Dict[str, Any]:
    reasons = gate_reasons(record)
    if reasons:
        raise ConfirmationRefused(reasons)

    boundary = validate_search_boundary(record.boundary)
    result: IntakeResult = record.result
    confirmed = build_confirmed_hiring_intent(result, boundary=boundary)
    intent = to_search_intent(confirmed, query_expander=query_expander)
    applied = apply_edits(intent, edits)

    payload: Dict[str, Any] = {
        "session_id": record.session_id,
        "raw_input": record.raw_input,
        "posted_title": confirmed.posted_title,
        "posted_title_source": confirmed.posted_title_source,
        "candidate_identity": intent.role.title,
        "boundary": dataclasses.asdict(boundary),
        "search_intent": TypeAdapter(SearchIntent).dump_python(intent, mode="json"),
        "answers": [dataclasses.asdict(answer) for answer in record.answers],
        "confirmed_changes": [dataclasses.asdict(change) for change in result.confirmed],
        "edits": applied,
    }
    payload["content_hash"] = content_hash(payload)
    return payload


class ConfirmationStore:
    """Immutable snapshots: a confirmation can be created and read, never changed."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._store = SearchStore(storage_dir=Path(storage_dir or DEFAULT_CONFIRMATION_DIR))

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        confirmation_id = str(uuid.uuid4())
        record = {**payload, "confirmation_id": confirmation_id, "created_at": datetime.now(timezone.utc).isoformat()}
        with self._store.lock:
            if self._store.load(confirmation_id) is not None:  # a uuid collision, in practice never
                raise FileExistsError(confirmation_id)
            self._store.save(confirmation_id, record)
        return record

    def load(self, confirmation_id: str) -> Optional[Dict[str, Any]]:
        record = self._store.load(confirmation_id or "")
        if record is None:
            return None
        # A stored snapshot that no longer matches its own hash is treated as invalid, never as "close enough".
        return record if record.get("content_hash") == content_hash(record) else None


def search_intent_from_snapshot(snapshot: Dict[str, Any]) -> SearchIntent:
    return TypeAdapter(SearchIntent).validate_python(snapshot["search_intent"])


def brief_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """What the workspace needs to show which role this search is for, without carrying the whole snapshot."""
    return {
        "confirmation_id": snapshot["confirmation_id"],
        "session_id": snapshot["session_id"],
        "posted_title": snapshot.get("posted_title"),
        "posted_title_source": snapshot.get("posted_title_source"),
        "candidate_identity": snapshot.get("candidate_identity"),
        "content_hash": snapshot["content_hash"],
    }


def location_override_for_search(intent: SearchIntent, boundary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The location the search filters on, derived from the confirmed intent exactly as the browser used to derive
    it (briefToLocationDetail): a single city with a radius is a radius search anchored on "City, State", several
    cities or states are a list, a country alone is a country search. Now done once, on the server."""
    location = intent.location
    country = location.countries[0] if location.countries else ""
    cities, states = list(location.cities), list(location.states)
    if cities:
        entries = [(city, states[index] if index < len(states) else "") for index, city in enumerate(cities)]
    else:
        entries = [("", state) for state in states]

    radius = location.radius_miles
    if len(entries) == 1 and radius is not None:
        geography = "radius"
    elif entries:
        geography = "multiple"
    else:
        geography = "country" if country else "global"

    def unique(values: List[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value and value.strip()))

    if geography == "country":
        countries, out_states, out_cities = [country], [], []
    else:
        countries = [country] if country and entries else []
        out_states, out_cities = unique([state for _, state in entries]), unique([city for city, _ in entries])

    radius_place = None
    if geography == "radius":
        city, state = entries[0]
        radius_place = ", ".join(part for part in (city, state) if part.strip()) or None

    return {
        "search_geography": geography,
        "countries": countries,
        "states": out_states,
        "cities": out_cities,
        "zip_codes": [],
        "radius_miles": radius if geography == "radius" else None,
        "radius_place": radius_place,
        "radius_unit": "mi",
        "work_mode": location.work_mode,
        "employment_type": intent.role.employment_type,
    }
