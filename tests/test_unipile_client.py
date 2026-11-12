"""UnipileClient — request shaping + error handling (offline, httpx MockTransport)."""

import json

import httpx
import pytest

from backend.providers import unipile as unipile_mod
from backend.providers.unipile import (
    UnipileAPIError,
    UnipileClient,
    UnipileNotConfiguredError,
)

ACC = "acc_123"


def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return UnipileClient(client=http, base_url="https://api.unipile.com", api_key="test-key")


def _json(request):
    return json.loads(request.content) if request.content else None


def test_list_accounts_parses_data_and_sends_api_key():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"object": "Accounts", "data": [{"id": "acc_1"}, {"id": "acc_2"}]})

    accounts = _client(handler).list_accounts()
    assert [a["id"] for a in accounts] == ["acc_1", "acc_2"]
    assert seen["path"] == "/v2/accounts/"
    assert seen["key"] == "test-key"


def test_send_relation_request_posts_user_id_and_message():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = _json(request)
        return httpx.Response(201, json={"object": "RelationRequest", "type": "sent", "id": "SENT_1"})

    out = _client(handler).send_relation_request(ACC, "user_x", message="hi")
    assert out["id"] == "SENT_1"
    assert captured["path"] == f"/v2/{ACC}/users/me/relation-requests"
    assert captured["body"] == {"user_id": "user_x", "message": "hi"}


def test_start_chat_sets_the_inmail_flag():
    captured = {}

    def handler(request):
        captured["body"] = _json(request)
        return httpx.Response(200, json={"object": "ChatStarted", "chat_id": "c1", "message_id": "m1"})

    _client(handler).start_chat(ACC, "user_x", "hello", inmail=True)
    assert captured["body"]["text"] == "hello"
    assert captured["body"]["users_ids"] == "user_x"
    assert captured["body"]["specifics"]["linkedin"]["classic"]["inmail"] is True


def test_send_email_shapes_body_with_tracking():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = _json(request)
        return httpx.Response(200, json={"object": "EmailSent", "id": "e1"})

    _client(handler).send_email(
        ACC, to=[{"email": "a@b.com"}], subject="Hi", html="<p>x</p>",
        tracking={"opens": True, "clicks": True},
    )
    assert captured["path"] == f"/v2/{ACC}/emails/send"
    assert captured["body"]["to"] == [{"email": "a@b.com"}]
    assert captured["body"]["subject"] == "Hi"
    assert captured["body"]["tracking_options"] == {"opens": True, "clicks": True}


def test_create_auth_link_carries_the_state_binding_token():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = _json(request)
        return httpx.Response(200, json={"object": "HostedAuthUrl", "url": "https://auth.unipile.com/x"})

    _client(handler).create_auth_link(
        providers=["LINKEDIN"], redirect_uri="https://hire.dayzero.partners/connect/callback",
        state="tok_abc", expires_on="2026-11-12T13:00:00.000Z",
    )
    assert captured["path"] == "/v2/auth/link"
    assert captured["body"]["state"] == "tok_abc"
    assert captured["body"]["providers"] == ["LINKEDIN"]


def test_api_error_surfaces_unipile_detail():
    def handler(request):
        return httpx.Response(400, json={
            "object": "Error", "status": 400, "type": "provider/invalid_parameters",
            "title": "Invalid parameters", "detail": "You have reached the maximum number of characters for the custom message.",
        })

    with pytest.raises(UnipileAPIError) as exc:
        _client(handler).send_relation_request(ACC, "user_x", message="too long")
    assert exc.value.status == 400
    assert "maximum number of characters" in exc.value.detail


def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(unipile_mod, "get_unipile_api_key", lambda: None)
    client = UnipileClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    with pytest.raises(UnipileNotConfiguredError):
        client.list_accounts()


def test_is_configured_reflects_key():
    assert UnipileClient(api_key="k").is_configured() is True
