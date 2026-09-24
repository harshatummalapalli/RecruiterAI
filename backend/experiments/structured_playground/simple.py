"""Recruiter-level layer over the Structured Search Playground.

Nothing new is invented here: every friendly filter maps onto ONE field and the operators the advanced builder and
the catalog already know. The recruiter thinks in "include / exclude", "any of / all of" and parentheses; this module
turns that into the same tree the advanced builder validates and runs. Values stay exactly as typed.

Simple state (what the recruiter page sends):
    {"combine": "and" | "or",                       # must match ALL / ANY of the top-level items
     "items": [ filter-item | group-item, ... ]}
    group-item  : {"type": "group", "combine": "and" | "or", "items": [filter-item, ...]}
    filter-item : {"type": "filter", "filter": <id>, "mode": "include" | "exclude",
                   "values": [text, ...],           # verbatim
                   "match": "any" | "all",          # several values: OR / AND   (text filters)
                   "phrase": bool,                  # text filters: exact phrase instead of words in any order
                   "min": "5", "max": "12",         # years filter
                   "place": str, "distance": n, "unit": "mi"|"km"}   # distance filter
"""

from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.structured_playground.catalog import BY_NAME, CLOSED_SETS

CURRENT = "experience.employment_details.current."
PAST = "experience.employment_details.past."
ANY_ROLE = "experience.employment_details."

# kind: text (words / phrase), list (exact stored value, in / not_in), choice (pick from a closed list),
#       years (at least / at most), distance (within N of a place)
FILTERS: List[Dict[str, Any]] = [
    {"id": "job_title", "label": "Current job title", "group": "Job", "field": CURRENT + "title", "kind": "text", "placeholder": "e.g. Backend Engineer", "help": "Matches the title they hold now."},
    {"id": "past_job_title", "label": "Past job title", "group": "Job", "field": PAST + "title", "kind": "text", "placeholder": "e.g. Platform Engineer", "help": "A title they held before their current job."},
    {"id": "any_job_title", "label": "Any job title (now or before)", "group": "Job", "field": ANY_ROLE + "title", "kind": "text", "placeholder": "e.g. Engineering Manager", "help": "Matches any role in their history."},
    {"id": "role_keywords", "label": "Keywords in current role description", "group": "Job", "field": CURRENT + "description", "kind": "text", "placeholder": "e.g. Kubernetes", "help": "Words in the description of their current role."},
    {"id": "any_role_keywords", "label": "Keywords in any role description", "group": "Job", "field": ANY_ROLE + "description", "kind": "text", "placeholder": "e.g. payments", "help": "Words in the description of any role they held."},
    {"id": "headline", "label": "Profile headline", "group": "Job", "field": "basic_profile.headline", "kind": "text", "placeholder": "e.g. Data Engineer", "help": "The line under their name."},
    {"id": "seniority", "label": "Seniority level", "group": "Job", "field": CURRENT + "seniority_level", "kind": "choice", "options": CLOSED_SETS["seniority_level"], "help": "CrustData's own seniority labels for their current role."},
    {"id": "function", "label": "Job function", "group": "Job", "field": CURRENT + "function_category", "kind": "choice", "options": CLOSED_SETS["function_category"], "help": "CrustData's function label for their current role."},
    {"id": "years", "label": "Years of experience", "group": "Job", "field": "years_of_experience_raw", "kind": "years", "help": "Total years across all roles."},
    {"id": "skills", "label": "Skills", "group": "Job", "field": "skills.professional_network_skills", "kind": "text", "placeholder": "e.g. Python", "help": "Skills listed on the profile."},
    {"id": "company", "label": "Current company", "group": "Company", "field": CURRENT + "company_name", "kind": "list", "placeholder": "e.g. Shopify", "help": "Type the company name exactly as CrustData stores it."},
    {"id": "past_company", "label": "Past company", "group": "Company", "field": PAST + "company_name", "kind": "list", "placeholder": "e.g. Google", "help": "A company they worked at before."},
    {"id": "ever_company", "label": "Ever worked at", "group": "Company", "field": ANY_ROLE + "company_name", "kind": "list", "placeholder": "e.g. Stripe", "help": "Any company in their history."},
    {"id": "industry", "label": "Current company industry", "group": "Company", "field": CURRENT + "company_professional_network_industry", "kind": "text", "placeholder": "e.g. Software Development", "help": "The industry label of their current employer."},
    {"id": "company_size", "label": "Current company size", "group": "Company", "field": CURRENT + "company_headcount_range", "kind": "choice", "options": CLOSED_SETS["company_headcount_range"], "help": "Employee-count band of their current employer."},
    {"id": "country", "label": "Country", "group": "Location", "field": "basic_profile.location.country", "kind": "list", "placeholder": "e.g. Canada", "help": "Full country name, e.g. United States."},
    {"id": "state", "label": "Province / State", "group": "Location", "field": "basic_profile.location.state", "kind": "list", "placeholder": "e.g. Ontario", "help": "Full name, e.g. California."},
    {"id": "city", "label": "City", "group": "Location", "field": "basic_profile.location.city", "kind": "list", "placeholder": "e.g. Toronto", "help": "City as it appears on the profile."},
    {"id": "distance", "label": "Within a distance of a place", "group": "Location", "field": "basic_profile.location", "kind": "distance", "help": "Type a place name, not a ZIP code (ZIP is not supported)."},
    {"id": "school", "label": "School", "group": "Education", "field": "education.schools.school", "kind": "text", "placeholder": "e.g. University of Toronto", "help": "Any school they attended."},
    {"id": "degree", "label": "Degree", "group": "Education", "field": "education.schools.degree", "kind": "text", "placeholder": "e.g. Master", "help": "Degree name."},
    {"id": "field_of_study", "label": "Field of study", "group": "Education", "field": "education.schools.field_of_study", "kind": "text", "placeholder": "e.g. Computer Science", "help": "Field of study."},
    {"id": "name", "label": "Name", "group": "Person", "field": "basic_profile.name", "kind": "text", "placeholder": "e.g. Jane Doe", "help": "Full name."},
]
BY_ID = {f["id"]: f for f in FILTERS}

STATUS_WORDS = {"verified": "Tested", "documented_unverified": "Not tested yet", "unavailable": "Not available"}


def filters_payload() -> List[Dict[str, Any]]:
    out = []
    for spec in FILTERS:
        entry = BY_NAME[spec["field"]]
        out.append({**spec, "status": entry["verified_in_our_account"], "status_word": STATUS_WORDS[entry["verified_in_our_account"]], "status_note": entry["notes"]})
    return out


def _values(item: Dict[str, Any]) -> List[str]:
    return [v for v in (item.get("values") or []) if isinstance(v, str) and v != ""]


def _cond(field: str, operator: str, values: Optional[List[str]] = None, **extra: Any) -> Dict[str, Any]:
    return {"type": "condition", "field": field, "operator": operator, "values": values or [], **extra}


def _group(op: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "group", "op": op, "children": children}


def _label(spec: Dict[str, Any]) -> str:
    return spec["label"]


def _filter_node(item: Dict[str, Any], problems: List[str]) -> Optional[Dict[str, Any]]:
    spec = BY_ID.get(item.get("filter", ""))
    if spec is None:
        problems.append(f"Unknown filter '{item.get('filter')}'.")
        return None
    exclude = item.get("mode") == "exclude"
    kind, field = spec["kind"], spec["field"]
    if kind == "years":
        parts = []
        for key, op in (("min", "=>"), ("max", "=<")):
            raw = str(item.get(key) or "").strip()
            if raw:
                parts.append(_cond(field, op, [raw]))
        if not parts:
            problems.append(f"{_label(spec)}: enter a minimum and/or a maximum number of years.")
            return None
        return parts[0] if len(parts) == 1 else _group("and", parts)
    if kind == "distance":
        place, distance = str(item.get("place") or "").strip(), item.get("distance")
        if not place or not str(distance or "").strip():
            problems.append(f"{_label(spec)}: enter a place and a distance.")
            return None
        return _cond(field, "geo_exclude" if exclude else "geo_distance", geo={"location": place, "distance": distance, "unit": item.get("unit") or "mi"})
    values = _values(item)
    if not values:
        problems.append(f"{_label(spec)}: add at least one value.")
        return None
    if kind in ("list", "choice"):
        return _cond(field, "not_in" if exclude else "in", values)
    # text
    if exclude:
        return _cond(field, "(!)", values, combine="and")          # NOT a AND NOT b  ==  NOT (a OR b)
    operator = "[.]" if item.get("phrase") else "(.)"
    return _cond(field, operator, values, combine="and" if item.get("match") == "all" else "or")


def _items(items: List[Dict[str, Any]], problems: List[str]) -> List[Dict[str, Any]]:
    nodes = []
    for item in items:
        if item.get("type") == "group":
            children = _items(item.get("items") or [], problems)
            if not (item.get("items") or []):
                problems.append("A group is empty: add a filter to it or remove it.")
            elif children:
                nodes.append(_group("or" if item.get("combine") == "or" else "and", children))
        else:
            node = _filter_node(item, problems)
            if node is not None:
                nodes.append(node)
    return nodes


def to_tree(state: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Simple state -> advanced builder tree, plus recruiter-language problems."""
    problems: List[str] = []
    items = state.get("items") or []
    if not items:
        return None, ["Add at least one filter to start."]
    nodes = _items(items, problems)
    if problems or not nodes:
        return None, problems or ["Add at least one filter to start."]
    return _group("or" if state.get("combine") == "or" else "and", nodes), []


# --- the search read back in recruiter notation ---------------------------------------------------------------------------
def _q(value: str) -> str:
    return '"' + value + '"'


def _filter_text(item: Dict[str, Any]) -> str:
    spec = BY_ID.get(item.get("filter", ""))
    if spec is None:
        return ""
    exclude = item.get("mode") == "exclude"
    kind = spec["kind"]
    if kind == "years":
        bits = []
        if str(item.get("min") or "").strip():
            bits.append(f"at least {str(item['min']).strip()}")
        if str(item.get("max") or "").strip():
            bits.append(f"at most {str(item['max']).strip()}")
        return f"{spec['label']}: " + " and ".join(bits)
    if kind == "distance":
        return f"{'NOT ' if exclude else ''}{spec['label']}: {item.get('distance')} {item.get('unit') or 'mi'} of {_q(str(item.get('place') or ''))}"
    values = [_q(v) for v in _values(item)]
    if kind == "text" and not exclude and item.get("match") == "all":
        joiner = " AND "
    else:
        joiner = " OR "
    body = "(" + joiner.join(values) + ")" if len(values) > 1 else (values[0] if values else "")
    if exclude:
        return f"{spec['label']}: NOT {body}"
    return f"{spec['label']}: {body}"


def to_text(state: Dict[str, Any], indent: int = 0) -> str:
    """e.g.  Current job title: ("A" OR "B")  AND  City: "Toronto"  AND  ( ... OR ... )"""
    joiner = "\n" + "  " * indent + ("OR" if state.get("combine") == "or" else "AND") + "\n"
    parts = []
    for item in state.get("items") or []:
        if item.get("type") == "group":
            inner = to_text(item, indent + 1)
            parts.append("  " * indent + "(\n" + inner + "\n" + "  " * indent + ")")
        else:
            text = _filter_text(item)
            if text:
                parts.append("  " * indent + text)
    return joiner.join(parts)
