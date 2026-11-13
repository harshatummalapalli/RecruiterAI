"""Per-recruiter binding of connected Unipile accounts — the isolation core of
the outreach integration (docs/planning/UNIPILE_OUTREACH_PHASE1.md §1).

THE INVARIANT: every connected account belongs to exactly one recruiter
(owner_email), every read/write here is scoped to an owner_email, and a caller
resolves the acting `account_id` from the authenticated session owner — it is
NEVER taken from client input. This is the same per-user scoping that fixed the
cross-tenant leak, extended to messaging accounts.

One file per recruiter (filename = hash of owner_email, so an email can never
collide or leak into another's path); a recruiter holds at most one account per
provider (linkedin | google | outlook | whatsapp…). Mirrors the atomic-write +
lock discipline of backend/services/search_store.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = Path(__file__).resolve().parents[2] / "output" / "connected_accounts"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_owner(email: str) -> str:
    return (email or "").strip().lower()


def _norm_provider(provider: str) -> str:
    return (provider or "").strip().lower()


class ConnectedAccountStore:
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, owner_email: str) -> Path:
        key = hashlib.sha256(_norm_owner(owner_email).encode()).hexdigest()[:40]
        return self.storage_dir / f"{key}.json"

    def _load(self, owner_email: str) -> Dict[str, Any]:
        path = self._path(owner_email)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("accounts"), dict):
                    return data
            except (ValueError, OSError):
                logger.exception("Failed to load connected accounts | owner=%s", owner_email)
        return {"owner_email": _norm_owner(owner_email), "accounts": {}}

    def _save(self, owner_email: str, data: Dict[str, Any]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(owner_email)
        payload = json.dumps(data, indent=2, default=str)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    # --- writes ------------------------------------------------------------
    def bind(
        self,
        owner_email: str,
        provider: str,
        account_id: str,
        *,
        status: str = "running",
        display_name: Optional[str] = None,
        raw_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bind a connected account to this recruiter. `provider` is our product
        CHANNEL (linkedin | email | whatsapp); `raw_provider` is Unipile's actual
        provider (e.g. google/outlook under the email channel). Upsert per
        channel — re-connecting replaces the account_id, preserving connected_at."""
        owner = _norm_owner(owner_email)
        prov = _norm_provider(provider)
        with self.lock:
            data = self._load(owner)
            data["owner_email"] = owner
            prior = data["accounts"].get(prov) or {}
            data["accounts"][prov] = {
                "provider": prov,
                "raw_provider": raw_provider if raw_provider is not None else prior.get("raw_provider"),
                "account_id": account_id,
                "status": status,
                "display_name": display_name if display_name is not None else prior.get("display_name"),
                "connected_at": prior.get("connected_at") or _now_iso(),
                "updated_at": _now_iso(),
            }
            self._save(owner, data)
            return data["accounts"][prov]

    def set_status(self, owner_email: str, provider: str, status: str) -> Optional[Dict[str, Any]]:
        owner = _norm_owner(owner_email)
        prov = _norm_provider(provider)
        with self.lock:
            data = self._load(owner)
            rec = data["accounts"].get(prov)
            if not rec:
                return None
            rec["status"] = status
            rec["updated_at"] = _now_iso()
            self._save(owner, data)
            return rec

    def unbind(self, owner_email: str, provider: str) -> bool:
        owner = _norm_owner(owner_email)
        prov = _norm_provider(provider)
        with self.lock:
            data = self._load(owner)
            if prov in data["accounts"]:
                del data["accounts"][prov]
                self._save(owner, data)
                return True
            return False

    # --- reads (always owner-scoped) --------------------------------------
    def account_for(self, owner_email: str, provider: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self._load(owner_email)["accounts"].get(_norm_provider(provider))

    def account_id_for(self, owner_email: str, provider: str) -> Optional[str]:
        rec = self.account_for(owner_email, provider)
        return rec.get("account_id") if rec else None

    def list_for(self, owner_email: str) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._load(owner_email)["accounts"].values())

    # --- reverse lookup (webhook routing only) ----------------------------
    def owner_of_account(self, account_id: str) -> Optional[Tuple[str, str]]:
        """Return (owner_email, provider) for an account, or None when we don't
        own it — so an inbound webhook for an unknown account is dropped and an
        event can only ever touch the owning recruiter's data. Scans per-owner
        files (fine for Phase 1's few recruiters; replace with an index at scale)."""
        if not account_id:
            return None
        with self.lock:
            for path in self.storage_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                for provider, rec in (data.get("accounts") or {}).items():
                    if isinstance(rec, dict) and rec.get("account_id") == account_id:
                        return (data.get("owner_email", ""), provider)
            return None

    def set_status_by_account(self, account_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update status from an `account.status.*` webhook, routed by account_id."""
        found = self.owner_of_account(account_id)
        if not found:
            return None
        owner_email, provider = found
        return self.set_status(owner_email, provider, status)
