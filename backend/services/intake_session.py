"""Thin, additive orchestration on top of IntakeReasoner for Phase 3 (Living
Brief UI). Does not change Task A, Task B, or the contradiction backstop —
it only tracks a conversation across multiple reasoning calls and gives each
issue a stable id the frontend can reference.

Reconciling a recruiter's answer works by re-running the SAME reasoning
pipeline (Task A -> Task B -> backstop) on the raw input with the recruiter's
prior answers appended as explicit, already-resolved facts — this is what
Phase 1/2 validated the model actually responds to (an explicit resolving
statement stops it from re-asking). The one exception is a backstop-detected
contradiction: since the raw text still literally contains both sides of the
contradiction, the regex backstop would fire again on every re-run, so a
resolved contradiction category is suppressed here rather than relied on the
LLM to drop — that is the "hard safety state" the product spec calls for.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.intake import IntakeIssue, IntakeResult, SearchBoundary
from backend.services.intake_reasoning import IntakeReasoner, apply_search_boundary, infer_backstop_category
from backend.services.search_store import SearchStore

DEFAULT_INTAKE_STORAGE_DIR = Path(__file__).resolve().parents[2] / "output" / "intake_sessions"


@dataclass
class RecordedAnswer:
    issue_key: str
    question: Optional[str]
    value: str
    label: str
    backstop_category: Optional[str] = None


@dataclass
class IntakeSessionRecord:
    session_id: str
    raw_input: str
    answers: List[RecordedAnswer] = field(default_factory=list)
    result: Optional[IntakeResult] = None
    # The recruiter-confirmed search boundary from intake start, if any —
    # authoritative for hiring company/location/work mode at confirm time
    # (see backend/services/search_translator.py's build_confirmed_hiring_
    # intent). None for any caller that doesn't submit one (backward
    # compatible with the pre-boundary intake flow).
    boundary: Optional[SearchBoundary] = None


def _augment_raw_input(raw_input: str, answers: List[RecordedAnswer]) -> str:
    if not answers:
        return raw_input
    lines = [raw_input, "", "Recruiter clarifications (already resolved — do not ask about these again):"]
    for answer in answers:
        question = answer.question or answer.issue_key
        lines.append(f"- Q: {question}  A: {answer.label}")
    return "\n".join(lines)


def _assign_issue_ids(result: IntakeResult) -> None:
    llm_index = 0
    backstop_index = 0
    for issue in result.decision.issues:
        if issue.injected_by_backstop:
            issue.id = f"backstop-{issue.backstop_category or backstop_index}"
            backstop_index += 1
        else:
            issue.id = f"issue-{llm_index}"
            llm_index += 1


def _suppress_resolved_issues(result: IntakeResult, answers: List[RecordedAnswer]) -> None:
    resolved_keys = {answer.issue_key for answer in answers}
    resolved_categories = {answer.backstop_category for answer in answers if answer.backstop_category}

    remaining: List[IntakeIssue] = []
    for issue in result.decision.issues:
        if issue.issue in resolved_keys:
            continue
        # Covers both a backstop-tagged reinjection AND a freshly-worded LLM
        # ask this round that turns out to address a category the recruiter
        # already resolved — Task B's exact phrasing varies run to run, so
        # matching by category (not just exact text) is what actually makes
        # a resolved contradiction stay resolved across re-runs.
        issue_category = issue.backstop_category or infer_backstop_category(issue.issue, issue.question)
        if issue_category and issue_category in resolved_categories:
            continue
        remaining.append(issue)

    result.decision.issues = remaining
    result.status = "needs_clarification" if any(issue.decision == "ask" for issue in remaining) else "ready"


class IntakeSessionManager:
    """Owns the additive persistence + reconciliation loop described above.
    `reasoner` and `store` are injectable for tests, matching the rest of
    this codebase's dependency-injection pattern."""

    def __init__(self, reasoner: Optional[IntakeReasoner] = None, store: Optional[SearchStore] = None) -> None:
        self._reasoner = reasoner or IntakeReasoner()
        self._store = store or SearchStore(storage_dir=DEFAULT_INTAKE_STORAGE_DIR)

    def start(self, raw_input: str, boundary: Optional[SearchBoundary] = None) -> IntakeSessionRecord:
        session_id = str(uuid.uuid4())
        # Task A/B run on raw_input alone, unmodified by the boundary — see
        # apply_search_boundary's docstring for why that independence matters.
        result = self._reasoner.run(raw_input)
        if boundary is not None:
            apply_search_boundary(result, boundary)
        _assign_issue_ids(result)
        record = IntakeSessionRecord(session_id=session_id, raw_input=raw_input, answers=[], result=result, boundary=boundary)
        self._save(record)
        return record

    def answer(self, session_id: str, issue_id: str, value: str, label: str) -> IntakeSessionRecord:
        record = self._load(session_id)
        if record is None:
            raise KeyError(session_id)
        if record.result is None:
            raise ValueError("Intake session has no prior result to answer against.")

        answered_issue = next((issue for issue in record.result.decision.issues if issue.id == issue_id), None)
        if answered_issue is None:
            raise ValueError(f"Unknown issue id: {issue_id}")

        record.answers.append(
            RecordedAnswer(
                issue_key=answered_issue.issue,
                question=answered_issue.question,
                value=value,
                label=label,
                # Even when an LLM-authored ask (not the backstop) is the one
                # that surfaced a contradiction, recognize which contradiction
                # category it addressed — otherwise the backstop would
                # re-inject a fresh ask for the same category on the very
                # next reasoning round, since the raw text still literally
                # contains both sides of the contradiction.
                backstop_category=answered_issue.backstop_category
                or infer_backstop_category(answered_issue.issue, answered_issue.question),
            )
        )

        augmented_input = _augment_raw_input(record.raw_input, record.answers)
        result = self._reasoner.run(augmented_input)
        if record.boundary is not None:
            apply_search_boundary(result, record.boundary)
        _assign_issue_ids(result)
        _suppress_resolved_issues(result, record.answers)

        record.result = result
        self._save(record)
        return record

    def get(self, session_id: str) -> Optional[IntakeSessionRecord]:
        return self._load(session_id)

    def _save(self, record: IntakeSessionRecord) -> None:
        self._store.save(record.session_id, _record_to_dict(record))

    def _load(self, session_id: str) -> Optional[IntakeSessionRecord]:
        raw = self._store.load(session_id)
        if raw is None:
            return None
        return _record_from_dict(raw)


def _record_to_dict(record: IntakeSessionRecord) -> Dict[str, Any]:
    import dataclasses

    return {
        "session_id": record.session_id,
        "raw_input": record.raw_input,
        "answers": [dataclasses.asdict(answer) for answer in record.answers],
        "result": dataclasses.asdict(record.result) if record.result else None,
        "boundary": dataclasses.asdict(record.boundary) if record.boundary else None,
    }


def _record_from_dict(data: Dict[str, Any]) -> IntakeSessionRecord:
    from backend.models.intake import (
        CapabilityItem,
        ExplicitConstraints,
        FieldValue,
        FinalSearchIntentDraft,
        IntakeDecision,
        LocationEntry,
        RoleUnderstanding,
        TechnologyGroup,
    )

    result_data = data.get("result")
    result: Optional[IntakeResult] = None
    if result_data:
        ru = result_data["role_understanding"]
        decision_data = result_data["decision"]
        constraints_data = dict(ru["explicit_constraints"])
        constraints_data["locations"] = [
            LocationEntry(**entry) for entry in constraints_data.get("locations") or []
        ]
        result = IntakeResult(
            raw_input=result_data.get("raw_input", ""),
            role_understanding=RoleUnderstanding(
                posted_title=ru.get("posted_title"),
                primary_candidate_identity=FieldValue(**ru["primary_candidate_identity"]),
                # .get(...) or {} (not bracket access): sessions persisted
                # before this field existed won't have this key at all.
                hiring_company=FieldValue(**(ru.get("hiring_company") or {})),
                candidate_archetype=FieldValue(**ru["candidate_archetype"]),
                role_interpretation=FieldValue(**(ru.get("role_interpretation") or {})),
                seniority_scope=FieldValue(**ru["seniority_scope"]),
                leadership_type=FieldValue(**ru["leadership_type"]),
                core_capabilities=[CapabilityItem(**item) for item in ru["core_capabilities"]],
                supporting_capabilities=[CapabilityItem(**item) for item in ru["supporting_capabilities"]],
                differentiators=[CapabilityItem(**item) for item in ru["differentiators"]],
                technologies_mentioned=[TechnologyGroup(**group) for group in ru.get("technologies_mentioned") or []],
                domain=list(ru["domain"]),
                explicit_constraints=ExplicitConstraints(**constraints_data),
                open_questions=list(ru["open_questions"]),
            ),
            decision=IntakeDecision(
                issues=[IntakeIssue(**item) for item in decision_data["issues"]],
                recommended_ask_count=decision_data.get("recommended_ask_count", 0),
                stop_reasoning=decision_data.get("stop_reasoning"),
                warnings=list(decision_data.get("warnings") or []),
                search_consequence_summary=decision_data.get("search_consequence_summary"),
                final_search_intent=FinalSearchIntentDraft(**decision_data["final_search_intent"]),
            ),
            contradictions=[],
            status=result_data.get("status", "ready"),
        )

    boundary_data = data.get("boundary")
    boundary = SearchBoundary(**boundary_data) if boundary_data else None

    return IntakeSessionRecord(
        session_id=data["session_id"],
        raw_input=data["raw_input"],
        answers=[RecordedAnswer(**answer) for answer in data.get("answers", [])],
        result=result,
        boundary=boundary,
    )
