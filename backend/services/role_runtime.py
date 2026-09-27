"""Role orchestration: multi-search summaries, recruiter decisions with feedback, one-time calibration, "Show me more",
pause/resume, and the daily background search.

A role is a search record (backend/services/search_store.py). This module never runs retrieval itself: it decides WHAT
should happen and asks `launch_cycle` (owned by backend/api.py) to run one N -> 50 -> 25 cycle through the existing
pipeline. Everything that is a rule about presentation, feedback or lifecycle lives in the small pure modules
(candidate_presentation, role_feedback, role_lifecycle, intent_change); this file wires them to the stored record.

Manual and automatic are deliberately different things:
  "Show me more"  the recruiter asks. Shows what is already read, then continues the current retrieval (next page).
  daily search    background, fresh retrieval from the first page, deduplicated against the whole role.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.services import candidate_presentation as presentation
from backend.services import role_lifecycle as lifecycle
from backend.services.role_feedback import REASON_DIMENSION, Guidance, build_guidance, calibration_summary, clean_note, evidence_guidance_score, valid_reason
from backend.services.search_store import SearchStore

logger = logging.getLogger(__name__)

STATUS_RUNNING = "running"
DECISIONS = ("shortlist", "maybe", "reject")
# Cycles that show up quietly as "N new candidates" rather than being shown straight away.
QUIET_SOURCES = ("daily", "resume")


class RoleError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


# ---- labels for the sidebar --------------------------------------------------------------------------------------------


def place_of(boundary: Optional[Dict[str, Any]]) -> str:
    boundary = boundary or {}
    mode = boundary.get("work_mode")
    if mode == "remote":
        return f"Remote · {boundary['country']}" if boundary.get("country") else "Remote"
    return boundary.get("city") or boundary.get("state") or boundary.get("country") or ""


def sidebar_label(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """What identifies this role in the sidebar: the posted title, the hiring company and where."""
    boundary = snapshot.get("boundary") or {}
    return {
        "title": snapshot.get("posted_title") or snapshot.get("candidate_identity") or "Untitled role",
        "company": boundary.get("hiring_company") or "",
        "place": place_of(boundary),
    }


def _legacy_label(record: Dict[str, Any]) -> Dict[str, Any]:
    brief = record.get("confirmed_brief") or {}
    first_line = next((line.strip() for line in (record.get("jd_text") or "").splitlines() if line.strip()), "")
    return {"title": brief.get("posted_title") or brief.get("candidate_identity") or first_line[:60] or "Earlier search", "company": "", "place": ""}


def search_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    role = record.get("role") or {}
    label = role.get("label") or _legacy_label(record)
    decisions = record.get("recruiter_decisions") or {}
    presented_ids = [cid for cid, entry in (record.get("presentation") or {}).items() if entry.get("state") == presentation.PRESENTED]
    to_review = sum(1 for cid in presented_ids if decisions.get(cid) not in DECISIONS) if role else None
    return {
        "id": record.get("search_id"),
        "kind": "search",
        "title": label.get("title"),
        "company": label.get("company"),
        "place": label.get("place"),
        "status": record.get("status"),
        "role_status": role.get("status"),
        "pause_kind": lifecycle.pause_kind(record),
        "new_count": _new_count(record) if role else 0,
        "to_review_count": to_review,
        "updated_at": record.get("updated_at"),
        "created_at": record.get("created_at"),
    }


def draft_summary(draft: Dict[str, Any]) -> Dict[str, Any]:
    boundary = draft.get("boundary") or {}
    return {
        "id": draft["session_id"],
        "kind": "draft",
        "title": draft.get("posted_title") or draft.get("identity") or "Untitled role",
        "company": boundary.get("hiring_company") or "",
        "place": place_of(boundary),
        "status": draft.get("status"),
        "role_status": None,
        "pause_kind": None,
        "new_count": 0,
        "to_review_count": None,
        "updated_at": draft.get("updated_at"),
        "created_at": draft.get("updated_at"),
    }


# ---- what the workspace receives on top of the candidates -------------------------------------------------------------------


def effective_feedback(record: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        event["candidate_id"]: {"decision": event.get("decision"), "reason": event.get("feedback_reason"), "note": event.get("feedback_note")}
        for event in lifecycle.effective_feedback_events(record)
        if event.get("feedback_reason") or event.get("feedback_note")
    }


def role_view(record: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The role as the workspace needs it. Internal lifecycle dates and limits are deliberately not exposed."""
    role = record.get("role")
    if not role:
        return None
    return {
        "status": role.get("status"),
        "pause_reason": role.get("pause_reason"),
        "pause_kind": lifecycle.pause_kind(record),
        "can_resume": lifecycle.can_resume(role, now or _now()),
        "has_feedback": lifecycle.has_meaningful_feedback(record),
        "exhausted": lifecycle.record_is_exhausted(record),
        "label": role.get("label") or {},
    }


def derived_fields(record: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Added to GET /search/{id}. Absent for a search stored before roles existed, which keeps behaving as before."""
    if not record.get("role"):
        return {}
    presentation_map = {
        candidate_id: {"state": entry.get("state"), "source": entry.get("source"), "seen": bool(entry.get("seen")), "stale": bool(entry.get("stale")), "batch": entry.get("batch")}
        for candidate_id, entry in (record.get("presentation") or {}).items()
    }
    calibration = record.get("calibration")
    return {
        "role": role_view(record, now),
        "presentation": presentation_map,
        "availability": record.get("availability"),
        "calibration": {"state": calibration.get("state"), "summary": calibration.get("summary"), "dismissed": calibration.get("dismissed") or []} if calibration else None,
        "feedback": effective_feedback(record),
        "new_candidates": _new_count(record),
        "retrieval_exhausted": lifecycle.record_is_exhausted(record),
    }


def _new_count(record: Dict[str, Any]) -> int:
    return sum(
        1
        for entry in (record.get("presentation") or {}).values()
        if entry.get("state") == presentation.RESERVE and entry.get("source") in QUIET_SOURCES and not entry.get("seen") and not entry.get("stale")
    )


# ---- recruiter decisions, feedback and the one-time calibration -----------------------------------------------------------


def has_calibration_signal(record: Dict[str, Any]) -> bool:
    """Is there enough signal from the FIRST candidates shown to say something useful? The recruiter is never asked to
    decide on all of them or on a set number. Signal means: at least two of them have a decision, and at least one
    Maybe or Reject carries a reason the search can act on (see role_feedback). A run of plain shortlists says nothing to
    adjust, so no statement is manufactured from it."""
    calibration = record.get("calibration") or {}
    initial = set(calibration.get("initial_ids") or [])
    decisions = record.get("recruiter_decisions") or {}
    decided = [cid for cid in initial if decisions.get(cid) in DECISIONS]
    actionable = [
        event
        for event in lifecycle.effective_feedback_events(record)
        if event.get("candidate_id") in initial and REASON_DIMENSION.get(event.get("feedback_reason") or "")
    ]
    return len(decided) >= 2 and len(actionable) >= 1


def update_calibration(record: Dict[str, Any]) -> None:
    """The one calibration opportunity. It stays pending while the recruiter reviews the first candidates, becomes
    ready once there is enough signal (has_calibration_signal), and is closed for good when the recruiter moves on after
    seeing it. The summary is refreshed while it is ready, so it always matches the decisions on record."""
    calibration = record.get("calibration")
    if not calibration or calibration.get("state") == "closed":
        return
    signal = has_calibration_signal(record)
    if calibration.get("state") == "pending" and signal:
        calibration["state"] = "ready"
    elif calibration.get("state") == "ready" and not signal:
        calibration["state"] = "pending"
        calibration["summary"] = None
    if calibration.get("state") == "ready":
        calibration["summary"] = calibration_summary(record)


def apply_candidate_update(
    record: Dict[str, Any],
    *,
    search_id: str,
    candidate_id: str,
    decision: Optional[str],
    note: Optional[str],
    feedback_reason: Optional[str],
    feedback_note: Optional[str],
    now: datetime,
) -> None:
    """Persists a decision and, for Maybe and Reject, the optional reason and note. Raises RoleError for a reason that
    does not belong to the decision. The confirmed brief is never touched."""
    if decision is not None:
        record.setdefault("recruiter_decisions", {})[candidate_id] = decision
        if decision in DECISIONS:
            record.setdefault("feedback_events", []).append(
                {"candidate_id": candidate_id, "search_id": search_id, "decision": decision, "feedback_reason": None, "feedback_note": None, "at": _iso(now)}
            )
    if note:
        record.setdefault("notes", {}).setdefault(candidate_id, []).append({"text": note, "created_at": _iso(now)})

    if feedback_reason or feedback_note:
        current = (record.get("recruiter_decisions") or {}).get(candidate_id)
        if current not in ("maybe", "reject"):
            raise RoleError(422, "A reason can be given for Maybe or Reject.")
        if feedback_reason and not valid_reason(current, feedback_reason):
            raise RoleError(422, "That reason does not fit this decision.")
        events = [e for e in record.get("feedback_events") or [] if e.get("candidate_id") == candidate_id and e.get("decision") == current]
        if not events:
            event = {"candidate_id": candidate_id, "search_id": search_id, "decision": current, "feedback_reason": None, "feedback_note": None, "at": _iso(now)}
            record.setdefault("feedback_events", []).append(event)
            events = [event]
        latest = events[-1]
        if feedback_reason:
            latest["feedback_reason"] = feedback_reason
        if feedback_note:
            latest["feedback_note"] = clean_note(feedback_note)
        latest["at"] = _iso(now)

    if record.get("role"):
        update_calibration(record)


# ---- the runtime ------------------------------------------------------------------------------------------------------------

LaunchCycle = Callable[[str, Dict[str, Any], Dict[str, Any], Guidance], None]


class RoleRuntime:
    def __init__(self, search_store: SearchStore, confirmation_store: Any, launch_cycle: LaunchCycle, clock: Callable[[], datetime] = _now) -> None:
        self._store = search_store
        self._confirmations = confirmation_store
        self._launch = launch_cycle
        self._clock = clock

    # -- helpers --------------------------------------------------------------------------------------------------------

    def _snapshot_for(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        confirmation_id = (record.get("confirmed_brief") or {}).get("confirmation_id")
        return self._confirmations.load(confirmation_id) if confirmation_id else None

    def _next_cycle_number(self, record: Dict[str, Any]) -> int:
        return len(record.get("cycles") or []) + 1

    def _start(self, search_id: str, record: Dict[str, Any], kind: str, *, cursor: Optional[str], present: int, dedupe: str = "all") -> bool:
        snapshot = self._snapshot_for(record)
        if snapshot is None:
            logger.warning("Cannot start a %s cycle: the confirmed brief is unavailable | search_id=%s", kind, search_id)
            return False
        cycle = {
            "kind": kind,
            "n": self._next_cycle_number(record),
            "cursor": cursor,
            "dedupe": dedupe,
            "present": present,
            "confirmation_id": snapshot["confirmation_id"],
        }
        self._launch(search_id, snapshot, cycle, build_guidance(record))
        return True

    # -- Show me more ---------------------------------------------------------------------------------------------------

    def show_more(self, search_id: str, *, only_new: bool = False) -> Dict[str, Any]:
        with self._store.lock:
            record = self._store.load(search_id)
            if record is None:
                raise RoleError(404, "Search not found.")
            if not record.get("role"):
                raise RoleError(409, "This search predates roles and cannot show more.")
            if record.get("status") == STATUS_RUNNING:
                raise RoleError(409, "RecruiterAI is still working on this search.")

            # Moving on after being shown the summary completes the calibration for good. Asking for more before there was
            # enough signal does not use it up: the first candidates can still be reviewed.
            calibration = record.get("calibration")
            if calibration and calibration.get("state") == "ready":
                calibration["state"] = "closed"

            guidance = build_guidance(record)
            rows = presentation.reserve_rows(record, evidence_guidance_score(guidance))
            if only_new:
                fresh = {cid for cid, entry in (record.get("presentation") or {}).items() if entry.get("source") in QUIET_SOURCES and not entry.get("seen")}
                rows = [row for row in rows if row["id"] in fresh]
            if rows:
                chosen = presentation.pick_batch(rows, presentation.MORE_BATCH)
                presentation.present(record, chosen, batch=presentation.next_batch_number(record))
                record["updated_at"] = _iso(self._clock())
                self._store.save(search_id, record)
                return {"presented": len(chosen), "cycle_started": False, "exhausted": False}
            if only_new:
                self._store.save(search_id, record)
                return {"presented": 0, "cycle_started": False, "exhausted": False}

            retrieval = record.get("retrieval") or {}
            cursor = retrieval.get("next_cursor")
            if retrieval.get("exhausted") or not cursor:
                self._store.save(search_id, record)
                return {"presented": 0, "cycle_started": False, "exhausted": True}
            self._store.save(search_id, record)
            started = self._start(search_id, record, "more", cursor=cursor, present=presentation.MORE_BATCH)
            return {"presented": 0, "cycle_started": started, "exhausted": not started}

    # -- pause / resume ---------------------------------------------------------------------------------------------------

    def set_role_action(self, search_id: str, action: str) -> Dict[str, Any]:
        with self._store.lock:
            record = self._store.load(search_id)
            if record is None:
                raise RoleError(404, "Search not found.")
            role = record.get("role")
            if not role:
                raise RoleError(409, "This search predates roles.")
            now = self._clock()
            start_resume_cycle = False
            if action == "pause":
                lifecycle.pause(role, now)
            elif action == "resume":
                if not lifecycle.resume(role, now):
                    raise RoleError(409, "This role has reached the end of its automatic search. You can still ask for more candidates.")
                start_resume_cycle = record.get("status") != STATUS_RUNNING
            else:
                raise RoleError(422, "Unknown action.")
            record["updated_at"] = _iso(now)
            self._store.save(search_id, record)
            if start_resume_cycle:
                cursor = (record.get("retrieval") or {}).get("next_cursor")
                if cursor and not (record.get("retrieval") or {}).get("exhausted"):
                    self._start(search_id, record, "resume", cursor=cursor, present=0)
            return self._store.load(search_id) or record

    def calibrate(self, search_id: str, dismiss: List[str]) -> Dict[str, Any]:
        """The recruiter corrects the summary by removing what it got wrong. Nothing else about the role changes."""
        with self._store.lock:
            record = self._store.load(search_id)
            if record is None or not record.get("calibration"):
                raise RoleError(404, "Search not found.")
            calibration = record["calibration"]
            calibration["dismissed"] = sorted({d for d in dismiss if d in ("experience", "technology", "seniority", "work_type")})
            if calibration.get("state") == "ready":
                calibration["summary"] = calibration_summary(record)
            self._store.save(search_id, record)
            return record

    # -- the clock --------------------------------------------------------------------------------------------------------

    def tick_record(self, search_id: str, *, allow_launch: bool = False) -> None:
        """Applies the lifecycle clock to one role: a finished window pauses it, and (only for the background timer) a
        due day starts a fresh retrieval."""
        with self._store.lock:
            record = self._store.load(search_id)
            role = (record or {}).get("role")
            if not role:
                return
            now = self._clock()
            changed = lifecycle.tick(role, now)
            due = allow_launch and lifecycle.daily_search_due(role, now) and record.get("status") != STATUS_RUNNING
            if due:
                role["last_auto_search_at"] = _iso(now)
                changed = True
            if changed:
                self._store.save(search_id, record)
            if due:
                self._start(search_id, record, "daily", cursor=None, present=0)

    def tick_all(self) -> None:
        for path in Path(self._store.storage_dir).glob("*.json"):
            try:
                self.tick_record(path.stem, allow_launch=True)
            except Exception:  # noqa: BLE001 - one bad record must never stop the timer
                logger.exception("Role tick failed | search_id=%s", path.stem)


class RoleScheduler:
    """A plain daemon timer: every `interval_seconds` it lets the runtime apply the lifecycle clock. It is started by
    the application's startup, never at import, so tests and tools that merely build the app never spend anything."""

    def __init__(self, runtime: RoleRuntime, interval_seconds: float = 900.0) -> None:
        self._runtime = runtime
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="role-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._runtime.tick_all()
            except Exception:  # noqa: BLE001
                logger.exception("Role scheduler tick failed")
