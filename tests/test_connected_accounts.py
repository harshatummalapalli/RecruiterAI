"""ConnectedAccountStore — per-recruiter isolation (offline, tmp storage)."""

from backend.services.connected_accounts import ConnectedAccountStore

A = "alice@example.com"
B = "bob@example.com"


def _store(tmp_path):
    return ConnectedAccountStore(storage_dir=tmp_path / "connected")


def test_bind_and_resolve_is_owner_scoped(tmp_path):
    s = _store(tmp_path)
    s.bind(A, "linkedin", "acc_alice_li", display_name="Alice")

    assert s.account_id_for(A, "linkedin") == "acc_alice_li"
    # Another recruiter sees nothing — no leak.
    assert s.account_for(B, "linkedin") is None
    assert s.account_id_for(B, "linkedin") is None


def test_two_recruiters_never_cross(tmp_path):
    s = _store(tmp_path)
    s.bind(A, "linkedin", "acc_alice_li")
    s.bind(B, "linkedin", "acc_bob_li")
    s.bind(A, "google", "acc_alice_gmail")

    assert s.account_id_for(A, "linkedin") == "acc_alice_li"
    assert s.account_id_for(B, "linkedin") == "acc_bob_li"
    assert s.account_id_for(A, "google") == "acc_alice_gmail"
    assert s.account_for(B, "google") is None
    assert {r["provider"] for r in s.list_for(A)} == {"linkedin", "google"}
    assert {r["provider"] for r in s.list_for(B)} == {"linkedin"}


def test_owner_lookup_is_case_insensitive(tmp_path):
    s = _store(tmp_path)
    s.bind("Alice@Example.com ", "linkedin", "acc_x")
    assert s.account_id_for("alice@example.com", "linkedin") == "acc_x"


def test_reverse_lookup_routes_webhooks_to_the_right_owner(tmp_path):
    s = _store(tmp_path)
    s.bind(A, "linkedin", "acc_alice_li")
    s.bind(B, "google", "acc_bob_gmail")

    assert s.owner_of_account("acc_alice_li") == ("alice@example.com", "linkedin")
    assert s.owner_of_account("acc_bob_gmail") == ("bob@example.com", "google")
    # An account we don't own -> dropped.
    assert s.owner_of_account("acc_unknown") is None


def test_set_status_by_account_updates_only_that_owner(tmp_path):
    s = _store(tmp_path)
    s.bind(A, "linkedin", "acc_alice_li")
    s.set_status_by_account("acc_alice_li", "disconnected")
    assert s.account_for(A, "linkedin")["status"] == "disconnected"
    assert s.set_status_by_account("acc_unknown", "disconnected") is None


def test_rebind_replaces_account_but_keeps_connected_at(tmp_path):
    s = _store(tmp_path)
    first = s.bind(A, "linkedin", "acc_old")
    second = s.bind(A, "linkedin", "acc_new")
    assert second["account_id"] == "acc_new"
    assert second["connected_at"] == first["connected_at"]   # preserved across reconnect


def test_unbind_removes_only_that_provider(tmp_path):
    s = _store(tmp_path)
    s.bind(A, "linkedin", "acc_li")
    s.bind(A, "google", "acc_gm")
    assert s.unbind(A, "linkedin") is True
    assert s.account_for(A, "linkedin") is None
    assert s.account_id_for(A, "google") == "acc_gm"
    assert s.unbind(A, "linkedin") is False   # already gone


def test_persists_across_store_instances(tmp_path):
    _store(tmp_path).bind(A, "linkedin", "acc_persist")
    assert _store(tmp_path).account_id_for(A, "linkedin") == "acc_persist"
