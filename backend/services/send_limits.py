"""Per-recruiter outreach send log, for rolling-24h safety caps (Phase 1, step 5).

One file per recruiter (filename = hash(owner_email)), holding the timestamps of
each send by category ("linkedin_invite" | "linkedin_message" | "email"). Counts
within the trailing 24h enforce the caps; older entries are pruned on write so the
file never grows unbounded. This protects a recruiter's LinkedIn/email account from
being restricted for sending too much too fast — it is NOT a billing or quota
system, just a guardrail.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "output" / "outreach_limits"
WINDOW_SECONDS = 86_400          # 24h enforcement window
_RETENTION_SECONDS = 2 * 86_400  # keep ~48h of history, prune the rest


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SendLimitStore:
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = Path(storage_dir or _DEFAULT_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, owner_email: str) -> Path:
        digest = hashlib.sha256((owner_email or "").strip().lower().encode("utf-8")).hexdigest()[:40]
        return self.storage_dir / f"{digest}.json"

    def _read(self, owner_email: str) -> List[Dict[str, Any]]:
        path = self._path(owner_email)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("sends", []) if isinstance(data, dict) else []
        except (ValueError, OSError):
            return []

    def _write(self, owner_email: str, sends: List[Dict[str, Any]]) -> None:
        path = self._path(owner_email)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"sends": sends}), encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _within(sends: List[Dict[str, Any]], seconds: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
        cutoff = _now() - timedelta(seconds=seconds)
        kept = []
        for entry in sends:
            try:
                at = datetime.fromisoformat(entry["at"])
            except (KeyError, ValueError, TypeError):
                continue
            if at >= cutoff and (category is None or entry.get("category") == category):
                kept.append(entry)
        return kept

    def count(self, owner_email: str, category: str, *, seconds: int = WINDOW_SECONDS) -> int:
        with self.lock:
            return len(self._within(self._read(owner_email), seconds, category))

    def record(self, owner_email: str, category: str) -> None:
        with self.lock:
            sends = self._read(owner_email)
            sends.append({"at": _now().isoformat(), "category": category})
            # Prune anything older than retention so the file stays small.
            self._write(owner_email, self._within(sends, _RETENTION_SECONDS))

    def usage(self, owner_email: str, limits: Dict[str, int]) -> Dict[str, Dict[str, int]]:
        """{category: {used, limit, remaining}} over the trailing 24h, for the UI."""
        with self.lock:
            sends = self._read(owner_email)
            out: Dict[str, Dict[str, int]] = {}
            for category, limit in limits.items():
                used = len(self._within(sends, WINDOW_SECONDS, category))
                out[category] = {"used": used, "limit": limit, "remaining": max(0, limit - used)}
            return out
