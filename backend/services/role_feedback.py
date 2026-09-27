"""Recruiter decision feedback, and the small, transparent way it guides the NEXT retrieval.

The confirmed hiring intent is the recruiter's explicit hiring decision. Feedback never rewrites it. Feedback is stored
as it was given, and a deterministic guidance is derived from it that does exactly two things, both conservative:

  1. Admission tie-break (next retrieval cycles only). Among retrieved candidates whose baseline scores are EXACTLY
     equal, the ones showing more of what the recruiter said was missing are admitted first. The baseline score,
     the ranking formula and the 50 -> 25 cut are unchanged; this only decides ties, which are common (a large share
     of a retrieved set can tie at the cutoff, see the Release 1.1 audit).
  2. Order of the next batch shown from candidates already read. Within an evidence level, candidates showing more
     of what was said to be missing come first. The evidence level itself is unchanged.

Only structured reasons are used. They map to four dimensions the evidence already measures:

  experience  <- "Required experience" (reject), "Relevant experience isn't clear" (maybe)
  technology  <- "Required technology" (reject), "Required skill isn't demonstrated" (maybe)
  seniority   <- "Seniority" (reject), "Seniority is unclear" (maybe)
  work_type   <- "Relevant type of work" (reject), "Type of work doesn't quite fit" (maybe)

"Domain/industry", "Career background" and "Other", and every free-text note, are stored for learning and are NOT
translated into guidance: nothing here can honestly measure them. When no reason can be translated the guidance is
empty and the search continues exactly as confirmed. There is no learned preference model and no free-text
interpretation.
"""

from typing import Any, Callable, Dict, List, Optional

from backend.services.role_lifecycle import effective_feedback_events

MAYBE_REASONS = {
    "experience_unclear": "Relevant experience isn't clear",
    "skill_not_demonstrated": "Required skill isn't demonstrated",
    "seniority_unclear": "Seniority is unclear",
    "type_of_work": "Type of work doesn't quite fit",
    "other": "Other",
}
REJECT_REASONS = {
    "required_experience": "Required experience",
    "required_technology": "Required technology",
    "type_of_work": "Relevant type of work",
    "seniority": "Seniority",
    "domain": "Domain/industry",
    "career_background": "Career background",
    "other": "Other",
}

REASON_DIMENSION = {
    "experience_unclear": "experience",
    "required_experience": "experience",
    "skill_not_demonstrated": "technology",
    "required_technology": "technology",
    "seniority_unclear": "seniority",
    "seniority": "seniority",
    "type_of_work": "work_type",
}

DIMENSIONS = ("experience", "technology", "seniority", "work_type")
MAX_NOTE_CHARS = 500


def valid_reason(decision: str, reason: str) -> bool:
    if decision == "maybe":
        return reason in MAYBE_REASONS
    if decision == "reject":
        return reason in REJECT_REASONS
    return False


def clean_note(note: Optional[str]) -> Optional[str]:
    text = " ".join((note or "").split())
    return text[:MAX_NOTE_CHARS] if text else None


class Guidance:
    """dimension -> how many (still current) decisions gave that reason. Empty means "no guidance"."""

    def __init__(self, dimensions: Optional[Dict[str, int]] = None, untranslated: int = 0) -> None:
        self.dimensions = {key: value for key, value in (dimensions or {}).items() if value > 0}
        self.untranslated = untranslated

    @property
    def empty(self) -> bool:
        return not self.dimensions

    def weights(self) -> Dict[str, float]:
        total = sum(self.dimensions.values())
        return {key: value / total for key, value in self.dimensions.items()} if total else {}

    def to_dict(self) -> Dict[str, Any]:
        return {"dimensions": dict(self.dimensions), "untranslated": self.untranslated}


def build_guidance(record: Dict[str, Any]) -> Guidance:
    """From the decisions that are still current. A dimension the recruiter removed when correcting the calibration
    summary is left out."""
    dismissed = set(((record.get("calibration") or {}).get("dismissed") or []))
    dimensions: Dict[str, int] = {}
    untranslated = 0
    for event in effective_feedback_events(record):
        reason = event.get("feedback_reason")
        if event.get("decision") not in ("maybe", "reject") or not reason:
            continue
        dimension = REASON_DIMENSION.get(reason)
        if dimension is None:
            untranslated += 1
        elif dimension not in dismissed:
            dimensions[dimension] = dimensions.get(dimension, 0) + 1
    return Guidance(dimensions, untranslated)


def evidence_value(dimension: str, evidence: Optional[Dict[str, Any]]) -> float:
    """How much a candidate's stored evidence shows on one dimension, from -1 to a few. Facts only: the same
    verdicts, level fit and experience arithmetic the workspace already shows."""
    evidence = evidence or {}
    alignment = evidence.get("role_alignment") or {}
    if dimension == "technology":
        judgments = evidence.get("requirement_judgments") or []
        weights = {"core": 1.0, "supporting": 0.6}
        return sum(weights[j["tier"]] for j in judgments if j.get("tier") in weights and j.get("verdict") == "met" and (j.get("source") or "").lower() != "career dates")
    if dimension == "experience":
        floor = alignment.get("experience_floor")
        return 1.0 if floor is True else -1.0 if floor is False else 0.0
    if dimension == "seniority":
        fit = alignment.get("level_fit")
        return 1.0 if fit == "aligned" else -1.0 if fit in ("above", "below") else 0.0
    if dimension == "work_type":
        return {"direct": 1.0, "adjacent": 0.5, "tangential": -1.0}.get(alignment.get("title_relevance"), 0.0)
    return 0.0


def evidence_guidance_score(guidance: Guidance) -> Callable[[Optional[Dict[str, Any]]], float]:
    weights = guidance.weights()

    def score(evidence: Optional[Dict[str, Any]]) -> float:
        return sum(weight * evidence_value(dimension, evidence) for dimension, weight in weights.items())

    return score


def apply_admission_tie_break(ranked: List[Any], guidance: Guidance, value_of: Callable[[Any, str], float]) -> List[Any]:
    """Re-orders ONLY candidates with exactly equal baseline scores; everyone else keeps their place. `value_of`
    reads a candidate's baseline evidence on one dimension. A no-op when the guidance is empty."""
    if guidance.empty or len(ranked) < 2:
        return list(ranked)
    weights = guidance.weights()

    def preference(candidate: Any) -> float:
        return sum(weight * value_of(candidate, dimension) for dimension, weight in weights.items())

    result: List[Any] = []
    index = 0
    while index < len(ranked):
        end = index + 1
        score = round(ranked[index].final_score or 0.0, 9)
        while end < len(ranked) and round(ranked[end].final_score or 0.0, 9) == score:
            end += 1
        block = ranked[index:end]
        result.extend(sorted(block, key=lambda candidate: -preference(candidate)) if len(block) > 1 else block)
        index = end
    return result


# ---- one-time calibration summary --------------------------------------------------------------------------------

DIMENSION_PHRASE = {
    "experience": "clearer relevant experience",
    "technology": "stronger evidence of the required technology",
    "seniority": "profiles closer to the level of this role",
    "work_type": "a closer fit to the type of work",
}


def _missing_core_requirements(record: Dict[str, Any], dimension_reasons: Dict[str, str]) -> List[str]:
    """The core requirements that most often were NOT shown on the profiles the recruiter marked as missing a
    technology. Read from the stored evidence, so the summary names things the recruiter can check."""
    response = record.get("response") or {}
    candidates = response.get("candidates") or []
    evidence = response.get("evidence") or []
    index_of = {c.get("candidate_id"): i for i, c in enumerate(candidates)}
    tally: Dict[str, int] = {}
    for event in effective_feedback_events(record):
        if REASON_DIMENSION.get(event.get("feedback_reason")) != "technology":
            continue
        i = index_of.get(event.get("candidate_id"))
        if i is None or i >= len(evidence):
            continue
        for judgment in (evidence[i] or {}).get("requirement_judgments") or []:
            if judgment.get("tier") == "core" and judgment.get("verdict") != "met" and (judgment.get("source") or "").lower() != "career dates":
                text = (judgment.get("signal_text") or "").strip().rstrip(".")
                if len(text) > 60:
                    text = text[:60].rsplit(" ", 1)[0].rstrip(",;:") + "…"
                if text:
                    tally[text] = tally.get(text, 0) + 1
    return [text for text, _ in sorted(tally.items(), key=lambda item: (-item[1], item[0]))[:2]]


def calibration_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """The one-time "Got it" line. Deterministic, built only from the structured reasons and stored evidence. It
    names only what the search can act on."""
    guidance = build_guidance(record)
    if guidance.empty:
        return {"text": "Got it. I'll keep searching against your brief.", "dimensions": [], "requirements": []}
    ordered = [key for key, _ in sorted(guidance.dimensions.items(), key=lambda item: (-item[1], DIMENSIONS.index(item[0])))]
    missing = _missing_core_requirements(record, {}) if "technology" in guidance.dimensions else []
    phrases: List[str] = []
    for key in ordered[:3]:
        if key == "technology" and missing:
            phrases.append("stronger evidence of " + " and ".join(missing))
        else:
            phrases.append(DIMENSION_PHRASE[key])
    text = "Got it. I'll look for " + (phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " and " + phrases[-1]) + "."
    return {"text": text, "dimensions": ordered, "requirements": missing}
