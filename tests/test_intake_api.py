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

    response = client.post("/intake/start", json={"raw_input": "Senior Backend Engineer, 5+ years Python, NYC."})
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "ready"
    assert body["result"]["decision"]["issues"] == []


def test_intake_confirm_maps_to_search_intent_when_ready(tmp_path: Path) -> None:
    app = _app_with_intake(tmp_path, [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)])
    client = TestClient(app)
    _login(client)

    start = client.post("/intake/start", json={"raw_input": "Senior Backend Engineer."}).json()
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


def test_intake_confirm_refuses_while_contradiction_unresolved(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A)
    task_b_missed_it = dict(CLEAR_ROLE_TASK_B)
    task_b_missed_it["issues"] = []
    app = _app_with_intake(tmp_path, [(task_a, task_b_missed_it)])
    client = TestClient(app)
    _login(client)

    start = client.post(
        "/intake/start",
        json={"raw_input": "Entry-level Product Manager role, but 10+ years of experience required."},
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

    app = _app_with_intake(tmp_path, [(task_a_round1, task_b_round1), (task_a_round2, task_b_round2)])
    client = TestClient(app)
    _login(client)

    start = client.post("/intake/start", json={"raw_input": "Frontend Engineer, React."}).json()
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
    response = client.post("/intake/start", json={"raw_input": "Some role."})
    assert response.status_code == 401
