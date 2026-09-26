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
def _isolated_default_stores(monkeypatch, tmp_path):
    """Tests that build the app without their own SearchStore used to share the real output/searches directory.
    POST /search starts a background pipeline thread that outlives a test that does not wait for it, so leftover
    threads from earlier tests kept writing there, each holding a different lock. On Windows os.replace is refused
    while another handle has the target open, which showed up as an occasional PermissionError in an unrelated test
    (and wrote test searches into the developer's real search folder). Every test now gets private default
    directories, and no pipeline thread is allowed to outlive its test."""
    import threading

    from backend.services import intake_session, search_store

    monkeypatch.setattr(search_store, "DEFAULT_STORAGE_DIR", tmp_path / "default_searches")
    monkeypatch.setattr(intake_session, "DEFAULT_INTAKE_STORAGE_DIR", tmp_path / "default_intake_sessions")
    yield
    for thread in threading.enumerate():
        if thread.name.startswith("search-") and thread is not threading.current_thread():
            thread.join(timeout=15)


@pytest.fixture(autouse=True)
def _legacy_search_path_by_default(monkeypatch):
    """Most existing tests exercise the search pipeline directly. Production requires a confirmed brief for every
    search (RECRUITERAI_REQUIRE_CONFIRMATION defaults to true); tests that cover the gate build the app with
    require_confirmation=True explicitly."""
    monkeypatch.setenv("RECRUITERAI_REQUIRE_CONFIRMATION", "false")


@pytest.fixture(autouse=True)
def _no_real_requirement_judge(monkeypatch):
    """RequirementJudge reads OPENAI_API_KEY from the environment/.env; on a
    developer machine that key exists, so without this every app-level test
    would quietly spend real API calls. Tests that exercise the judge inject
    a fake client, which this leaves available."""
    from backend.services.requirement_judge import RequirementJudge

    monkeypatch.setattr(RequirementJudge, "is_available", lambda self: self._client is not None)
