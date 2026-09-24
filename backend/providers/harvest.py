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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_harvest_api_key, get_harvest_enrichment_concurrency, get_harvest_enrichment_top_n
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


@dataclass
class HarvestEnrichmentDiagnostics:
    """Internal-only diagnostics for one enrich_top_n() call — never sent to
    the recruiter (see backend/api.py, which logs this and persists it under
    a separate internal_diagnostics key, never inside SearchResponse).
    max_observed_concurrency is measured directly (a lock-protected counter
    incremented/decremented around each real fetch), not assumed from the
    configured limit — "actually verify concurrency is real," not just
    configure a bound and trust it."""

    selected_count: int = 0
    reused_count: int = 0
    attempted_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    concurrency_limit: int = 0
    max_observed_concurrency: int = 0
    total_elapsed_ms: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    total_cost: float = 0.0


class HarvestEnrichmentService:
    """Orchestrates second-stage enrichment for a small top-N slice of an
    already baseline-ranked candidate list. Never enriches the whole pool.
    Idempotent: a candidate with an existing successful HarvestEvidence is
    reused, never re-fetched; a previously failed attempt is retried. If
    Harvest isn't configured at all, this returns {} immediately — zero
    network calls, zero per-candidate failures logged, discovery unaffected.

    Fetches for the selected-but-not-yet-successfully-enriched candidates run
    with bounded concurrency (HARVEST_ENRICHMENT_CONCURRENCY, default 3) via
    a plain ThreadPoolExecutor — the whole backend is synchronous (no asyncio
    anywhere in this codebase), so this is the minimal, architecture-
    consistent way to bound fan-out without introducing an async runtime.
    One candidate's failure (timeout, HTTP error, malformed response) never
    affects any other — each future resolves independently, exactly as the
    prior sequential loop already guaranteed per-candidate isolation."""

    def __init__(
        self,
        client: Optional[HarvestClient] = None,
        top_n: Optional[int] = None,
        concurrency: Optional[int] = None,
    ) -> None:
        self._client = client or HarvestClient()
        self.top_n = top_n if top_n is not None else get_harvest_enrichment_top_n()
        self.concurrency = concurrency if concurrency is not None else get_harvest_enrichment_concurrency()
        # Diagnostics from the most recent enrich_top_n() call — read by the
        # caller (backend/api.py) after the call returns. Not part of the
        # method's return value so the existing Dict[str, HarvestEvidence]
        # contract every current call site relies on stays unchanged.
        self.last_enrichment_diagnostics: Optional[HarvestEnrichmentDiagnostics] = None

    def _select_for_enrichment(self, ranked_candidates: List[Candidate]) -> List[Candidate]:
        """The enrichment-selection policy, isolated from fetch/concurrency/
        idempotency logic so it can change later (e.g. an adjacent-candidate
        sample) without touching anything else in this class. V1: a plain
        positional top-N slice of the baseline-ranked list — unchanged
        behavior from before Phase 3, just callable/replaceable on its own."""
        return ranked_candidates[: self.top_n]

    def enrich_top_n(
        self,
        ranked_candidates: List[Candidate],
        existing: Optional[Dict[str, HarvestEvidence]] = None,
    ) -> Dict[str, HarvestEvidence]:
        existing = existing or {}
        results: Dict[str, HarvestEvidence] = {}
        selected = self._select_for_enrichment(ranked_candidates)
        diagnostics = HarvestEnrichmentDiagnostics(
            selected_count=len(selected),
            concurrency_limit=max(1, self.concurrency),
        )
        self.last_enrichment_diagnostics = diagnostics

        if not self._client.is_configured():
            return results

        to_fetch: List[Candidate] = []
        for candidate in selected:
            candidate_id = candidate.candidate_id or ""
            if not candidate_id:
                continue

            cached = existing.get(candidate_id)
            if cached is not None and cached.success:
                results[candidate_id] = cached
                diagnostics.reused_count += 1
                continue

            to_fetch.append(candidate)

        if not to_fetch:
            return results

        # Lock-protected active/peak counters around the REAL fetch calls
        # (not the executor's own internal state) — this is what makes
        # max_observed_concurrency an actual measurement rather than an
        # assumption that the configured limit is being honored.
        lock = threading.Lock()
        active = 0
        peak = 0

        def _tracked_fetch(candidate: Candidate) -> HarvestEvidence:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                return self._fetch_one(candidate)
            finally:
                with lock:
                    active -= 1

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=diagnostics.concurrency_limit) as pool:
            future_to_candidate = {pool.submit(_tracked_fetch, candidate): candidate for candidate in to_fetch}
            for future in as_completed(future_to_candidate):
                candidate = future_to_candidate[future]
                candidate_id = candidate.candidate_id or ""
                evidence = future.result()
                results[candidate_id] = evidence

                diagnostics.attempted_count += 1
                if evidence.success:
                    diagnostics.successful_count += 1
                    if evidence.cost:
                        diagnostics.total_cost += evidence.cost
                else:
                    diagnostics.failed_count += 1
                if evidence.latency_ms is not None:
                    diagnostics.latencies_ms.append(evidence.latency_ms)

        diagnostics.total_elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        diagnostics.max_observed_concurrency = peak

        return results

    def _fetch_one(self, candidate: Candidate) -> HarvestEvidence:
        attempts = 1
        if not candidate.profile_url:
            return HarvestEvidence(attempts=attempts, success=False, error="missing_profile_url", fetched_at=_now_iso())

        started = time.perf_counter()
        try:
            body = self._client.fetch_profile(candidate.profile_url)
            # A 200 whose body has no profile ("malformed_response") failed 2
            # of 15 reads on a real search. It is cheap and usually transient,
            # so one immediate retry; every other failure mode is unchanged.
            if not isinstance(body, dict) or not isinstance(body.get("element"), dict):
                attempts = 2
                body = self._client.fetch_profile(candidate.profile_url)
        except HarvestNotConfiguredError:
            return HarvestEvidence(attempts=attempts, success=False, error="not_configured", fetched_at=_now_iso())
        except httpx.TimeoutException:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("Harvest enrichment timed out | candidate_id=%s", candidate.candidate_id)
            return HarvestEvidence(attempts=attempts, success=False, error="timeout", latency_ms=latency_ms, fetched_at=_now_iso())
        except httpx.HTTPStatusError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            status = exc.response.status_code
            error = "rate_limited" if status == 429 else f"http_{status}"
            logger.warning("Harvest enrichment failed | candidate_id=%s status=%s", candidate.candidate_id, status)
            return HarvestEvidence(attempts=attempts, success=False, error=error, latency_ms=latency_ms, fetched_at=_now_iso())
        except (httpx.RequestError, HarvestResponseError) as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.warning("Harvest enrichment failed | candidate_id=%s error=%s", candidate.candidate_id, exc)
            return HarvestEvidence(attempts=attempts, success=False, error="request_error", latency_ms=latency_ms, fetched_at=_now_iso())

        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if not isinstance(body, dict) or not isinstance(body.get("element"), dict):
            logger.warning("Harvest enrichment returned a malformed response | candidate_id=%s", candidate.candidate_id)
            return HarvestEvidence(attempts=attempts, 
                success=False,
                error="malformed_response",
                latency_ms=latency_ms,
                raw=body if isinstance(body, dict) else {},
                fetched_at=_now_iso(),
            )

        cost = body.get("cost") if isinstance(body.get("cost"), (int, float)) else None
        return HarvestEvidence(attempts=attempts, raw=body, success=True, cost=cost, latency_ms=latency_ms, fetched_at=_now_iso())
