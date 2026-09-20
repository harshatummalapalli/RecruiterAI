"""HarvestAPI (harvestapi.io) client and second-stage enrichment service.

This is second-stage ENRICHMENT, not a search/discovery provider — it does
not implement BaseProvider and is never registered in ProviderRegistry.
CrustData finds candidates; Harvest deepens evidence for a small top-N
slice of them, after baseline ranking. A Harvest failure of any kind must
never prevent candidate discovery — every failure mode here degrades to
HarvestEvidence(success=False, ...) and the caller proceeds on CrustData-
only evidence.

Real schema confirmed live against the actual account during the Harvest
enrichment experiment (not assumed from documentation): GET
https://api.harvestapi.io/linkedin/profile, auth via the X-API-Key header,
lookup by `url`, an optional `main=true` for a cheaper/truncated response.
A successful response is {"element": {...profile...}, "cost": <float>, ...}.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_harvest_api_key, get_harvest_enrichment_top_n
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence

logger = logging.getLogger(__name__)

HARVEST_PROFILE_URL = "https://api.harvestapi.io/linkedin/profile"
DEFAULT_TIMEOUT_SECONDS = 30.0


class HarvestNotConfiguredError(Exception):
    """Raised when HARVEST_API_KEY is not set. Caught by
    HarvestEnrichmentService, never propagated to the recruiter."""


class HarvestResponseError(Exception):
    """Raised when HarvestAPI returns a 200 with a body that isn't valid
    JSON — distinct from an HTTP error status."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarvestClient:
    """Thin wrapper around HarvestAPI's GET /linkedin/profile endpoint.
    Raises on failure — never swallows errors itself; HarvestEnrichmentService
    is the one place that turns a failure into HarvestEvidence(success=False)."""

    def __init__(self, client: Optional[httpx.Client] = None, base_url: Optional[str] = None) -> None:
        self._client = client
        self._base_url = base_url or HARVEST_PROFILE_URL

    def is_configured(self) -> bool:
        return bool(get_harvest_api_key())

    def fetch_profile(self, profile_url: str, *, full: bool = True, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
        api_key = get_harvest_api_key()
        if not api_key:
            raise HarvestNotConfiguredError("HARVEST_API_KEY is not configured.")

        params: Dict[str, str] = {"url": profile_url}
        if not full:
            params["main"] = "true"

        client = self._client or httpx.Client(timeout=timeout)
        should_close = self._client is None
        try:
            response = client.get(self._base_url, params=params, headers={"X-API-Key": api_key})
            response.raise_for_status()
        finally:
            if should_close:
                client.close()

        try:
            return response.json()
        except ValueError as exc:
            raise HarvestResponseError("HarvestAPI returned a response that was not valid JSON.") from exc


class HarvestEnrichmentService:
    """Orchestrates second-stage enrichment for a small top-N slice of an
    already baseline-ranked candidate list. Never enriches the whole pool.
    Idempotent: a candidate with an existing successful HarvestEvidence is
    reused, never re-fetched; a previously failed attempt is retried. If
    Harvest isn't configured at all, this returns {} immediately — zero
    network calls, zero per-candidate failures logged, discovery unaffected."""

    def __init__(self, client: Optional[HarvestClient] = None, top_n: Optional[int] = None) -> None:
        self._client = client or HarvestClient()
        self.top_n = top_n if top_n is not None else get_harvest_enrichment_top_n()

    def enrich_top_n(
        self,
        ranked_candidates: List[Candidate],
        existing: Optional[Dict[str, HarvestEvidence]] = None,
    ) -> Dict[str, HarvestEvidence]:
        existing = existing or {}
        results: Dict[str, HarvestEvidence] = {}

        if not self._client.is_configured():
            return results

        for candidate in ranked_candidates[: self.top_n]:
            candidate_id = candidate.candidate_id or ""
            if not candidate_id:
                continue

            cached = existing.get(candidate_id)
            if cached is not None and cached.success:
                results[candidate_id] = cached
                continue

            results[candidate_id] = self._fetch_one(candidate)

        return results

    def _fetch_one(self, candidate: Candidate) -> HarvestEvidence:
        if not candidate.profile_url:
            return HarvestEvidence(success=False, error="missing_profile_url", fetched_at=_now_iso())

        started = time.perf_counter()
        try:
            body = self._client.fetch_profile(candidate.profile_url)
        except HarvestNotConfiguredError:
            return HarvestEvidence(success=False, error="not_configured", fetched_at=_now_iso())
        except httpx.TimeoutException:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("Harvest enrichment timed out | candidate_id=%s", candidate.candidate_id)
            return HarvestEvidence(success=False, error="timeout", latency_ms=latency_ms, fetched_at=_now_iso())
        except httpx.HTTPStatusError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            status = exc.response.status_code
            error = "rate_limited" if status == 429 else f"http_{status}"
            logger.warning("Harvest enrichment failed | candidate_id=%s status=%s", candidate.candidate_id, status)
            return HarvestEvidence(success=False, error=error, latency_ms=latency_ms, fetched_at=_now_iso())
        except (httpx.RequestError, HarvestResponseError) as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("Harvest enrichment failed | candidate_id=%s error=%s", candidate.candidate_id, exc)
            return HarvestEvidence(success=False, error="request_error", latency_ms=latency_ms, fetched_at=_now_iso())

        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if not isinstance(body, dict) or not isinstance(body.get("element"), dict):
            logger.warning("Harvest enrichment returned a malformed response | candidate_id=%s", candidate.candidate_id)
            return HarvestEvidence(
                success=False,
                error="malformed_response",
                latency_ms=latency_ms,
                raw=body if isinstance(body, dict) else {},
                fetched_at=_now_iso(),
            )

        cost = body.get("cost") if isinstance(body.get("cost"), (int, float)) else None
        return HarvestEvidence(raw=body, success=True, cost=cost, latency_ms=latency_ms, fetched_at=_now_iso())
