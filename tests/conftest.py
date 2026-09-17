import pytest


@pytest.fixture(autouse=True)
def _auth_env_vars(monkeypatch):
    """Every test gets a working auth configuration by default — individual
    tests can still override ALLOWED_EMAIL_DOMAIN etc. via monkeypatch.setenv
    to exercise the wrong-domain/misconfigured-server paths."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAIN", "example.com")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret")
