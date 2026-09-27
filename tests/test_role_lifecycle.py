"""Role lifecycle: Day 0, a normal window that ends in a pause, a one-day extension for a meaningful change, a hard
limit of five days, manual pause, and which message a paused role shows. Pure functions with an explicit clock."""

from datetime import datetime, timedelta, timezone

from backend.services import role_lifecycle as lifecycle

DAY0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def at(days: float) -> datetime:
    return DAY0 + timedelta(days=days)


def test_a_role_starts_searching_on_the_day_it_is_confirmed() -> None:
    role = lifecycle.new_role(DAY0)
    assert role["status"] == lifecycle.SEARCHING
    assert lifecycle.parse_time(role["day0"]) == DAY0
    assert lifecycle.parse_time(role["window_end"]) == at(3)
    assert lifecycle.parse_time(role["hard_end"]) == at(5)


def test_the_normal_window_pauses_the_role_without_calling_it_expired() -> None:
    role = lifecycle.new_role(DAY0)
    assert lifecycle.tick(role, at(2.99)) is False and role["status"] == lifecycle.SEARCHING
    assert lifecycle.tick(role, at(3.01)) is True
    assert role["status"] == lifecycle.PAUSED and role["pause_reason"] == lifecycle.PAUSE_WINDOW_ENDED
    # Nothing more to do once paused.
    assert lifecycle.tick(role, at(4)) is False


def test_a_meaningful_change_extends_by_one_day() -> None:
    role = lifecycle.new_role(DAY0)
    assert lifecycle.extend_for_change(role, at(1), ["core requirements"]) is True
    assert lifecycle.parse_time(role["window_end"]) == at(4)
    assert role["changes"][0]["changed"] == ["core requirements"]
    assert lifecycle.tick(role, at(3.5)) is False  # still searching
    assert lifecycle.tick(role, at(4.01)) is True


def test_extensions_never_go_past_five_days_from_day_zero() -> None:
    role = lifecycle.new_role(DAY0)
    for day in (1, 2, 3, 3.5, 3.9, 4):
        lifecycle.extend_for_change(role, at(day), ["experience"])
    assert lifecycle.parse_time(role["window_end"]) == at(5)
    # After the hard end nothing extends and nothing resumes.
    assert lifecycle.extend_for_change(role, at(5.5), ["experience"]) is False
    assert lifecycle.parse_time(role["window_end"]) == at(5)
    assert lifecycle.tick(role, at(5.01)) is True and role["status"] == lifecycle.PAUSED


def test_a_change_after_an_automatic_pause_resumes_within_the_limit() -> None:
    role = lifecycle.new_role(DAY0)
    lifecycle.tick(role, at(3.2))
    assert role["status"] == lifecycle.PAUSED
    lifecycle.extend_for_change(role, at(3.5), ["location or work mode"])
    assert role["status"] == lifecycle.SEARCHING
    assert lifecycle.parse_time(role["window_end"]) == at(4.5)


def test_a_change_after_the_hard_end_does_not_resume_the_role() -> None:
    role = lifecycle.new_role(DAY0)
    lifecycle.tick(role, at(5.5))
    assert lifecycle.extend_for_change(role, at(6), ["skills"]) is False
    assert role["status"] == lifecycle.PAUSED


def test_manual_pause_keeps_everything_and_can_be_resumed_before_the_hard_end() -> None:
    role = lifecycle.new_role(DAY0)
    lifecycle.pause(role, at(1))
    assert role["status"] == lifecycle.PAUSED and role["pause_reason"] == lifecycle.PAUSE_MANUAL
    assert lifecycle.tick(role, at(9)) is False  # a paused role is not touched by the clock
    assert lifecycle.resume(role, at(2)) is True
    assert role["status"] == lifecycle.SEARCHING
    assert lifecycle.parse_time(role["window_end"]) >= at(3)


def test_resume_is_refused_after_the_hard_end() -> None:
    role = lifecycle.new_role(DAY0)
    lifecycle.pause(role, at(1))
    assert lifecycle.can_resume(role, at(5.1)) is False
    assert lifecycle.resume(role, at(5.1)) is False and role["status"] == lifecycle.PAUSED


def test_resume_never_extends_past_the_hard_end() -> None:
    role = lifecycle.new_role(DAY0)
    lifecycle.pause(role, at(4.5))
    assert lifecycle.resume(role, at(4.5)) is True
    assert lifecycle.parse_time(role["window_end"]) == at(5)


def test_a_daily_search_is_due_a_day_after_the_last_one() -> None:
    role = lifecycle.new_role(DAY0)
    assert lifecycle.daily_search_due(role, at(0.5)) is False
    assert lifecycle.daily_search_due(role, at(1.01)) is True
    role["last_auto_search_at"] = at(1.01).isoformat()
    assert lifecycle.daily_search_due(role, at(1.5)) is False
    assert lifecycle.daily_search_due(role, at(2.02)) is True
    lifecycle.pause(role, at(2.1))
    assert lifecycle.daily_search_due(role, at(9)) is False  # paused roles do not search


# ---- which message a paused role shows ---------------------------------------------------------------------------------


def _paused(**extra):
    role = lifecycle.new_role(DAY0)
    lifecycle.tick(role, at(3.5))
    record = {"role": role, "recruiter_decisions": {}, "feedback_events": [], "presentation": {}, "retrieval": {"exhausted": False}, "availability": {"kind": "ok"}}
    record.update(extra)
    return record


def test_paused_without_engagement_asks_the_recruiter_to_review() -> None:
    assert lifecycle.pause_kind(_paused()) == lifecycle.PAUSE_NO_ENGAGEMENT
    # One or two decisions are not yet meaningful.
    assert lifecycle.pause_kind(_paused(recruiter_decisions={"a": "shortlist", "b": "reject"})) == lifecycle.PAUSE_NO_ENGAGEMENT


def test_paused_with_meaningful_decisions_or_a_reason_offers_to_resume() -> None:
    assert lifecycle.pause_kind(_paused(recruiter_decisions={"a": "shortlist", "b": "reject", "c": "maybe"})) == lifecycle.PAUSE_FEEDBACK
    record = _paused(
        recruiter_decisions={"a": "reject"},
        feedback_events=[{"candidate_id": "a", "decision": "reject", "feedback_reason": "required_technology"}],
    )
    assert lifecycle.pause_kind(record) == lifecycle.PAUSE_FEEDBACK


def test_a_reason_for_an_old_decision_no_longer_counts() -> None:
    record = _paused(
        recruiter_decisions={"a": "shortlist"},  # the recruiter changed their mind
        feedback_events=[{"candidate_id": "a", "decision": "reject", "feedback_reason": "required_technology"}],
    )
    assert lifecycle.pause_kind(record) == lifecycle.PAUSE_NO_ENGAGEMENT


def test_paused_when_nothing_more_can_be_shown_says_so_without_claiming_the_market_is_empty() -> None:
    record = _paused(retrieval={"exhausted": True}, recruiter_decisions={"a": "shortlist", "b": "reject", "c": "maybe"})
    assert lifecycle.pause_kind(record) == lifecycle.PAUSE_EXHAUSTED


def test_paused_and_narrow_needs_both_a_small_universe_and_nothing_left() -> None:
    assert lifecycle.pause_kind(_paused(retrieval={"exhausted": True}, availability={"kind": "narrow", "profiles_returned": 12})) == lifecycle.PAUSE_NARROW
    # A narrow search that still has candidates waiting is not "narrow" yet.
    waiting = {"c1": {"state": "reserve"}}
    assert lifecycle.pause_kind(_paused(retrieval={"exhausted": True}, availability={"kind": "narrow"}, presentation=waiting)) != lifecycle.PAUSE_NARROW
    assert lifecycle.pause_kind(_paused(retrieval={"exhausted": True}, availability={"kind": "zero"})) == lifecycle.PAUSE_NARROW


def test_a_searching_role_has_no_pause_message() -> None:
    assert lifecycle.pause_kind({"role": lifecycle.new_role(DAY0)}) is None
    assert lifecycle.pause_kind({}) is None
