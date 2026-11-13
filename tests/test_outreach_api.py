"""/search/{id}/outreach/{draft,send} — owned-search scoped, state persisted."""

import backend.api as api_mod
import backend.services.outreach_draft as draft_mod
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.services.outreach import OutreachActionError
from backend.services.search_store import SearchStore

OWNER = "alice@example.com"
URL = "https://www.linkedin.com/in/jane-doe-123/"


class FakeOutreach:
    def __init__(self):
        self.calls = []
        self.interp = None  # canned interpret_event result for webhook tests

    def interpret_event(self, event):
        return self.interp

    def sender_name(self, owner, channel):
        return "Alice R"

    # send-safety caps
    def check_limit(self, owner, category):
        if getattr(self, "over_limit", False):
            from backend.services.outreach import OutreachLimitError
            raise OutreachLimitError("You've reached the daily limit of 20 LinkedIn invites.")

    def record_send(self, owner, category):
        self.calls.append(("record", owner, category))

    def usage(self, owner):
        return {"linkedin_invite": {"used": 1, "limit": 20, "remaining": 19}}

    def connect_linkedin(self, owner, *, profile_url, note=None):
        self.calls.append(("connect", owner, profile_url, note))
        return {"channel": "linkedin", "state": "invited", "kind": "connect", "at": "2026-11-13T00:00:00+00:00"}

    def message_linkedin(self, owner, *, profile_url, text, inmail=False):
        self.calls.append(("message", owner, profile_url, text, inmail))
        return {"channel": "linkedin", "state": "inmailed", "kind": "inmail", "at": "2026-11-13T00:00:00+00:00"}

    def email_candidate(self, owner, *, to_email, subject, body, display_name=None):
        self.calls.append(("email", owner, to_email, subject, body, display_name))
        return {"channel": "email", "state": "emailed", "kind": "email", "subject": subject or "", "at": "2026-11-13T00:00:00+00:00"}


def _seed(store, owner=OWNER):
    store.save("s1", {
        "owner_email": owner,
        "response": {
            "provider": "crustdata", "search_id": "s1", "candidate_count": 1,
            "candidates": [{"candidate_id": "c1", "name": "Jane Doe", "profile_url": URL, "email": "jane@acme.com"}],
            "explanations": [{}],
            "evidence": [{"contact": {"email": "jane@acme.com"}, "role_alignment": {"matched_signals": []}}],
            "diagnostics": {},
        },
        "confirmed_brief": {"posted_title": "Principal Backend Engineer", "hiring_company": "Northwind"},
    })


def _client(tmp_path, owner=OWNER):
    store = SearchStore(storage_dir=tmp_path / "s")
    _seed(store, owner)
    fake = FakeOutreach()
    app = create_app(outreach_service=fake, search_store=store)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(OWNER))
    return client, fake, store


def test_draft_returns_subject_and_body(tmp_path, monkeypatch):
    # Keep the draft hermetic — no model call.
    monkeypatch.setattr(draft_mod, "complete_json", lambda *a, **k: {"subject": "A role at Northwind", "body": "Hi Jane, interested?"})
    client, _, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/draft", json={"candidate_id": "c1", "channel": "email"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "A role at Northwind" and body["body"].startswith("Hi Jane")


def test_draft_falls_back_when_model_fails(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(draft_mod, "complete_json", boom)
    client, _, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/draft", json={"candidate_id": "c1", "channel": "linkedin"})
    assert resp.status_code == 200
    assert resp.json()["body"]  # deterministic fallback still drafts something


def test_send_connect_persists_state_and_returns_it(tmp_path):
    client, fake, store = _client(tmp_path)
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi Jane"})
    assert resp.status_code == 200
    assert resp.json()["outreach"]["state"] == "invited"
    assert any(c[0] == "connect" for c in fake.calls)
    # Persisted on the record, keyed by candidate -> channel.
    assert store.load("s1")["outreach"]["c1"]["linkedin"]["state"] == "invited"


def test_send_surfaces_in_get_search(tmp_path):
    client, _, _ = _client(tmp_path)
    client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    got = client.get("/search/s1")
    assert got.status_code == 200
    assert got.json()["outreach"]["c1"]["linkedin"]["state"] == "invited"


def test_send_email_resolves_candidate_address(tmp_path):
    client, fake, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "email", "subject": "Hi", "body": "Hello Jane"})
    assert resp.status_code == 200
    email_call = next(c for c in fake.calls if c[0] == "email")
    assert email_call[2] == "jane@acme.com"


def test_send_inmail_routes_to_message(tmp_path):
    client, fake, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi", "inmail": True})
    msg_call = next(c for c in fake.calls if c[0] == "message")
    assert resp.status_code == 200 and msg_call[4] is True


def test_stated_action_error_is_400(tmp_path):
    client, fake, _ = _client(tmp_path)
    def raise_err(*a, **k):
        raise OutreachActionError("Connect your LinkedIn in Settings → Integrations first.")
    fake.connect_linkedin = raise_err
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    assert resp.status_code == 400 and "Connect your LinkedIn" in resp.json()["detail"]


def test_unknown_candidate_is_404(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "nope", "channel": "linkedin", "body": "Hi"})
    assert resp.status_code == 404


def test_another_recruiter_cannot_reach_this_search(tmp_path):
    # Search owned by someone else -> invisible (404), never actionable.
    store = SearchStore(storage_dir=tmp_path / "s")
    _seed(store, owner="someone.else@example.com")
    app = create_app(outreach_service=FakeOutreach(), search_store=store)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(OWNER))
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    assert resp.status_code == 404


# --- reply webhook (step 4) ------------------------------------------------
def _set_outreach(store, entry):
    store.update("s1", lambda r: r.setdefault("outreach", {}).__setitem__("c1", {"linkedin": entry}))


def test_webhook_flips_matching_candidate_to_replied(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "get_unipile_webhook_secret", lambda: "SECRET")
    client, fake, store = _client(tmp_path)
    _set_outreach(store, {"channel": "linkedin", "state": "invited", "target_id": "PID-JANE"})
    fake.interp = {"owner_email": OWNER, "channel": "linkedin", "identifiers": ["PID-JANE"], "state": "replied"}
    resp = client.post("/integrations/webhook?token=SECRET", json={"account_id": "acc_li", "type": "message.new", "payload": {}})
    assert resp.status_code == 200 and resp.json()["updated"] == 1
    assert store.load("s1")["outreach"]["c1"]["linkedin"]["state"] == "replied"


def test_webhook_rejects_bad_token(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "get_unipile_webhook_secret", lambda: "SECRET")
    client, _, _ = _client(tmp_path)
    assert client.post("/integrations/webhook?token=wrong", json={}).status_code == 401


def test_webhook_no_match_is_a_quiet_200(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "get_unipile_webhook_secret", lambda: "SECRET")
    client, fake, store = _client(tmp_path)
    _set_outreach(store, {"channel": "linkedin", "state": "invited", "target_id": "PID-JANE"})
    fake.interp = {"owner_email": OWNER, "channel": "linkedin", "identifiers": ["SOMEONE-ELSE"], "state": "replied"}
    resp = client.post("/integrations/webhook?token=SECRET", json={"type": "message.new"})
    assert resp.status_code == 200 and resp.json()["updated"] == 0
    assert store.load("s1")["outreach"]["c1"]["linkedin"]["state"] == "invited"


def test_webhook_connected_does_not_downgrade_a_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod, "get_unipile_webhook_secret", lambda: "SECRET")
    client, fake, store = _client(tmp_path)
    _set_outreach(store, {"channel": "linkedin", "state": "replied", "target_id": "PID-JANE"})
    fake.interp = {"owner_email": OWNER, "channel": "linkedin", "identifiers": ["PID-JANE"], "state": "connected"}
    client.post("/integrations/webhook?token=SECRET", json={"type": "relation.new"})
    assert store.load("s1")["outreach"]["c1"]["linkedin"]["state"] == "replied"


def test_webhook_register_requires_admin(tmp_path):
    client, _, _ = _client(tmp_path)  # OWNER is not the super admin
    assert client.post("/integrations/webhook/register").status_code in (403, 404)


# --- replies & outreach view (round 2, part 2a) ----------------------------
def test_inbox_lists_contacted_rows(tmp_path):
    client, _, store = _client(tmp_path)
    store.update("s1", lambda r: r.__setitem__("outreach", {
        "c1": {"linkedin": {"channel": "linkedin", "state": "invited", "at": "2026-11-13T01:00:00+00:00", "target_id": "PID"}},
    }))
    data = client.get("/integrations/outreach/inbox").json()
    assert data["counts"]["total"] == 1
    row = data["inbox"][0]
    assert row["candidate_id"] == "c1" and row["name"] == "Jane Doe"
    assert row["role_title"] == "Principal Backend Engineer" and row["replied"] is False


def test_inbox_floats_replied_and_is_owner_scoped(tmp_path):
    client, _, store = _client(tmp_path)
    store.update("s1", lambda r: r.__setitem__("outreach", {
        "c1": {"linkedin": {"channel": "linkedin", "state": "replied", "at": "2026-11-13T01:00:00+00:00", "replied_at": "2026-11-13T02:00:00+00:00"}},
    }))
    # A different recruiter's contacted candidate must never show up here.
    store.save("s2", {"owner_email": "other@example.com", "response": {"candidates": [{"candidate_id": "x", "name": "Bob"}]},
                      "outreach": {"x": {"email": {"channel": "email", "state": "emailed", "at": "2026-11-13T03:00:00+00:00"}}}})
    data = client.get("/integrations/outreach/inbox").json()
    assert data["counts"]["total"] == 1 and data["counts"]["replied"] == 1
    assert data["inbox"][0]["replied"] is True and data["inbox"][0]["candidate_id"] == "c1"


# --- send-safety caps (step 5) ---------------------------------------------
def test_send_records_against_the_cap(tmp_path):
    client, fake, _ = _client(tmp_path)
    client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    assert ("record", OWNER, "linkedin_invite") in fake.calls


def test_send_blocked_when_cap_reached_returns_429(tmp_path):
    client, fake, store = _client(tmp_path)
    fake.over_limit = True
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    assert resp.status_code == 429 and "daily limit" in resp.json()["detail"]
    # Nothing was sent or recorded, and no outreach state was written.
    assert not any(c[0] == "connect" for c in fake.calls)
    assert "outreach" not in (store.load("s1") or {})


def test_limits_endpoint_is_owner_scoped(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/integrations/outreach/limits")
    assert resp.status_code == 200
    assert resp.json()["limits"]["linkedin_invite"]["remaining"] == 19


def test_send_response_includes_fresh_limits(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.post("/search/s1/outreach/send", json={"candidate_id": "c1", "channel": "linkedin", "body": "Hi"})
    assert resp.json()["limits"]["linkedin_invite"]["limit"] == 20
