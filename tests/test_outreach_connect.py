"""OutreachService connect flow — binding + isolation (offline, fake client)."""

import pytest

from backend.services.connected_accounts import ConnectedAccountStore
from backend.services.outreach import (
    OutreachConnectError,
    OutreachService,
    PendingConnectStore,
)

A = "alice@example.com"
B = "bob@example.com"
CB = "https://hire.dayzero.partners/integrations/callback"


class FakeClient:
    def __init__(self):
        self.auth_links = []
        self.deleted = []
        self.accounts = {}  # account_id -> {"name": ...}

    def create_auth_link(self, *, providers, redirect_uri, state, expires_on, domain=None):
        self.auth_links.append({"providers": providers, "state": state, "redirect_uri": redirect_uri, "domain": domain})
        host = domain or "auth.unipile.com"
        return {"object": "HostedAuthLink", "link": f"https://{host}/{state}"}

    def get_account(self, account_id):
        return self.accounts.get(account_id, {"name": None})

    def delete_account(self, account_id):
        self.deleted.append(account_id)
        return {}


def _svc(tmp_path):
    client = FakeClient()
    svc = OutreachService(
        client,
        ConnectedAccountStore(storage_dir=tmp_path / "accounts"),
        PendingConnectStore(path=tmp_path / "pending"),
    )
    return svc, client


def test_begin_connect_mints_link_and_maps_channel(tmp_path):
    svc, client = _svc(tmp_path)
    link = svc.begin_connect(A, "linkedin", callback_url=CB)
    # Host-agnostic: the hosted host is the white-label domain when
    # UNIPILE_HOSTED_AUTH_DOMAIN is set, else auth.unipile.com — either way the
    # single-use state token rides the link. Don't couple the test to ambient env.
    assert link.startswith("https://")
    assert link.endswith(client.auth_links[0]["state"])
    assert client.auth_links[0]["providers"] == ["linkedin"]
    assert client.auth_links[0]["redirect_uri"] == CB

    svc.begin_connect(A, "email", callback_url=CB)
    assert client.auth_links[1]["providers"] == ["*:EMAILS"]


def test_begin_connect_rejects_unknown_channel(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(OutreachConnectError):
        svc.begin_connect(A, "telegram", callback_url=CB)


def test_full_connect_binds_to_the_recruiter_who_started_it(tmp_path):
    svc, client = _svc(tmp_path)
    client.accounts["acc_li"] = {"name": "Alice R"}
    state = client_state(svc, client, A, "linkedin")

    owner, channel = svc.complete_connect(state, "acc_li", "linkedin")
    assert (owner, channel) == (A, "linkedin")

    integ = {i["channel"]: i for i in svc.list_integrations(A)}
    assert integ["linkedin"]["connected"] is True
    assert integ["linkedin"]["display_name"] == "Alice R"
    # Bob sees nothing — no leak.
    assert all(i["connected"] is False for i in svc.list_integrations(B))


def test_email_channel_binds_under_email_even_though_provider_is_google(tmp_path):
    svc, client = _svc(tmp_path)
    state = client_state(svc, client, A, "email")
    owner, channel = svc.complete_connect(state, "acc_gm", "google")
    assert channel == "email"
    integ = {i["channel"]: i for i in svc.list_integrations(A)}
    assert integ["email"]["connected"] is True
    assert integ["email"]["raw_provider"] == "google"


def test_state_token_is_single_use(tmp_path):
    svc, client = _svc(tmp_path)
    state = client_state(svc, client, A, "linkedin")
    svc.complete_connect(state, "acc_li", "linkedin")
    with pytest.raises(OutreachConnectError):
        svc.complete_connect(state, "acc_li", "linkedin")   # replay rejected


def test_unknown_state_is_rejected(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(OutreachConnectError):
        svc.complete_connect("not-a-real-token", "acc_li", "linkedin")


def test_provider_channel_mismatch_is_rejected(tmp_path):
    svc, client = _svc(tmp_path)
    state = client_state(svc, client, A, "linkedin")
    # The recruiter chose LinkedIn but a google account came back -> reject.
    with pytest.raises(OutreachConnectError):
        svc.complete_connect(state, "acc_gm", "google")


def test_disconnect_unbinds_and_revokes_at_unipile(tmp_path):
    svc, client = _svc(tmp_path)
    state = client_state(svc, client, A, "linkedin")
    svc.complete_connect(state, "acc_li", "linkedin")

    assert svc.disconnect(A, "linkedin") is True
    assert "acc_li" in client.deleted
    assert all(i["connected"] is False for i in svc.list_integrations(A))


def test_list_integrations_always_lists_all_channels(tmp_path):
    svc, _ = _svc(tmp_path)
    channels = [i["channel"] for i in svc.list_integrations(A)]
    assert channels == ["linkedin", "email", "whatsapp"]
    assert all(i["connected"] is False for i in svc.list_integrations(A))


# helper: run begin_connect and pull the state token the fake client recorded
def client_state(svc, client, owner, channel):
    svc.begin_connect(owner, channel, callback_url=CB)
    return client.auth_links[-1]["state"]
