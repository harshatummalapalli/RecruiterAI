"""Query builder for the Structured Search Playground.

The ONLY intelligence here is Boolean grouping and the syntax CrustData requires. Values are used exactly as
entered: no synonyms, no spelling correction, no trimming, no case changes, no title expansion, no LLM. The only
transformation is the type coercion the provider syntax strictly needs (a number field gets a JSON number, a
boolean field a JSON boolean, an `in` list a JSON array).

Tree model (what the UI sends):
    {"type": "group", "op": "and" | "or" | "all_of", "children": [node, ...]}
    {"type": "condition", "field": <provider path>, "operator": <op>,
     "values": [<text>, ...],          # one entry per value, verbatim
     "combine": "or" | "and" | "all_of",   # how several values of a scalar operator are joined (default "or")
     "geo": {"location": str, "lat_lng": [lat, lng], "distance": n, "unit": str}}   # geo operators only

Output: the exact `filters` object CrustData receives, a readable Boolean rendering, and validation messages
(errors block a run; warnings and notes never change the query)."""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.structured_playground.catalog import (
    BY_NAME,
    GROUP_OPS,
    NEGATIVE_OPERATORS,
    OPERATORS,
    STATUS_UNAVAILABLE,
    STATUS_UNVERIFIED,
    nested_array_path,
)

_BOOLEAN_IN_VALUE = re.compile(r'"\s*(OR|AND)\s*"|\)\s+(OR|AND)\s+\(')


class Issues:
    def __init__(self) -> None:
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []
        self.notes: List[Dict[str, str]] = []

    def error(self, path: str, message: str) -> None:
        self.errors.append({"path": path, "message": message})

    def warn(self, path: str, message: str) -> None:
        self.warnings.append({"path": path, "message": message})

    def note(self, path: str, message: str) -> None:
        self.notes.append({"path": path, "message": message})

    def as_dict(self) -> Dict[str, Any]:
        return {"errors": self.errors, "warnings": self.warnings, "notes": self.notes}


def _coerce(raw: Any, value_type: str, path: str, issues: Issues) -> Any:
    """Verbatim, except for the JSON type the field requires."""
    if not isinstance(raw, str):
        return raw
    if value_type in ("integer", "number"):
        try:
            number = float(raw)
        except ValueError:
            issues.error(path, f"'{raw}' is not a number, and this field takes a number.")
            return raw
        return int(number) if number.is_integer() and "." not in raw else number
    if value_type == "boolean":
        if raw.strip().lower() in ("true", "false"):
            return raw.strip().lower() == "true"
        issues.error(path, f"'{raw}' is not true/false; boolean fields accept only true or false.")
        return raw
    return raw


def _check_text(raw: Any, path: str, issues: Issues) -> None:
    if not isinstance(raw, str):
        return
    if raw != raw.strip():
        issues.warn(path, f"The value {json.dumps(raw)} has leading/trailing whitespace. It is sent exactly as entered; CrustData rejects such values on closed-set fields.")
    if _BOOLEAN_IN_VALUE.search(raw):
        issues.warn(path, "This value contains a quoted Boolean (\"x\" OR \"y\"). CrustData matches values literally and answers 400; put each term in its own value and choose OR instead.")


def _leaf(field: str, operator: str, value: Any) -> Dict[str, Any]:
    return {"field": field, "type": operator, "value": value}


def _condition(node: Dict[str, Any], path: str, issues: Issues, in_all_of: bool) -> Optional[Dict[str, Any]]:
    field, operator = node.get("field"), node.get("operator")
    entry = BY_NAME.get(field or "")
    if entry is None:
        issues.error(path, f"'{field}' is not a documented In-Database People Search filter field.")
        return None
    if operator not in OPERATORS:
        issues.error(path, f"'{operator}' is not a CrustData filter operator.")
        return None
    if operator not in entry["supported_operators"]:
        issues.error(path, f"Operator {operator} is not offered for {field} ({entry['value_type']}). Offered: {', '.join(entry['supported_operators'])}.")
        return None
    status = entry["verified_in_our_account"]
    if status == STATUS_UNAVAILABLE:
        issues.warn(path, f"{field} is marked UNAVAILABLE for our account: {entry['notes']} The query is built as entered.")
    elif status == STATUS_UNVERIFIED:
        issues.note(path, f"{field} is documented by CrustData but not yet verified in our account.")
    elif operator not in entry["verified_operators"] and entry["verified_operators"]:
        issues.note(path, f"{field} is verified in our account, but not with operator {operator} (verified: {', '.join(entry['verified_operators'])}).")
    if entry["response_gated"]:
        issues.note(path, f"{field} is a plan-gated response field on our account; you can filter on it but it cannot be shown in results.")

    shape = OPERATORS[operator]["shape"]
    if in_all_of and operator in NEGATIVE_OPERATORS:
        issues.error(path, f"Operator {operator} is a negation and is not allowed inside an all_of group. Apply negation outside the group.")
        return None
    values = node.get("values") or []
    closed = entry["allowed_values"]

    def closed_check(v: Any) -> None:
        if closed and isinstance(v, str) and v not in closed:
            same_case = [c for c in closed if c.lower() == v.lower()]
            if same_case and operator in ("=", "!="):
                return
            issues.warn(path, f"{json.dumps(v)} is not in the closed value set for {field}: {', '.join(closed)}. CrustData answers 400 for such values; the value is sent unchanged.")

    if shape == "null":
        return _leaf(field, operator, None)
    if shape == "geo":
        geo = node.get("geo") or {}
        value: Dict[str, Any] = {}
        if geo.get("lat_lng"):
            value["lat_lng"] = geo["lat_lng"]
        if geo.get("location"):
            value["location"] = geo["location"]
        if not value:
            issues.error(path, f"{operator} needs a location (a place name) or lat_lng coordinates.")
            return None
        try:
            distance = float(geo.get("distance"))
        except (TypeError, ValueError):
            distance = 0
        if distance <= 0:
            issues.error(path, f"{operator} needs a positive distance.")
            return None
        value["distance"] = int(distance) if distance.is_integer() else distance
        if geo.get("unit"):
            value["unit"] = geo["unit"]
        return _leaf(field, operator, value)
    if not values:
        issues.error(path, "This condition has no value.")
        return None
    for v in values:
        _check_text(v, path, issues)
        closed_check(v)
    if shape == "array":
        if operator == "has_all" and in_all_of:
            issues.error(path, "has_all cannot be used inside an all_of group; list the values as separate = conditions instead.")
            return None
        return _leaf(field, operator, [_coerce(v, entry["value_type"], path, issues) for v in values])
    # scalar operator: one leaf per value, joined by the chosen combine (OR by default)
    leaves = [_leaf(field, operator, _coerce(v, entry["value_type"], path, issues)) for v in values]
    if len(leaves) == 1:
        return leaves[0]
    combine = node.get("combine") or "or"
    if combine not in GROUP_OPS:
        issues.error(path, f"'{combine}' is not a group operator.")
        return None
    if combine == "all_of":
        if not nested_array_path(field):
            issues.error(path, f"all_of applies only to nested-array fields (employment, education, certifications, honors); {field} is not one.")
            return None
        if operator in NEGATIVE_OPERATORS:
            issues.error(path, f"all_of accepts only positive operators; {operator} is a negation.")
            return None
    return {"op": combine, "conditions": leaves}


def _array_paths(node: Any) -> List[str]:
    """Every nested-array path used by the conditions beneath `node` ('' for a scalar field)."""
    if node.get("type") == "condition":
        return [nested_array_path(node.get("field") or "") or ""]
    out: List[str] = []
    for child in node.get("children", []):
        out += _array_paths(child)
    return out


def _group(node: Dict[str, Any], path: str, issues: Issues, in_all_of: bool) -> Optional[Dict[str, Any]]:
    op = node.get("op")
    if op not in GROUP_OPS:
        issues.error(path, f"'{op}' is not a group operator (and, or, all_of).")
        return None
    children = node.get("children") or []
    if not children:
        issues.error(path, "This group is empty; CrustData rejects an empty conditions list.")
        return None
    if op == "all_of":
        if in_all_of:
            issues.error(path, "An all_of group cannot be nested inside another all_of group.")
            return None
        paths = set(_array_paths(node))
        if "" in paths:
            issues.error(path, "all_of applies only to nested-array fields (employment, education, certifications, honors); this group contains a scalar field.")
            return None
        families = {p.split(".")[0] for p in paths}
        if len(families) > 1:
            issues.error(path, "All fields inside one all_of group must sit on the same nested-array path; this mixes " + ", ".join(sorted(paths)) + ". Split it into separate all_of groups.")
            return None
        if len(paths) > 1:
            issues.warn(path, "This all_of mixes " + " and ".join(sorted(paths)) + ". CrustData resolves one nested-array path per all_of; it may reject this.")
    if op == "and":
        nested = [p for p in _array_paths(node) if p]
        for candidate in set(nested):
            if nested.count(candidate) > 1:
                issues.note(path, f"Several conditions on {candidate} inside an `and` group must all match the SAME entry (one role, one school). Use all_of to allow different entries.")
                break
    conditions: List[Dict[str, Any]] = []
    for index, child in enumerate(children):
        built = _node(child, f"{path}.{index}", issues, in_all_of or op == "all_of")
        if built is not None:
            conditions.append(built)
    if len(conditions) != len(children):
        return None
    return {"op": op, "conditions": conditions}


def _node(node: Dict[str, Any], path: str, issues: Issues, in_all_of: bool = False) -> Optional[Dict[str, Any]]:
    kind = node.get("type")
    if kind == "group":
        return _group(node, path, issues, in_all_of)
    if kind == "condition":
        return _condition(node, path, issues, in_all_of)
    issues.error(path, f"Unknown node type '{kind}'.")
    return None


# --- Boolean rendering -------------------------------------------------------------------------------------------------
def _fmt_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def render(filters: Dict[str, Any], indent: int = 0) -> str:
    """Readable Boolean form; every group is parenthesised and its members are separated by the group operator."""
    pad = "  " * indent
    if "op" in filters:
        joiner = {"and": "AND", "or": "OR", "all_of": "ALL OF"}[filters["op"]]
        lines = [f"{pad}("]
        for i, child in enumerate(filters["conditions"]):
            if i:
                lines.append(f"{pad}  {joiner}")
            lines.append(render(child, indent + 1))
        lines.append(f"{pad})")
        return chr(10).join(lines)
    if filters["type"] in ("is_null", "is_not_null"):
        return f"{pad}{filters['field']} {filters['type']}"
    return f"{pad}{filters['field']} {filters['type']} {_fmt_value(filters['value'])}"


def build(tree: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and build. `filters` is None when there are errors."""
    issues = Issues()
    built = _node(tree, "0", issues) if tree else None
    if not tree:
        issues.error("0", "The query is empty.")
    ok = built is not None and not issues.errors
    return {
        "ok": ok,
        "filters": built if ok else None,
        "boolean_text": render(built) if ok else "",
        **issues.as_dict(),
    }
