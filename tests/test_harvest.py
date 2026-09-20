import httpx
import pytest

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.providers.harvest import HarvestClient, HarvestEnrichmentService, HarvestNotConfiguredError


def _candidate(candidate_id: str, profile_url: str | None) -> Candidate:
    return Candidate(candidate_id=candidate_id, name=f"Candidate {candidate_id}", profile_url=profile_url)


# ---------------------------------------------------------------------------
# HarvestClient
# ---------------------------------------------------------------------------


def test_client_raises_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("HARVEST_API_KEY", raising=False)
    import backend.config as config_module

    config_module._settings = None
    config_module._settings_env_signature = None

    client = HarvestClient()
    assert client.is_configured() is False
    with pytest.raises(HarvestNotConfiguredError):
        client.fetch_profile("https://www.linkedin.com/in/someone")


def test_client_fetch_profile_success(monkeypatch) -> None:
    monkeypatch.setenv("HARVEST_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "test-key"
        assert "url=" in str(request.url)
        return httpx.Response(200, json={"element": {"about": "AI engineer"}, "cost": 0.0064})

    client = HarvestClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    body = client.fetch_profile("https://www.linkedin.com/in/someone")

    assert body["element"]["about"] == "AI engineer"
    assert body["cost"] == 0.0064


# ---------------------------------------------------------------------------
# HarvestEnrichmentService
# ---------------------------------------------------------------------------


def test_service_returns_empty_and_makes_no_calls_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("HARVEST_API_KEY", raising=False)
    import backend.config as config_module

    config_module._settings = None
    config_module._settings_env_signature = None

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"element": {}})

    service = HarvestEnrichmentService(client=HarvestClient(client=httpx.Client(transport=httpx.MockTransport(handler))))
    candidates = [_candidate("1", "https://www.linkedin.com/in/a")]

    results = service.enrich_top_n(candidates)

    assert results == {}
    assert calls == []


def test_service_success_preserves_raw_response_and_cost(monkeypatch) -> None:
    monkeypatch.setenv("HARVEST_API_KEY", "test-key")
    raw_body = {"element": {"about": "Builds RAG systems", "skills": []}, "cost": 0.0064}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_body)

    service = HarvestEnrichmentService(client=HarvestClient(client=httpx.Client(transport=httpx.MockTransport(handler))))
    candidate = _candidate("1", "https://www.linkedin.com/in/a")

    results = service.enrich_top_n([candidate])

    evidence = results["1"]
    assert evidence.success is True
    assert evidence.cost == 0.0064
    assert evidence.raw == raw_body  # preserved exactly, not reshaped
    assert evidence.latency_ms is not None
    assert evidence.fetched_at is not None


def test_service_marks_missing_profile_url_as_failure_without_a_network_call(monkeypatch) -> None:
    monkeypatch.setenv("HARVEST_API_KEY", "test-key")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"element": {}})

    service = HarvestEnrichmentService(client=HarvestClient(client=httpx.Client(transport=httpx.MockTransport(handler))))
    candidate = _candidate("1", None)

    results = service.enrich_top_n([candidate])

    assert results["1"].success is False
    assert results["1"].error == "missing_profile_url"
    assert calls == []


def test_service_marks_malformed_response_as_failure() -> None:
    class MalformedClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            return {"unexpected": "shape"}  # no "element" key at all

    service = HarvestEnrichmentService(client=MalformedClient())
    candidate = _candidate("1", "https://www.linkedin.com/in/a")

    results = service.enrich_top_n([candidate])

    assert results["1"].success is False
    assert results["1"].error == "malformed_response"


def test_service_marks_http_error_as_failure_without_raising() -> None:
    class FailingClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            raise httpx.HTTPStatusError("boom", request=httpx.Request("GET", profile_url), response=httpx.Response(500))

    service = HarvestEnrichmentService(client=FailingClient())
    candidate = _candidate("1", "https://www.linkedin.com/in/a")

    # Must never raise — discovery/search must never break because of Harvest.
    results = service.enrich_top_n([candidate])

    assert results["1"].success is False
    assert results["1"].error == "http_500"


def test_service_marks_timeout_as_failure() -> None:
    class TimingOutClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            raise httpx.TimeoutException("timed out")

    service = HarvestEnrichmentService(client=TimingOutClient())
    results = service.enrich_top_n([_candidate("1", "https://www.linkedin.com/in/a")])

    assert results["1"].success is False
    assert results["1"].error == "timeout"


def test_service_only_enriches_the_top_n_slice() -> None:
    attempted = []

    class RecordingClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            attempted.append(profile_url)
            return {"element": {}}

    service = HarvestEnrichmentService(client=RecordingClient(), top_n=3)
    candidates = [_candidate(str(i), f"https://www.linkedin.com/in/{i}") for i in range(7)]

    results = service.enrich_top_n(candidates)

    assert len(results) == 3
    assert set(results.keys()) == {"0", "1", "2"}
    assert len(attempted) == 3


def test_service_reuses_an_existing_successful_enrichment_without_recalling() -> None:
    attempted = []

    class RecordingClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            attempted.append(profile_url)
            return {"element": {"about": "new call happened"}}

    cached = HarvestEvidence(raw={"element": {"about": "cached"}}, success=True, cost=0.0064)
    service = HarvestEnrichmentService(client=RecordingClient(), top_n=5)
    candidate = _candidate("1", "https://www.linkedin.com/in/a")

    results = service.enrich_top_n([candidate], existing={"1": cached})

    assert attempted == []  # no network call — the cached success was reused
    assert results["1"] is cached


def test_service_retries_a_previously_failed_enrichment() -> None:
    attempted = []

    class RecordingClient:
        def is_configured(self):
            return True

        def fetch_profile(self, profile_url, **kwargs):
            attempted.append(profile_url)
            return {"element": {"about": "succeeded this time"}}

    previous_failure = HarvestEvidence(success=False, error="timeout")
    service = HarvestEnrichmentService(client=RecordingClient(), top_n=5)
    candidate = _candidate("1", "https://www.linkedin.com/in/a")

    results = service.enrich_top_n([candidate], existing={"1": previous_failure})

    assert attempted == ["https://www.linkedin.com/in/a"]  # retried
    assert results["1"].success is True
