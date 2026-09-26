"""Server-side Search Boundary validation. The browser gates the button, but the server decides."""

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.models.intake import SearchBoundary
from backend.services.search_boundary import BoundaryValidationError, validate_search_boundary
from tests.test_intake_api import NYC_BOUNDARY, _app_with_intake, _login
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B


def _boundary(**overrides: Any) -> SearchBoundary:
    values: Dict[str, Any] = dict(hiring_company="Acme", country="Canada", work_mode="hybrid", state="Ontario", city="Toronto", radius_miles=25.0)
    values.update(overrides)
    return SearchBoundary(**values)


def test_a_complete_onsite_or_hybrid_boundary_is_accepted_and_normalized() -> None:
    boundary = validate_search_boundary(_boundary(hiring_company="  Acme  ", country="USA", state="NY", work_mode="Hybrid"))
    assert (boundary.hiring_company, boundary.country, boundary.state, boundary.work_mode) == ("Acme", "United States", "New York", "hybrid")


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"hiring_company": "  "}, "hiring company"),
        ({"country": ""}, "country"),
        ({"work_mode": ""}, "work mode"),
        ({"work_mode": "sometimes"}, "work mode"),
        ({"state": ""}, "state"),
        ({"city": None}, "city"),
        ({"radius_miles": None}, "radius"),
        ({"radius_miles": 0}, "radius"),
        ({"radius_miles": 9000}, "exceed"),
    ],
)
def test_incomplete_onsite_hybrid_boundaries_are_rejected_with_plain_messages(overrides: Dict[str, Any], message: str) -> None:
    with pytest.raises(BoundaryValidationError) as raised:
        validate_search_boundary(_boundary(**overrides))
    assert any(message in error.lower() for error in raised.value.errors)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(BoundaryValidationError) as raised:
        validate_search_boundary(_boundary(hiring_company="", country="", work_mode="onsite", state="", city="", radius_miles=None))
    assert len(raised.value.errors) >= 5


def test_a_missing_boundary_is_rejected() -> None:
    with pytest.raises(BoundaryValidationError):
        validate_search_boundary(None)


def test_remote_needs_a_resolved_scope() -> None:
    remote = dict(work_mode="remote", state=None, city=None, radius_miles=None)
    with pytest.raises(BoundaryValidationError):
        validate_search_boundary(_boundary(**remote))  # no scope chosen
    with pytest.raises(BoundaryValidationError):
        validate_search_boundary(_boundary(**remote, remote_scope="states", remote_states=[]))
    with pytest.raises(BoundaryValidationError):
        validate_search_boundary(_boundary(**remote, remote_scope="cities", remote_cities=["  "]))
    assert validate_search_boundary(_boundary(**remote, remote_scope="anywhere")).remote_scope == "anywhere"
    states = validate_search_boundary(_boundary(**remote, remote_scope="states", remote_states=["TX", "Texas", "CA"]))
    assert states.remote_states == ["Texas", "California"]  # normalized and de-duplicated


def test_fields_that_belong_to_the_other_work_mode_are_dropped() -> None:
    remote = validate_search_boundary(_boundary(work_mode="remote", remote_scope="anywhere", state="Ontario", city="Toronto", radius_miles=25.0))
    assert (remote.state, remote.city, remote.radius_miles) == (None, None, None)
    onsite = validate_search_boundary(_boundary(remote_scope="cities", remote_cities=["Austin"]))
    assert (onsite.remote_scope, onsite.remote_cities) == (None, [])


def test_the_api_rejects_a_bad_boundary_with_a_list_of_recruiter_readable_errors(tmp_path: Path) -> None:
    client = TestClient(_app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)]))
    _login(client)
    bad = dict(NYC_BOUNDARY, work_mode="", hiring_company="")
    response = client.post("/intake/start", json={"raw_input": "Backend engineer", "boundary": bad})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["errors"] and any("hiring company" in e.lower() for e in detail["errors"])


def test_the_api_rejects_an_empty_description(tmp_path: Path) -> None:
    client = TestClient(_app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)]))
    _login(client)
    response = client.post("/intake/start", json={"raw_input": "   ", "boundary": NYC_BOUNDARY})
    assert response.status_code == 422


def test_the_api_stores_the_normalized_boundary(tmp_path: Path) -> None:
    client = TestClient(_app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)]))
    _login(client)
    boundary = dict(NYC_BOUNDARY, country="USA", state="NY")
    session_id = client.post("/intake/start", json={"raw_input": "Backend engineer", "boundary": boundary}).json()["session_id"]
    intent = client.post(f"/intake/{session_id}/confirm").json()
    assert intent["location"]["countries"] == ["United States"] and intent["location"]["states"] == ["New York"]


def test_editing_the_boundary_over_the_api_is_validated_and_makes_no_model_call(tmp_path: Path) -> None:
    from tests.test_intake_api import _QueuedFakeClient

    task_a = dict(CLEAR_ROLE_TASK_A, explicit_constraints=dict(CLEAR_ROLE_TASK_A["explicit_constraints"], locations=[{"city": "Toronto", "state": "Ontario", "country": "Canada"}]))
    queue = _QueuedFakeClient([(task_a, CLEAR_ROLE_TASK_B)])
    from backend.api import create_app
    from backend.services.intake_reasoning import IntakeReasoner
    from backend.services.intake_session import IntakeSessionManager
    from backend.services.search_store import SearchStore

    manager = IntakeSessionManager(reasoner=IntakeReasoner(client=queue), store=SearchStore(storage_dir=tmp_path / "s"))
    client = TestClient(create_app(intake_session_manager=manager))
    _login(client)

    started = client.post("/intake/start", json={"raw_input": "Backend engineer", "boundary": NYC_BOUNDARY}).json()
    assert started["result"]["status"] == "needs_clarification"  # the JD says Toronto, the boundary says New York
    remaining = len(queue._remaining)

    bad = client.patch(f"/intake/{started['session_id']}/boundary", json=dict(NYC_BOUNDARY, radius_miles=0))
    assert bad.status_code == 422

    toronto = dict(NYC_BOUNDARY, country="Canada", state="Ontario", city="Toronto")
    fixed = client.patch(f"/intake/{started['session_id']}/boundary", json=toronto)
    assert fixed.status_code == 200 and fixed.json()["result"]["status"] == "ready"
    assert len(queue._remaining) == remaining  # no model call was made

    assert client.patch("/intake/nope/boundary", json=toronto).status_code == 404
