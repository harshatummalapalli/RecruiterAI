"""OutreachService send actions (connect / InMail / email) — offline, fake client.

Proves the recruiter's account is resolved from owner_email (never the client),
LinkedIn URLs resolve to a provider id, the note cap + InMail-vs-message rule
hold, and the stated errors fire when a channel/link/email is missing."""

import pytest

from backend.services.connected_accounts import ConnectedAccountStore
from backend.services.outreach import (
    LINKEDIN_NOTE_CAP,
    OutreachActionError,
    OutreachService,
    PendingConnectStore,
    _linkedin_public_id,
)

A = "alice@example.com"
URL = "https://www.linkedin.com/in/jane-doe-123/"


class FakeClient:
    def __init__(self):
        self.profiles = {"jane-doe-123": {"provider_id": "PID-JANE", "network_distance": "DISTANCE_2", "name": "Jane Doe"}}
        self.relation_requests = []
        self.chats = []
        self.emails = []

    def get_profile(self, account_id, identifier, **_):
        return self.profiles.get(identifier, {})

    def send_relation_request(self, account_id, user_id, message=None):
        self.relation_requests.append({"account_id": account_id, "user_id": user_id, "message": message})
        return {"object": "RelationRequestSent"}

    def start_chat(self, account_id, users_ids, text, *, inmail=False, linkedin_specifics=None):
        self.chats.append({"account_id": account_id, "users_ids": users_ids, "text": text, "inmail": inmail})
        return {"object": "ChatStarted"}

    def send_email(self, account_id, *, to, subject=None, html=None, plain_text=None, **_):
        self.emails.append({"account_id": account_id, "to": to, "subject": subject, "html": html, "plain_text": plain_text})
        return {"object": "EmailSent"}

    # unused here but part of the client surface
    def get_account(self, account_id):
        return {}

    def delete_account(self, account_id):
        return {}


def _svc(tmp_path, *, connect_linkedin=True, connect_email=False):
    client = FakeClient()
    accounts = ConnectedAccountStore(storage_dir=tmp_path / "accounts")
    if connect_linkedin:
        accounts.bind(A, "linkedin", "acc_li", status="running", display_name="Alice R")
    if connect_email:
        accounts.bind(A, "email", "acc_gm", status="running", display_name="Alice R", raw_provider="google")
    svc = OutreachService(client, accounts, PendingConnectStore(path=tmp_path / "pending"))
    return svc, client


def test_public_id_parsing():
    assert _linkedin_public_id("https://www.linkedin.com/in/jane-doe-123/") == "jane-doe-123"
    assert _linkedin_public_id("https://linkedin.com/in/bob?trk=x") == "bob"
    assert _linkedin_public_id("https://linkedin.com/company/acme") is None
    assert _linkedin_public_id(None) is None


def test_connect_resolves_profile_and_sends_request(tmp_path):
    svc, client = _svc(tmp_path)
    result = svc.connect_linkedin(A, profile_url=URL, note="Hi Jane, loved your work.")
    assert result["state"] == "invited"
    req = client.relation_requests[0]
    assert req["account_id"] == "acc_li"      # resolved from owner, not client
    assert req["user_id"] == "PID-JANE"       # public id -> provider id
    assert req["message"] == "Hi Jane, loved your work."


def test_connect_truncates_note_to_cap(tmp_path):
    svc, client = _svc(tmp_path)
    svc.connect_linkedin(A, profile_url=URL, note="x" * 400)
    assert len(client.relation_requests[0]["message"]) == LINKEDIN_NOTE_CAP


def test_connect_without_linkedin_connected_is_a_stated_error(tmp_path):
    svc, _ = _svc(tmp_path, connect_linkedin=False)
    with pytest.raises(OutreachActionError, match="Connect your LinkedIn"):
        svc.connect_linkedin(A, profile_url=URL, note="hi")


def test_connect_without_profile_link_is_a_stated_error(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(OutreachActionError, match="no LinkedIn profile link"):
        svc.connect_linkedin(A, profile_url=None, note="hi")


def test_message_uses_inmail_for_non_first_degree(tmp_path):
    svc, client = _svc(tmp_path)
    result = svc.message_linkedin(A, profile_url=URL, text="Quick note about a role.", inmail=True)
    assert result["state"] == "inmailed" and client.chats[0]["inmail"] is True


def test_message_downgrades_inmail_for_first_degree(tmp_path):
    svc, client = _svc(tmp_path)
    client.profiles["jane-doe-123"]["network_distance"] = "DISTANCE_1"
    result = svc.message_linkedin(A, profile_url=URL, text="Hey!", inmail=True)
    assert result["state"] == "messaged" and client.chats[0]["inmail"] is False


def test_email_sends_with_email_keyed_recipient(tmp_path):
    svc, client = _svc(tmp_path, connect_email=True)
    result = svc.email_candidate(A, to_email="jane@acme.com", subject="A role", body="Hi Jane,\n\nInterested?", display_name="Jane Doe")
    assert result["state"] == "emailed"
    sent = client.emails[0]
    assert sent["account_id"] == "acc_gm"
    assert sent["to"] == [{"email": "jane@acme.com", "display_name": "Jane Doe"}]  # Unipile uses `email`, not `identifier`
    assert "<p>" in sent["html"] and sent["plain_text"].startswith("Hi Jane")


def test_email_without_address_is_a_stated_error(tmp_path):
    svc, _ = _svc(tmp_path, connect_email=True)
    with pytest.raises(OutreachActionError, match="no email address"):
        svc.email_candidate(A, to_email=None, subject="x", body="y")


def test_sender_name_from_connected_account(tmp_path):
    svc, _ = _svc(tmp_path)
    assert svc.sender_name(A, "linkedin") == "Alice R"
    assert svc.sender_name(A, "email") is None  # not connected in this fixture
