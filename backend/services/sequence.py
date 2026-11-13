"""The one built-in follow-up flow (Phase 2 — approve-each).

A pure state machine. It NEVER sends anything: it only tells the recruiter what
the next step is and records progress as they send each step themselves through
the normal composer. The moment a candidate replies, the sequence is done. There
is no scheduler and no auto-advance — every touch is a human click.

Standard flow: Connect → (on acceptance) Message → (after a few days, if no reply)
one Nudge. LinkedIn-only in v1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

STANDARD_FLOW = "standard"
NUDGE_DELAY_DAYS = 3
_ORDER = ["connect", "message", "nudge"]

_STEP_META = {
    "connect": {"channel": "linkedin", "inmail": False, "label": "Send connection request"},
    "message": {"channel": "linkedin", "inmail": False, "label": "Send a message"},
    "nudge": {"channel": "linkedin", "inmail": False, "label": "Send a follow-up nudge"},
}


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def new_enrollment(now: Optional[datetime] = None) -> Dict[str, Any]:
    return {"flow": STANDARD_FLOW, "status": "active", "enrolled_at": _now(now).isoformat(), "steps": []}


def _done_names(seq: Dict[str, Any]) -> set:
    return {s.get("step") for s in (seq.get("steps") or [])}


def _channel_states(channels: Dict[str, Any]) -> Dict[str, Any]:
    """The per-channel entries, excluding the sequence object itself."""
    return {k: v for k, v in channels.items() if k != "sequence" and isinstance(v, dict)}


def _replied(channels: Dict[str, Any]) -> bool:
    return any(v.get("state") == "replied" for v in _channel_states(channels).values())


def _connected(channels: Dict[str, Any]) -> bool:
    li = channels.get("linkedin") or {}
    return li.get("state") in ("connected", "replied")


def advance_on_send(seq: Dict[str, Any], channel: str, inmail: bool, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Record the next not-yet-done standard step after a LinkedIn send. A non-
    LinkedIn send doesn't advance the (LinkedIn-only) standard flow. Mutates and
    returns seq."""
    if not isinstance(seq, dict) or seq.get("status") != "active" or (channel or "") != "linkedin":
        return seq
    done = _done_names(seq)
    for step in _ORDER:
        if step not in done:
            seq.setdefault("steps", []).append({"step": step, "at": _now(now).isoformat()})
            if step == _ORDER[-1]:
                seq["status"] = "done"
            break
    return seq


def next_due(seq: Optional[Dict[str, Any]], channels: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """What the recruiter should do next for this enrollment:
      {status: "ready", step, channel, inmail, label} — an actionable step now,
      {status: "waiting", label} — blocked on acceptance or the nudge delay,
      {status: "done"} — replied / stopped / finished,
    or None when there's no enrollment."""
    if not isinstance(seq, dict):
        return None
    if seq.get("status") != "active":
        return {"status": seq.get("status", "done")}
    if _replied(channels):
        return {"status": "done"}
    done = _done_names(seq)
    now = _now(now)

    if "connect" not in done:
        return {"status": "ready", "step": "connect", **_STEP_META["connect"]}

    if "message" not in done:
        if _connected(channels):
            return {"status": "ready", "step": "message", **_STEP_META["message"]}
        return {"status": "waiting", "label": "Waiting for the connection to be accepted"}

    if "nudge" not in done:
        message_step = next((s for s in seq.get("steps", []) if s.get("step") == "message"), None)
        due_at = now
        if message_step:
            try:
                due_at = datetime.fromisoformat(message_step["at"]) + timedelta(days=NUDGE_DELAY_DAYS)
            except (KeyError, ValueError, TypeError):
                due_at = now
        if now >= due_at:
            return {"status": "ready", "step": "nudge", **_STEP_META["nudge"]}
        days = max(1, (due_at - now).days + 1)
        return {"status": "waiting", "label": f"Nudge available in ~{days}d if no reply"}

    return {"status": "done"}
