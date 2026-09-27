"""Did the recruiter change something that can materially affect retrieval?

Compares two confirmed search intents (the stored snapshots, as JSON). A change is meaningful when it alters an input
the search or the evidence check actually uses. Wording is not: case, spacing and punctuation are ignored, and the
order of set-like lists does not matter. The model-written search sentence is ignored (it is not what is searched on
while RECRUITERAI_SEND_CONFIRMED_SEARCH_SENTENCE is off, and rewording it is not a decision).

Returns the names of what changed, so the role can record it. A typo fix in a requirement reads as a different
requirement and counts as meaningful; that is the conservative direction (one more retrieval, never a missed one).
"""

import re
from typing import Any, Dict, List

_PUNCT = re.compile(r"[^a-z0-9+#.]+")


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return _PUNCT.sub(" ", value.lower()).strip(" .")
    return value


def _set(values: Any) -> List[str]:
    return sorted({_norm(v) for v in (values or []) if isinstance(v, str) and _norm(v)})


def _projection(intent: Dict[str, Any]) -> Dict[str, Any]:
    role = intent.get("role") or {}
    location = intent.get("location") or {}
    experience = intent.get("experience") or {}
    titles = intent.get("titles") or {}
    skills = intent.get("skills") or {}
    company = intent.get("company_preferences") or {}
    background = intent.get("previous_background") or {}
    return {
        "role": {"title": _norm(role.get("title")), "seniority": _norm(role.get("seniority")), "employment_type": _norm(role.get("employment_type"))},
        "location": {
            "countries": _set(location.get("countries")),
            "states": _set(location.get("states")),
            "cities": _set(location.get("cities")),
            "radius_miles": location.get("radius_miles"),
            "radius_place": _norm(location.get("radius_place")),
            "work_mode": _norm(location.get("work_mode")),
        },
        "experience": {"minimum": experience.get("minimum_years"), "maximum": experience.get("maximum_years")},
        "titles": {"include": _set(titles.get("include_titles")), "exclude": _set(titles.get("exclude_titles"))},
        "skills": {"required": _set(skills.get("required_skills")), "preferred": _set(skills.get("preferred_skills"))},
        "companies": {
            "exclude": _set(company.get("exclude_current_companies")),
            "types": _set(company.get("preferred_company_types")),
            "preferred": _set(background.get("preferred_companies")),
        },
        # Core / Supporting / Preferred membership: moving a requirement between tiers changes it.
        "core": _set(intent.get("core_signals")),
        "supporting": _set(intent.get("supporting_signals")),
        "preferred": _set(intent.get("differentiator_signals")),
    }


LABELS = {
    "role": "role or level",
    "location": "location or work mode",
    "experience": "experience",
    "titles": "title family",
    "skills": "skills",
    "companies": "company preferences or exclusions",
    "core": "core requirements",
    "supporting": "supporting requirements",
    "preferred": "preferred requirements",
}


def meaningful_changes(old_intent: Dict[str, Any], new_intent: Dict[str, Any]) -> List[str]:
    """Empty when nothing that affects retrieval changed."""
    before, after = _projection(old_intent or {}), _projection(new_intent or {})
    return [LABELS[key] for key in before if before[key] != after[key]]
