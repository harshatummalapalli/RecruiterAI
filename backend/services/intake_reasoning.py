import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.errors import ConfigurationError, ParsingError
from backend.models.intake import (
    CapabilityItem,
    ContradictionFinding,
    ExplicitConstraints,
    FieldValue,
    FinalSearchIntentDraft,
    IntakeDecision,
    IntakeIssue,
    IntakeResult,
    LocationEntry,
    RoleUnderstanding,
    TechnologyGroup,
    role_understanding_to_dict,
)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# ---------------------------------------------------------------------------
# Deterministic contradiction backstop.
#
# This exists ONLY because the reasoning spike showed single-call LLM
# contradiction detection is probabilistic (it caught the entry-level/10-years
# and remote/onsite contradictions most, not all, of the time — one run in
# three silently produced a self-contradictory natural_language_search_query
# with zero warning). It is a narrow safety floor under Task B, never a
# replacement for its judgment, and never a general rules engine: it
# recognizes exactly two contradiction shapes and asserts nothing else. It
# never decides which side of a contradiction is correct — only that the
# recruiter must.
# ---------------------------------------------------------------------------

JUNIOR_TERMS = ["entry level", "entry-level", "junior", "graduate", "new grad"]
SENIOR_TERMS = ["senior", "lead", "principal", "staff", "architect", "head"]
REMOTE_TERMS = ["fully remote", "work from anywhere", "remote", "anywhere"]
ONSITE_TERMS = ["on-site", "onsite", "office-based", "must work from office", "required in office"]

# A junior/entry signal alongside a stated experience requirement at or above
# this many years is treated as an obvious contradiction (e.g. "entry-level...
# 10+ years"), even without an explicit senior-title word present.
_SENIOR_EXPERIENCE_YEARS_THRESHOLD = 5
_EXPERIENCE_YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*years?\b", re.IGNORECASE)


def _find_terms(text_lower: str, terms: List[str]) -> List[str]:
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text_lower)]


# "mentor junior engineers"/"manage junior developers" describes people the
# candidate supervises, not the candidate's own level — excluded so it can't
# trigger the experience/seniority contradiction check on its own. Found via
# the stability test against scenario 8 (an Engineering Manager JD that
# mentions mentoring junior engineers while being an otherwise senior IC role).
_JUNIOR_ABOUT_OTHERS_RE = re.compile(
    r"\b(?:mentor|manage|lead|coach|supervise|guide|support)\w*\s+(?:\w+\s+){0,2}junior\s+"
    r"(?:engineers?|developers?|analysts?|staff|hires?|team\s+members?|colleagues?|reports?)\b",
    re.IGNORECASE,
)


def _junior_terms_about_the_candidate(text_lower: str) -> List[str]:
    """Same as _find_terms(text_lower, JUNIOR_TERMS), but with any "mentor/
    manage junior engineers"-style mention (about a third party the candidate
    supervises, not the candidate) removed first."""
    sanitized = _JUNIOR_ABOUT_OTHERS_RE.sub(" ", text_lower)
    return _find_terms(sanitized, JUNIOR_TERMS)


def detect_intake_contradictions(raw_input: str) -> List[ContradictionFinding]:
    """Pure, deterministic. Looks only at the raw input text — never at Task
    A/B's interpretation — so it can't be fooled by an LLM that already
    smoothed the contradiction away. Detects exactly two shapes: an
    experience/seniority contradiction, and a location/work-mode
    contradiction. Never rewrites or resolves either side."""
    text_lower = raw_input.lower()
    findings: List[ContradictionFinding] = []

    junior_hits = _junior_terms_about_the_candidate(text_lower)
    senior_hits = _find_terms(text_lower, SENIOR_TERMS)
    year_numbers = [int(match) for match in _EXPERIENCE_YEARS_RE.findall(raw_input)]
    high_experience = [n for n in year_numbers if n >= _SENIOR_EXPERIENCE_YEARS_THRESHOLD]

    if junior_hits and (senior_hits or high_experience):
        senior_side = sorted(set(senior_hits)) or [f"{max(high_experience)}+ years"]
        findings.append(
            ContradictionFinding(
                category="experience_seniority",
                warning=(
                    "This input mixes an entry-level/junior signal with a senior-level or "
                    f"high-experience signal ({', '.join(sorted(set(junior_hits)))} vs "
                    f"{', '.join(senior_side)}) — these cannot both be correct. "
                    "The recruiter must resolve which is intended before searching."
                ),
                evidence=sorted(set(junior_hits)) + senior_side,
            )
        )

    remote_hits = _find_terms(text_lower, REMOTE_TERMS)
    onsite_hits = _find_terms(text_lower, ONSITE_TERMS)
    if remote_hits and onsite_hits:
        findings.append(
            ContradictionFinding(
                category="location_work_mode",
                warning=(
                    "This input states both a remote/anywhere work-mode signal and a specific "
                    f"onsite requirement ({', '.join(sorted(set(remote_hits)))} vs "
                    f"{', '.join(sorted(set(onsite_hits)))}) — these cannot both be correct. "
                    "The recruiter must resolve which is intended before searching."
                ),
                evidence=sorted(set(remote_hits)) + sorted(set(onsite_hits)),
            )
        )

    return findings


_CATEGORY_KEYWORDS = {
    "experience_seniority": ["year", "senior", "junior", "entry", "seniority", "experience"],
    "location_work_mode": ["remote", "onsite", "on-site", "location", "work mode", "office"],
    "missing_location": ["location", "where", "city", "remote", "onsite"],
}

# If none of these appear, an absent location is treated as a genuine gap
# (per the search boundary: location is almost always a real filter) rather
# than an intentional "open to anywhere" choice.
_LOCATION_AGNOSTIC_TERMS = ["remote", "anywhere", "work from home", "fully remote", "open to any location"]


def detect_missing_location(raw_input: str, has_structured_location: bool) -> List[ContradictionFinding]:
    """Same guaranteed-floor idea as detect_intake_contradictions, but for a
    different, equally demonstrated gap: Task A does not always flag a
    genuinely absent location as an open question (observed live, non-
    deterministically), which would otherwise let the confirmed search run
    with no location filter and no indication to the recruiter at all."""
    if has_structured_location:
        return []
    if _find_terms(raw_input.lower(), _LOCATION_AGNOSTIC_TERMS):
        return []
    return [
        ContradictionFinding(
            category="missing_location",
            warning=(
                "No location was stated for this role, and it isn't described as remote/open to any "
                "location. Location materially affects candidate availability, so this should be "
                "confirmed before searching."
            ),
            evidence=[],
        )
    ]


def infer_backstop_category(issue_text: str, question_text: Optional[str]) -> Optional[str]:
    """Given an arbitrary ask issue's text (LLM-authored or backstop-
    injected), returns which contradiction category it addresses, if any —
    using the same keyword lists `_existing_ask_covers` uses in the other
    direction. Lets the session layer (intake_session.py) recognize that an
    LLM-authored ask already resolved a contradiction category, even though
    only backstop-injected issues carry `backstop_category` directly."""
    haystack = f"{issue_text} {question_text or ''}".lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


def _existing_ask_covers(decision: IntakeDecision, category: str) -> bool:
    keywords = _CATEGORY_KEYWORDS[category]
    for issue in decision.issues:
        if issue.decision != "ask":
            continue
        haystack = f"{issue.issue} {issue.question or ''}".lower()
        if any(keyword in haystack for keyword in keywords):
            return True
    return False


def _default_options_for(category: str) -> List[Dict[str, str]]:
    if category == "experience_seniority":
        return [
            {"value": "as_junior_senior_dropped", "label": "Treat as entry-level (drop the years requirement)"},
            {"value": "as_stated_years", "label": "Treat as senior (keep the stated years requirement)"},
            {"value": "recruiter_will_clarify", "label": "Let me clarify"},
        ]
    if category == "missing_location":
        return [
            {"value": "specify_location", "label": "Let me specify a location"},
            {"value": "remote_any", "label": "Fully remote — open to any location"},
        ]
    return [
        {"value": "remote", "label": "Fully remote — drop the onsite requirement"},
        {"value": "onsite", "label": "Onsite as stated — drop the remote framing"},
        {"value": "recruiter_will_clarify", "label": "Let me clarify"},
    ]


def _default_question_for(category: str) -> str:
    if category == "experience_seniority":
        return "This role states both an entry-level/junior signal and a senior-level or high-experience requirement. Which is correct?"
    if category == "missing_location":
        return "No location was mentioned for this role. Should the search target a specific location, or is it open to any location?"
    return "This role states both a remote/anywhere work-mode signal and a specific onsite requirement. Which is correct?"


def apply_contradiction_backstop(raw_input: str, decision: IntakeDecision) -> tuple[IntakeDecision, List[ContradictionFinding]]:
    """Runs AFTER Task B. Guarantees a floor: every genuine contradiction
    detected in the raw text ends up represented in `decision.warnings`, and
    as an "ask" issue if Task B did not already create an equivalent one.
    Never removes or edits anything Task B produced."""
    return _merge_findings(raw_input, decision, detect_intake_contradictions(raw_input))


def apply_intake_backstops(
    raw_input: str, has_structured_location: bool, decision: IntakeDecision
) -> tuple[IntakeDecision, List[ContradictionFinding]]:
    """The full deterministic floor used by IntakeReasoner: contradiction
    safety (Phase 1/2) plus the missing-location guarantee (Phase 3) — both
    additive checks over Task B's own output, never a replacement for it."""
    findings = detect_intake_contradictions(raw_input) + detect_missing_location(raw_input, has_structured_location)
    return _merge_findings(raw_input, decision, findings)


def _merge_findings(
    raw_input: str, decision: IntakeDecision, findings: List[ContradictionFinding]
) -> tuple[IntakeDecision, List[ContradictionFinding]]:
    if not findings:
        return decision, findings

    existing_warnings = set(decision.warnings)
    new_warnings = list(decision.warnings)
    new_issues = list(decision.issues)

    for finding in findings:
        if finding.warning not in existing_warnings:
            new_warnings.append(finding.warning)
            existing_warnings.add(finding.warning)

        if not _existing_ask_covers(decision, finding.category):
            is_gap = finding.category == "missing_location"
            new_issues.append(
                IntakeIssue(
                    issue=(
                        "Missing location" if is_gap else f"Contradiction: {finding.category.replace('_', ' ')}"
                    ),
                    decision="ask",
                    reasoning=finding.warning,
                    question=_default_question_for(finding.category),
                    options=_default_options_for(finding.category),
                    consequence_if_answer_a=(
                        "Applies a specific location filter." if is_gap else "Resolves the contradiction toward the first stated reading."
                    ),
                    consequence_if_answer_b=(
                        "Leaves the search unconstrained by location (fully remote)." if is_gap else "Resolves the contradiction toward the second stated reading."
                    ),
                    injected_by_backstop=True,
                    backstop_category=finding.category,
                )
            )

    updated = IntakeDecision(
        issues=new_issues,
        recommended_ask_count=sum(1 for issue in new_issues if issue.decision == "ask"),
        stop_reasoning=decision.stop_reasoning,
        warnings=new_warnings,
        final_search_intent=decision.final_search_intent,
    )
    return updated, findings


# ---------------------------------------------------------------------------
# Parsing raw LLM JSON into the dataclasses above. Tolerant of missing keys —
# the model's exact key set can vary slightly run to run.
# ---------------------------------------------------------------------------


def _parse_field_value(data: Optional[Dict[str, Any]]) -> FieldValue:
    data = data or {}
    return FieldValue(value=data.get("value"), evidence=data.get("evidence"), source=data.get("source"))


def _parse_capability_items(data: Optional[List[Dict[str, Any]]]) -> List[CapabilityItem]:
    return [
        CapabilityItem(value=item.get("value", ""), tier_signal=item.get("tier_signal"), evidence=item.get("evidence"))
        for item in (data or [])
        if item.get("value")
    ]


def _parse_technology_groups(data: Optional[List[Dict[str, Any]]]) -> List[TechnologyGroup]:
    groups: List[TechnologyGroup] = []
    for item in data or []:
        category = (item.get("category") or "").strip()
        items = [value for value in (item.get("items") or []) if value]
        if category and items:
            groups.append(TechnologyGroup(category=category, items=items))
    return groups


def _parse_locations(data: Optional[List[Dict[str, Any]]]) -> List[LocationEntry]:
    entries: List[LocationEntry] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        city = (item.get("city") or "").strip() or None
        state = (item.get("state") or "").strip() or None
        country = (item.get("country") or "").strip() or None
        if city or state or country:
            entries.append(LocationEntry(city=city, state=state, country=country))
    return entries


def parse_role_understanding(data: Dict[str, Any]) -> RoleUnderstanding:
    constraints_data = data.get("explicit_constraints") or {}
    return RoleUnderstanding(
        posted_title=data.get("posted_title"),
        primary_candidate_identity=_parse_field_value(data.get("primary_candidate_identity")),
        hiring_company=_parse_field_value(data.get("hiring_company")),
        candidate_archetype=_parse_field_value(data.get("candidate_archetype")),
        role_interpretation=_parse_field_value(data.get("role_interpretation")),
        seniority_scope=_parse_field_value(data.get("seniority_scope")),
        leadership_type=_parse_field_value(data.get("leadership_type")),
        core_capabilities=_parse_capability_items(data.get("core_capabilities")),
        supporting_capabilities=_parse_capability_items(data.get("supporting_capabilities")),
        differentiators=_parse_capability_items(data.get("differentiators")),
        technologies_mentioned=_parse_technology_groups(data.get("technologies_mentioned")),
        domain=list(data.get("domain") or []),
        explicit_constraints=ExplicitConstraints(
            locations=_parse_locations(constraints_data.get("locations")),
            work_mode=constraints_data.get("work_mode"),
            experience_minimum_years=constraints_data.get("experience_minimum_years"),
            experience_maximum_years=constraints_data.get("experience_maximum_years"),
            employment_type=constraints_data.get("employment_type"),
            exclusions=list(constraints_data.get("exclusions") or []),
        ),
        open_questions=list(data.get("open_questions_the_text_leaves_genuinely_unresolved") or []),
    )


def parse_intake_decision(data: Dict[str, Any]) -> IntakeDecision:
    issues = [
        IntakeIssue(
            issue=item.get("issue", ""),
            decision=item.get("decision", "ignore"),
            reasoning=item.get("reasoning"),
            question=item.get("question"),
            options=list(item.get("options") or []),
            consequence_if_answer_a=item.get("consequence_if_answer_a"),
            consequence_if_answer_b=item.get("consequence_if_answer_b"),
            insight_text=item.get("insight_text"),
        )
        for item in (data.get("issues") or [])
        # Occasionally the model returns a malformed entry (e.g. a plain
        # string instead of an object) — skip it rather than fail the whole
        # intake turn; the recruiter still sees whatever else came back.
        if isinstance(item, dict)
    ]
    final_data = data.get("final_search_intent") or {}
    final_intent = FinalSearchIntentDraft(
        hard_requirements=list(final_data.get("hard_requirements") or []),
        strong_signals=list(final_data.get("strong_signals") or []),
        preferred_differentiators=list(final_data.get("preferred_differentiators") or []),
        natural_language_search_query=final_data.get("natural_language_search_query"),
        exclusions=list(final_data.get("exclusions") or []),
    )
    return IntakeDecision(
        issues=issues,
        recommended_ask_count=data.get("recommended_ask_count", sum(1 for i in issues if i.decision == "ask")),
        stop_reasoning=data.get("stop_reasoning"),
        warnings=list(data.get("warnings") or []),
        search_consequence_summary=data.get("search_consequence_summary"),
        final_search_intent=final_intent,
    )


class IntakeReasoner:
    """Orchestrates the two-task intake reasoning pipeline (Task A: Role
    Understanding, Task B: Intake Decision) plus the deterministic
    contradiction backstop. Additive — does not touch JDParser, SearchPlanner,
    or any existing search-pipeline component. `client` is injectable for
    tests, mirroring OpenAIProvider's constructor pattern."""

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        self._client = client

    def run(self, raw_input: str) -> IntakeResult:
        api_key = get_openai_api_key()
        if not api_key:
            raise ConfigurationError("The language model configuration is unavailable.")
        client = self._client or OpenAI(api_key=api_key)

        task_a_raw = self._call_json(
            client,
            self._load_prompt("intake_task_a_understanding.txt"),
            f"Raw hiring input:\n{raw_input}\n\nReturn the JSON now.",
        )
        role_understanding = parse_role_understanding(task_a_raw)

        task_b_template = self._load_prompt("intake_task_b_decision.txt")
        task_b_prompt = task_b_template.replace(
            "{role_understanding_json}", json.dumps(role_understanding_to_dict(role_understanding))
        ).replace("{raw_input}", raw_input)
        task_b_raw = self._call_json(
            client,
            "Follow the instructions in the user message exactly and return only the JSON they specify.",
            task_b_prompt,
        )
        decision = parse_intake_decision(task_b_raw)

        decision, contradictions = apply_intake_backstops(
            raw_input, bool(role_understanding.explicit_constraints.locations), decision
        )
        status = "needs_clarification" if any(issue.decision == "ask" for issue in decision.issues) else "ready"

        return IntakeResult(
            raw_input=raw_input,
            role_understanding=role_understanding,
            decision=decision,
            contradictions=contradictions,
            status=status,
        )

    def _load_prompt(self, filename: str) -> str:
        return (PROMPTS_DIR / filename).read_text(encoding="utf-8")

    def _call_json(self, client: OpenAI, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={"format": {"type": "json_object"}},
        )
        content = getattr(response, "output_text", None)
        if not content:
            raise ParsingError("The intake reasoning response could not be read.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParsingError("The intake reasoning response was not valid JSON.") from exc
