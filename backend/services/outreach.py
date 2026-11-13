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

import html as _html
import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import get_unipile_hosted_auth_domain
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

# LinkedIn caps the custom note on a connection request (~200 chars on a free
# seat). We truncate rather than let the provider 400 — the draft aims shorter.
LINKEDIN_NOTE_CAP = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _linkedin_public_id(profile_url: Optional[str]) -> Optional[str]:
    """The /in/<slug> identifier from a LinkedIn profile URL — what Unipile's
    get_profile accepts to resolve the internal provider_id. None if the URL has
    no /in/ segment (e.g. a company page or a missing link)."""
    if not profile_url:
        return None
    match = re.search(r"/in/([^/?#]+)", str(profile_url))
    return match.group(1).strip() if match else None


def _is_first_degree(network_distance: Optional[str]) -> bool:
    """Whether the candidate is already a 1st-degree connection — in which case a
    normal message is sent instead of (and without spending) an InMail."""
    value = (network_distance or "").upper()
    return "1" in value or "FIRST" in value


def _text_to_html(text: str) -> str:
    """Plain draft text -> safe minimal HTML (blank lines split paragraphs,
    single newlines become <br>). `html` is required by Unipile for email
    tracking and renders consistently across clients."""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", (text or "").strip()) if block.strip()]
    paras = ["<p>" + _html.escape(block).replace("\n", "<br>") + "</p>" for block in blocks]
    return "".join(paras) or "<p></p>"


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


class OutreachActionError(Exception):
    """An outreach action that cannot proceed for a reason we state to the
    recruiter: the channel isn't connected, the candidate has no reachable
    LinkedIn link / email, or there's nothing to send. Provider-side rejections
    (char cap, already-connected, rate limit) surface as UnipileAPIError and are
    translated at the API layer, not here."""


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
            domain=get_unipile_hosted_auth_domain(),  # white-label host; no vendor shown
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

    # --- outreach actions (Phase 1, step 3) --------------------------------
    # Every action resolves the recruiter's own account_id from owner_email via
    # the ConnectedAccountStore — the account is NEVER taken from client input,
    # so one recruiter can only ever send from accounts they connected.

    def sender_name(self, owner_email: str, channel: str) -> Optional[str]:
        """Display name of the recruiter's connected account for this channel, to
        sign a draft with. None if not connected."""
        rec = self._accounts.account_for(owner_email, (channel or "").strip().lower())
        return (rec or {}).get("display_name")

    def _require_account_id(self, owner_email: str, channel: str) -> str:
        rec = self._accounts.account_for(owner_email, channel)
        if not rec or not rec.get("account_id"):
            label = {"linkedin": "LinkedIn", "email": "email", "whatsapp": "WhatsApp"}.get(channel, channel)
            raise OutreachActionError(f"Connect your {label} in Settings → Integrations first.")
        return rec["account_id"]

    def _resolve_linkedin(self, owner_email: str, profile_url: Optional[str]) -> Tuple[str, str, Optional[str]]:
        """(account_id, provider user_id, network_distance) for a candidate's
        LinkedIn profile, resolved through the recruiter's own account."""
        account_id = self._require_account_id(owner_email, "linkedin")
        public_id = _linkedin_public_id(profile_url)
        if not public_id:
            raise OutreachActionError("This candidate has no LinkedIn profile link to reach out to.")
        profile = self._client.get_profile(account_id, public_id) or {}
        user_id = profile.get("provider_id") or profile.get("id")
        if not user_id:
            raise OutreachActionError("Couldn't open this LinkedIn profile to send a message.")
        return account_id, str(user_id), profile.get("network_distance")

    def connect_linkedin(self, owner_email: str, *, profile_url: Optional[str], note: Optional[str] = None) -> Dict[str, Any]:
        """Send a LinkedIn connection request (with an optional note) from the
        recruiter's account."""
        account_id, user_id, _ = self._resolve_linkedin(owner_email, profile_url)
        note = (note or "").strip()[:LINKEDIN_NOTE_CAP] or None
        self._client.send_relation_request(account_id, user_id, note)
        return {"channel": "linkedin", "state": "invited", "kind": "connect", "at": _now().isoformat()}

    def message_linkedin(self, owner_email: str, *, profile_url: Optional[str], text: str, inmail: bool = False) -> Dict[str, Any]:
        """Message a candidate on LinkedIn. A 1st-degree connection gets a normal
        message; otherwise `inmail=True` sends an InMail (needs a Premium/Recruiter
        seat and spends an InMail credit)."""
        text = (text or "").strip()
        if not text:
            raise OutreachActionError("There's nothing to send.")
        account_id, user_id, distance = self._resolve_linkedin(owner_email, profile_url)
        use_inmail = bool(inmail) and not _is_first_degree(distance)
        self._client.start_chat(account_id, user_id, text, inmail=use_inmail)
        return {
            "channel": "linkedin",
            "state": "inmailed" if use_inmail else "messaged",
            "kind": "inmail" if use_inmail else "message",
            "at": _now().isoformat(),
        }

    def email_candidate(self, owner_email: str, *, to_email: Optional[str], subject: Optional[str], body: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        """Send an email to a candidate from the recruiter's connected mailbox."""
        account_id = self._require_account_id(owner_email, "email")
        to_email = (to_email or "").strip()
        if not to_email:
            raise OutreachActionError("There's no email address on file for this candidate.")
        body = (body or "").strip()
        if not body:
            raise OutreachActionError("There's nothing to send.")
        recipient: Dict[str, str] = {"email": to_email}
        if display_name:
            recipient["display_name"] = display_name
        self._client.send_email(
            account_id,
            to=[recipient],
            subject=(subject or None),
            html=_text_to_html(body),
            plain_text=body,
        )
        return {"channel": "email", "state": "emailed", "kind": "email", "subject": subject or "", "at": _now().isoformat()}
