import json
from typing import Any, Dict, List

import pytest

from backend.models.intake import IntakeDecision, IntakeIssue
from backend.services.intake_reasoning import (
    IntakeReasoner,
    apply_contradiction_backstop,
    build_confirmed_search_intent,
    detect_intake_contradictions,
)


# ---------------------------------------------------------------------------
# Deterministic contradiction backstop — pure function, no LLM involved.
# ---------------------------------------------------------------------------


def test_detect_experience_seniority_contradiction() -> None:
    findings = detect_intake_contradictions(
        "This is an entry-level Product Manager role, but we need 10+ years of experience."
    )
    assert [f.category for f in findings] == ["experience_seniority"]


def test_detect_location_work_mode_contradiction() -> None:
    findings = detect_intake_contradictions(
        "This is a fully remote Backend Engineer role, based out of our Boston office, onsite 5 days a week."
    )
    assert [f.category for f in findings] == ["location_work_mode"]


def test_no_contradiction_on_clear_role() -> None:
    findings = detect_intake_contradictions(
        "Senior Backend Engineer, 5+ years of Python experience, based in New York, hybrid."
    )
    assert findings == []


def test_no_false_positive_when_junior_describes_a_mentee_not_the_candidate() -> None:
    """'mentor junior engineers' describes people the candidate supervises,
    not the candidate's own level — must not trigger the contradiction check
    even though the JD separately requires 6+ years (a senior-level amount)."""
    findings = detect_intake_contradictions(
        "Engineering Manager role. You will have no direct reports initially, though you may "
        "mentor junior engineers informally. 6+ years of hands-on backend engineering experience required."
    )
    assert findings == []


def test_no_false_positive_on_lead_word_alone() -> None:
    """'lead' (a senior term) with no junior term present anywhere must not trigger anything."""
    findings = detect_intake_contradictions(
        "Take lead on internal project workflow discussions. 4+ years required."
    )
    assert findings == []


def test_senior_word_alone_with_junior_word_still_triggers() -> None:
    findings = detect_intake_contradictions("We need a Junior Software Engineer, but must be Senior level.")
    assert [f.category for f in findings] == ["experience_seniority"]


# ---------------------------------------------------------------------------
# apply_contradiction_backstop — merging with Task B's own output.
# ---------------------------------------------------------------------------


def test_backstop_injects_ask_when_task_b_missed_the_contradiction() -> None:
    decision = IntakeDecision(issues=[], recommended_ask_count=0, warnings=[])
    updated, findings = apply_contradiction_backstop(
        "Entry-level Product Manager, 10+ years required.", decision
    )
    assert len(findings) == 1
    ask_issues = [issue for issue in updated.issues if issue.decision == "ask"]
    assert len(ask_issues) == 1
    assert ask_issues[0].injected_by_backstop is True
    assert len(updated.warnings) == 1


def test_backstop_does_not_duplicate_ask_already_covering_the_contradiction() -> None:
    existing_ask = IntakeIssue(
        issue="Seniority contradiction",
        decision="ask",
        question="Is this role entry-level or senior?",
    )
    decision = IntakeDecision(issues=[existing_ask], recommended_ask_count=1, warnings=[])
    updated, findings = apply_contradiction_backstop(
        "Entry-level Product Manager, 10+ years required.", decision
    )
    ask_issues = [issue for issue in updated.issues if issue.decision == "ask"]
    assert len(ask_issues) == 1
    assert ask_issues[0].injected_by_backstop is False
    # The warning is still guaranteed even though no new ask was injected.
    assert len(updated.warnings) == 1


def test_backstop_is_a_no_op_when_no_contradiction_exists() -> None:
    decision = IntakeDecision(issues=[], recommended_ask_count=0, warnings=[])
    updated, findings = apply_contradiction_backstop("Senior Backend Engineer, 5+ years, New York.", decision)
    assert findings == []
    assert updated.issues == []
    assert updated.warnings == []


# ---------------------------------------------------------------------------
# IntakeReasoner — integration with a fake OpenAI client (existing repo
# pattern: inject a fake provider/client rather than call the real API).
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.output_text = json.dumps(payload)


class _FakeResponses:
    def __init__(self, payloads: List[Dict[str, Any]]) -> None:
        self._payloads = list(payloads)

    def create(self, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(self._payloads.pop(0))


class FakeOpenAIClient:
    """Queues canned Task A then Task B JSON payloads, mirroring how
    OpenAIProvider is faked elsewhere in this repo (inject a fake instead of
    hitting the real API)."""

    def __init__(self, task_a_payload: Dict[str, Any], task_b_payload: Dict[str, Any]) -> None:
        self.responses = _FakeResponses([task_a_payload, task_b_payload])


CLEAR_ROLE_TASK_A = {
    "primary_candidate_identity": {"value": "Senior Backend Engineer", "source": "explicit"},
    "candidate_archetype": {"value": "Experienced backend engineer", "source": "explicit"},
    "seniority_scope": {"value": "Senior", "source": "explicit"},
    "leadership_type": {"value": "none", "evidence": "no leadership mentioned"},
    "core_capabilities": [{"value": "Python", "tier_signal": "required", "evidence": "Strong Python required"}],
    "supporting_capabilities": [],
    "differentiators": [],
    "domain": ["backend"],
    "explicit_constraints": {
        "locations": [{"city": "New York", "state": "NY", "country": "United States"}],
        "work_mode": "hybrid",
        "experience_minimum_years": 5,
        "experience_maximum_years": None,
        "employment_type": None,
        "exclusions": [],
    },
    "open_questions_the_text_leaves_genuinely_unresolved": [],
}

CLEAR_ROLE_TASK_B = {
    "issues": [],
    "recommended_ask_count": 0,
    "stop_reasoning": "Everything is resolved.",
    "warnings": [],
    "final_search_intent": {
        "hard_requirements": ["Python"],
        "strong_signals": [],
        "preferred_differentiators": [],
        "natural_language_search_query": "Senior backend engineer with strong Python experience.",
        "exclusions": [],
    },
}


def test_clear_role_produces_zero_questions_and_ready_status() -> None:
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)
    result = IntakeReasoner(client=client).run("Senior Backend Engineer, 5+ years Python, New York, hybrid.")
    assert result.status == "ready"
    assert result.pending_ask_issues == []
    assert result.role_understanding.primary_candidate_identity.value == "Senior Backend Engineer"
    assert result.role_understanding.primary_candidate_identity.source == "explicit"


def test_missing_search_critical_info_produces_an_ask() -> None:
    task_a = dict(CLEAR_ROLE_TASK_A, explicit_constraints={**CLEAR_ROLE_TASK_A["explicit_constraints"], "locations": []})
    task_a["open_questions_the_text_leaves_genuinely_unresolved"] = ["missing location"]
    task_b = {
        "issues": [
            {
                "issue": "Missing location",
                "decision": "ask",
                "question": "What location should we search?",
                "options": [],
                "consequence_if_answer_a": "Applies a specific city filter.",
                "consequence_if_answer_b": "Leaves the search unconstrained by location.",
            }
        ],
        "recommended_ask_count": 1,
        "stop_reasoning": "Only location is missing.",
        "warnings": [],
        "final_search_intent": CLEAR_ROLE_TASK_B["final_search_intent"],
    }
    client = FakeOpenAIClient(task_a, task_b)
    result = IntakeReasoner(client=client).run("Senior Backend Engineer, 5+ years Python.")
    assert result.status == "needs_clarification"
    assert len(result.pending_ask_issues) == 1
    assert result.pending_ask_issues[0].decision == "ask"


def test_unsearchable_information_is_never_asked_about() -> None:
    """Task B choosing not to ask about salary (an IGNORE per the search
    boundary) must be preserved as-is — the backstop must never add one."""
    task_b_with_ignore = dict(CLEAR_ROLE_TASK_B)
    task_b_with_ignore["issues"] = [
        {"issue": "Salary expectations", "decision": "ignore", "reasoning": "Cannot be searched/filtered on."}
    ]
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, task_b_with_ignore)
    result = IntakeReasoner(client=client).run("Senior Backend Engineer, competitive salary.")
    assert result.status == "ready"
    assert all(issue.decision != "ask" for issue in result.decision.issues)
    assert any(issue.decision == "ignore" for issue in result.decision.issues)


def test_experience_range_is_not_split_into_two_separate_questions() -> None:
    task_b = dict(CLEAR_ROLE_TASK_B)
    task_b["issues"] = [
        {
            "issue": "Missing experience range",
            "decision": "ask",
            "question": "What experience range should we search for?",
            "options": [],
            "consequence_if_answer_a": "Sets a junior-level experience filter.",
            "consequence_if_answer_b": "Sets a senior-level experience filter.",
        }
    ]
    task_b["recommended_ask_count"] = 1
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, task_b)
    result = IntakeReasoner(client=client).run("Frontend Engineer, strong React skills.")
    experience_asks = [
        issue for issue in result.pending_ask_issues if "experience" in issue.issue.lower()
    ]
    assert len(experience_asks) == 1


def test_provenance_and_ask_tell_ignore_are_preserved_through_the_pipeline() -> None:
    task_b = dict(CLEAR_ROLE_TASK_B)
    task_b["issues"] = [
        {"issue": "Tiering decision", "decision": "tell", "insight_text": "Treated as differentiator because it was listed as 'a plus'."},
        {"issue": "Notice period", "decision": "ignore", "reasoning": "Not searchable."},
    ]
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, task_b)
    result = IntakeReasoner(client=client).run("Some role text.")
    decisions = {issue.issue: issue.decision for issue in result.decision.issues}
    assert decisions == {"Tiering decision": "tell", "Notice period": "ignore"}
    tell_issue = next(issue for issue in result.decision.issues if issue.decision == "tell")
    assert "differentiator" in tell_issue.insight_text


def test_contradiction_is_caught_deterministically_even_if_llm_missed_it() -> None:
    """The core value of the backstop: even when Task B (simulated here as
    having missed it entirely, exactly like the observed non-deterministic
    LLM failure) reports zero issues, a genuine contradiction in the raw text
    still results in needs_clarification, never a silent 'ready'."""
    task_a = dict(CLEAR_ROLE_TASK_A)
    task_a["explicit_constraints"] = {**CLEAR_ROLE_TASK_A["explicit_constraints"], "experience_minimum_years": 10}
    task_b_missed_it = dict(CLEAR_ROLE_TASK_B)
    task_b_missed_it["issues"] = []
    task_b_missed_it["recommended_ask_count"] = 0
    client = FakeOpenAIClient(task_a, task_b_missed_it)
    result = IntakeReasoner(client=client).run("Entry-level Product Manager role, 10+ years of experience required.")
    assert result.status == "needs_clarification"
    assert len(result.pending_ask_issues) == 1
    assert result.pending_ask_issues[0].injected_by_backstop is True
    assert len(result.decision.warnings) == 1


def test_contradiction_blocks_building_an_executable_search_intent() -> None:
    task_b_missed_it = dict(CLEAR_ROLE_TASK_B)
    task_b_missed_it["issues"] = []
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, task_b_missed_it)
    result = IntakeReasoner(client=client).run(
        "This is a fully remote Backend Engineer role, onsite 5 days a week in Boston."
    )
    assert result.status == "needs_clarification"
    with pytest.raises(ValueError):
        build_confirmed_search_intent(result)


def test_build_confirmed_search_intent_maps_ready_result_onto_existing_search_intent() -> None:
    client = FakeOpenAIClient(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)
    result = IntakeReasoner(client=client).run("Senior Backend Engineer, 5+ years Python, New York, hybrid.")
    intent = build_confirmed_search_intent(result)
    assert intent.role.title == "Senior Backend Engineer"
    assert intent.experience.minimum_years == 5
    assert intent.location.cities == ["New York"]
    # Confirms the state-abbreviation backstop fires even through the full
    # IntakeReasoner pipeline, not just in isolated search_translator tests.
    assert intent.location.states == ["New York"]
    # Core/Supporting/Differentiator tiers no longer land in the dead
    # `ranking` namespace (see search_translator.py) — they only ever
    # influence the natural-language query, never a fabricated skill filter.
    assert intent.ranking.must_have == []
    assert intent.skills.required_skills == []
    assert intent.natural_language_search_query == "Senior backend engineer with strong Python experience."
