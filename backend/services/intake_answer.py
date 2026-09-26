"""Applying a recruiter's answer to a PINNED role understanding.

The model proposes a small patch (which structured fields the answer changes). Code validates every operation
against the current state and applies only what passes. Nothing the patch does not name can change, so answering one
question cannot make an unrelated part of the brief drift. Rejected operations are dropped, never repaired.

Deterministic apart from the single model call that proposes the patch.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.models.intake import (
    ConfirmedChange,
    FieldValue,
    IntakeIssue,
    IntakeResult,
)
from backend.services.intake_reasoning import IntakeReasoner, detect_intake_contradictions, parse_intake_decision, role_understanding_to_dict

TIERS = {"core": "hard_requirements", "supporting": "strong_signals", "preferred": "preferred_differentiators"}
_DURATION_MENTION = re.compile(r"\b\d+\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
# A requirement that is just "N years of (professional ...) experience": the generic years requirement, which the
# structured experience range replaces. "5+ years of Python" is not generic and is never removed on its own.
_GENERIC_YEARS_RE = re.compile(r"^\W*\d+\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs?)(?:\s+of)?(?:\s+(?:professional|relevant|industry|software|engineering|total|overall|hands-on|work|working|commercial|proven|practical|development))*\s+experience\b", re.IGNORECASE)
_LEADERSHIP_VALUES = {"people", "technical", "workflow", "none", "unclear"}
MAX_NEW_ISSUES = 1


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#.]+", " ", (text or "").lower()).split())


def _requirement_lists(result: IntakeResult) -> Dict[str, List[str]]:
    intent = result.decision.final_search_intent
    return {tier: getattr(intent, attribute) for tier, attribute in TIERS.items()}


def find_requirement(result: IntakeResult, text: str) -> Optional[Tuple[str, int]]:
    """(tier, index) of the requirement whose text matches exactly (ignoring case and punctuation)."""
    wanted = _norm(text)
    if not wanted:
        return None
    for tier, items in _requirement_lists(result).items():
        for index, item in enumerate(items):
            if _norm(item) == wanted:
                return tier, index
    return None


def _describe_years(minimum: Optional[int], maximum: Optional[int]) -> str:
    if minimum and maximum:
        return f"{minimum}-{maximum} years"
    if minimum:
        return f"{minimum}+ years"
    if maximum:
        return f"up to {maximum} years"
    return "no stated minimum"


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _set_field(field_value: FieldValue, value: str) -> None:
    field_value.value = value
    field_value.source = "recruiter"
    field_value.evidence = "Confirmed by the recruiter."


def apply_patch(result: IntakeResult, patch: Dict[str, Any], issue: IntakeIssue, answer_label: str, raw_input: str) -> List[str]:
    """Validates and applies the patch in place. Returns human-readable notes about anything it refused, for logs
    and tests. Only whitelisted operations on things that exist can succeed."""
    refused: List[str] = []
    role = result.role_understanding
    constraints = role.explicit_constraints
    intent = result.decision.final_search_intent

    def record(field: str, description: str, item: Optional[str] = None) -> None:
        result.confirmed.append(ConfirmedChange(field=field, description=description, item=item, issue=issue.issue, answer=answer_label))

    changes = patch.get("changes")
    if not isinstance(changes, list):
        changes = []

    altered_requirements = False
    for change in changes:
        if not isinstance(change, dict):
            refused.append("not an object")
            continue
        op = change.get("op")

        if op == "set_experience":
            minimum, maximum = _int_or_none(change.get("minimum_years")), _int_or_none(change.get("maximum_years"))
            if minimum is not None and maximum is not None and maximum < minimum:
                refused.append("experience range is inverted")
                continue
            constraints.experience_minimum_years, constraints.experience_maximum_years = minimum, maximum
            # The structured range now says how many years. An old generic years sentence would contradict it, so it
            # goes; when the requirement is dropped entirely, any years sentence goes.
            for attribute in TIERS.values():
                kept = [
                    text
                    for text in getattr(intent, attribute)
                    if not (_GENERIC_YEARS_RE.search(text) or (minimum is None and _DURATION_MENTION.search(text)))
                ]
                if len(kept) != len(getattr(intent, attribute)):
                    altered_requirements = True
                setattr(intent, attribute, kept)
            record("experience", f"Experience: {_describe_years(minimum, maximum)}")

        elif op == "set_seniority":
            value = str(change.get("value") or "").strip()
            if not value:
                refused.append("empty seniority")
                continue
            _set_field(role.seniority_scope, value)
            record("seniority", f"Seniority: {value}")

        elif op == "set_identity":
            value = str(change.get("value") or "").strip()
            if not value or len(value.split()) > 8:
                refused.append("identity must be a short label")
                continue
            _set_field(role.primary_candidate_identity, value)
            record("identity", f"Candidate identity: {value}")

        elif op == "set_leadership":
            value = str(change.get("value") or "").strip().lower()
            if value not in _LEADERSHIP_VALUES:
                refused.append(f"unknown leadership value {value!r}")
                continue
            role.leadership_type.value = value
            record("leadership", f"Leadership: {value}")

        elif op == "move_requirement":
            found = find_requirement(result, str(change.get("text") or ""))
            target = str(change.get("to") or "")
            if found is None:
                refused.append(f"no such requirement: {change.get('text')!r}")
                continue
            if target not in (*TIERS, "remove"):
                refused.append(f"unknown tier {target!r}")
                continue
            tier, index = found
            source_list = _requirement_lists(result)[tier]
            text = source_list.pop(index)
            if target != "remove":
                _requirement_lists(result)[target].append(text)
            altered_requirements = True
            record("requirement", f"{text}: {'removed' if target == 'remove' else 'now ' + target}", item=text)

        elif op == "add_requirement":
            text = str(change.get("text") or "").strip()
            tier = str(change.get("tier") or "")
            if not text or tier not in TIERS:
                refused.append("add_requirement needs text and a tier")
                continue
            # Only what the recruiter's own answer (or the input they gave) actually says.
            support = _norm(f"{answer_label} {raw_input}")
            if not any(word in support for word in _norm(text).split() if len(word) > 3):
                refused.append(f"requirement not supported by the answer: {text!r}")
                continue
            if find_requirement(result, text) is None:
                _requirement_lists(result)[tier].append(text)
                altered_requirements = True
                record("requirement", f"{text}: added as {tier}", item=text)

        elif op == "add_exclusion":
            value = str(change.get("value") or "").strip()
            if not value:
                refused.append("empty exclusion")
                continue
            if value not in constraints.exclusions:
                constraints.exclusions.append(value)
            if value not in intent.exclusions:
                intent.exclusions.append(value)
            record("exclusion", f"Excluded: {value}")

        else:
            refused.append(f"unknown operation {op!r}")

    sentence = patch.get("natural_language_search_query")
    if isinstance(sentence, str) and sentence.strip():
        if detect_intake_contradictions(sentence):
            refused.append("proposed search sentence contradicts itself")
        else:
            intent.natural_language_search_query = sentence.strip()
    elif altered_requirements or any(c.get("op") in ("set_experience", "set_seniority", "set_identity") for c in changes if isinstance(c, dict)):
        # The requirements changed but the model gave no new sentence. Keep the old one only if it does not now
        # contradict the resolved reading; otherwise clear it so the translator builds a deterministic one.
        if detect_intake_contradictions(intent.natural_language_search_query or ""):
            intent.natural_language_search_query = None
    return refused


def valid_new_issues(patch: Dict[str, Any], result: IntakeResult, answered: List[IntakeIssue], resolved_categories: set) -> List[IntakeIssue]:
    """At most one new question, and never one that repeats something already asked or resolved."""
    raw = patch.get("new_issues")
    if not isinstance(raw, list) or not raw:
        return []
    candidates = parse_intake_decision({"issues": raw}).issues
    known = {_norm(i.issue) for i in [*result.decision.issues, *answered]} | {_norm(i.question or "") for i in [*result.decision.issues, *answered]}
    accepted: List[IntakeIssue] = []
    for issue in candidates:
        if issue.decision != "ask" or not issue.question or len(issue.options) < 2:
            continue
        if not (issue.consequence_if_answer_a and issue.consequence_if_answer_b) or issue.consequence_if_answer_a.strip().lower() == issue.consequence_if_answer_b.strip().lower():
            continue
        if _norm(issue.issue) in known or _norm(issue.question) in known:
            continue
        accepted.append(issue)
        if len(accepted) >= MAX_NEW_ISSUES:
            break
    return accepted


def propose_patch(reasoner: IntakeReasoner, result: IntakeResult, issue: IntakeIssue, value: str, label: str, prior: List[Dict[str, str]], raw_input: str) -> Dict[str, Any]:
    """The single model call for one answer."""
    intent = result.decision.final_search_intent
    prompt = (
        reasoner._load_prompt("intake_task_c_answer.txt")
        .replace("{role_understanding_json}", json.dumps(role_understanding_to_dict(result.role_understanding)))
        .replace(
            "{final_search_intent_json}",
            json.dumps(
                {
                    "core": list(intent.hard_requirements),
                    "supporting": list(intent.strong_signals),
                    "preferred": list(intent.preferred_differentiators),
                    "exclusions": list(intent.exclusions),
                    "natural_language_search_query": intent.natural_language_search_query,
                }
            ),
        )
        .replace(
            "{answered_issue_json}",
            json.dumps({"issue": issue.issue, "question": issue.question, "options": issue.options, "consequence_if_answer_a": issue.consequence_if_answer_a, "consequence_if_answer_b": issue.consequence_if_answer_b}),
        )
        .replace("{answer_json}", json.dumps({"value": value, "label": label}))
        .replace("{prior_answers_json}", json.dumps(prior))
        .replace("{raw_input}", raw_input)
    )
    return reasoner.call_json("Follow the instructions in the user message exactly and return only the JSON they specify.", prompt)
