"""Gold-assertion evaluator for the Role 1 intake-strategy experiment (EXPERIMENT ONLY).

Deterministic and applied AFTER extraction. The recruiter-established ground truth lives here and is never put in an
LLM prompt. Each critical assertion is reported as PASS / PARTIAL / FAIL (or UNEVALUATED), never rolled into one score,
and every non-PASS carries exactly one primary failure class:

    EXTRACTION       the model missed something the representation could express
    REPRESENTATION   the schema cannot express the concept without flattening it
    VALIDATION       the concept is present but its support cannot be established
    RECONCILIATION   JD and recruiter brief were not merged / prioritised correctly
    COMPILER         the representation is right but the compiler would translate it wrongly
    TAXONOMY         the representation is right but approved knowledge is insufficient

Representability is decided from the schema itself (field introspection), not from whether the prompt happened to
succeed, so "the prompt failed" is never mislabelled a representation failure.

This module evaluates the CURRENT StructuredHiringIntent shape. A concept the schema does support but that has no
adapter here is reported UNEVALUATED rather than guessed.
"""

from __future__ import annotations

import re
import typing
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from backend.models.structured_intent import RoleArchetype, StructuredHiringIntent

PASS, PARTIAL, FAIL, UNEVALUATED = "PASS", "PARTIAL", "FAIL", "UNEVALUATED"
EXTRACTION, REPRESENTATION, VALIDATION, RECONCILIATION, COMPILER, TAXONOMY = (
    "EXTRACTION", "REPRESENTATION", "VALIDATION", "RECONCILIATION", "COMPILER", "TAXONOMY",
)

# Security-OPERATIONS vocabulary. A positive requirement/preference built on these contradicts the recruiter's
# "not SOC / not security operations" even when the JD itself says them (the JD lists "security monitoring").
HARD_SECOPS = re.compile(
    r"\b(soc|security operations?|security monitoring|siem|threat (detection|hunting|intelligence)|"
    r"security incident response|incident response|security analyst|cyber ?security operations?)\b",
    re.IGNORECASE,
)
# Broader security vocabulary the JD also uses. Reported as a note, never a failure on its own.
SOFT_SECURITY = re.compile(r"\b(cyber ?security|information security|security (framework|standard)s?)\b", re.IGNORECASE)
POSITIVE_DOMAIN = re.compile(r"(cyber incident review|data breach|breach (analysis|investigation)|data privacy review)", re.IGNORECASE)
PEOPLE_LEADERSHIP = re.compile(
    r"(lead(ing)? (a )?(team|analysts)|mentor|people (management|leadership)|manag\w* (a )?team|team lead|supervis|coach)",
    re.IGNORECASE,
)
POWER_QUERY = re.compile(r"power ?query", re.IGNORECASE)

# schema-concept -> field-name fragments that would carry it
_CONCEPTS: Dict[str, Tuple[str, ...]] = {
    "sourcing_paths": ("path", "sourcing"),
    "proficiency": ("proficien", "hands_on", "working_knowledge"),
    "hard_negatives": ("negative", "not_equivalent", "avoid"),
    "leadership": ("leadership",),
    "domain": ("domain",),
    "provenance": ("provenance", "source"),
}


@dataclass
class AssertionResult:
    id: str
    title: str
    status: str
    failure_class: Optional[str]
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------- schema introspection


def _field_names(model: Type[BaseModel], seen: Optional[set] = None) -> List[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return []
    seen.add(model)
    names: List[str] = []
    for name, info in model.model_fields.items():
        names.append(name)
        stack = [info.annotation]
        while stack:
            ann = stack.pop()
            for arg in typing.get_args(ann):
                stack.append(arg)
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                names.extend(_field_names(ann, seen))
    return names


def schema_supports(model: Type[BaseModel] = StructuredHiringIntent) -> Dict[str, bool]:
    """Which recruiter-strategy concepts the schema has ANY field for. Name-based on purpose: it answers "is there a
    place to put this", independent of what a model emitted."""
    names = [n.lower() for n in _field_names(model)]
    supports = {concept: any(frag in name for name in names for frag in frags) for concept, frags in _CONCEPTS.items()}
    try:
        RoleArchetype(value="domain_led", confidence=0.5, rationale="probe")
        supports["domain_led_archetype"] = True
    except ValidationError:
        supports["domain_led_archetype"] = False
    return supports


# ---------------------------------------------------------------------------- intent helpers


def positive_atoms(intent: StructuredHiringIntent) -> List[Dict[str, str]]:
    """Every skill-like / role-like claim the intent makes, with its strength. Education is deliberately excluded:
    the JD's degree list legitimately includes "Cybersecurity"."""
    atoms: List[Dict[str, str]] = []
    for s in intent.skills:
        atoms.append({"kind": "skill", "text": s.name, "strength": s.strength, "relationship": s.relationship})
    for g in intent.skill_any_of:
        for option in g.any_of:
            atoms.append({"kind": "skill_any_of", "text": option, "strength": g.strength, "relationship": g.relationship})
    for e in intent.evidence_signals:
        atoms.append({"kind": "evidence_signal", "text": e.name, "strength": e.strength, "relationship": "any"})
    for role in intent.role_family:
        atoms.append({"kind": "role_family", "text": role, "strength": "required", "relationship": "current"})
    return atoms


def _find(intent: StructuredHiringIntent, pattern: "re.Pattern[str]") -> List[Dict[str, str]]:
    return [a for a in positive_atoms(intent) if pattern.search(a["text"])]


def _fmt(atoms: Iterable[Dict[str, str]]) -> str:
    return "; ".join(f"{a['kind']}:{a['text']!r}/{a['strength']}/{a['relationship']}" for a in atoms) or "none"


def _leaves(tree: Any, acc: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    acc = acc if acc is not None else []
    if isinstance(tree, dict) and "op" in tree:
        for c in tree.get("conditions", []):
            _leaves(c, acc)
    elif isinstance(tree, dict):
        acc.append(tree)
    return acc


# ---------------------------------------------------------------------------- critical assertions


def evaluate_critical(intent: StructuredHiringIntent, supports: Optional[Dict[str, bool]] = None) -> List[AssertionResult]:
    supports = supports if supports is not None else schema_supports()
    out: List[AssertionResult] = []

    def add(id_: str, title: str, status: str, cls: Optional[str], evidence: str) -> None:
        out.append(AssertionResult(id_, title, status, None if status in (PASS, UNEVALUATED) else cls, evidence))

    def needs(concept: str) -> bool:
        return not supports.get(concept, False)

    no_paths = needs("sourcing_paths")
    archetype = intent.role_archetype.value
    location = intent.location.entries if intent.location else []

    # 1-4 path structure
    add("two_paths_preserved", "Two sourcing paths preserved", UNEVALUATED if not no_paths else FAIL, REPRESENTATION,
        "schema has no field that can hold more than one sourcing path" if no_paths else "schema supports paths; no adapter yet")
    add("path_a_domain_led", "Path A is domain-led", UNEVALUATED if not no_paths else FAIL, REPRESENTATION,
        f"no per-path archetype; global archetype={archetype!r}; domain_led archetype supported={supports.get('domain_led_archetype')}")
    add("path_b_capability_led", "Path B is capability-led / hybrid", UNEVALUATED if not no_paths else FAIL, REPRESENTATION,
        f"no per-path archetype; global archetype={archetype!r}")
    add("path_geography_differs", "Path A geography differs from Path B", UNEVALUATED if not no_paths else FAIL, REPRESENTATION,
        f"single location for the whole intent: entries={location}")

    # 5-6 Power Query
    pq = _find(intent, POWER_QUERY)
    if not pq:
        add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", FAIL, EXTRACTION, "Power Query absent from the intent (the JD names it)")
        add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", FAIL, EXTRACTION, "Power Query absent from the intent")
    else:
        required = any(a["strength"] == "required" for a in pq)
        if required:
            add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", FAIL, REPRESENTATION,
                f"required with no path scope, so it applies to every path including A: {_fmt(pq)}")
        else:
            add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", PARTIAL, REPRESENTATION,
                f"not forced on A, but Path B's requirement is also not preserved: {_fmt(pq)}")
        if needs("proficiency") or no_paths:
            add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", FAIL, REPRESENTATION,
                f"no proficiency field and no path scope; flattened to strength only: {_fmt(pq)}")
        else:
            add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", UNEVALUATED, None, "schema supports it; no adapter yet")

    # 7-8 hands-on SQL / Python
    for tool, id_ in (("SQL", "sql_hands_on"), ("Python", "python_hands_on")):
        hit = _find(intent, re.compile(rf"\b{tool}\b", re.IGNORECASE))
        if not hit or not any(a["strength"] == "required" for a in hit):
            add(id_, f"{tool} is hands-on", FAIL, EXTRACTION, f"{tool} missing or not required: {_fmt(hit)}")
        elif needs("proficiency"):
            add(id_, f"{tool} is hands-on", PARTIAL, REPRESENTATION, f"present and required, but 'hands-on' has no field to live in: {_fmt(hit)}")
        else:
            add(id_, f"{tool} is hands-on", UNEVALUATED, None, "schema supports proficiency; no adapter yet")

    # 9-10 Path B experience / level (carried, but not path-scoped)
    exp = intent.experience
    if exp is None or exp.minimum_years != 6 or exp.strength != "required":
        add("path_b_min_6_years", "Path B requires 6+ years", FAIL, EXTRACTION, f"experience={exp.model_dump() if exp else None}")
    else:
        add("path_b_min_6_years", "Path B requires 6+ years", PARTIAL if no_paths else UNEVALUATED, REPRESENTATION,
            "6+ required, but global rather than scoped to Path B (whether Path A inherits it is a recruiter-brief ambiguity)")
    sen = intent.seniority
    if sen is None or "lead" not in sen.value.lower() or sen.strength != "required":
        add("path_b_lead_requirement", "Path B requires Lead level", FAIL, EXTRACTION, f"seniority={sen.model_dump() if sen else None}")
    else:
        add("path_b_lead_requirement", "Path B requires Lead level", PARTIAL if no_paths else UNEVALUATED, REPRESENTATION,
            "Lead required, but global rather than scoped to Path B")

    # 11 cyber incident review != cybersecurity / SOC
    domain = _find(intent, POSITIVE_DOMAIN)
    secops = [a for a in positive_atoms(intent) if HARD_SECOPS.search(a["text"]) and a["kind"] != "role_family"]
    secops_pos = [a for a in secops if a["strength"] in ("required", "preferred")]
    soft = [a for a in positive_atoms(intent) if SOFT_SECURITY.search(a["text"])]
    if secops_pos:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", FAIL, RECONCILIATION,
            f"security-operations vocabulary became a positive requirement/preference (recruiter says not SOC): {_fmt(secops_pos)}")
    elif not domain:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", FAIL, EXTRACTION,
            f"the positive domain (cyber incident review / data breach analysis) is absent. soft security terms: {_fmt(soft)}")
    elif needs("hard_negatives") or needs("domain"):
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", PARTIAL, REPRESENTATION,
            f"domain captured ({_fmt(domain)}) and no SecOps promoted, but there is no way to state the distinction itself. soft security terms: {_fmt(soft)}")
    else:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", UNEVALUATED, None, "schema supports it; no adapter yet")

    # 12 hard negative preserved
    neg_exclusions = [e for e in intent.exclusions if HARD_SECOPS.search(e.value) or SOFT_SECURITY.search(e.value)]
    if needs("hard_negatives"):
        partial = f"only a current-title exclusion exists: {[e.model_dump() for e in neg_exclusions]}" if neg_exclusions else "no security-operations negative anywhere"
        add("hard_negative_secops_preserved", "Security-operations hard negative preserved", PARTIAL if neg_exclusions else FAIL, REPRESENTATION,
            f"exclusions can only name a title or company, not a domain or work-type; {partial}")
    else:
        add("hard_negative_secops_preserved", "Security-operations hard negative preserved", UNEVALUATED, None, "schema supports it; no adapter yet")

    # 13 leadership semantics
    people = [a for a in positive_atoms(intent) if PEOPLE_LEADERSHIP.search(a["text"]) and a["strength"] == "required"]
    if needs("leadership") and people:
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", FAIL, RECONCILIATION,
            f"the JD's people-leadership wording became a required signal, overriding the brief's 'people OR technical': {_fmt(people)}")
    elif needs("leadership"):
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", PARTIAL, REPRESENTATION,
            "no people-vs-technical field; the alternative cannot be stated (it is only avoided by omission)")
    else:
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", UNEVALUATED, None, "schema supports it; no adapter yet")

    # 14 no invented radius
    radius = intent.location.radius if intent.location else None
    add("no_invented_radius", "No radius invented", FAIL if radius else PASS, EXTRACTION, f"radius={radius.model_dump() if radius else None} (no source states a radius)")

    # 15 no invented current-company hard filter
    company_hits = [c.model_dump() for c in intent.companies if c.strength == "required" and c.relationship in ("current", "any")]
    scale = intent.company_scale.model_dump() if intent.company_scale and intent.company_scale.strength == "required" else None
    add("no_invented_company_filter", "No current-company hard filter invented", FAIL if (company_hits or scale) else PASS, EXTRACTION,
        f"required companies={company_hits} required company_scale={scale}")

    # 16 provenance
    if needs("provenance"):
        add("provenance_preserved", "Explicit vs inferred provenance preserved", FAIL, REPRESENTATION, "no provenance field on any atom")
    else:
        add("provenance_preserved", "Explicit vs inferred provenance preserved", UNEVALUATED, None, "schema supports it; no adapter yet")
    return out


# ---------------------------------------------------------------------------- compiler checks (separate class of failure)


def evaluate_compiler(intent: StructuredHiringIntent, plan: Any) -> List[AssertionResult]:
    """Only meaningful where the intent is already right about the thing checked. Reported separately so a compiler
    defect is never blamed on the model."""
    leaves = _leaves(plan.filter_tree)
    out: List[AssertionResult] = []

    def add(id_: str, title: str, status: str, evidence: str) -> None:
        out.append(AssertionResult(id_, title, status, None if status in (PASS, UNEVALUATED) else COMPILER, evidence))

    entries = intent.location.entries if intent.location else []
    country_like = {"india", "united states", "usa", "uk", "united kingdom"}
    city_values = [v for l in leaves if str(l.get("field", "")).endswith("location.city") for v in (l.get("value") or [])]
    leaked = [v for v in city_values if str(v).strip().lower() in country_like]
    if not entries:
        add("compiler_country_not_city", "A country is never compiled as a city", UNEVALUATED, "intent has no location")
    else:
        add("compiler_country_not_city", "A country is never compiled as a city", FAIL if leaked else PASS, f"entries={entries} city filter values={city_values}")

    country_only = [e for e in entries if "," not in e]
    has_country_leaf = any(str(l.get("field", "")).endswith("location.country") for l in leaves)
    if len(entries) > 1 and country_only:
        add("compiler_multi_location_keeps_country", "A multi-entry location keeps country-level scope", PASS if has_country_leaf else FAIL,
            f"entries={entries}; country filter present={has_country_leaf}")
    else:
        add("compiler_multi_location_keeps_country", "A multi-entry location keeps country-level scope", UNEVALUATED, "not a mixed country+city multi-entry location")

    company_leaf = [l for l in leaves if "company_name" in str(l.get("field", "")) and l.get("type") in ("in",)]
    add("compiler_no_company_filter", "No company-name filter compiled from background preferences", FAIL if company_leaf else PASS, f"company leaves={company_leaf}")
    return out


# ---------------------------------------------------------------------------- JD retention (do not discard JD requirements)

_JD_RETENTION: List[Tuple[str, "re.Pattern[str]"]] = [
    ("Relativity", re.compile(r"relativity", re.I)),
    ("Canopy", re.compile(r"canopy", re.I)),
    ("review/QA/compliance/audit experience", re.compile(r"(quality assurance|\bqa\b|compliance|audit|review)", re.I)),
    ("data privacy / regulatory", re.compile(r"(data privacy|regulatory)", re.I)),
    ("team leadership / mentoring (any representation)", re.compile(r"(lead|mentor|team)", re.I)),
]
_JD_DEGREES = ("Cybersecurity", "Information Technology", "Computer Science", "Information Systems", "Data Analytics")


def jd_retention(intent: StructuredHiringIntent) -> Dict[str, Any]:
    """Which formal JD items survived somewhere in the intent. Informational: whether an item SHOULD be kept at what
    strength is the recruiter's reconciliation call, not an automatic pass/fail."""
    blob_parts = [a["text"] for a in positive_atoms(intent)]
    if intent.seniority:
        blob_parts.append(intent.seniority.value)
    blob = " | ".join(blob_parts)
    kept = {name: bool(pat.search(blob)) for name, pat in _JD_RETENTION}
    streams = {s.lower() for s in (intent.education.streams if intent.education else [])}
    degrees = {d: d.lower() in streams for d in _JD_DEGREES}
    return {"items": kept, "degree_streams": degrees}


def evaluate(intent: StructuredHiringIntent, plan: Any) -> Dict[str, Any]:
    supports = schema_supports()
    return {
        "schema_supports": supports,
        "critical": [r.to_dict() for r in evaluate_critical(intent, supports)],
        "compiler": [r.to_dict() for r in evaluate_compiler(intent, plan)],
        "jd_retention": jd_retention(intent),
    }
