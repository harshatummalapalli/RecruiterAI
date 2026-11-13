"""Unipile client — the server-side rail for outreach & messaging (LinkedIn,
email, WhatsApp-later) behind RecruiterAI.

Thin wrapper over Unipile's REST API (base https://api.unipile.com, auth header
`X-API-KEY`), same shape as backend/providers/harvest.py. Every provider action
is scoped to an `account_id` (acc_xxx) — the connected account of ONE recruiter.
This client does NOT know which recruiter owns an account; that mapping and its
per-recruiter isolation live in backend/services/connected_accounts.py, and the
`account_id` passed here is always resolved there from the authenticated
owner_email (never taken from client input). See docs/planning/
UNIPILE_OUTREACH_PHASE1.md.

The client RAISES on failure (it never silently swallows) — the API/service
layer decides how to surface an outreach error to the recruiter. The production
key is UNIPILE_API_KEY in the server env; the MCP key used for exploration is
test-only and never used here.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_unipile_api_key, get_unipile_base_url

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0


class UnipileError(Exception):
    """Base for every Unipile client failure."""


class UnipileNotConfiguredError(UnipileError):
    """UNIPILE_API_KEY is not set."""


class UnipileResponseError(UnipileError):
    """A 2xx whose body was not the expected JSON."""


class UnipileAPIError(UnipileError):
    """A non-2xx response. Carries Unipile's own error fields so the caller can
    surface a precise message (e.g. the custom-message character cap)."""

    def __init__(self, status: int, *, type: str = "", title: str = "", detail: str = "") -> None:
        self.status = status
        self.type = type
        self.title = title
        self.detail = detail
        super().__init__(f"Unipile API error {status}: {type or title} {detail}".strip())


class UnipileClient:
    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        # `client`/`base_url`/`api_key` are injectable for tests; production reads
        # the key and base URL from the server env at call time.
        self._client = client
        self._base_url_override = base_url
        self._api_key_override = api_key

    def is_configured(self) -> bool:
        return bool(self._api_key_override or get_unipile_api_key())

    # --- transport ---------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> Any:
        api_key = self._api_key_override or get_unipile_api_key()
        if not api_key:
            raise UnipileNotConfiguredError("UNIPILE_API_KEY is not configured.")
        base = (self._base_url_override or get_unipile_base_url()).rstrip("/")
        url = f"{base}/{path.lstrip('/')}"
        headers = {"X-API-KEY": api_key, "accept": "application/json"}

        client = self._client or httpx.Client(timeout=timeout)
        should_close = self._client is None
        try:
            response = client.request(method, url, params=params, json=json, headers=headers)
        finally:
            if should_close:
                client.close()

        if response.status_code >= 400:
            raise self._api_error(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise UnipileResponseError("Unipile returned a non-JSON response.") from exc

    @staticmethod
    def _api_error(response: httpx.Response) -> UnipileAPIError:
        detail = title = type_ = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or "")
                title = str(body.get("title") or "")
                type_ = str(body.get("type") or "")
        except ValueError:
            detail = response.text[:300]
        logger.warning("Unipile API error | status=%s type=%s detail=%s", response.status_code, type_, detail)
        return UnipileAPIError(response.status_code, type=type_, title=title, detail=detail)

    # --- accounts & auth ---------------------------------------------------
    def list_accounts(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/v2/accounts/")
        return list(data.get("data", [])) if isinstance(data, dict) else []

    def get_account(self, account_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v2/accounts/{account_id}")

    def delete_account(self, account_id: str) -> Dict[str, Any]:
        """Unlink an account at Unipile (revokes the provider session). Used on
        disconnect so a removed integration stops billing and receiving events."""
        return self._request("DELETE", f"/v2/accounts/{account_id}")

    def create_auth_link(
        self,
        *,
        providers: List[str],
        redirect_uri: str,
        state: str,
        expires_on: str,
        notify_url: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hosted-auth link. `state` is our opaque, single-use recruiter token —
        it returns on the redirect AND the account.add webhook, binding the new
        account to the right recruiter (see the isolation model in the spec).
        `domain` serves the wizard on our white-label host (must be verified with
        Unipile) so recruiters never see the vendor."""
        body: Dict[str, Any] = {
            "providers": providers,
            "redirect_uri": redirect_uri,
            "state": state,
            "expires_on": expires_on,
        }
        if notify_url:
            body["notify_url"] = notify_url
        if domain:
            body["domain"] = domain
        return self._request("POST", "/v2/auth/link", json=body)

    # --- people / profiles -------------------------------------------------
    def get_profile(self, account_id: str, identifier: str, *, notify: bool = False) -> Dict[str, Any]:
        params = {"notify": "true"} if notify else None
        return self._request("GET", f"/v2/{account_id}/users/{identifier}", params=params)

    def search_people(self, account_id: str, body: Dict[str, Any], *, cursor: Optional[str] = None) -> Dict[str, Any]:
        params = {"cursor": cursor} if cursor else None
        return self._request("POST", f"/v2/{account_id}/linkedin/search/people", params=params, json=body)

    # --- outreach: connections & messages ----------------------------------
    def send_relation_request(self, account_id: str, user_id: str, message: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"user_id": user_id}
        if message:
            body["message"] = message
        return self._request("POST", f"/v2/{account_id}/users/me/relation-requests", json=body)

    def start_chat(
        self,
        account_id: str,
        users_ids: Any,
        text: str,
        *,
        inmail: bool = False,
        linkedin_specifics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start a 1:1 (users_ids as a string) or group chat. `inmail` sets the
        LinkedIn classic InMail flag; pass richer `linkedin_specifics` for Sales
        Navigator / Recruiter sends later."""
        body: Dict[str, Any] = {"text": text, "users_ids": users_ids}
        linkedin = dict(linkedin_specifics or {})
        if inmail:
            linkedin.setdefault("classic", {})["inmail"] = True
        if linkedin:
            body["specifics"] = {"linkedin": linkedin}
        return self._request("POST", f"/v2/{account_id}/chats/send", json=body)

    def send_message(self, account_id: str, chat_id: str, text: str) -> Dict[str, Any]:
        return self._request("POST", f"/v2/{account_id}/chats/{chat_id}/messages/send", json={"text": text})

    def list_chats(self, account_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", f"/v2/{account_id}/chats", params=params)

    # --- outreach: email ---------------------------------------------------
    def send_email(
        self,
        account_id: str,
        *,
        to: List[Dict[str, str]],
        subject: Optional[str] = None,
        html: Optional[str] = None,
        plain_text: Optional[str] = None,
        cc: Optional[List[Dict[str, str]]] = None,
        reply_to_provider_id: Optional[str] = None,
        tracking: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"to": to}
        if subject is not None:
            body["subject"] = subject
        if html is not None:
            body["html"] = html
        if plain_text is not None:
            body["plain_text"] = plain_text
        if cc:
            body["cc"] = cc
        if reply_to_provider_id:
            body["reply_to_provider_id"] = reply_to_provider_id
        if tracking:
            body["tracking_options"] = tracking
        return self._request("POST", f"/v2/{account_id}/emails/send", json=body)

    # --- webhooks ----------------------------------------------------------
    def create_webhook(self, *, url: str, trigger_events: List[str], account_ids: Optional[List[str]] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Create a webhook endpoint (v2 shape: `trigger_events` + `url`). Omitting
        `account_ids` listens to every account in the application — we route each
        event to its owner by account_id, so one endpoint serves all recruiters.
        Unipile generates and returns a `secret`; we secure the receiver with our
        own token in the `url` query instead."""
        body: Dict[str, Any] = {"trigger_events": trigger_events, "url": url}
        if account_ids:
            body["account_ids"] = account_ids
        if description:
            body["description"] = description
        return self._request("POST", "/v2/webhooks/endpoints/", json=body)

    def list_webhooks(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/v2/webhooks/endpoints/")
        if isinstance(data, dict):
            return list(data.get("data", data.get("items", [])) or [])
        return list(data) if isinstance(data, list) else []

    def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v2/webhooks/endpoints/{webhook_id}")
