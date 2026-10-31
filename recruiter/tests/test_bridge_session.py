"""Bridge persistence — RoleModel over the reused file-JSON SearchStore."""

import pytest

pytest.importorskip("backend.services.search_store")

from backend.bridge.session_store import ConfirmationStore, RoleSessionStore
from backend.services.search_store import SearchStore
from recruiter.role_model import JD, Location, Provenance, RoleModel, Seniority


def _model(identity="Engineer", model_id=None):
    return RoleModel(identity=identity, seniority=Seniority(5, None, Provenance(JD)),
                     role_level="ic", location=Location(countries=("India",)), model_id=model_id)


def test_role_session_store_round_trips(tmp_path):
    store = RoleSessionStore(store=SearchStore(storage_dir=tmp_path / "sessions"))
    store.save("s1", _model("Analyst"), raw_input="JD text", boundary={"country": "India"},
               posted_title="Analyst")
    got = store.get("s1")
    assert got["model"].identity == "Analyst"
    assert got["boundary"] == {"country": "India"} and got["posted_title"] == "Analyst"
    assert store.get("missing") is None


def test_role_session_update_model(tmp_path):
    store = RoleSessionStore(store=SearchStore(storage_dir=tmp_path / "sessions"))
    store.save("s1", _model("Analyst"))
    store.update_model("s1", _model("Senior Analyst"), boundary={"country": "USA"})
    got = store.get("s1")
    assert got["model"].identity == "Senior Analyst" and got["boundary"] == {"country": "USA"}


def test_confirmation_store_round_trips(tmp_path):
    store = ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "conf"))
    cid = store.create(_model("Confirmed", model_id="m-1"))
    assert cid == "m-1"
    assert store.load("m-1").identity == "Confirmed"
    assert store.load("nope") is None


def test_confirmation_requires_model_id(tmp_path):
    store = ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "conf"))
    with pytest.raises(ValueError):
        store.create(_model("NoId", model_id=None))
