"""Provider request-timeout configuration — no real network.

Regression anchor: the old hard-coded 10s read timeout tripped on a slow
geo+hybrid query, retried, and the provider returned an unfiltered global pool.
The read timeout is now generous and configurable; the connect timeout stays short.
"""
from __future__ import annotations

import httpx
import pytest

import backend.providers.crustdata as cd
from backend.providers.crustdata import (
    CrustDataProvider,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
)


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"profiles": []}


class _FakeClient:
    """Records the timeout it was constructed with; returns an empty result."""
    last_timeout = None

    def __init__(self, timeout=None):
        _FakeClient.last_timeout = timeout

    def post(self, *args, **kwargs):
        return _FakeResponse()

    def close(self):
        return None


@pytest.fixture(autouse=True)
def _fake_http(monkeypatch):
    monkeypatch.setattr(cd, "get_crustdata_api_key", lambda: "test-key")
    monkeypatch.setattr(cd.httpx, "Client", _FakeClient)
    _FakeClient.last_timeout = None


def test_default_read_timeout_is_generous_not_ten_seconds():
    assert DEFAULT_REQUEST_TIMEOUT >= 45.0        # a slow geo+hybrid query must not trip it
    CrustDataProvider()._search_api({"filters": {}})
    t = _FakeClient.last_timeout
    assert isinstance(t, httpx.Timeout)
    assert t.read == DEFAULT_REQUEST_TIMEOUT
    assert t.connect == DEFAULT_CONNECT_TIMEOUT    # connect stays short


def test_timeout_is_overridable_per_request():
    CrustDataProvider()._search_api({"filters": {}}, options={"request_timeout": 90})
    assert _FakeClient.last_timeout.read == 90.0


def test_timeout_is_overridable_via_env(monkeypatch):
    monkeypatch.setenv("CRUSTDATA_REQUEST_TIMEOUT", "120")
    CrustDataProvider()._search_api({"filters": {}})
    assert _FakeClient.last_timeout.read == 120.0


def test_injected_client_is_used_as_is():
    injected = _FakeClient(timeout="sentinel")
    CrustDataProvider(client=injected)._search_api({"filters": {}})
    # an injected client is reused untouched (its own timeout governs)
    assert _FakeClient.last_timeout == "sentinel"
