"""Pinned role understanding: an answer resolves ambiguity, it does not reinvent the role.

Task A and Task B run once. Each answer is ONE small model call that proposes a patch; code validates it and applies
only what passes. These tests use a scripted fake model that records every call, so "the role was not re-read" is
asserted, not assumed.
"""

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.models.intake import SearchBoundary
from backend.services.intake_answer import apply_patch
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore
from backend.services.search_translator import build_confirmed_hiring_intent, to_search_intent
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B

RAW = "AI Engineer\nWe want an engineer with 3+ years... Requirements: 8-10 years of professional experience. Python, Kafka, PostgreSQL."
BOUNDARY = SearchBoundary(hiring_company="Acme", country="United States", work_mode="hybrid", state="New York", city="New York", radius_miles=25.0)

TASK_A = dict(
    CLEAR_ROLE_TASK_A,
    posted_title="AI Engineer",
    role_interpretation={"value": "A backend-heavy AI engineer.", "evidence": "70% backend", "source": "inferred"},
    core_capabilities=[{"value": "Python backend services", "tier_signal": "required", "evidence": "Python"}],
    technologies_mentioned=[{"category": "Languages", "items": ["Python"]}],
)
EXPERIENCE_ASK = {
    "issue": "Conflicting experience ranges",
    "decision": "ask",
    "question": "The description states 3+ years and also 8-10 years. Which range is correct?",
    "options": [{"value": "3plus", "label": "3+ years"}, {"value": "8to10", "label": "8-10 years"}],
    "consequence_if_answer_a": "Sets the experience filter to 3+ years.",
    "consequence_if_answer_b": "Sets the experience filter to 8-10 years.",
}
KAFKA_ASK = {
    "issue": "Kafka requirement level",
    "decision": "ask",
    "question": "Is Kafka a must-have or a nice-to-have?",
    "options": [{"value": "must", "label": "Must-have"}, {"value": "nice", "label": "Nice-to-have"}],
    "consequence_if_answer_a": "Keeps Kafka as a core requirement in the search.",
    "consequence_if_answer_b": "Moves Kafka to a preferred signal in the search.",
}
TELL = {"issue": "Title versus work", "decision": "tell", "insight_text": "Even though the title says AI Engineer, the work is backend-dominant."}
TASK_B = dict(
    CLEAR_ROLE_TASK_B,
    issues=[EXPERIENCE_ASK, KAFKA_ASK, TELL],
    recommended_ask_count=2,
    final_search_intent={
        "hard_requirements": ["3+ years of professional experience", "Python backend services", "Kafka"],
        "strong_signals": ["PostgreSQL"],
        "preferred_differentiators": ["Snowflake"],
        "natural_language_search_query": "Senior backend engineer with Python, Kafka and PostgreSQL.",
        "exclusions": [],
    },
)
PATCH_YEARS = {
    "reasoning": "The recruiter chose 8-10 years.",
    "changes": [{"op": "set_experience", "minimum_years": 8, "maximum_years": 10}],
    "natural_language_search_query": "Senior backend engineer with 8-10 years of Python, Kafka and PostgreSQL.",
    "new_issues": [],
}
PATCH_KAFKA = {"reasoning": "Kafka is nice to have.", "changes": [{"op": "move_requirement", "text": "Kafka", "to": "preferred"}], "natural_language_search_query": None, "new_issues": []}


class _Response:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.output_text = json.dumps(payload)


class ScriptedClient:
    """Returns queued payloads in order and records every prompt it was given."""

    def __init__(self, payloads: List[Dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.prompts: List[str] = []
        self.responses = self

    def create(self, **kwargs: Any) -> _Response:
        self.prompts.append(kwargs["input"][1]["content"])
        return _Response(self.payloads.pop(0))


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _manager(tmp_path: Path, patches: List[Dict[str, Any]], task_b: Dict[str, Any] = TASK_B):
    client = ScriptedClient([copy.deepcopy(TASK_A), copy.deepcopy(task_b), *copy.deepcopy(patches)])
    store = SearchStore(storage_dir=tmp_path / "sessions")
    return IntakeSessionManager(reasoner=IntakeReasoner(client=client), store=store), client, store


def _issue_id(record, text: str) -> str:
    return next(i.id for i in record.result.decision.issues if i.issue == text)


def _asdict(record) -> Dict[str, Any]:
    return dataclasses.asdict(record.result)


def test_an_answer_makes_one_model_call_and_never_rereads_the_role(tmp_path: Path) -> None:
    manager, client, _ = _manager(tmp_path, [PATCH_YEARS])
    record = manager.start(RAW, boundary=BOUNDARY)
    assert len(client.prompts) == 2  # Task A and Task B, once
    manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    assert len(client.prompts) == 3
    # The third call is the small patch prompt, not Task A ("Raw hiring input:") and not Task B again.
    assert "ANSWERED one question" in client.prompts[2]
    assert "Return the JSON now." not in client.prompts[2]


def test_answering_one_question_changes_only_the_fields_it_names(tmp_path: Path) -> None:
    manager, client, _ = _manager(tmp_path, [PATCH_YEARS])
    record = manager.start(RAW, boundary=BOUNDARY)
    before = copy.deepcopy(_asdict(record))
    kafka_id = _issue_id(record, "Kafka requirement level")

    after = _asdict(manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years"))

    # The role reading is identical except for the two experience fields the answer named.
    b_role, a_role = before["role_understanding"], after["role_understanding"]
    assert (a_role["explicit_constraints"]["experience_minimum_years"], a_role["explicit_constraints"]["experience_maximum_years"]) == (8, 10)
    b_role["explicit_constraints"].update(experience_minimum_years=8, experience_maximum_years=10)
    assert a_role == b_role

    # Requirements: only the superseded generic years sentence left. Everything else is untouched.
    b_final, a_final = before["decision"]["final_search_intent"], after["decision"]["final_search_intent"]
    assert a_final["hard_requirements"] == ["Python backend services", "Kafka"]
    assert a_final["strong_signals"] == b_final["strong_signals"] and a_final["preferred_differentiators"] == b_final["preferred_differentiators"]

    # The other pending question and the TELL are exactly as they were, with the same ids.
    assert [i for i in after["decision"]["issues"] if i["issue"] == "Kafka requirement level"] == [i for i in before["decision"]["issues"] if i["issue"] == "Kafka requirement level"]
    assert [i["id"] for i in after["decision"]["issues"] if i["decision"] == "ask"] == [kafka_id]
    assert [i for i in after["decision"]["issues"] if i["decision"] == "tell"] == [i for i in before["decision"]["issues"] if i["decision"] == "tell"]


def test_confirmed_answers_persist_and_are_recorded_field_by_field(tmp_path: Path) -> None:
    manager, client, store = _manager(tmp_path, [PATCH_YEARS, PATCH_KAFKA])
    record = manager.start(RAW, boundary=BOUNDARY)
    manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    record = manager.answer(record.session_id, _issue_id(manager.get(record.session_id), "Kafka requirement level"), "nice", "Nice-to-have")

    assert [(c.field, c.description) for c in record.result.confirmed] == [
        ("experience", "Experience: 8-10 years"),
        ("requirement", "Kafka: now preferred"),
    ]
    reloaded = IntakeSessionManager(store=SearchStore(storage_dir=tmp_path / "sessions")).get(record.session_id)
    assert [c.description for c in reloaded.result.confirmed] == ["Experience: 8-10 years", "Kafka: now preferred"]
    assert [a.label for a in reloaded.answers] == ["8-10 years", "Nice-to-have"]
    assert reloaded.result.decision.final_search_intent.preferred_differentiators == ["Snowflake", "Kafka"]


def test_resolved_questions_do_not_reappear(tmp_path: Path) -> None:
    repeat = dict(PATCH_YEARS, new_issues=[dict(EXPERIENCE_ASK)])  # the model tries to re-ask the answered question
    manager, client, _ = _manager(tmp_path, [repeat, PATCH_KAFKA])
    record = manager.start(RAW, boundary=BOUNDARY)
    record = manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    assert [i.issue for i in record.result.decision.issues if i.decision == "ask"] == ["Kafka requirement level"]

    record = manager.answer(record.session_id, _issue_id(record, "Kafka requirement level"), "nice", "Nice-to-have")
    assert record.result.status == "ready" and not [i for i in record.result.decision.issues if i.decision == "ask"]
    assert not manager.get(record.session_id).result.pending_ask_issues

    # Answering something that is no longer pending is refused rather than silently re-applied.
    with pytest.raises(ValueError):
        manager.answer(record.session_id, "issue-0", "8to10", "8-10 years")


def test_a_genuinely_new_question_is_allowed_once_and_only_once(tmp_path: Path) -> None:
    follow_up = {
        "issue": "Leadership scope",
        "decision": "ask",
        "question": "Should this role manage a team?",
        "options": [{"value": "ic", "label": "Individual contributor"}, {"value": "lead", "label": "Lead a team"}],
        "consequence_if_answer_a": "Searches individual contributor titles.",
        "consequence_if_answer_b": "Adds lead titles to the search.",
    }
    manager, client, _ = _manager(tmp_path, [dict(PATCH_YEARS, new_issues=[follow_up, dict(follow_up, issue="Another", question="Another?")]), {"reasoning": "ic", "changes": [], "new_issues": [dict(follow_up)]}])
    record = manager.start(RAW, boundary=BOUNDARY)
    record = manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    asks = [i.issue for i in record.result.decision.issues if i.decision == "ask"]
    assert asks == ["Kafka requirement level", "Leadership scope"]  # at most one new question per answer

    record = manager.answer(record.session_id, _issue_id(record, "Leadership scope"), "ic", "Individual contributor")
    assert "Leadership scope" not in [i.issue for i in record.result.decision.issues]  # not re-asked after being answered


def test_the_final_brief_is_stable_across_reload(tmp_path: Path) -> None:
    manager, client, store = _manager(tmp_path, [PATCH_YEARS, PATCH_KAFKA])
    record = manager.start(RAW, boundary=BOUNDARY)
    manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    finished = manager.answer(record.session_id, _issue_id(manager.get(record.session_id), "Kafka requirement level"), "nice", "Nice-to-have")

    fresh = IntakeSessionManager(store=SearchStore(storage_dir=tmp_path / "sessions"))
    first, second = fresh.get(record.session_id), fresh.get(record.session_id)
    assert _asdict(first) == _asdict(second) == _asdict(finished)
    assert dataclasses.asdict(first.boundary) == dataclasses.asdict(BOUNDARY)
    assert to_search_intent(build_confirmed_hiring_intent(first.result, boundary=first.boundary)) == to_search_intent(
        build_confirmed_hiring_intent(finished.result, boundary=finished.boundary)
    )


def test_the_same_confirmed_inputs_produce_the_same_executable_intent(tmp_path: Path) -> None:
    def run(directory: str):
        manager, _, _ = _manager(tmp_path / directory, [PATCH_YEARS, PATCH_KAFKA])
        record = manager.start(RAW, boundary=BOUNDARY)
        manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
        done = manager.answer(record.session_id, _issue_id(manager.get(record.session_id), "Kafka requirement level"), "nice", "Nice-to-have")
        return to_search_intent(build_confirmed_hiring_intent(done.result, boundary=done.boundary))

    first, second = run("a"), run("b")
    assert first == second
    assert first.experience.minimum_years == 8 and first.experience.maximum_years == 10
    assert "Kafka" not in first.core_signals and "Kafka" in first.differentiator_signals
    assert not any("3+" in signal for signal in first.core_signals)  # the superseded years sentence is gone
    assert any(signal.startswith("8+ years") for signal in first.core_signals)  # the structured minimum is the years requirement


# ---------------------------------------------------------------------------
# The patch is validated, never trusted.
# ---------------------------------------------------------------------------


def _fresh_result(tmp_path: Path):
    manager, _, _ = _manager(tmp_path, [])
    record = manager.start(RAW, boundary=BOUNDARY)
    return record.result, next(i for i in record.result.decision.issues if i.decision == "ask")


def test_invalid_operations_are_refused_and_change_nothing(tmp_path: Path) -> None:
    result, issue = _fresh_result(tmp_path)
    snapshot = copy.deepcopy(dataclasses.asdict(result))
    refused = apply_patch(
        result,
        {
            "changes": [
                {"op": "delete_everything"},
                {"op": "move_requirement", "text": "A requirement that does not exist", "to": "core"},
                {"op": "move_requirement", "text": "Kafka", "to": "sideways"},
                {"op": "set_experience", "minimum_years": 10, "maximum_years": 3},
                {"op": "set_identity", "value": "a very long sentence that is clearly not a title-like label at all"},
                {"op": "set_leadership", "value": "emperor"},
                {"op": "add_requirement", "text": "Quantum cryptography", "tier": "core"},
                "not even an object",
            ]
        },
        issue,
        "8-10 years",
        RAW,
    )
    assert len(refused) == 8
    assert dataclasses.asdict(result) == snapshot


def test_a_search_sentence_that_contradicts_itself_is_not_accepted(tmp_path: Path) -> None:
    result, issue = _fresh_result(tmp_path)
    before = result.decision.final_search_intent.natural_language_search_query
    refused = apply_patch(result, {"changes": [], "natural_language_search_query": "Entry-level engineer, junior, with 10+ years of experience required."}, issue, "x", RAW)
    assert refused and result.decision.final_search_intent.natural_language_search_query == before


def test_a_requirement_can_only_be_added_when_the_answer_or_input_says_it(tmp_path: Path) -> None:
    result, issue = _fresh_result(tmp_path)
    apply_patch(result, {"changes": [{"op": "add_requirement", "text": "Terraform experience", "tier": "supporting"}]}, issue, "We also need Terraform", RAW)
    assert "Terraform experience" in result.decision.final_search_intent.strong_signals
    assert [c.field for c in result.confirmed] == ["requirement"]


def test_dropping_the_years_requirement_removes_years_sentences_but_keeps_skill_tenure(tmp_path: Path) -> None:
    result, issue = _fresh_result(tmp_path)
    result.decision.final_search_intent.hard_requirements.append("5+ years of Python")
    apply_patch(result, {"changes": [{"op": "set_experience", "minimum_years": None, "maximum_years": None}]}, issue, "Treat as entry-level", RAW)
    hard = result.decision.final_search_intent.hard_requirements
    assert "3+ years of professional experience" not in hard
    assert "5+ years of Python" not in hard  # a dropped years requirement takes its years sentences with it
    assert "Python backend services" in hard


def test_the_recruiters_answer_is_marked_as_the_source_of_what_it_changed(tmp_path: Path) -> None:
    result, issue = _fresh_result(tmp_path)
    apply_patch(result, {"changes": [{"op": "set_seniority", "value": "Staff"}, {"op": "set_identity", "value": "Platform Engineer"}]}, issue, "Staff platform", RAW)
    role = result.role_understanding
    assert (role.seniority_scope.value, role.seniority_scope.source) == ("Staff", "recruiter")
    assert (role.primary_candidate_identity.value, role.primary_candidate_identity.source) == ("Platform Engineer", "recruiter")


# ---------------------------------------------------------------------------
# The boundary: deterministic, and the recruiter's choices stay theirs.
# ---------------------------------------------------------------------------


def _conflict_task_a() -> Dict[str, Any]:
    constraints = dict(TASK_A["explicit_constraints"], locations=[{"city": "Toronto", "state": "Ontario", "country": "Canada"}])
    return dict(TASK_A, explicit_constraints=constraints)


def _conflict_manager(tmp_path: Path):
    client = ScriptedClient([_conflict_task_a(), dict(CLEAR_ROLE_TASK_B)])
    store = SearchStore(storage_dir=tmp_path / "sessions")
    return IntakeSessionManager(reasoner=IntakeReasoner(client=client), store=store), client


def test_editing_the_boundary_makes_no_model_call_and_reevaluates_the_conflict(tmp_path: Path) -> None:
    manager, client = _conflict_manager(tmp_path)
    record = manager.start(RAW, boundary=BOUNDARY)  # JD says Toronto, the boundary says New York
    calls = len(client.prompts)
    assert record.result.status == "needs_clarification"

    canada = dataclasses.replace(BOUNDARY, country="Canada", state="Ontario", city="Toronto")
    record = manager.update_boundary(record.session_id, canada)
    assert len(client.prompts) == calls  # no model call
    assert record.result.status == "ready" and not record.result.pending_ask_issues

    record = manager.update_boundary(record.session_id, BOUNDARY)  # back to a conflicting boundary
    assert len(client.prompts) == calls
    assert record.result.status == "needs_clarification"


def test_keeping_the_selected_boundary_resolves_the_conflict_without_a_model_call_until_the_boundary_changes(tmp_path: Path) -> None:
    manager, client = _conflict_manager(tmp_path)
    record = manager.start(RAW, boundary=BOUNDARY)
    calls = len(client.prompts)
    issue_id = next(i.id for i in record.result.decision.issues if i.decision == "ask")

    record = manager.answer(record.session_id, issue_id, "keep_selected_location", "Keep my selected location")
    assert len(client.prompts) == calls and record.result.status == "ready"

    # Re-applying the same boundary does not bring the resolved question back.
    assert manager.update_boundary(record.session_id, BOUNDARY).result.status == "ready"
    # A different boundary is a different choice, so the conflict is evaluated afresh.
    other = dataclasses.replace(BOUNDARY, state="California", city="San Francisco")
    assert manager.update_boundary(record.session_id, other).result.status == "needs_clarification"


def test_let_me_reconsider_resolves_nothing_and_asks_the_model_nothing(tmp_path: Path) -> None:
    manager, client = _conflict_manager(tmp_path)
    record = manager.start(RAW, boundary=BOUNDARY)
    calls = len(client.prompts)
    issue_id = next(i.id for i in record.result.decision.issues if i.decision == "ask")
    record = manager.answer(record.session_id, issue_id, "recruiter_will_clarify", "Let me reconsider")
    assert len(client.prompts) == calls
    assert record.result.status == "needs_clarification" and record.answers == []


def test_issue_ids_never_change_once_assigned(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path, [PATCH_YEARS])
    record = manager.start(RAW, boundary=BOUNDARY)
    ids_before = {i.issue: i.id for i in record.result.decision.issues}
    record = manager.answer(record.session_id, _issue_id(record, "Conflicting experience ranges"), "8to10", "8-10 years")
    for issue in record.result.decision.issues:
        assert issue.id == ids_before[issue.issue]


def test_a_session_can_be_resumed_after_a_reload_without_any_model_call(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from backend.api import create_app
    from tests.test_api import _login

    manager, client_model, _ = _manager(tmp_path, [PATCH_YEARS])
    client = TestClient(create_app(intake_session_manager=manager))
    _login(client)
    boundary = {"hiring_company": "Acme", "country": "United States", "work_mode": "hybrid", "state": "New York", "city": "New York", "radius_miles": 25}
    started = client.post("/intake/start", json={"raw_input": RAW, "boundary": boundary, "posted_title": "AI Engineer"}).json()
    calls = len(client_model.prompts)

    resumed = client.get(f"/intake/{started['session_id']}")
    assert resumed.status_code == 200 and len(client_model.prompts) == calls
    body = resumed.json()
    assert body["result"] == started["result"]
    assert body["boundary"]["city"] == "New York" and body["posted_title_input"] == "AI Engineer"
    assert client.get("/intake/nope").status_code == 404
