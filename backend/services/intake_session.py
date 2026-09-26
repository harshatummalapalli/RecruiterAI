"""Orchestration of an intake conversation on top of IntakeReasoner.

The role understanding is PINNED. Task A runs once, at the start. Task B decides ASK/TELL/IGNORE once, at the start.
After that:

    recruiter answers a question
      -> ONE small model call proposes a patch (which structured fields the answer changes)
      -> code validates the patch and applies only what passes (backend/services/intake_answer.py)
      -> the answered question, and only that question, is resolved

Nothing the answer does not name can change, so answering one question never makes an unrelated part of the brief
drift, and a resolved question can never reappear (it is not re-derived). Task A is never re-run. Editing the Search
Boundary is fully deterministic and makes no model call at all.

Every recruiter-confirmed change is recorded (IntakeResult.confirmed) so the brief can say exactly which fields the
recruiter confirmed.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.intake import IntakeIssue, IntakeResult, SearchBoundary
from backend.services.intake_answer import apply_patch, propose_patch, valid_new_issues
from backend.services.intake_reasoning import (
    IntakeReasoner,
    apply_search_boundary,
    boundary_fingerprint,
    infer_backstop_category,
)
from backend.services.search_store import SearchStore

DEFAULT_INTAKE_STORAGE_DIR = Path(__file__).resolve().parents[2] / "output" / "intake_sessions"

# Answer values that resolve nothing by themselves.
_DEFERRING_VALUE = "recruiter_will_clarify"
_KEEP_BOUNDARY_VALUE = "keep_selected_location"


@dataclass
class RecordedAnswer:
    issue_key: str
    question: Optional[str]
    value: str
    label: str
    backstop_category: Optional[str] = None
    # For a boundary conflict the recruiter chose to keep: which boundary that choice was about.
    boundary_fingerprint: Optional[str] = None


@dataclass
class IntakeSessionRecord:
    session_id: str
    raw_input: str
    answers: List[RecordedAnswer] = field(default_factory=list)
    result: Optional[IntakeResult] = None
    # The recruiter-confirmed search boundary, authoritative for hiring company/location/work mode. None only for a
    # session stored before boundaries were mandatory.
    boundary: Optional[SearchBoundary] = None
    # The title exactly as the recruiter typed it (None when they left it blank).
    posted_title_input: Optional[str] = None


def _assign_issue_ids(result: IntakeResult) -> None:
    """Gives an id to every issue that has none. Existing ids never change, so an id the browser holds stays valid
    across answers and reloads."""
    llm_used = [
        int(i.id.split("-", 1)[1])
        for i in result.decision.issues
        if i.id and i.id.startswith("issue-") and i.id.split("-", 1)[1].isdigit()
    ]
    next_llm = (max(llm_used) + 1) if llm_used else 0
    for issue in result.decision.issues:
        if issue.id:
            continue
        if issue.injected_by_backstop:
            issue.id = f"backstop-{issue.backstop_category or 'issue'}"
        else:
            issue.id = f"issue-{next_llm}"
            next_llm += 1


def _refresh_status(result: IntakeResult) -> None:
    result.decision.recommended_ask_count = sum(1 for issue in result.decision.issues if issue.decision == "ask")
    result.status = "needs_clarification" if result.decision.recommended_ask_count else "ready"


def _resolved_conflicts(answers: List[RecordedAnswer]) -> List[str]:
    return [a.boundary_fingerprint for a in answers if a.backstop_category == "location_boundary_conflict" and a.boundary_fingerprint]


def _drop_resolved_category(result: IntakeResult, category: Optional[str], answered_key: str) -> None:
    """Removes the answered question, anything else that is the same contradiction, and its now-stale warnings."""
    stale_warnings = {c.warning for c in result.contradictions if category and c.category == category}
    remaining: List[IntakeIssue] = []
    for issue in result.decision.issues:
        if issue.issue == answered_key:
            continue
        issue_category = issue.backstop_category or infer_backstop_category(issue.issue, issue.question)
        if category and issue.decision == "ask" and issue_category == category:
            continue
        remaining.append(issue)
    result.decision.issues = remaining
    if category:
        result.decision.warnings = [
            w for w in result.decision.warnings if w not in stale_warnings and infer_backstop_category(w, None) != category
        ]
        result.contradictions = [c for c in result.contradictions if c.category != category]


class IntakeSessionManager:
    """`reasoner` and `store` are injectable for tests, matching the rest of this codebase's dependency-injection
    pattern."""

    def __init__(self, reasoner: Optional[IntakeReasoner] = None, store: Optional[SearchStore] = None) -> None:
        self._reasoner = reasoner or IntakeReasoner()
        self._store = store or SearchStore(storage_dir=DEFAULT_INTAKE_STORAGE_DIR)

    def start(self, raw_input: str, boundary: Optional[SearchBoundary] = None, posted_title: Optional[str] = None) -> IntakeSessionRecord:
        session_id = str(uuid.uuid4())
        # Task A and Task B run on raw_input alone, unmodified by the boundary, so Task A's own location reading
        # stays an independent check. This is the only time either runs.
        result = self._reasoner.run(raw_input, posted_title=posted_title)
        if boundary is not None:
            apply_search_boundary(result, boundary)
        _assign_issue_ids(result)
        _refresh_status(result)
        record = IntakeSessionRecord(
            session_id=session_id, raw_input=raw_input, answers=[], result=result, boundary=boundary, posted_title_input=posted_title
        )
        self._save(record)
        return record

    def answer(self, session_id: str, issue_id: str, value: str, label: str) -> IntakeSessionRecord:
        record = self._load(session_id)
        if record is None:
            raise KeyError(session_id)
        if record.result is None:
            raise ValueError("Intake session has no prior result to answer against.")
        result = record.result

        issue = next((i for i in result.decision.issues if i.id == issue_id and i.decision == "ask"), None)
        if issue is None:
            raise ValueError(f"Unknown or already resolved question: {issue_id}")

        # "Let me reconsider" resolves nothing: the question stays until the boundary or the description changes.
        if value == _DEFERRING_VALUE:
            return record

        category = issue.backstop_category or infer_backstop_category(issue.issue, issue.question)
        answer = RecordedAnswer(issue_key=issue.issue, question=issue.question, value=value, label=label, backstop_category=category)
        prior = [{"question": a.question or a.issue_key, "answer": a.label} for a in record.answers]

        new_issues: List[IntakeIssue] = []
        if category == "location_boundary_conflict" and value == _KEEP_BOUNDARY_VALUE and record.boundary is not None:
            # Deterministic: the recruiter kept the boundary they chose. Nothing to interpret.
            answer.boundary_fingerprint = boundary_fingerprint(record.boundary)
        else:
            patch = propose_patch(self._reasoner, result, issue, value, label, prior, record.raw_input)
            apply_patch(result, patch, issue, label, record.raw_input)
            answered_stubs = [IntakeIssue(issue=a.issue_key, decision="ask", question=a.question) for a in record.answers]
            new_issues = valid_new_issues(patch, result, [*answered_stubs, issue], {a.backstop_category for a in record.answers if a.backstop_category})
            reasoning = patch.get("reasoning") if isinstance(patch.get("reasoning"), str) else None
            if reasoning:
                result.decision.stop_reasoning = reasoning

        record.answers.append(answer)
        _drop_resolved_category(result, category, issue.issue)
        result.decision.issues.extend(new_issues)
        _assign_issue_ids(result)
        _refresh_status(result)
        self._save(record)
        return record

    def update_boundary(self, session_id: str, boundary: SearchBoundary) -> IntakeSessionRecord:
        """Deterministic. Re-applies the new boundary to the pinned reading; no model call is made."""
        record = self._load(session_id)
        if record is None:
            raise KeyError(session_id)
        if record.result is None:
            raise ValueError("Intake session has no result to apply a boundary to.")
        record.boundary = boundary
        apply_search_boundary(record.result, boundary, resolved_conflicts=_resolved_conflicts(record.answers))
        _assign_issue_ids(record.result)
        _refresh_status(record.result)
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
        "posted_title_input": record.posted_title_input,
    }


def _record_from_dict(data: Dict[str, Any]) -> IntakeSessionRecord:
    from backend.models.intake import (
        CapabilityItem,
        ConfirmedChange,
        ContradictionFinding,
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
        constraints_data["locations"] = [LocationEntry(**entry) for entry in constraints_data.get("locations") or []]
        result = IntakeResult(
            raw_input=result_data.get("raw_input", ""),
            role_understanding=RoleUnderstanding(
                posted_title=ru.get("posted_title"),
                posted_title_source=ru.get("posted_title_source"),
                primary_candidate_identity=FieldValue(**ru["primary_candidate_identity"]),
                # .get(...) or {} (not bracket access): sessions persisted before this field existed won't have it.
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
                limitations=list(decision_data.get("limitations") or []),
                final_search_intent=FinalSearchIntentDraft(**decision_data["final_search_intent"]),
            ),
            contradictions=[ContradictionFinding(**item) for item in result_data.get("contradictions") or []],
            status=result_data.get("status", "ready"),
            confirmed=[ConfirmedChange(**item) for item in result_data.get("confirmed") or []],
        )

    boundary_data = data.get("boundary")
    boundary = SearchBoundary(**boundary_data) if boundary_data else None

    return IntakeSessionRecord(
        session_id=data["session_id"],
        raw_input=data["raw_input"],
        answers=[RecordedAnswer(**answer) for answer in data.get("answers", [])],
        result=result,
        boundary=boundary,
        posted_title_input=data.get("posted_title_input"),
    )
