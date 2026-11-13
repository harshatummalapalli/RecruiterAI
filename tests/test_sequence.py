"""The built-in follow-up flow — pure state machine (no sends, no scheduler)."""

from datetime import datetime, timedelta, timezone

from backend.services.sequence import advance_on_send, new_enrollment, next_due

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def _seq(steps):
    return {"flow": "standard", "status": "active", "enrolled_at": NOW.isoformat(), "steps": steps}


def test_new_enrollment_is_active_with_no_steps():
    seq = new_enrollment(NOW)
    assert seq["status"] == "active" and seq["steps"] == []


def test_fresh_enrollment_is_ready_to_connect():
    due = next_due(new_enrollment(NOW), {}, now=NOW)
    assert due == {"status": "ready", "step": "connect", "channel": "linkedin", "inmail": False, "label": "Send connection request"}


def test_after_connect_waits_for_acceptance():
    seq = _seq([{"step": "connect", "at": NOW.isoformat()}])
    channels = {"linkedin": {"channel": "linkedin", "state": "invited"}}
    assert next_due(seq, channels, now=NOW)["status"] == "waiting"


def test_once_connected_is_ready_to_message():
    seq = _seq([{"step": "connect", "at": NOW.isoformat()}])
    channels = {"linkedin": {"channel": "linkedin", "state": "connected"}}
    due = next_due(seq, channels, now=NOW)
    assert due["status"] == "ready" and due["step"] == "message"


def test_nudge_waits_then_becomes_ready_after_the_delay():
    four_days_ago = (NOW - timedelta(days=4)).isoformat()
    seq_recent = _seq([{"step": "connect", "at": NOW.isoformat()}, {"step": "message", "at": NOW.isoformat()}])
    channels = {"linkedin": {"channel": "linkedin", "state": "connected"}}
    assert next_due(seq_recent, channels, now=NOW)["status"] == "waiting"   # just messaged

    seq_old = _seq([{"step": "connect", "at": four_days_ago}, {"step": "message", "at": four_days_ago}])
    due = next_due(seq_old, channels, now=NOW)
    assert due["status"] == "ready" and due["step"] == "nudge"


def test_a_reply_ends_the_sequence():
    seq = _seq([{"step": "connect", "at": NOW.isoformat()}])
    channels = {"linkedin": {"channel": "linkedin", "state": "replied"}}
    assert next_due(seq, channels, now=NOW) == {"status": "done"}


def test_stopped_sequence_has_nothing_due():
    seq = _seq([])
    seq["status"] = "stopped"
    assert next_due(seq, {}, now=NOW) == {"status": "stopped"}


def test_advance_records_steps_in_order_and_finishes():
    seq = new_enrollment(NOW)
    advance_on_send(seq, "linkedin", False, now=NOW)
    assert [s["step"] for s in seq["steps"]] == ["connect"] and seq["status"] == "active"
    advance_on_send(seq, "linkedin", False, now=NOW)
    advance_on_send(seq, "linkedin", False, now=NOW)
    assert [s["step"] for s in seq["steps"]] == ["connect", "message", "nudge"] and seq["status"] == "done"


def test_email_send_does_not_advance_the_linkedin_flow():
    seq = new_enrollment(NOW)
    advance_on_send(seq, "email", False, now=NOW)
    assert seq["steps"] == []
