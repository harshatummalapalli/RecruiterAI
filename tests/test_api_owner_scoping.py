"""Per-user isolation (owner scoping): a recruiter sees and acts on only their own
searches and intake sessions; the super admin sees everything; unowned legacy records
are never shown to an identified non-admin. Offline, no credits — reuses the new-engine
fake pipeline harness from test_api_new_engine."""

import time

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.services.search_store import SearchStore

from tests.test_api_new_engine import _BOUNDARY, _service, _poll_until_done, _start_and_read


def _app(tmp_path):
    """One app + shared stores, so two clients with different login emails exercise
    the SAME data — the real cross-account condition."""
    return create_app(intake_service=_service(tmp_path),
                       search_store=SearchStore(storage_dir=tmp_path / "searches"))


def _client(app, email):
    c = TestClient(app)
    if email is not None:
        c.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(email))
    else:
        c.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value())
    return c


def _run_search(c):
    """Drive a full brief->confirm->search to completion; return (session_id, search_id)."""
    sid, started = _start_and_read(c, {"raw_input": "eDiscovery ops", "boundary": _BOUNDARY,
                                       "posted_title": "Operations Analyst"})
    assert started["result"]["status"] == "ready"
    cid = c.post(f"/intake/{sid}/confirmations", json={"edits": {}}).json()["confirmation_id"]
    posted = c.post("/search", json={"jd_text": "", "confirmation_id": cid, "provider": "crustdata",
                                     "autocomplete": True}).json()
    resp = _poll_until_done(c, posted["search_id"])
    assert resp["status"] == "complete"
    return sid, posted["search_id"]


def test_a_search_is_invisible_to_a_different_recruiter(tmp_path):
    app = _app(tmp_path)
    alice = _client(app, "alice@example.com")
    bob = _client(app, "bob@example.com")

    sid, search_id = _run_search(alice)

    # Alice (the owner) sees it both ways.
    assert alice.get(f"/search/{search_id}").status_code == 200
    assert search_id in {s["id"] for s in alice.get("/searches").json()["searches"]}

    # Bob cannot read it, cannot list it, cannot act on it, cannot read the brief.
    assert bob.get(f"/search/{search_id}").status_code == 404
    assert search_id not in {s.get("id") for s in bob.get("/searches").json()["searches"]}
    assert bob.patch(f"/search/{search_id}/candidate",
                     json={"candidate_id": "real", "decision": "shortlist"}).status_code == 404
    assert bob.get(f"/intake/{sid}").status_code == 404


def test_bob_cannot_hijack_alices_campaign_by_posting_her_search_id(tmp_path):
    app = _app(tmp_path)
    alice = _client(app, "alice@example.com")
    bob = _client(app, "bob@example.com")
    _, search_id = _run_search(alice)

    # POST /search carries the id in the body (no path guard), so this is the inline check.
    r = bob.post("/search", json={"jd_text": "", "confirmation_id": "whatever",
                                  "provider": "crustdata", "search_id": search_id})
    assert r.status_code == 404


def test_super_admin_sees_every_recruiters_search(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "boss@example.com")
    app = _app(tmp_path)
    alice = _client(app, "alice@example.com")
    admin = _client(app, "boss@example.com")

    _, search_id = _run_search(alice)
    assert admin.get(f"/search/{search_id}").status_code == 200
    assert search_id in {s["id"] for s in admin.get("/searches").json()["searches"]}


def test_owner_is_sticky_across_the_background_pipeline_rebuild(tmp_path):
    # The pipeline thread rewrites the whole record dict with no session; the store's
    # sticky-owner save must keep the owner so the completed search stays Alice's.
    app = _app(tmp_path)
    alice = _client(app, "alice@example.com")
    bob = _client(app, "bob@example.com")
    _, search_id = _run_search(alice)
    # After completion (several background saves later) it is still hers, not public.
    assert bob.get(f"/search/{search_id}").status_code == 404
    assert alice.get(f"/search/{search_id}").status_code == 200
