"""Persist the new engine's RoleModel over the existing file-JSON SearchStore.

Two stores, same primitive the OCI backend already uses (atomic writes, locked
read-modify-write), at two dirs:
  * RoleSessionStore  — the in-progress intake session (model + boundary + answers),
    the analogue of the legacy intake_session manager.
  * ConfirmationStore — the immutable confirmed model that /search runs from,
    keyed by the model's own id (the legacy confirmation snapshot).

No database, no migration — the §6 read confirmed storage is file-JSON.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from recruiter.role_model import RoleModel
from recruiter.role_model.serde import from_dict, to_dict

_ROOT = Path(__file__).resolve().parents[2] / "output"


def _store(storage_dir: Path):
    from backend.services.search_store import SearchStore
    return SearchStore(storage_dir=storage_dir)


class RoleSessionStore:
    """The intake session: a confirmed-or-draft RoleModel plus the raw inputs
    needed to re-assemble it deterministically (boundary edits, answers)."""

    def __init__(self, store=None) -> None:
        self._store = store or _store(_ROOT / "role_sessions")

    def save(self, session_id: str, model: RoleModel, *, raw_input: str = "",
             boundary: Optional[Dict[str, Any]] = None, answers: Optional[Dict[str, Any]] = None,
             posted_title: Optional[str] = None) -> None:
        self._store.save(session_id, {
            "session_id": session_id,
            "model": to_dict(model),
            "raw_input": raw_input,
            "boundary": boundary or {},
            "answers": answers or {},
            "posted_title": posted_title,
        })

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        rec = self._store.load(session_id)
        if rec is None or not rec.get("model"):
            return None
        return {
            "session_id": rec.get("session_id", session_id),
            "model": from_dict(rec["model"]),
            "raw_input": rec.get("raw_input", ""),
            "boundary": rec.get("boundary") or {},
            "answers": rec.get("answers") or {},
            "posted_title": rec.get("posted_title"),
        }

    def update_model(self, session_id: str, model: RoleModel, *,
                     boundary: Optional[Dict[str, Any]] = None,
                     answers: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        def mutate(rec: Dict[str, Any]) -> None:
            rec["model"] = to_dict(model)
            if boundary is not None:
                rec["boundary"] = boundary
            if answers is not None:
                rec["answers"] = answers
        return self._store.update(session_id, mutate)


class ConfirmationStore:
    """The immutable confirmed model /search runs from, keyed by its model_id."""

    def __init__(self, store=None) -> None:
        self._store = store or _store(_ROOT / "confirmations_v2")

    def create(self, model: RoleModel) -> str:
        if not model.model_id:
            raise ValueError("a confirmed model must carry a model_id")
        self._store.save(model.model_id, {"model_id": model.model_id, "model": to_dict(model)})
        return model.model_id

    def load(self, confirmation_id: str) -> Optional[RoleModel]:
        rec = self._store.load(confirmation_id)
        if rec is None or not rec.get("model"):
            return None
        return from_dict(rec["model"])
