"""IntakeService — the new 7-agent brain behind the frontend's intake/search
contract. Wraps `recruiter.pipeline` + file-JSON session storage, and returns the
dayzero.partners shapes via `translate`.

Design mirrors the legacy semantics the frontend relies on:
  * the reader (LLM) runs ONCE at `start`; `answer` and `update_boundary` only
    re-run the pure `assemble` over the cached Understanding (no model call), the
    same "deterministic, no model call" guarantee the legacy boundary edit made.
  * `confirm` builds the immutable confirmed RoleModel (content-hashed id) that
    `run_search` is the only thing allowed to execute.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.bridge.session_store import ConfirmationStore
from backend.bridge.translate import (
    to_intake_result,
    to_intake_result_pending,
    to_search_intent,
    to_search_intent_from_understanding,
    to_search_response,
)
from recruiter.agents.calibration.apply import apply_answers
from recruiter.role_model.serde import to_dict

_ROOT = Path(__file__).resolve().parents[2] / "output"


class ConfirmationNotReady(ValueError):
    def __init__(self, reasons: List[str]) -> None:
        super().__init__("; ".join(reasons) or "The brief is not ready to search.")
        self.reasons = reasons


def _session_store():
    from backend.services.search_store import SearchStore
    return SearchStore(storage_dir=_ROOT / "intake_sessions")


def _u_to_dict(u) -> Dict[str, Any]:
    return dataclasses.asdict(u)


def _u_from_dict(d: Dict[str, Any]):
    from recruiter.agents.intake.model import ReadRequirement, Understanding
    return Understanding(
        identity=d["identity"],
        requirements=tuple(ReadRequirement(r["text"], r["tier"], r.get("evidence"), r.get("when", "any"))
                           for r in (d.get("requirements") or ())),
        posted_title=d.get("posted_title"), posted_title_source=d.get("posted_title_source"),
        min_years=d.get("min_years"), max_years=d.get("max_years"),
        employment_type=d.get("employment_type"), work_mode_in_notes=d.get("work_mode_in_notes"),
    )


def _content_id(model_dict: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(model_dict, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _coerce_answer(issue_id: str, value: Any) -> Any:
    if issue_id in ("min_years", "max_years"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


class IntakeService:
    def __init__(self, pipeline, sessions=None, confirmations: Optional[ConfirmationStore] = None) -> None:
        self._pipe = pipeline
        self._sessions = sessions or _session_store()
        self._confirmations = confirmations or ConfirmationStore()

    # --- internals ---
    def _result_from(self, raw_input, understanding, boundary, answers) -> Dict[str, Any]:
        outcome = self._pipe.intake.assemble(understanding, boundary, answers)
        if not outcome.ready:
            return to_intake_result_pending(raw_input, understanding, outcome.clarifications)
        return to_intake_result(raw_input, outcome.model, outcome.refinements, "ready")

    def _save(self, session_id, raw_input, understanding, boundary, answers, posted_title) -> None:
        self._sessions.save(session_id, {
            "session_id": session_id, "raw_input": raw_input,
            "understanding": _u_to_dict(understanding), "boundary": boundary or {},
            "answers": answers or {}, "posted_title": posted_title,
        })

    def _require(self, session_id) -> Dict[str, Any]:
        rec = self._sessions.load(session_id)
        if rec is None or not rec.get("understanding"):
            raise KeyError(session_id)
        return rec

    # --- API ---
    def parse_jd(self, jd_text: str) -> Dict[str, Any]:
        return to_search_intent_from_understanding(self._pipe.intake.read(jd_text, None))

    def start(self, raw_input: str, boundary: Dict[str, Any], posted_title: Optional[str] = None) -> Dict[str, Any]:
        u = self._pipe.intake.read(raw_input, posted_title or (boundary or {}).get("posted_title"))
        session_id = str(uuid4())
        result = self._result_from(raw_input, u, boundary or {}, {})
        self._save(session_id, raw_input, u, boundary or {}, {}, posted_title)
        return {"session_id": session_id, "result": result, "boundary": boundary or {}}

    def answer(self, session_id: str, issue_id: str, value: Any, label: str = "") -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        answers[issue_id] = _coerce_answer(issue_id, value)
        result = self._result_from(rec["raw_input"], u, rec.get("boundary") or {}, answers)
        self._save(session_id, rec["raw_input"], u, rec.get("boundary") or {}, answers, rec.get("posted_title"))
        return {"session_id": session_id, "result": result}

    def update_boundary(self, session_id: str, boundary: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        result = self._result_from(rec["raw_input"], u, boundary or {}, answers)
        self._save(session_id, rec["raw_input"], u, boundary or {}, answers, rec.get("posted_title"))
        return {"session_id": session_id, "result": result, "boundary": boundary or {}}

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        rec = self._sessions.load(session_id)
        if rec is None or not rec.get("understanding"):
            return None
        u = _u_from_dict(rec["understanding"])
        result = self._result_from(rec["raw_input"], u, rec.get("boundary") or {}, rec.get("answers") or {})
        return {"session_id": session_id, "result": result, "boundary": rec.get("boundary") or {},
                "posted_title_input": rec.get("posted_title")}

    def confirm(self, session_id: str, edits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        outcome = self._pipe.intake.assemble(u, rec.get("boundary") or {}, answers)
        if not outcome.ready:
            raise ConfirmationNotReady([q.prompt for q in outcome.clarifications])
        model = apply_answers(outcome.model, {**answers, **(edits or {})}, outcome.refinements)
        model = dataclasses.replace(model, model_id=_content_id(to_dict(model)))
        self._confirmations.create(model)
        return {"confirmation_id": model.model_id, "session_id": session_id,
                "posted_title": model.posted_title, "posted_title_source": model.posted_title_source,
                "candidate_identity": model.identity, "content_hash": model.model_id,
                "search_intent": to_search_intent(model), "edits": edits or {}}

    def run_search(self, confirmation_id: str, search_id: str, provider: str = "crustdata") -> Dict[str, Any]:
        model = self._confirmations.load(confirmation_id)
        if model is None:
            raise KeyError(confirmation_id)
        plan = self._pipe.briefing.build(model)
        search_result = self._pipe.search.run(plan.query)
        ranking = self._pipe.ranking.rank(model, list(search_result.candidates))
        return to_search_response(provider, search_id, model, search_result, ranking)

    def preview(self, confirmation_id: str):
        model = self._confirmations.load(confirmation_id)
        if model is None:
            raise KeyError(confirmation_id)
        return self._pipe.preview(model)
