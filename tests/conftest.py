import pytest


@pytest.fixture(autouse=True)
def _auth_env_vars(monkeypatch):
    """Every test gets a working auth configuration by default — individual
    tests can still override ALLOWED_EMAIL_DOMAIN etc. via monkeypatch.setenv
    to exercise the wrong-domain/misconfigured-server paths."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAIN", "example.com")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret")


@pytest.fixture(autouse=True)
def _no_real_requirement_judge(monkeypatch):
    """RequirementJudge reads OPENAI_API_KEY from the environment/.env; on a
    developer machine that key exists, so without this every app-level test
    would quietly spend real API calls. Tests that exercise the judge inject
    a fake client, which this leaves available."""
    from backend.services.requirement_judge import RequirementJudge

    monkeypatch.setattr(RequirementJudge, "is_available", lambda self: self._client is not None)
