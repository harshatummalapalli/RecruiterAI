"""Reply-inbox service: event interpretation (account -> owner routing) and
idempotent webhook registration. Offline, fake client."""

import backend.services.outreach as outreach_mod
from backend.services.connected_accounts import ConnectedAccountStore
from backend.services.outreach import OutreachActionError, OutreachService, PendingConnectStore, REPLY_EVENTS

A = "alice@example.com"


class FakeClient:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.created = []

    def list_webhooks(self):
        return self.existing

    def create_webhook(self, *, url, trigger_events, account_ids=None, description=None):
        self.created.append({"url": url, "trigger_events": trigger_events})
        return {"object": "WebhookEndpoint", "id": "we_1", "secret": "unipile-gen", "url": url}


def _svc(tmp_path, existing=None):
    client = FakeClient(existing)
    accounts = ConnectedAccountStore(storage_dir=tmp_path / "accounts")
    accounts.bind(A, "linkedin", "acc_li", status="running", display_name="Alice R")
    accounts.bind(A, "email", "acc_gm", status="running", raw_provider="google")
    svc = OutreachService(client, accounts, PendingConnectStore(path=tmp_path / "pending"))
    return svc, client


def test_email_reply_maps_to_owner_sender_and_preview(tmp_path):
    svc, _ = _svc(tmp_path)
    event = {"account_id": "acc_gm", "type": "email.new", "payload": {"email": {"from": [{"email": "Jane@Acme.com"}], "snippet": "Sure, happy to chat next week."}}}
    interp = svc.interpret_event(event)
    assert interp["owner_email"] == A and interp["identifiers"] == ["jane@acme.com"] and interp["state"] == "replied"
    assert interp["preview"] == "Sure, happy to chat next week."


def test_inbound_linkedin_message_is_a_reply_with_text(tmp_path):
    svc, _ = _svc(tmp_path)
    event = {"account_id": "acc_li", "type": "message.new", "payload": {"is_sender": False, "sender_id": "PID-JANE", "text": "Thanks for reaching out!"}}
    interp = svc.interpret_event(event)
    assert interp["state"] == "replied" and interp["identifiers"] == ["PID-JANE"] and interp["channel"] == "linkedin"
    assert interp["preview"] == "Thanks for reaching out!"


def test_our_own_outbound_message_is_not_a_reply(tmp_path):
    svc, _ = _svc(tmp_path)
    event = {"account_id": "acc_li", "type": "message.new", "payload": {"is_sender": True, "sender_id": "ME"}}
    assert svc.interpret_event(event) is None


def test_relation_new_maps_to_connected(tmp_path):
    svc, _ = _svc(tmp_path)
    event = {"account_id": "acc_li", "type": "relation.new", "payload": {"member_id": "PID-JANE"}}
    interp = svc.interpret_event(event)
    assert interp["state"] == "connected" and interp["identifiers"] == ["PID-JANE"]


def test_unknown_account_is_ignored(tmp_path):
    svc, _ = _svc(tmp_path)
    assert svc.interpret_event({"account_id": "acc_other", "type": "message.new", "payload": {"sender_id": "x"}}) is None


def test_untracked_event_type_is_ignored(tmp_path):
    svc, _ = _svc(tmp_path)
    assert svc.interpret_event({"account_id": "acc_li", "type": "message.receipt.read", "payload": {}}) is None


def test_register_webhook_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach_mod, "get_unipile_webhook_secret", lambda: "s3cr3t")
    svc, client = _svc(tmp_path, existing=[{"id": "we_old", "url": "https://hire.dayzero.partners/integrations/webhook?token=s3cr3t"}])
    out = svc.ensure_reply_webhook(public_base_url="https://hire.dayzero.partners/")
    assert out["registered"] is False and out["id"] == "we_old"
    assert client.created == []  # did not create a duplicate


def test_register_webhook_creates_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach_mod, "get_unipile_webhook_secret", lambda: "s3cr3t")
    svc, client = _svc(tmp_path)
    out = svc.ensure_reply_webhook(public_base_url="https://hire.dayzero.partners/")
    assert out["registered"] is True
    assert client.created[0]["url"].endswith("/integrations/webhook?token=s3cr3t")
    assert set(client.created[0]["trigger_events"]) == set(REPLY_EVENTS)


def test_register_webhook_requires_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach_mod, "get_unipile_webhook_secret", lambda: "")
    svc, _ = _svc(tmp_path)
    try:
        svc.ensure_reply_webhook(public_base_url="https://hire.dayzero.partners/")
        assert False, "expected OutreachActionError"
    except OutreachActionError:
        pass
