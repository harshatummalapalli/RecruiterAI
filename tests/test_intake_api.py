import json
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B, FakeOpenAIClient


def _login(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value())


NYC_BOUNDARY = {
    "hiring_company": "Acme Corp",
    "country": "United States",
    "work_mode": "hybrid",
    "state": "New York",
    "city": "New York",
    "radius_miles": 25,
}


class _QueuedFakeClient:
    """Same shape as FakeOpenAIClient but supports queuing more than one
    Task A/Task B pair, for tests that answer a question (triggering a
    second reasoning round)."""

    def __init__(self, payload_pairs: list[tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
        flat = [payload for pair in payload_pairs for payload in pair]
        self._client = FakeOpenAIClient(flat[0], flat[1]) if len(flat) >= 2 else None
        self._remaining = flat

    @property
    def responses(self):
        return self

    def create(self, **kwargs: Any):
        import json as _json

        class _Resp:
            def __init__(self, text: str) -> None:
                self.output_text = text

        return _Resp(_json.dumps(self._remaining.pop(0)))


def _app_with_intake(tmp_path: Path, payload_pairs):
    client = _QueuedFakeClient(payload_pairs)
    manager = IntakeSessionManager(
        reasoner=IntakeReasoner(client=client),
        store=SearchStore(storage_dir=tmp_path / "intake_sessions"),
    )
    return create_app(intake_session_manager=manager)


def test_intake_start_returns_zero_questions_for_clear_role(tmp_path: Path) -> None:
    app = _app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    response = client.post("/intake/start", json={"raw_input": "Senior Backend Engineer, 5+ years Python, NYC.", "boundary": NYC_BOUNDARY})
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "ready"
    assert body["result"]["decision"]["issues"] == []


def test_intake_confirm_maps_to_search_intent_when_ready(tmp_path: Path) -> None:
    app = _app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    start = client.post("/intake/start", json={"raw_input": "Senior Backend Engineer.", "boundary": NYC_BOUNDARY}).json()
    session_id = start["session_id"]

    confirm = client.post(f"/intake/{session_id}/confirm")
    assert confirm.status_code == 200
    intent = confirm.json()
    assert intent["role"]["title"] == "Senior Backend Engineer"
    assert intent["location"]["cities"] == ["New York"]
    assert intent["location"]["states"] == ["New York"]
    # Core/Supporting/Differentiator tiers reach the natural-language query,
    # never the dead `ranking` namespace or a fabricated skill filter.
    assert intent["ranking"]["must_have"] == []
    assert intent["skills"]["required_skills"] == []
    assert "Python" in intent["natural_language_search_query"]
    # The requirement sentences must reach the frontend so it can send them back
    # with the search; dropping them left every candidate with zero evidence.
    assert intent["core_signals"] and any("Python" in signal for signal in intent["core_signals"])


def test_intake_confirm_refuses_while_contradiction_unresolved(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A)
    task_b_missed_it = dict(CLEAR_ROLE_TASK_B)
    task_b_missed_it["issues"] = []
    app = _app_with_intake(tmp_path, [(task_a, task_b_missed_it)])
    client = TestClient(app)
    _login(client)

    start = client.post(
        "/intake/start",
        json={"raw_input": "Entry-level Product Manager role, but 10+ years of experience required.", "boundary": NYC_BOUNDARY},
    ).json()
    assert start["result"]["status"] == "needs_clarification"
    session_id = start["session_id"]

    confirm = client.post(f"/intake/{session_id}/confirm")
    assert confirm.status_code == 409


def test_intake_answer_resolves_the_pending_issue(tmp_path: Path) -> None:
    task_a_round1 = dict(CLEAR_ROLE_TASK_A)
    task_b_round1 = {
        "issues": [
            {
                "issue": "Missing experience range",
                "decision": "ask",
                "question": "What experience range should we search for?",
                "options": [{"value": "junior", "label": "Junior"}, {"value": "senior", "label": "Senior"}],
                "consequence_if_answer_a": "Sets a junior filter.",
                "consequence_if_answer_b": "Sets a senior filter.",
            }
        ],
        "recommended_ask_count": 1,
        "stop_reasoning": "One gap remains.",
        "warnings": [],
        "final_search_intent": CLEAR_ROLE_TASK_B["final_search_intent"],
    }
    task_a_round2 = dict(CLEAR_ROLE_TASK_A)
    task_b_round2 = dict(CLEAR_ROLE_TASK_B)
    task_b_round2["issues"] = []

    # One small patch call, not a second Task A/B round: the role reading is pinned.
    patch = {"reasoning": "The recruiter chose senior.", "changes": [{"op": "set_seniority", "value": "Senior"}], "new_issues": []}
    app = _app_with_intake(tmp_path, [(task_a_round1, task_b_round1), (patch, {})])
    client = TestClient(app)
    _login(client)

    start = client.post("/intake/start", json={"raw_input": "Frontend Engineer, React.", "boundary": NYC_BOUNDARY}).json()
    session_id = start["session_id"]
    issue_id = start["result"]["decision"]["issues"][0]["id"]
    assert start["result"]["status"] == "needs_clarification"

    answered = client.post(
        f"/intake/{session_id}/answer",
        json={"issue_id": issue_id, "value": "senior", "label": "Senior"},
    ).json()
    assert answered["result"]["status"] == "ready"
    assert answered["result"]["decision"]["issues"] == []


def test_intake_requires_session(tmp_path: Path) -> None:
    app = _app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    response = client.post("/intake/start", json={"raw_input": "Some role.", "boundary": NYC_BOUNDARY})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Search boundary (Final Intake Form Pass) — full HTTP round trip, exercising
# api.py's request parsing + intake_session.py's start()/confirm() wiring
# together (see tests/test_intake_reasoning.py and tests/test_search_
# translator.py for the reasoning/translation unit coverage this builds on).
# ---------------------------------------------------------------------------


def test_intake_start_with_boundary_suppresses_missing_location_ask(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A, explicit_constraints={**CLEAR_ROLE_TASK_A["explicit_constraints"], "locations": []})
    task_b_asks_for_location = {
        "issues": [
            {
                "issue": "Missing location",
                "decision": "ask",
                "question": "Where should we search for candidates?",
                "options": [{"value": "specify_location", "label": "Specify a location"}],
                "consequence_if_answer_a": "Searches without a location filter.",
                "consequence_if_answer_b": "Pauses until a location is provided.",
            }
        ],
        "recommended_ask_count": 1,
        "stop_reasoning": "Location is unresolved.",
        "warnings": [],
        "final_search_intent": CLEAR_ROLE_TASK_B["final_search_intent"],
    }
    app = _app_with_intake(tmp_path, [(task_a, task_b_asks_for_location)])
    client = TestClient(app)
    _login(client)

    response = client.post(
        "/intake/start",
        json={
            "raw_input": "Senior Backend Engineer, 5+ years Python.",
            "boundary": {
                "hiring_company": "Epiq",
                "country": "India",
                "work_mode": "onsite",
                "state": "Telangana",
                "city": "Hyderabad",
                "radius_miles": 25,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The backstop-detected "missing location" ask must not survive — the
    # recruiter already answered it on the intake form itself.
    assert body["result"]["status"] == "ready"
    # The JD says hybrid and the recruiter selected onsite: a visible notice, never a question.
    assert [i["decision"] for i in body["result"]["decision"]["issues"]] == ["tell"]
    assert body["result"]["decision"]["issues"][0]["backstop_category"] == "work_mode_precedence"


def test_intake_confirm_uses_boundary_location_and_radius_not_task_as_own_extraction(tmp_path: Path) -> None:
    # Task A's own JD reading names a DIFFERENT location than the boundary —
    # the boundary must still win at confirm time (never silently overridden,
    # per the product spec's "AI must treat recruiter selections as
    # confirmed facts").
    task_a = dict(
        CLEAR_ROLE_TASK_A,
        explicit_constraints={
            **CLEAR_ROLE_TASK_A["explicit_constraints"],
            "locations": [{"city": "Toronto", "state": None, "country": "Canada"}],
        },
    )
    # Answering re-runs the reasoning pipeline once more (see intake_session.
    # py's answer()), so a second Task A/B pair must be queued even though
    # this stub always returns the same (still-Toronto) JD reading.
    app = _app_with_intake(tmp_path, [(task_a, CLEAR_ROLE_TASK_B), (task_a, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    start = client.post(
        "/intake/start",
        json={
            "raw_input": "Senior Backend Engineer, 5+ years Python.",
            "boundary": {
                "hiring_company": "Epiq",
                "country": "India",
                "work_mode": "onsite",
                "state": "Telangana",
                "city": "Hyderabad",
                "radius_miles": 25,
            },
        },
    ).json()
    session_id = start["session_id"]
    # The mismatch must surface as a clarification, not be silently resolved.
    assert start["result"]["status"] == "needs_clarification"
    pending = [issue for issue in start["result"]["decision"]["issues"] if issue["decision"] == "ask"]
    assert any(issue["backstop_category"] == "location_boundary_conflict" for issue in pending)

    conflict_issue_id = next(issue["id"] for issue in pending if issue["backstop_category"] == "location_boundary_conflict")
    answered = client.post(
        f"/intake/{session_id}/answer",
        json={"issue_id": conflict_issue_id, "value": "keep_selected_location", "label": "Keep my selected location"},
    ).json()
    assert answered["result"]["status"] == "ready"

    confirm = client.post(f"/intake/{session_id}/confirm")
    assert confirm.status_code == 200
    intent = confirm.json()

    assert intent["location"]["cities"] == ["Hyderabad"]
    assert intent["location"]["states"] == ["Telangana"]
    assert intent["location"]["countries"] == ["India"]
    assert intent["location"]["radius_miles"] == 25
    assert intent["location"]["work_mode"] == "onsite"
    assert intent["company_preferences"]["exclude_current_companies"] == ["Epiq"]


def test_intake_confirm_remote_anywhere_boundary(tmp_path: Path) -> None:
    # No JD-extracted location at all (unlike CLEAR_ROLE_TASK_A's "New York")
    # so the boundary-vs-JD conflict check has nothing to disagree with —
    # this test is about the remote/anywhere translation itself.
    task_a = dict(CLEAR_ROLE_TASK_A, explicit_constraints={**CLEAR_ROLE_TASK_A["explicit_constraints"], "locations": []})
    app = _app_with_intake(tmp_path, [(task_a, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    start = client.post(
        "/intake/start",
        json={
            "raw_input": "Senior Backend Engineer, 5+ years Python.",
            "boundary": {
                "hiring_company": "Epiq",
                "country": "India",
                "work_mode": "remote",
                "remote_scope": "anywhere",
            },
        },
    ).json()
    session_id = start["session_id"]
    assert start["result"]["status"] == "ready"

    confirm = client.post(f"/intake/{session_id}/confirm")
    assert confirm.status_code == 200
    intent = confirm.json()
    assert intent["location"]["countries"] == ["India"]
    assert intent["location"]["cities"] == []
    assert intent["location"]["radius_miles"] is None
    assert intent["location"]["work_mode"] == "remote"


def test_intake_start_without_a_boundary_is_rejected_by_the_server(tmp_path: Path) -> None:
    app = _app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    response = client.post("/intake/start", json={"raw_input": "Senior Backend Engineer, 5+ years Python, NYC."})
    assert response.status_code == 422  # the boundary is required, and validated by the server, not the browser
