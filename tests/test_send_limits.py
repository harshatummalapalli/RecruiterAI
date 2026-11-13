"""Per-recruiter send-safety caps: the rolling-24h store + OutreachService glue."""

from datetime import datetime, timedelta, timezone

import pytest

import backend.services.outreach as outreach_mod
from backend.services.connected_accounts import ConnectedAccountStore
from backend.services.outreach import OutreachLimitError, OutreachService, PendingConnectStore, send_category
from backend.services.send_limits import SendLimitStore

A = "alice@example.com"
B = "bob@example.com"


def test_category_mapping():
    assert send_category("linkedin", inmail=False) == "linkedin_invite"
    assert send_category("linkedin", inmail=True) == "linkedin_message"
    assert send_category("email", inmail=False) == "email"


def test_count_is_per_owner_and_per_category(tmp_path):
    store = SendLimitStore(storage_dir=tmp_path)
    store.record(A, "linkedin_invite")
    store.record(A, "linkedin_invite")
    store.record(A, "email")
    assert store.count(A, "linkedin_invite") == 2
    assert store.count(A, "email") == 1
    assert store.count(B, "linkedin_invite") == 0  # isolation


def test_entries_older_than_24h_are_not_counted(tmp_path):
    store = SendLimitStore(storage_dir=tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store._write(A, [{"at": old, "category": "linkedin_invite"}, {"at": recent, "category": "linkedin_invite"}])
    assert store.count(A, "linkedin_invite") == 1


def test_usage_reports_used_limit_remaining(tmp_path):
    store = SendLimitStore(storage_dir=tmp_path)
    store.record(A, "linkedin_invite")
    usage = store.usage(A, {"linkedin_invite": 20, "email": 100})
    assert usage["linkedin_invite"] == {"used": 1, "limit": 20, "remaining": 19}
    assert usage["email"] == {"used": 0, "limit": 100, "remaining": 100}


def _svc(tmp_path):
    return OutreachService(
        client=None,
        accounts=ConnectedAccountStore(storage_dir=tmp_path / "acc"),
        pending=PendingConnectStore(path=tmp_path / "pend"),
        limits=SendLimitStore(storage_dir=tmp_path / "lim"),
    )


def test_check_limit_raises_once_cap_is_reached(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach_mod, "get_outreach_daily_limits", lambda: {"linkedin_invite": 2, "linkedin_message": 40, "email": 100})
    svc = _svc(tmp_path)
    svc.check_limit(A, "linkedin_invite")   # 0 used — fine
    svc.record_send(A, "linkedin_invite")
    svc.record_send(A, "linkedin_invite")
    with pytest.raises(OutreachLimitError, match="daily limit of 2"):
        svc.check_limit(A, "linkedin_invite")
    # A different category is unaffected.
    svc.check_limit(A, "email")


def test_usage_through_service(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach_mod, "get_outreach_daily_limits", lambda: {"linkedin_invite": 20, "linkedin_message": 40, "email": 100})
    svc = _svc(tmp_path)
    svc.record_send(A, "linkedin_invite")
    assert svc.usage(A)["linkedin_invite"]["remaining"] == 19
