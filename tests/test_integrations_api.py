"""/integrations/* endpoints — owner-scoped connect flow (offline, fake service)."""

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.services.search_store import SearchStore

OWNER = "alice@example.com"


class FakeOutreach:
    def __init__(self):
        self.calls = []

    def list_integrations(self, owner):
        self.calls.append(("list", owner))
        return [{"channel": "linkedin", "connected": False}]

    def begin_connect(self, owner, channel, *, callback_url):
        self.calls.append(("begin", owner, channel, callback_url))
        return "https://connect.dayzero.partners/hosted/xyz"

    def complete_connect(self, state, account_id, provider):
        self.calls.append(("complete", state, account_id, provider))
        return (OWNER, "linkedin")

    def disconnect(self, owner, channel):
        self.calls.append(("disconnect", owner, channel))
        return True


def _client(tmp_path):
    fake = FakeOutreach()
    app = create_app(outreach_service=fake, search_store=SearchStore(storage_dir=tmp_path / "s"))
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(OWNER))
    return client, fake


def test_list_integrations_is_owner_scoped(tmp_path):
    client, fake = _client(tmp_path)
    resp = client.get("/integrations")
    assert resp.status_code == 200
    assert resp.json()["integrations"][0]["channel"] == "linkedin"
    assert fake.calls[-1] == ("list", OWNER)


def test_connect_returns_white_label_link_and_passes_owner(tmp_path):
    client, fake = _client(tmp_path)
    resp = client.post("/integrations/connect", json={"channel": "linkedin"})
    assert resp.status_code == 200
    assert resp.json()["link"].startswith("https://connect.dayzero.partners/")
    kind, owner, channel, callback = fake.calls[-1]
    assert (kind, owner, channel) == ("begin", OWNER, "linkedin")
    assert callback.endswith("/integrations/callback")


def test_callback_binds_and_returns_our_page(tmp_path):
    client, fake = _client(tmp_path)
    resp = client.get("/integrations/callback", params={"account_id": "acc_1", "provider": "linkedin", "state": "tok"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "unipile" not in resp.text.lower()          # no vendor name on our page
    assert fake.calls[-1] == ("complete", "tok", "acc_1", "linkedin")


def test_callback_error_shows_friendly_page_without_binding(tmp_path):
    client, fake = _client(tmp_path)
    resp = client.get("/integrations/callback", params={"error_title": "Cancelled"})
    assert resp.status_code == 200
    assert "Cancelled" in resp.text
    assert not any(c[0] == "complete" for c in fake.calls)


def test_disconnect(tmp_path):
    client, fake = _client(tmp_path)
    resp = client.post("/integrations/disconnect", json={"channel": "linkedin"})
    assert resp.status_code == 200 and resp.json()["disconnected"] is True
    assert fake.calls[-1] == ("disconnect", OWNER, "linkedin")


def test_unauthenticated_cannot_list(tmp_path):
    fake = FakeOutreach()
    app = create_app(outreach_service=fake, search_store=SearchStore(storage_dir=tmp_path / "s"))
    client = TestClient(app)  # no session cookie
    assert client.get("/integrations").status_code in (401, 403)
