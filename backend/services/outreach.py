"""Outreach connect-flow service (Phase 1, step 2).

Turns our product CHANNELS (linkedin | email | whatsapp) into Unipile hosted-auth
connections, binding each connected account to the recruiter who started the flow
— the per-recruiter isolation from docs/planning/UNIPILE_OUTREACH_PHASE1.md §1.

The binding hinge is a single-use, short-TTL `state` token minted per connect
attempt and tied to the authenticated owner_email. It travels to Unipile's hosted
page and returns on the callback (and the account.add webhook), so the new
account can only ever bind to the recruiter who started the flow. account_id is
never taken from client input.

Pure orchestration over an injected UnipileClient + ConnectedAccountStore +
PendingConnectStore, so the whole flow is unit-testable offline.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.providers.unipile import UnipileClient
from backend.services.connected_accounts import ConnectedAccountStore

logger = logging.getLogger(__name__)

# Product channels shown in Settings → Integrations, in display order.
CHANNELS: Tuple[str, ...] = ("linkedin", "email", "whatsapp")

# channel -> Unipile hosted-auth `providers` value. "email" offers every
# email-capable provider (Gmail/Outlook/IMAP) on Unipile's page.
_AUTH_PROVIDERS: Dict[str, str] = {
    "linkedin": "linkedin",
    "email": "*:EMAILS",
    "whatsapp": "whatsapp",
}

# Unipile's raw provider -> our channel (for validating the callback).
_CHANNEL_FOR_RAW: Dict[str, str] = {
    "linkedin": "linkedin",
    "google": "email",
    "outlook": "email",
    "imap": "email",
    "whatsapp": "whatsapp",
}

CONNECT_TTL_SECONDS = 900  # 15 min
_DEFAULT_PENDING_DIR = Path(__file__).resolve().parents[2] / "output" / "connect_tokens"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PendingConnectStore:
    """Single-use, TTL'd connect tokens: state_token -> {owner_email, channel}.
    File-backed so a server restart mid-flow doesn't silently bind to the wrong
    recruiter (an expired/missing token simply fails, and the recruiter retries)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        base = Path(path or _DEFAULT_PENDING_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self._path = base / "pending.json"
        self.lock = threading.RLock()

    def _read(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        tmp = self._path.with_name(f"pending.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)

    def put(self, token: str, owner_email: str, channel: str) -> None:
        with self.lock:
            data = self._prune(self._read())
            data[token] = {
                "owner_email": owner_email,
                "channel": channel,
                "expires_at": (_now() + timedelta(seconds=CONNECT_TTL_SECONDS)).isoformat(),
            }
            self._write(data)

    def take(self, token: str) -> Optional[Dict[str, str]]:
        """Return and REMOVE the token's record if present and unexpired; else None."""
        with self.lock:
            data = self._read()
            rec = data.pop(token, None)
            self._write(self._prune(data))
            if not rec:
                return None
            try:
                if datetime.fromisoformat(rec["expires_at"]) < _now():
                    return None
            except (KeyError, ValueError):
                return None
            return {"owner_email": rec["owner_email"], "channel": rec["channel"]}

    @staticmethod
    def _prune(data: Dict[str, Any]) -> Dict[str, Any]:
        now = _now()
        kept = {}
        for token, rec in data.items():
            try:
                if datetime.fromisoformat(rec["expires_at"]) >= now:
                    kept[token] = rec
            except (KeyError, ValueError, TypeError):
                continue
        return kept


class OutreachConnectError(Exception):
    """A connect attempt that cannot proceed (unknown channel, bad/expired token)."""


class OutreachService:
    def __init__(
        self,
        client: UnipileClient,
        accounts: ConnectedAccountStore,
        pending: PendingConnectStore,
    ) -> None:
        self._client = client
        self._accounts = accounts
        self._pending = pending

    def begin_connect(self, owner_email: str, channel: str, *, callback_url: str) -> str:
        """Mint a state token for this recruiter+channel and return the Unipile
        hosted-auth link to redirect them to."""
        channel = (channel or "").strip().lower()
        if channel not in _AUTH_PROVIDERS:
            raise OutreachConnectError(f"Unknown channel: {channel!r}")
        token = secrets.token_urlsafe(32)
        self._pending.put(token, owner_email, channel)
        expires_on = (_now() + timedelta(seconds=CONNECT_TTL_SECONDS)).isoformat()
        data = self._client.create_auth_link(
            providers=[_AUTH_PROVIDERS[channel]],
            redirect_uri=callback_url,
            state=token,
            expires_on=expires_on,
        )
        link = data.get("link") if isinstance(data, dict) else None
        if not link:
            raise OutreachConnectError("Unipile did not return a hosted-auth link.")
        return link

    def complete_connect(self, state: str, account_id: str, provider: str) -> Tuple[str, str]:
        """Bind a freshly connected account to the recruiter who started the flow.
        Returns (owner_email, channel). Raises if the state token is unknown/expired
        or the returned provider doesn't match the channel the recruiter chose."""
        rec = self._pending.take(state or "")
        if not rec:
            raise OutreachConnectError("This connection link has expired or was already used.")
        owner_email, channel = rec["owner_email"], rec["channel"]
        raw = (provider or "").strip().lower()
        if raw and _CHANNEL_FOR_RAW.get(raw, channel) != channel:
            raise OutreachConnectError("The connected account did not match the requested integration.")
        display_name = None
        try:
            display_name = (self._client.get_account(account_id) or {}).get("name")
        except Exception:  # best-effort; binding must not depend on it
            logger.warning("Could not fetch account name on connect | account_id=%s", account_id)
        self._accounts.bind(
            owner_email, channel, account_id,
            status="running", display_name=display_name, raw_provider=raw or None,
        )
        logger.info("Bound account | owner=%s channel=%s account_id=%s", owner_email, channel, account_id)
        return owner_email, channel

    def list_integrations(self, owner_email: str) -> List[Dict[str, Any]]:
        """Every channel with its connection state, for Settings → Integrations."""
        connected = {r["provider"]: r for r in self._accounts.list_for(owner_email)}
        out: List[Dict[str, Any]] = []
        for channel in CHANNELS:
            rec = connected.get(channel)
            out.append({
                "channel": channel,
                "connected": bool(rec),
                "status": (rec or {}).get("status"),
                "display_name": (rec or {}).get("display_name"),
                "raw_provider": (rec or {}).get("raw_provider"),
                "connected_at": (rec or {}).get("connected_at"),
            })
        return out

    def disconnect(self, owner_email: str, channel: str) -> bool:
        """Unbind a channel for this recruiter and revoke it at Unipile (best-effort)."""
        channel = (channel or "").strip().lower()
        rec = self._accounts.account_for(owner_email, channel)
        if rec and rec.get("account_id"):
            try:
                self._client.delete_account(rec["account_id"])
            except Exception:  # local unbind still proceeds
                logger.warning("Unipile account delete failed on disconnect | account_id=%s", rec.get("account_id"))
        return self._accounts.unbind(owner_email, channel)
