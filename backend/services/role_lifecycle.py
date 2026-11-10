"""Role lifecycle for a budgeted sourcing campaign.

A role is a search record. It starts SEARCHING the day the recruiter confirms it (Day 0), and pauses on its own at the
end of its chosen window — one day or three — unless the recruiter made a meaningful change, which extends the window by
one day. Nothing ever runs automatically past the campaign's hard end, which sits MAX_EXTENSION_DAYS beyond the chosen
window, so a one-day campaign can be nudged out to three days and a three-day campaign to five. The recruiter can pause
and resume at any time.

Everything here is a pure function of the record and a clock (`now`), so the rules are tested without waiting for time
to pass. There is no scheduler in this module; role_runtime.py calls `tick` on a timer.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SEARCHING = "searching"
PAUSED = "paused"

# A brief change may request another day, but never beyond the campaign's hard end.
EXTENSION_DAYS = 1
# How far past the chosen window a run of meaningful changes may push the campaign. The window is the normal
# pause point; the hard end (window + this) is the absolute ceiling. A 3-day campaign therefore ends, at most,
# at five days from Day 0 — the same ceiling the pre-campaign model used.
MAX_EXTENSION_DAYS = 2
CAMPAIGN_INTERVAL = timedelta(hours=6)
CAMPAIGN_CREDIT_CAP = 6.0

# Why a role is paused.
PAUSE_WINDOW_ENDED = "window_ended"
PAUSE_MANUAL = "manual"

# What the recruiter is told when paused (the wording lives in the frontend; these are the cases).
PAUSE_NO_ENGAGEMENT = "no_engagement"
PAUSE_FEEDBACK = "feedback"
PAUSE_NARROW = "narrow"
PAUSE_EXHAUSTED = "exhausted"

# A search is called narrow when the provider returned fewer profiles than one retrieval holds.
NARROW_UNIVERSE = 50
# A recruiter has "meaningfully reviewed" once this many candidates have a decision.
MEANINGFUL_DECISIONS = 3


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def new_role(now: datetime, *, label: Optional[Dict[str, Any]] = None, duration_days: int = 1) -> Dict[str, Any]:
    """Start a 24-hour or 3-day budgeted campaign when the recruiter confirms the role."""
    if duration_days not in (1, 3):
        duration_days = 1
    return {
        "status": SEARCHING,
        "pause_reason": None,
        "day0": _iso(now),
        "window_end": _iso(now + timedelta(days=duration_days)),
        # The hard end sits MAX_EXTENSION_DAYS past the chosen window, so a meaningful change can genuinely
        # extend the campaign (the window) up to this ceiling, and nothing runs automatically beyond it.
        "hard_end": _iso(now + timedelta(days=duration_days + MAX_EXTENSION_DAYS)),
        "campaign_duration_days": duration_days,
        "campaign_credit_cap": CAMPAIGN_CREDIT_CAP,
        "paused_at": None,
        "last_auto_search_at": None,
        "changes": [],
        "label": label or {},
    }


def is_searching(role: Optional[Dict[str, Any]]) -> bool:
    return bool(role) and role.get("status") == SEARCHING


def _pause(role: Dict[str, Any], reason: str, now: datetime) -> None:
    role["status"] = PAUSED
    role["pause_reason"] = reason
    role["paused_at"] = _iso(now)


def pause(role: Dict[str, Any], now: datetime) -> None:
    """The recruiter pauses. Candidates, decisions, feedback and retrieval state are untouched."""
    if role.get("status") != PAUSED:
        _pause(role, PAUSE_MANUAL, now)


def can_resume(role: Dict[str, Any], now: datetime) -> bool:
    if role.get("campaign_budget_exhausted"):
        return False
    hard_end = parse_time(role.get("hard_end"))
    return role.get("status") == PAUSED and hard_end is not None and now < hard_end


def resume(role: Dict[str, Any], now: datetime) -> bool:
    """Resume a paused campaign only while its selected window and credit budget remain open."""
    if not can_resume(role, now):
        return False
    hard_end = parse_time(role["hard_end"])
    window_end = parse_time(role.get("window_end")) or now
    role["status"] = SEARCHING
    role["pause_reason"] = None
    role["paused_at"] = None
    role["window_end"] = _iso(min(max(window_end, now + timedelta(days=EXTENSION_DAYS)), hard_end))
    return True


def extend_for_change(role: Dict[str, Any], now: datetime, changed: List[str]) -> bool:
    """Record a meaningful brief change; never extend past the selected campaign end."""
    role.setdefault("changes", []).append({"at": _iso(now), "changed": list(changed)})
    hard_end = parse_time(role.get("hard_end"))
    if hard_end is None or now >= hard_end:
        return False
    window_end = parse_time(role.get("window_end")) or now
    extended = min(max(window_end, now) + timedelta(days=EXTENSION_DAYS), hard_end)
    role["window_end"] = _iso(extended)
    if role.get("status") == PAUSED and role.get("pause_reason") == PAUSE_WINDOW_ENDED:
        role["status"] = SEARCHING
        role["pause_reason"] = None
        role["paused_at"] = None
    return True


def tick(role: Optional[Dict[str, Any]], now: datetime) -> bool:
    """Applies the clock: a SEARCHING role whose window has ended pauses. Returns True when it changed."""
    if not is_searching(role):
        return False
    window_end = parse_time(role.get("window_end"))
    if window_end is not None and now >= window_end:
        _pause(role, PAUSE_WINDOW_ENDED, window_end if window_end < now else now)
        return True
    return False


def daily_search_due(role: Optional[Dict[str, Any]], now: datetime) -> bool:
    """A background campaign retrieval is due every six hours after the initial page."""
    if not is_searching(role):
        return False
    last = parse_time(role.get("last_auto_search_at")) or parse_time(role.get("day0"))
    return last is not None and now - last >= CAMPAIGN_INTERVAL


def campaign_results_used(record: Dict[str, Any]) -> int:
    """Count CrustData results returned by all cycles in this role campaign."""
    return sum(max(0, int(cycle.get("retrieved") or 0)) for cycle in record.get("cycles") or [])


def campaign_credits_used(record: Dict[str, Any]) -> float:
    return round(sum(
        max(0.0, float(cycle.get("credits_used", max(0, int(cycle.get("retrieved") or 0)) * 0.03)))
        for cycle in record.get("cycles") or []
    ), 4)


def campaign_budget_exhausted(record: Dict[str, Any]) -> bool:
    role = record.get("role") or {}
    cap = float(role.get("campaign_credit_cap") or CAMPAIGN_CREDIT_CAP)
    return campaign_credits_used(record) >= cap


def decision_count(record: Dict[str, Any]) -> int:
    return sum(1 for value in (record.get("recruiter_decisions") or {}).values() if value in ("shortlist", "maybe", "reject"))


def initial_validation_ids(record: Dict[str, Any]) -> List[str]:
    """Return the true first batch, correcting records where later cycles replaced it.

    Older campaign code rewrote `campaign_initial_ids` for each retrieval cycle.
    Prefer that stored set unless the current response's first five have stronger
    decision coverage, which identifies the original batch on those older records.
    """
    stored = [cid for cid in (record.get("campaign_initial_ids") or []) if cid]
    response_ids = [candidate.get("candidate_id") for candidate in
                    ((record.get("response") or {}).get("candidates") or [])[:5]
                    if candidate.get("candidate_id")]
    if not stored:
        return response_ids
    decisions = record.get("recruiter_decisions") or {}
    stored_decided = sum(decisions.get(cid) in ("shortlist", "maybe", "reject") for cid in stored)
    response_decided = sum(decisions.get(cid) in ("shortlist", "maybe", "reject") for cid in response_ids)
    return response_ids if response_decided > stored_decided else stored


def has_meaningful_feedback(record: Dict[str, Any]) -> bool:
    if decision_count(record) >= MEANINGFUL_DECISIONS:
        return True
    return any(event.get("feedback_reason") for event in effective_feedback_events(record))


def effective_feedback_events(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The latest feedback event per candidate, and only while the candidate still has that decision. Clearing or
    changing a decision retires the older reason."""
    decisions = record.get("recruiter_decisions") or {}
    latest: Dict[str, Dict[str, Any]] = {}
    for event in record.get("feedback_events") or []:
        latest[event.get("candidate_id", "")] = event
    return [event for candidate_id, event in latest.items() if decisions.get(candidate_id) == event.get("decision")]


def pause_kind(record: Dict[str, Any]) -> Optional[str]:
    """Which message a paused role shows. Derived from the stored facts, so it is always consistent with them.

    narrow     the provider returned fewer profiles than one retrieval holds AND nothing more can be shown
    exhausted  nothing more can be shown from this search
    feedback   the recruiter has given meaningful decisions or reasons
    otherwise  no engagement
    """
    role = record.get("role")
    if not role or role.get("status") != PAUSED:
        return None
    nothing_left = record_is_exhausted(record)
    availability = record.get("availability") or {}
    if nothing_left and availability.get("kind") in ("narrow", "zero"):
        return PAUSE_NARROW
    if nothing_left:
        return PAUSE_EXHAUSTED
    return PAUSE_FEEDBACK if has_meaningful_feedback(record) else PAUSE_NO_ENGAGEMENT


def record_is_exhausted(record: Dict[str, Any]) -> bool:
    """No candidate is waiting and the current retrieval has no further page. Says nothing about the market."""
    presentation = record.get("presentation") or {}
    reserve_waiting = any(entry.get("state") == "reserve" and not entry.get("stale") for entry in presentation.values())
    retrieval = record.get("retrieval") or {}
    return not reserve_waiting and bool(retrieval.get("exhausted"))
