"""EXPERIMENT ONLY (EXP-002b/c). Not used by the product: neither approach met its pre-registered rule.

Feasibility review: at most two factual notes about a brief, from one dedicated model call.

The model reasons (does one of three specific situations clearly apply?). Code validates: every finding must be about
something the brief actually contains, and must cite enough of it. Findings are TELLs only; they never block a
search. A sensible brief gets none.
"""

import json
from typing import Any, Dict, List, Optional

from backend.models.intake import IntakeIssue, RoleUnderstanding
from pathlib import Path

from backend.models.intake import IntakeDecision
from backend.services.intake_reasoning import IntakeReasoner, _match_form

MAX_FINDINGS = 2
PROMPT = Path(__file__).with_name("feasibility_review_prompt.txt")
SITUATIONS = {
    "over_constrained": ("Requirements that rarely go together", 2),
    "impossible_tenure": ("Years of experience longer than the technology has existed", 1),
    "level_vs_years": ("Title level and years of experience disagree", 2),
}


def brief_for_review(understanding: RoleUnderstanding, hard: List[str], strong: List[str], preferred: List[str]) -> Dict[str, Any]:
    constraints = understanding.explicit_constraints
    years = {"minimum_years": constraints.experience_minimum_years, "maximum_years": constraints.experience_maximum_years}
    return {
        "posted_title": understanding.posted_title,
        "seniority": understanding.seniority_scope.value,
        "experience_range": years,
        "core": list(hard),
        "supporting": list(strong),
        "preferred": list(preferred),
    }


def review_feasibility(reasoner: IntakeReasoner, understanding: RoleUnderstanding, hard: List[str], strong: List[str], preferred: List[str]) -> List[IntakeIssue]:
    if not hard and not strong:
        return []
    brief = brief_for_review(understanding, hard, strong, preferred)
    prompt = PROMPT.read_text(encoding="utf-8").replace("{brief_json}", json.dumps(brief, indent=1))
    payload = reasoner.call_json("Follow the instructions in the user message exactly and return only the JSON they specify.", prompt)
    return validate_findings(payload, understanding.posted_title, hard, strong, preferred)


def validate_findings(payload: Dict[str, Any], posted_title: Optional[str], hard: List[str], strong: List[str], preferred: List[str]) -> List[IntakeIssue]:
    requirements = {_match_form(text) for text in [*hard, *strong, *preferred]}
    title = _match_form(posted_title or "")
    raw = payload.get("findings") if isinstance(payload, dict) else None
    issues: List[IntakeIssue] = []
    for finding in raw if isinstance(raw, list) else []:
        if not isinstance(finding, dict):
            continue
        situation = finding.get("situation")
        statement = finding.get("statement")
        references = [ref for ref in (finding.get("references") or []) if isinstance(ref, str) and ref.strip()]
        if situation not in SITUATIONS or not isinstance(statement, str) or not statement.strip():
            continue
        forms = [_match_form(ref) for ref in references]
        if any(form not in requirements and form != title for form in forms):
            continue  # about something the brief does not contain
        label, minimum = SITUATIONS[situation]
        if len(set(forms)) < minimum:
            continue
        if situation == "level_vs_years" and not (title and title in forms):
            continue  # a level mismatch has to cite the title it is about
        issues.append(
            IntakeIssue(
                issue=f"Feasibility: {label}",
                decision="tell",
                reasoning="A factual note about the brief, not a question.",
                insight_text=statement.strip(),
                kind="feasibility",
                references=references,
            )
        )
        if len(issues) >= MAX_FINDINGS:
            break
    return issues


# --- EXP-002b: validators for the "feasibility inside Task B" variant (also not adopted) ---------------------------

MAX_FEASIBILITY_ISSUES = 2
_MIN_QUOTE_CHARS = 4


def verify_requirement_evidence(decision: IntakeDecision, raw_input: str) -> None:
    """Keeps a model-supplied evidence quote only when it really appears in the raw input."""
    draft = decision.final_search_intent
    known = {_match_form(text): text for text in [*draft.hard_requirements, *draft.strong_signals, *draft.preferred_differentiators]}
    haystack = _match_form(raw_input)
    verified = {}
    for text, quote in (getattr(draft, "model_evidence", None) or {}).items():
        original = known.get(_match_form(text))
        form = _match_form(quote or "")
        if original is not None and len(form) >= _MIN_QUOTE_CHARS and form in haystack:
            verified[original] = quote.strip()
    draft.evidence = verified


def validate_feasibility_issues(decision: IntakeDecision, posted_title: Optional[str]) -> None:
    """Drops any feasibility issue that is not about something the brief contains."""
    draft = decision.final_search_intent
    allowed = {_match_form(text) for text in [*draft.hard_requirements, *draft.strong_signals, *draft.preferred_differentiators]}
    if posted_title:
        allowed.add(_match_form(posted_title))
    kept: List[IntakeIssue] = []
    seen = 0
    for issue in decision.issues:
        if issue.kind != "feasibility":
            kept.append(issue)
            continue
        refs = [_match_form(ref) for ref in issue.references]
        if not refs or any(ref not in allowed for ref in refs) or issue.decision not in ("tell", "ask"):
            continue
        seen += 1
        if seen <= MAX_FEASIBILITY_ISSUES:
            kept.append(issue)
    decision.issues = kept
