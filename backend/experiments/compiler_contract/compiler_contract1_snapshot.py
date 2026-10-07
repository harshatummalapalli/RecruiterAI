"""Phase 3 — the deterministic Hiring-Intent Compiler (contract version 1; see backend/services/COMPILER_CONTRACT.md).

Input:  StructuredHiringIntent (optionally with the extension fields, read by duck typing)  +  capability map  +  role-family taxonomy
Output: a provider filter tree (hard filters only) + a per-constraint audit record (routing/provenance) + a per-ATOM audit
        (`atom_audit`: exactly one fate per meaningful intent atom) + warnings. With sourcing paths: one independent plan per path.

No LLM. No provider call. Boring and deterministic: for each signal it looks up the capability, applies the one approved
transformation, and records how it was routed. It NEVER broadens a filter, relaxes a requirement, invents a title, or
"simplifies" the recruiter's logic.

THE CONTRACT (the invariant this module exists to keep):
    If intent means X, the compiler must either ENFORCE X, route X to downstream verification / context
    (VERIFIED_DOWNSTREAM / PREFERENCE_CONTEXT), NORMALIZE X deterministically, or declare X UNRESOLVED, with a
    justification when it deliberately sets X aside (DROPPED_WITH_JUSTIFICATION). It must never silently discard X.

Extraction preserves meaning; the compiler expands REPRESENTATION, never meaning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

from backend.models.structured_intent import StructuredHiringIntent
from backend.services import crustdata_capabilities as cap
from backend.services import role_family_taxonomy as tax

# Field sets for keyword skill retrieval by temporal relationship.
_CURRENT_SKILL_FIELDS = ["experience.employment_details.current.description", "basic_profile.headline", "basic_profile.summary"]
_PAST_SKILL_FIELDS = ["experience.employment_details.past.description", "experience.employment_details.past.title"]
_ANY_SKILL_FIELDS = ["experience.employment_details.description", "basic_profile.headline", "basic_profile.summary"]

_CUR_TITLE = "experience.employment_details.current.title"
_CUR_COMPANY = "experience.employment_details.current.company_name"
_PAST_COMPANY = "experience.employment_details.past.company_name"
_ANY_COMPANY = "experience.employment_details.company_name"
_HEADCOUNT = "experience.employment_details.current.company_headcount_latest"
_DEGREE = "education.schools.degree"
_STREAM = "education.schools.field_of_study"

COMPILER_VERSION = "v2-2026-10-07"
CONTRACT_VERSION = "compiler-contract-1"

# Small, explicit, versioned canonical-city aliases: the recruiter's word -> the
# string CrustData stores for exact city filtering. Verified live: city
# "Bangalore" matches 0 (CrustData uses "Bengaluru"). This is representation
# normalization, NOT a rewrite of the recruiter's visible intent (the source
# value is preserved in the audit). Deliberately tiny — not a geo synonym engine.
CITY_ALIAS_VERSION = "v1-2026-10-02"
_CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "madras": "Chennai",
    "gurgaon": "Gurugram",
}


def _canonical_city(city: str) -> str:
    return _CITY_ALIASES.get(city.strip().lower(), city)

_HARD_ROUTES = {"enforce", "enforce_with_warning", "enforce_but_not_verifiable"}

# Degree surface-form normalization: the SAME degree, the strings providers
# actually store. Whole-word "(.)" means "B.Tech" never matches "Bachelor of
# Technology", so a narrow literal list misses most real records (verified live:
# 3 vs 39). This expands REPRESENTATION, not meaning; scoped to the engineering/
# tech degrees (so "B.E" is read as Bachelor of Engineering, as the role implies).
# An unlisted degree is used verbatim (no expansion). Literal degree strings beyond this list are a TAXONOMY item.
_DEGREE_SURFACE_FORMS = {
    "b.tech": ["B.Tech", "Bachelor of Technology"],
    "btech": ["B.Tech", "Bachelor of Technology"],
    "b.e": ["B.E", "Bachelor of Engineering"],
    "be": ["B.E", "Bachelor of Engineering"],
    "m.tech": ["M.Tech", "Master of Technology"],
    "mtech": ["M.Tech", "Master of Technology"],
}


def _expand_degrees(degrees):
    out = []
    for d in degrees:
        for v in _DEGREE_SURFACE_FORMS.get(d.strip().lower(), [d]):
            if v not in out:
                out.append(v)
    return out


# --- fates ---------------------------------------------------------------------------------------------------------------
ENFORCED = "ENFORCED"
NORMALIZED = "NORMALIZED"
VERIFIED_DOWNSTREAM = "VERIFIED_DOWNSTREAM"
PREFERENCE_CONTEXT = "PREFERENCE_CONTEXT"
UNRESOLVED = "UNRESOLVED"
DROPPED_WITH_JUSTIFICATION = "DROPPED_WITH_JUSTIFICATION"
FATES = (ENFORCED, NORMALIZED, VERIFIED_DOWNSTREAM, PREFERENCE_CONTEXT, UNRESOLVED, DROPPED_WITH_JUSTIFICATION)
# SILENTLY_DROPPED is not a fate the compiler may assign. It is the name of the failure when an atom has no record at all.

# Proficiency wording for the downstream checklist: the depth is carried verbatim, never weakened or strengthened.
_PROFICIENCY_TEXT = {
    "hands_on": "hands-on {n}",
    "working_knowledge": "working knowledge of {n}",
    "advanced": "advanced proficiency in {n}",
}


@lru_cache(maxsize=1)
def _approved_levels() -> frozenset:
    """Levels known to approved versioned knowledge (backend/knowledge/seniority.json: its keys and synonyms)."""
    path = Path(__file__).resolve().parents[1] / "knowledge" / "seniority.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    known: Set[str] = set()
    for k, vs in data.items():
        known.add(k.strip().lower())
        known.update(v.strip().lower() for v in vs)
    return frozenset(known)


@dataclass
class CompiledConstraint:
    source: str
    strength: str
    route: str
    provider_fields: List[str] = field(default_factory=list)
    temporal: Optional[str] = None
    capability: Optional[str] = None
    note: str = ""
    scope: str = "global"      # "global" or "path:<id>"
    semantic: str = ""         # recruiter-meaning text for the downstream checklist ("" = derive it from `source`)


@dataclass
class AtomRecord:
    """The contract record for ONE meaningful intent atom: exactly one fate and where it went."""
    atom_id: str
    concept: str
    scope: str                       # where the atom was stated: "global" or "path:<id>"
    value: str
    provenance: Dict[str, Any]       # state: source | knowledge | model_only | unrecorded; sources; quote
    strength: Optional[str]
    proficiency: Optional[str]
    relationship: Optional[str]
    fate: str
    destination: str
    justification: str
    components: List[Dict[str, Any]] = field(default_factory=list)   # sub-values with their own fate (e.g. a location's state)
    kind: str = "MEANING"            # MEANING | RECORD (a reconciliation decision) | METADATA


@dataclass
class CompiledPath:
    path_id: str
    label: str
    strategy: str
    filter_tree: Dict[str, Any]
    audit: List[CompiledConstraint]
    retrieval_title_family: List[str]
    warnings: List[str] = field(default_factory=list)
    normalizations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CompiledPlan:
    filter_tree: Dict[str, Any]
    audit: List[CompiledConstraint]
    retrieval_title_family: List[str]
    taxonomy_version: str
    warnings: List[str] = field(default_factory=list)
    # Representation normalizations (source value preserved) — e.g. a canonical
    # city alias. These are NOT meaning changes; they record how the recruiter's
    # value was mapped to the provider's stored form.
    normalizations: List[Dict[str, Any]] = field(default_factory=list)
    atom_audit: List[AtomRecord] = field(default_factory=list)
    # One independent plan per sourcing path. The plans are ALTERNATIVES (an OR), never cumulative ANDs. Empty for an intent with no paths.
    paths: List[CompiledPath] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


def _leaf(f: str, t: str, v: Any) -> Dict[str, Any]:
    return {"field": f, "type": t, "value": v}


def _or(conds: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    conds = [c for c in conds if c]
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return {"op": "or", "conditions": conds}


def _skill_fields(temporal: Optional[str]) -> List[str]:
    return {"current": _CURRENT_SKILL_FIELDS, "past": _PAST_SKILL_FIELDS}.get(temporal, _ANY_SKILL_FIELDS)


# --- provenance ----------------------------------------------------------------------------------------------------------


def _prov(obj: Any) -> Dict[str, Any]:
    """What the intent claims supports an atom. MODEL_ONLY (inference, no JD / brief / approved knowledge) can never be a hard filter.
    UNRECORDED (a production-shaped intent carries no `basis`) keeps its legacy behaviour; the audit says so."""
    b = getattr(obj, "basis", None)
    if b is None:
        return {"state": "unrecorded", "sources": [], "quote": None}
    sources = list(b.sources)
    if set(sources) & {"jd", "recruiter_brief"}:
        state = "source"
    elif "approved_knowledge" in sources:
        state = "knowledge"
    else:
        state = "model_only"
    return {"state": state, "sources": sources, "quote": b.quote}


def _blocked(prov: Dict[str, Any]) -> bool:
    return prov["state"] == "model_only"


def _supports(prov: Dict[str, Any], text: str) -> bool:
    """Is a component value (a state, a country) supported by the cited source text? Only a recorded source quote can contradict a value:
    an unrecorded / knowledge-backed atom, or a source atom with no quote, is not second-guessed (the intake validators verified the quote)."""
    if prov["state"] != "source" or not prov["quote"]:
        return True
    return " ".join(text.casefold().split()) in " ".join(prov["quote"].casefold().split())


def _norm(s: str) -> str:
    """Case- and punctuation-insensitive text for comparing two quotations."""
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s.casefold()).split())


def _g(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


# --- views: one global view, or one effective view per sourcing path -----------------------------------------------------------


class _It(NamedTuple):
    obj: Any
    idx: int          # index inside the list the atom was STATED in (stable atom identity)
    origin: str       # "global" or "path:<id>"


@dataclass
class _View:
    scope: str
    intent: Any
    role_family: List[str]
    seniority: Optional[_It]
    skills: List[_It]
    skill_any_of: List[_It]
    companies: List[_It]
    company_scale: Optional[_It]
    education: Optional[_It]
    experience: Optional[_It]
    location: Optional[_It]
    exclusions: List[_It]
    evidence_signals: List[_It]
    domain: List[_It]
    semantic_exclusions: List[_It]
    reconciliations: List[Any]
    path: Any = None


def _items(seq: Any, origin: str = "global") -> List[_It]:
    return [_It(x, i, origin) for i, x in enumerate(seq or [])]


def _single(obj: Any, origin: str = "global") -> Optional[_It]:
    return _It(obj, 0, origin) if obj is not None else None


def _applicable(recs: List[Any], path_id: Optional[str]) -> List[Any]:
    return [r for r in recs if r.path_id is None or r.path_id == path_id]


def _global_view(intent: Any, scope: str = "global", recs_for: Optional[str] = None) -> _View:
    return _View(
        scope=scope, intent=intent, role_family=list(intent.role_family), seniority=_single(intent.seniority),
        skills=_items(intent.skills), skill_any_of=_items(intent.skill_any_of), companies=_items(intent.companies),
        company_scale=_single(intent.company_scale), education=_single(intent.education), experience=_single(intent.experience),
        location=_single(intent.location), exclusions=_items(intent.exclusions), evidence_signals=_items(intent.evidence_signals),
        domain=_items(_g(intent, "domain", [])), semantic_exclusions=_items(_g(intent, "semantic_exclusions", [])),
        reconciliations=_applicable(list(_g(intent, "reconciliations", [])), recs_for),
    )


def _path_view(intent: Any, path: Any) -> _View:
    """Inheritance, explicit: a path inherits the whole global intent. A singleton it sets (seniority, experience, location) REPLACES the
    global one; a skill or domain with the same (case-folded) name REPLACES the global entry; everything else it states is ADDED.
    Nothing a path states is visible to another path. (Mirrors the frozen `effective_view`; a test proves the two agree.)"""
    origin = f"path:{path.id}"
    v = _global_view(intent, scope=origin, recs_for=path.id)

    def merge(global_items: List[_It], path_seq: Any, key) -> List[_It]:
        by = {key(i.obj): i for i in global_items}
        for j, x in enumerate(path_seq or []):
            by[key(x)] = _It(x, j, origin)
        return list(by.values())

    if path.seniority is not None:
        v.seniority = _It(path.seniority, 0, origin)
    if path.experience is not None:
        v.experience = _It(path.experience, 0, origin)
    if path.location is not None:
        v.location = _It(path.location, 0, origin)
    v.skills = merge(v.skills, path.skills, lambda s: s.name.strip().lower())
    v.domain = merge(v.domain, path.domain, lambda d: d.name.strip().lower())
    v.path = path
    return v


# --- the per-scope compiler ----------------------------------------------------------------------------------------------


class _Scope:
    def __init__(self, view: _View):
        self.v = view
        self.conditions: List[Dict[str, Any]] = []
        self.audit: List[CompiledConstraint] = []
        self.atoms: List[Tuple[str, AtomRecord]] = []    # (origin, record)
        self.retired_ids: Set[str] = set()
        self.last_id = ""
        self.warnings: List[str] = []
        self.normalizations: List[Dict[str, Any]] = []
        self.titles: List[str] = []

    # -- plumbing --
    def row(self, source, strength, route, fields=None, temporal=None, capability=None, note="", semantic="") -> CompiledConstraint:
        c = CompiledConstraint(source, strength, route, list(fields or []), temporal, capability, note, scope=self.v.scope, semantic=semantic)
        self.audit.append(c)
        return c

    def atom(self, it: Optional[_It], concept: str, value: str, fate: str, destination: str, justification: str, *, strength=None,
             proficiency=None, relationship=None, components=None, kind="MEANING", obj: Any = None, idx: Optional[int] = None, origin: Optional[str] = None,
             prov: Optional[Dict[str, Any]] = None) -> None:
        o = obj if obj is not None else (it.obj if it is not None else None)
        origin = origin or (it.origin if it is not None else "global")
        i = idx if idx is not None else (it.idx if it is not None else 0)
        rec = AtomRecord(
            atom_id=f"{origin}|{concept}[{i}]", concept=concept, scope=origin, value=str(value), provenance=prov or _prov(o),
            strength=strength, proficiency=proficiency, relationship=relationship, fate=fate, destination=destination,
            justification=justification, components=list(components or []), kind=kind)
        self.atoms.append((origin, rec))
        self.last_id = rec.atom_id
        if fate == UNRESOLVED:
            self.warnings.append(f"UNRESOLVED {concept} {value!r} ({self.v.scope}): {justification}")

    def retired(self, obj: Any, labels: List[str]) -> Optional[Any]:
        """A JD atom the recruiter brief retired (waived / narrowed / contradicted / left unresolved) must not stay active. Precision over recall,
        because retiring the wrong atom would silently WEAKEN the search: an atom is retired only when ALL hold: it is REQUIRED, it rests on the JD
        alone (an atom the brief also supports, or one at a lower strength, IS the reconciled meaning), its quoted JD text overlaps the reconciliation's
        `jd_quote`, AND the reconciliation's TOPIC names it (the `result` is never used: it often lists what REMAINS required). Several atoms can share one
        JD sentence; only the one the reconciliation is about is retired."""
        b = getattr(obj, "basis", None)
        if b is None or not b.quote or _g(obj, "strength", "required") != "required" or set(b.sources) - {"jd"}:
            return None
        q = _norm(b.quote)
        for r in self.v.reconciliations:
            jq = _norm(r.jd_quote or "")
            if not (len(jq) >= 12 and len(q) >= 12 and (jq in q or q in jq)):
                continue
            named = _norm(r.topic)
            if any(_norm(l) and _norm(l) in named for l in labels):
                return r
        return None

    def retire(self, it: _It, concept: str, value: str, rec: Any, **kw) -> None:
        self._retire(it, concept, value, rec, **kw)
        self.retired_ids.add(self.last_id)

    def _retire(self, it: _It, concept: str, value: str, rec: Any, **kw) -> None:
        if rec.action == "unresolved":
            self.atom(it, concept, value, UNRESOLVED, "not compiled",
                      f"the JD requirement conflicts with the brief and the conflict is unresolved ({rec.topic}); not enforced either way", **kw)
        else:
            self.atom(it, concept, value, DROPPED_WITH_JUSTIFICATION, "reconciliation record",
                      f"retired by reconciliation: {rec.action} — {rec.topic}. The final reconciled meaning is compiled instead: {rec.result}", **kw)

    @staticmethod
    def _soft_fate(strength: Optional[str]) -> str:
        return VERIFIED_DOWNSTREAM if strength == "required" else PREFERENCE_CONTEXT

    def hard_ok(self, field_name: str, strength: str) -> str:
        # Only `required` is a candidate-selection requirement. `preferred` and `context` are never routed as required.
        return cap.recommend_routing(field_name, "required" if strength == "required" else "preferred")

    def city(self, raw: str) -> str:
        canon = _canonical_city(raw)
        if canon != raw:
            self.normalizations.append({"field": "basic_profile.location.city", "source_value": raw, "provider_normalized_value": canon,
                                        "normalization": "canonical_city_alias", "version": CITY_ALIAS_VERSION})
        return canon

    # -- concepts --
    def location(self) -> None:
        it = self.v.location
        if it is None:
            return
        loc = it.obj
        st = loc.strength
        prov = _prov(loc)
        rec = self.retired(loc, list(loc.entries) + list(_g(loc, "countries", []) or []) + [e.split(",")[0] for e in loc.entries])
        entries = list(loc.entries)
        countries = list(_g(loc, "countries", []) or [])
        remote = _g(loc, "remote")
        work_mode = _g(loc, "work_mode")
        hard = st == "required" and not _blocked(prov) and rec is None

        def aset(concept, value, i, fate, dest, just, **kw):
            self.atom(it, concept, value, fate, dest, just, strength=st, idx=i, prov=prov, **kw)

        def off(concept, value, i):
            """Why this location atom is not a provider filter."""
            if rec is not None:
                self.retire(it, concept, value, rec, strength=st, idx=i, prov=prov)
            elif _blocked(prov):
                aset(concept, value, i, UNRESOLVED, "not compiled", "model-only inference (no JD, brief or approved-knowledge support) is never a hard provider filter")
            else:
                aset(concept, value, i, PREFERENCE_CONTEXT, "audit row 'location' (context_or_evidence)",
                     f"location strength is {st!r}: a non-required place is preserved as context, not enforced")

        entry_cond: Optional[Dict[str, Any]] = None
        country_cond: Optional[Dict[str, Any]] = None
        if (entries or countries or loc.radius) and not hard:
            for j, e in enumerate(entries):
                off("location.entry", e, j)
            for j, c in enumerate(countries):
                off("location.country", c, j)
            soft = not _blocked(prov) and rec is None
            self.row("location", st, "context_or_evidence" if soft else "disclose", ["basic_profile.location.*"],
                     note=f"entries={entries}; countries={countries}; not a hard filter", capability="context_or_evidence" if soft else None)
        if hard and entries:
            leaves: List[Dict[str, Any]] = []
            comp_by_entry: List[List[Dict[str, Any]]] = []
            if len(entries) == 1:
                parts = [p.strip() for p in entries[0].split(",") if p.strip()]
                comps: List[Dict[str, Any]] = []
                if len(parts) == 3:
                    city, state, country = parts
                    ok_c, ok_s = _supports(prov, country), _supports(prov, state)
                    if ok_c:
                        leaves.append(_leaf("basic_profile.location.country", "in", [country]))
                    comps.append({"component": "country", "value": country, "fate": ENFORCED if ok_c else DROPPED_WITH_JUSTIFICATION,
                                  "justification": "stated in the cited source" if ok_c else "model-supplied: not in the cited source text and no approved normalization; never a provider filter"})
                    if ok_s:
                        leaves.append(_leaf("basic_profile.location.state", "in", [state]))
                    comps.append({"component": "state", "value": state, "fate": ENFORCED if ok_s else DROPPED_WITH_JUSTIFICATION,
                                  "justification": "stated in the cited source" if ok_s else "model-supplied: not in the cited source text and no approved normalization; never a provider filter"})
                    leaves.append(_leaf("basic_profile.location.city", "in", [self.city(city)]))
                    comps.append({"component": "city", "value": city, "fate": ENFORCED, "justification": "the stated place"})
                else:  # fall back to a city-level match on whatever was given (existing rule)
                    leaves.append(_leaf("basic_profile.location.city", "in", [self.city(parts[0])]))
                    comps.append({"component": "city", "value": parts[0], "fate": ENFORCED, "justification": "the stated place"})
                    for extra in parts[1:]:
                        comps.append({"component": "qualifier", "value": extra, "fate": DROPPED_WITH_JUSTIFICATION,
                                      "justification": "a place with fewer than three parts compiles to its city only (existing rule); not enforced"})
                comp_by_entry.append(comps)
            else:
                cities = []
                for e in entries:
                    parts = [p.strip() for p in e.split(",") if p.strip()]
                    cities.append(self.city(parts[0]))
                    comp_by_entry.append([{"component": "city", "value": parts[0], "fate": ENFORCED, "justification": "the stated place"}] +
                                         [{"component": "qualifier", "value": x, "fate": DROPPED_WITH_JUSTIFICATION,
                                           "justification": "a multi-entry location compiles to its cities only (existing rule); state and country are not enforced"} for x in parts[1:]])
                leaves.append(_leaf("basic_profile.location.city", "in", cities))
            entry_cond = {"op": "and", "conditions": leaves} if len(leaves) > 1 else leaves[0]
            for j, e in enumerate(entries):
                comps = comp_by_entry[j if len(entries) > 1 else 0]
                dropped = [c for c in comps if c["fate"] != ENFORCED]
                norm = any(n["source_value"] == e.split(",")[0].strip() for n in self.normalizations)
                aset("location.entry", e, j, NORMALIZED if norm else ENFORCED, "provider filter: " + ", ".join(sorted({l["field"].rsplit(".", 1)[-1] for l in leaves})),
                     "enforced as the stated place" + (f"; {len(dropped)} component(s) not enforced (see components)" if dropped else ""), components=comps)
        if hard and countries:
            country_cond = _leaf("basic_profile.location.country", "in", countries)
            for j, c in enumerate(countries):
                aset("location.country", c, j, ENFORCED, "provider filter: country", "a country-wide area is a country filter")
        if hard and (entry_cond or country_cond):
            if entry_cond and country_cond:
                self.conditions.append({"op": "or", "conditions": [entry_cond, country_cond]})
            else:
                c = entry_cond or country_cond
                if c.get("op") == "and":
                    self.conditions += c["conditions"]
                else:
                    self.conditions.append(c)
            self.row("location", st, "provider_hard_filter", ["basic_profile.location.*"], note=f"entries={entries}" + (f"; countries={countries}" if countries else ""))

        radius = loc.radius
        if radius:
            val = f"{radius.value} {radius.unit} around {radius.around}"
            if hard:
                unit = {"miles": "mi", "mile": "mi", "mi": "mi", "km": "km", "kilometers": "km"}.get(radius.unit.lower(), "mi")
                around_parts = [p.strip() for p in radius.around.split(",")]
                if around_parts:
                    around_parts[0] = self.city(around_parts[0])
                self.conditions.append(_leaf("basic_profile.location", "geo_distance", {"location": ", ".join(around_parts), "distance": radius.value, "unit": unit}))
                self.row("location.radius", st, "provider_hard_filter", ["basic_profile.location"], note=f"{radius.value} {unit} around {radius.around}")
                aset("location.radius", val, 0, ENFORCED, "provider filter: geo_distance", "enforced")
            else:
                off("location.radius", val, 0)

        if remote:
            if remote == "not_allowed" and st == "required" and rec is None:
                self.row("location.remote", st, "downstream_evidence", [], note="remote candidates are not acceptable for this scope; no provider filter exists",
                         semantic="Candidates who work remotely are not acceptable")
                aset("location.remote", remote, 0, VERIFIED_DOWNSTREAM, "downstream checklist", "a requirement no provider field can express; verified downstream")
            else:
                self.row("location.remote", st, "context_or_evidence", [], note=f"remote={remote}: an allowance; it neither adds nor relaxes a provider filter")
                aset("location.remote", remote, 0, PREFERENCE_CONTEXT, "audit row 'location.remote' (context_or_evidence)",
                     "remote acceptability is an allowance, not a candidate filter; preserved as context and it does not relax the place filter")
        if work_mode:
            routing = cap.recommend_routing("work_mode", "required" if st == "required" else "preferred")
            if st != "required" or rec is not None:
                self.row("location.work_mode", st, "context_or_evidence", [], note=f"work_mode={work_mode} (strength {st})")
                aset("location.work_mode", work_mode, 0, PREFERENCE_CONTEXT, "audit row 'location.work_mode' (context_or_evidence)", f"strength {st!r}: preserved as context")
            elif routing == "judge":
                self.row("location.work_mode", st, "downstream_evidence", [], capability=routing, note=f"work_mode={work_mode}",
                         semantic=f"Working arrangement: {work_mode}")
                aset("location.work_mode", work_mode, 0, VERIFIED_DOWNSTREAM, "downstream checklist", "verifiable downstream per the capability map")
            else:
                self.row("location.work_mode", st, "disclose", [], capability=routing,
                         note=f"work_mode={work_mode}: no provider filter and not verifiable from the profile (capability map); preserved verbatim, not remapped to remote or on-site")
                aset("location.work_mode", work_mode, 0, UNRESOLVED, "audit row 'location.work_mode' (disclose)",
                     "capability map: no work-mode filter on person search and not verifiable from candidate data; preserved as typed, never converted to another mode")

    def experience(self) -> None:
        it = self.v.experience
        if it is None:
            return
        ex = it.obj
        st = ex.strength
        prov = _prov(ex)
        rec = self.retired(ex, ["experience", "years"])
        hard = st == "required" and not _blocked(prov) and rec is None
        items = []
        if ex.minimum_years is not None:
            items.append(("experience.min", f"{ex.minimum_years}+ years", "=>", ex.minimum_years, 0))
        if ex.maximum_years is not None:
            items.append(("experience.max", f"<= {ex.maximum_years} years", "=<", ex.maximum_years, 1))
        if not items:
            return
        if hard:
            for concept, label, op, val, i in items:
                self.conditions.append(_leaf("years_of_experience_raw", op, val))
                self.atom(it, concept, label, ENFORCED, "provider filter: years_of_experience_raw", "enforced", strength=st, idx=i, prov=prov)
            self.row("experience", st, "provider_hard_filter", ["years_of_experience_raw"])
        else:
            for concept, label, _op, _val, i in items:
                if rec is not None:
                    self.retire(it, concept, label, rec, strength=st, idx=i, prov=prov)
                elif _blocked(prov):
                    self.atom(it, concept, label, UNRESOLVED, "not compiled", "model-only inference is never a hard provider filter", strength=st, idx=i, prov=prov)
                else:
                    self.atom(it, concept, label, PREFERENCE_CONTEXT, "audit row 'experience' (context_or_evidence)",
                              f"experience strength is {st!r}: a non-required range is preserved as context, not enforced", strength=st, idx=i, prov=prov)
            if rec is None:
                self.row("experience", st, "context_or_evidence" if not _blocked(prov) else "disclose", ["years_of_experience_raw"],
                         note=f"{ex.minimum_years}..{ex.maximum_years} (strength {st}): not a hard filter")

    def role_family(self) -> None:
        titles, used_tax, notes = tax.expand_retrieval_titles(self.v.role_family)
        self.titles = titles
        group = _or([_leaf(_CUR_TITLE, "(.)", t) for t in titles])
        if group:
            self.conditions.append(group)
        self.row("role_family", "required", "provider_hard_filter", [_CUR_TITLE], note="; ".join(notes))
        for i, src in enumerate(self.v.role_family):
            fam = tax.lookup(src)
            fate = NORMALIZED if fam else ENFORCED
            self.atom(None, "role_family", src, fate, "provider filter: current title",
                      (f"expanded by the approved role-family taxonomy ({fam.version}) to {fam.approved_retrieval_titles}" if fam
                       else "no taxonomy entry: the source title is used verbatim (no expansion)"),
                      strength="required", idx=i, origin="global", prov={"state": "unrecorded", "sources": [], "quote": None})

    def seniority(self) -> None:
        it = self.v.seniority
        if it is None:
            return
        sn = it.obj
        st = sn.strength
        leadership = list(_g(sn, "leadership", []) or [])
        alternatives = list(_g(sn, "alternatives", []) or [])
        prov = _prov(sn)
        known = _approved_levels()
        rec = self.retired(sn, [sn.value])
        note = f"value={sn.value}; enforced by Phase-1a admission gate"
        if alternatives:
            note += f"; also accepts levels={alternatives}"
        if leadership:
            note += f"; leadership={' or '.join(leadership)}"

        def level_fate(level: str) -> Tuple[str, str]:
            if level.strip().lower() in known:
                return self._soft_fate(st), "level known to approved knowledge (seniority.json); carried to the admission gate verbatim"
            return UNRESOLVED, ("no approved taxonomy mapping for this level: preserved verbatim for the admission gate, never remapped to another level")

        if rec is not None:
            self.retire(it, "seniority.value", sn.value, rec, strength=st, prov=prov)
            return
        value_fate, why = level_fate(sn.value)
        if value_fate == UNRESOLVED:
            note += "; level not in approved taxonomy: preserved verbatim, not remapped"
        self.row("seniority", st, "admission_level_fit", [], note=note)
        self.atom(it, "seniority.value", sn.value, value_fate, "audit row 'seniority' (admission_level_fit)", why, strength=st, prov=prov)
        for j, a in enumerate(alternatives):
            f, w = level_fate(a)
            self.atom(it, "seniority.alternatives", a, f, "audit row 'seniority' (admission_level_fit)", "an accepted alternative level: " + w, strength=st, idx=j, prov=prov)
        if leadership:
            self.row("seniority.leadership", st, "downstream_evidence", [], note=f"leadership kinds accepted: {leadership}",
                     semantic=" or ".join(f"{m} leadership" for m in leadership).capitalize())
            for j, m in enumerate(leadership):
                self.atom(it, "seniority.leadership", m, self._soft_fate(st), "downstream checklist",
                          "a leadership requirement no provider field can express; verified downstream", strength=st, idx=j, prov=prov)

    def skills(self) -> None:
        for it in self.v.skills:
            s = it.obj
            prov = _prov(s)
            rec = self.retired(s, [s.name])
            if rec is not None:
                self.retire(it, "skill", s.name, rec, strength=s.strength, relationship=s.relationship, proficiency=getattr(s, "proficiency", None), prov=prov)
                if getattr(s, "proficiency", None):
                    self.retire(it, "skill.proficiency", f"{s.name} = {s.proficiency}", rec, strength=s.strength, proficiency=s.proficiency, prov=prov)
                continue
            self._skill_like(it, s.name, f"skill:{s.name}", "skill", s.strength, s.relationship, prov, [s.name])
            prof = getattr(s, "proficiency", None)
            if prof:
                text = _PROFICIENCY_TEXT.get(prof, "{n} (" + prof + ")").format(n=s.name)
                self.row(f"proficiency:{s.name}={prof}", s.strength, "downstream_evidence", [], note=f"depth {prof} is not provider-filterable; verified downstream",
                         semantic=text)
                self.atom(it, "skill.proficiency", f"{s.name} = {prof}", self._soft_fate(s.strength), "downstream checklist",
                          "no provider field states depth; the stated level travels with the skill unchanged" + ("" if s.strength == "required" else f" (preference: strength {s.strength!r})"),
                          strength=s.strength, proficiency=prof, relationship=s.relationship, prov=prov)

    def skill_groups(self) -> None:
        for it in self.v.skill_any_of:
            g = it.obj
            prov = _prov(g)
            rec = self.retired(g, list(g.any_of))
            if rec is not None:
                self.retire(it, "skill_any_of", " | ".join(g.any_of), rec, strength=g.strength, relationship=g.relationship, prov=prov)
                continue
            self._skill_like(it, " | ".join(g.any_of), f"skill_any_of:{'|'.join(g.any_of)}", "skill_any_of", g.strength, g.relationship, prov, g.any_of)

    def _skill_like(self, it: _It, label: str, source: str, concept: str, strength: str, rel: Optional[str], prov: Dict[str, Any], terms: List[str]) -> None:
        fields = _skill_fields(rel)
        common = dict(strength=strength, relationship=rel, prov=prov)
        if rel is None:
            # UNSPECIFIED != CURRENT. The source did not say when; nothing is invented. Not provider-enforceable without a time scope.
            self.row(source, strength, "downstream_evidence", fields, temporal=None, capability="unspecified_relationship",
                     note="relationship unspecified: not treated as current; verified downstream (no time-scoped provider filter is invented)")
            self.atom(it, concept, label, self._soft_fate(strength), "downstream checklist",
                      "temporal relationship unspecified: never defaulted to current, so no current-role provider filter" + ("" if strength == "required" else f"; strength {strength!r} is a preference"),
                      **common)
            return
        route = self.hard_ok(fields[0], strength)
        if route in _HARD_ROUTES and _blocked(prov):
            self.row(source, strength, "downstream_evidence", fields, temporal=rel, capability="provenance_gate",
                     note="model-only inference (no JD, brief or approved-knowledge support): never a provider filter; verified downstream")
            self.atom(it, concept, label, VERIFIED_DOWNSTREAM, "downstream checklist", "provenance gate: model-only inference is never a hard provider filter", **common)
        elif route in _HARD_ROUTES:
            grp = _or([_leaf(f, "(.)", term) for term in terms for f in fields])
            if grp:
                self.conditions.append(grp)
            if route == "enforce_but_not_verifiable" and concept == "skill":
                self.warnings.append(f"skill {terms[0]!r}: filtered on response-gated text; not displayable from the provider")
            self.row(source, strength, "provider_hard_filter", fields, temporal=rel, capability=route)
            self.atom(it, concept, label, ENFORCED, f"provider filter: {rel}-role text", f"required with an explicit {rel!r} relationship; capability {route}", **common)
        else:
            self.row(source, strength, "downstream_evidence", fields, temporal=rel, capability=route,
                     note="preferred/unverified -> judge/context, no hard filter")
            why = (f"strength {strength!r} is a preference, never a hard filter" if strength != "required"
                   else f"relationship {rel!r} has no verified provider field (capability {route}); verified downstream")
            self.atom(it, concept, label, self._soft_fate(strength), "downstream checklist", why, **common)

    def company_scale(self) -> None:
        it = self.v.company_scale
        if it is None:
            return
        cs = it.obj
        prov = _prov(cs)
        rec = self.retired(cs, ["company size", "headcount", "employees"])
        label = f">={cs.minimum_employees} employees"
        common = dict(strength=cs.strength, relationship=cs.relationship, prov=prov)
        if rec is not None:
            self.retire(it, "company_scale", label, rec, **common)
            return
        route = self.hard_ok(_HEADCOUNT, cs.strength)
        if cs.relationship == "current" and route in _HARD_ROUTES and not _blocked(prov):
            self.conditions.append(_leaf(_HEADCOUNT, "=>", cs.minimum_employees))
            allowed, warn = cap.can_hard_filter(_HEADCOUNT)
            if warn:
                self.warnings.append(warn)
            self.row("company_scale", cs.strength, "provider_hard_filter", [_HEADCOUNT], temporal=cs.relationship, capability=route,
                     note="completeness unestablished; verify downstream where possible")
            self.atom(it, "company_scale", label, ENFORCED, "provider filter: current headcount", "explicit current relationship; verified provider field", **common)
        elif cs.strength != "required":
            self.row("company_scale", cs.strength, "downstream_evidence", [_HEADCOUNT], temporal=cs.relationship, capability=route)
            self.atom(it, "company_scale", label, PREFERENCE_CONTEXT, "downstream checklist", f"strength {cs.strength!r} is a preference, never a hard filter", **common)
        else:
            reason = ("model-only inference is never a hard provider filter" if _blocked(prov) else
                      f"the only verified headcount field is the CURRENT employer's; the stated relationship is {cs.relationship!r}, so no current-employer filter is invented")
            self.row("company_scale", cs.strength, "disclose", [_HEADCOUNT], temporal=cs.relationship, capability="relationship_not_current", note=reason)
            self.atom(it, "company_scale", label, UNRESOLVED, "audit row 'company_scale' (disclose)", reason, **common)

    def education(self) -> None:
        it = self.v.education
        if it is None:
            return
        ed = it.obj
        prov = _prov(ed)
        rec = self.retired(ed, list(ed.degrees) + list(ed.streams) + ["education", "degree"])
        common = dict(strength=ed.strength, prov=prov)
        atoms = [("education.degree", d, j) for j, d in enumerate(ed.degrees)] + [("education.stream", s, j) for j, s in enumerate(ed.streams)]
        if not atoms:
            return
        if rec is not None:
            for concept, v, j in atoms:
                self.retire(it, concept, v, rec, idx=j, **common)
            return
        if ed.strength != "required" or _blocked(prov):
            reason = "model-only inference is never a hard provider filter" if _blocked(prov) else \
                f"education strength is {ed.strength!r}: a non-required qualification is preserved as a preference, not enforced"
            self.row("education", ed.strength, "disclose" if _blocked(prov) else "context_or_evidence", [_DEGREE, _STREAM],
                     note=f"degrees={ed.degrees}; streams={ed.streams}; {reason}", capability=None if _blocked(prov) else "context_or_evidence")
            for concept, v, j in atoms:
                self.atom(it, concept, v, UNRESOLVED if _blocked(prov) else PREFERENCE_CONTEXT, "audit row 'education'", reason, idx=j, **common)
            return
        degree_route = self.hard_ok(_DEGREE, ed.strength) if ed.degrees else None
        stream_route = self.hard_ok(_STREAM, ed.strength) if ed.streams else None
        degree_grp = _or([_leaf(_DEGREE, "(.)", d) for d in _expand_degrees(ed.degrees)]) if (degree_route in _HARD_ROUTES) else None
        stream_grp = _or([_leaf(_STREAM, "(.)", s) for s in ed.streams]) if (stream_route in _HARD_ROUTES) else None
        members = [g for g in (degree_grp, stream_grp) if g]
        # ONE grouped predicate: degree and stream must match the SAME school entry (verified live), so two members are an all_of group.
        if len(members) >= 2:
            self.conditions.append({"op": "all_of", "conditions": members})
        elif members:
            self.conditions.append(members[0])
        if stream_route == "enforce_but_not_verifiable":
            self.warnings.append("education stream: filterable but response-gated (not displayable); verify via Harvest if needed")
        if degree_grp or stream_grp:
            self.row("education", ed.strength, "provider_hard_filter", [f for f, g in ((_DEGREE, degree_grp), (_STREAM, stream_grp)) if g],
                     capability=stream_route or degree_route, note="degree + stream grouped on the same school entry (all_of)")
        for concept, v, j in atoms:
            grp = degree_grp if concept == "education.degree" else stream_grp
            if grp:
                norm = concept == "education.degree" and _expand_degrees([v]) != [v]
                self.atom(it, concept, v, NORMALIZED if norm else ENFORCED, "provider filter: education.schools",
                          "degree surface forms expanded deterministically" if norm else "enforced (literal provider string; normalization beyond the approved degree list is a taxonomy item)",
                          idx=j, **common)
            else:
                self.atom(it, concept, v, UNRESOLVED, "audit row 'education'", "no verified provider field", idx=j, **common)

    def companies(self) -> None:
        for it in self.v.companies:
            c = it.obj
            prov = _prov(c)
            rec = self.retired(c, [c.name])
            common = dict(strength=c.strength, relationship=c.relationship, prov=prov)
            if rec is not None:
                self.retire(it, "company", c.name, rec, **common)
                continue
            fld = {"current": _CUR_COMPANY, "past": _PAST_COMPANY}.get(c.relationship, _ANY_COMPANY)
            route = self.hard_ok(fld, c.strength)
            if route in _HARD_ROUTES and not _blocked(prov):
                self.conditions.append(_leaf(fld, "in", [c.name]))
                self.row(f"company:{c.name}", c.strength, "provider_hard_filter", [fld], temporal=c.relationship, capability=route)
                self.atom(it, "company", c.name, ENFORCED, "provider filter: company name", "required company", **common)
            else:
                self.row(f"company:{c.name}", c.strength, "context_or_evidence", [fld], temporal=c.relationship, capability=route,
                         note="no verified provider preference mechanism -> context/evidence, not a filter")
                self.atom(it, "company", c.name, PREFERENCE_CONTEXT, "audit row (context_or_evidence)",
                          ("model-only inference is never a hard provider filter" if _blocked(prov) else
                           f"strength {c.strength!r}: a company preference is never a hard company filter; no provider preference mechanism exists"), **common)

    def exclusions(self) -> None:
        by_kind = {"current_company": _CUR_COMPANY, "exclude_current_company": _CUR_COMPANY, "exclude_past_company": _PAST_COMPANY,
                   "exclude_any_company": _ANY_COMPANY}
        for it in self.v.exclusions:
            x = it.obj
            prov = _prov(x)
            rec = self.retired(x, [x.value])
            common = dict(strength="required", prov=prov)
            label = f"{x.kind}: {x.value}"
            if rec is not None:
                self.retire(it, f"exclusion.{x.kind}", label, rec, **common)
                continue
            if x.kind in by_kind or x.kind in ("title", "exclude_title"):
                if _blocked(prov):
                    self.row(f"{x.kind}:{x.value}", "required", "disclose", [], note="model-only inference is never a provider filter")
                    self.atom(it, f"exclusion.{x.kind}", label, UNRESOLVED, "audit row (disclose)", "model-only inference is never a hard provider filter", **common)
                elif x.kind in by_kind:
                    fld = by_kind[x.kind]
                    self.conditions.append(_leaf(fld, "not_in", [x.value]))
                    self.row(f"{x.kind}:{x.value}", "required", "provider_hard_filter", [fld])
                    self.atom(it, f"exclusion.{x.kind}", label, ENFORCED, "provider filter: not_in", "explicit company exclusion", **common)
                else:
                    self.conditions.append(_leaf(_CUR_TITLE, "(!)", x.value))
                    self.row(f"exclude_title:{x.value}", "required", "provider_hard_filter", [_CUR_TITLE])
                    self.atom(it, f"exclusion.{x.kind}", label, ENFORCED, "provider filter: title not-match", "explicit title exclusion", **common)
            else:
                self.row(f"{x.kind}:{x.value}", "required", "disclose", [], note=f"unsupported exclusion kind {x.kind!r}: not compiled")
                self.atom(it, f"exclusion.{x.kind}", label, UNRESOLVED, "audit row (disclose)", f"exclusion kind {x.kind!r} has no provider mapping: preserved, not compiled", **common)

    def semantic_exclusions(self) -> None:
        for it in self.v.semantic_exclusions:
            x = it.obj
            prov = _prov(x)
            rec = self.retired(x, [x.concept] + list(x.includes))
            if rec is not None:
                self.retire(it, "semantic_exclusion", x.concept, rec, strength="required", prov=prov)
                continue
            inc = f"; includes={list(x.includes)}" if x.includes else ""
            self.row(f"semantic_exclusion:{x.concept}", "required", "downstream_exclusion", [], capability="semantic_negative",
                     note=f"a work-type to screen OUT, kept as meaning; never a company or title filter{inc}", semantic=x.concept)
            self.atom(it, "semantic_exclusion", x.concept, VERIFIED_DOWNSTREAM, "downstream exclusion checklist",
                      "a semantic negative is verified by the Judge; no provider constraint is equivalent, so none is invented", strength="required", prov=prov)

    def domain(self) -> None:
        for it in self.v.domain:
            d = it.obj
            prov = _prov(d)
            rec = self.retired(d, [d.name])
            if rec is not None:
                self.retire(it, "domain", d.name, rec, strength=d.strength, prov=prov)
                continue
            self.row(f"domain:{d.name}", d.strength, "downstream_evidence", [], capability="domain_not_a_provider_field",
                     note="a work domain is not a literal provider field; it is never converted to a keyword or company filter")
            self.atom(it, "domain", d.name, self._soft_fate(d.strength), "downstream checklist",
                      "domain is verified from the candidate's evidence" + ("" if d.strength == "required" else f"; strength {d.strength!r} is a preference"),
                      strength=d.strength, prov=prov)

    def evidence(self) -> None:
        for it in self.v.evidence_signals:
            e = it.obj
            prov = _prov(e)
            rec = self.retired(e, [e.name])
            if rec is not None:
                self.retire(it, "evidence_signal", e.name, rec, strength=e.strength, prov=prov)
                continue
            self.row(f"evidence:{e.name}", e.strength, "downstream_evidence", [], note="verified by RequirementJudge; never a provider filter")
            self.atom(it, "evidence_signal", e.name, self._soft_fate(e.strength), "downstream checklist", "verified by the Judge; never a provider filter", strength=e.strength, prov=prov)

    def metadata(self) -> None:
        arche = _g(self.v.intent, "role_archetype", None)
        if arche is not None:
            self.atom(None, "role_archetype", arche.value, DROPPED_WITH_JUSTIFICATION, "atom audit",
                      "classification metadata about the role (title/skill/hybrid): it carries no execution semantics and no candidate constraint",
                      kind="METADATA", origin="global", prov={"state": "unrecorded", "sources": [], "quote": None})

    def reconciliations(self, recs: List[Any]) -> None:
        for i, r in enumerate(recs):
            fate = UNRESOLVED if r.action == "unresolved" else DROPPED_WITH_JUSTIFICATION
            just = (f"the sources conflict and the brief does not settle it; surfaced, no side enforced: {r.result}" if fate == UNRESOLVED else
                    f"decision record: {r.action}; the final reconciled meaning is carried by the surviving atoms (and any retired JD atom is recorded as such): {r.result}")
            self.atom(None, "reconciliation", f"{r.action}: {r.topic}", fate, "atom audit (decision record)", just, kind="RECORD", obj=None, idx=i,
                      origin=f"path:{r.path_id}" if r.path_id else "global",
                      prov={"state": "source", "sources": ["jd", "recruiter_brief"], "quote": r.brief_quote})

    def run(self) -> None:
        self.location()
        self.experience()
        self.role_family()
        self.seniority()
        self.skills()
        self.skill_groups()
        self.company_scale()
        self.education()
        self.companies()
        self.exclusions()
        self.semantic_exclusions()
        self.domain()
        self.evidence()


def _tree(conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"op": "and", "conditions": conditions}


def _dedupe(seq: List[Any]) -> List[Any]:
    out: List[Any] = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def compile_intent(intent: StructuredHiringIntent) -> CompiledPlan:
    paths = list(_g(intent, "sourcing_paths", []) or [])
    if not paths:
        s = _Scope(_global_view(intent))
        s.run()
        s.metadata()
        s.reconciliations(list(_g(intent, "reconciliations", []) or []))
        return CompiledPlan(filter_tree=_tree(s.conditions), audit=s.audit, retrieval_title_family=s.titles, taxonomy_version=tax.TAXONOMY_VERSION,
                            warnings=_dedupe(s.warnings), normalizations=s.normalizations, atom_audit=[r for _o, r in s.atoms])
    return _compile_paths(intent, paths)


def _compile_paths(intent: Any, paths: List[Any]) -> CompiledPlan:
    """Each path is compiled INDEPENDENTLY from its own effective view. The plans are alternatives (an OR), never cumulative ANDs.
    Atom records: a path-scoped atom has one record (its path); a GLOBAL atom has ONE record whose fate is the one it has where it applies,
    with the paths that inherit it, retire it, or override it named in the destination / justification."""
    path_ids = [p.id for p in paths]
    base = _Scope(_global_view(intent))          # what each global atom is, before any path overrides it
    base.run()
    base.metadata()
    base.reconciliations(list(_g(intent, "reconciliations", []) or []))
    compiled: List[CompiledPath] = []
    scope_records: Dict[str, AtomRecord] = {}    # path-origin atoms, by id
    inherited: Dict[str, Tuple[AtomRecord, List[str]]] = {}   # global atom id -> (record as compiled in the first inheriting path, paths)
    retired_in: Dict[str, List[str]] = {}
    for p in paths:
        sc = _Scope(_path_view(intent, p))
        sc.run()
        compiled.append(CompiledPath(path_id=p.id, label=p.label, strategy=p.strategy, filter_tree=_tree(sc.conditions), audit=sc.audit,
                                     retrieval_title_family=sc.titles, warnings=_dedupe(sc.warnings), normalizations=sc.normalizations))
        for origin, rec in sc.atoms:
            if origin != "global":
                scope_records[rec.atom_id] = rec
            elif rec.atom_id in sc.retired_ids:
                retired_in.setdefault(rec.atom_id, []).append(p.id)
            else:
                inherited.setdefault(rec.atom_id, (rec, []))[1].append(p.id)
    out: List[AtomRecord] = []
    for _o, brec in base.atoms:
        if brec.kind in ("METADATA", "RECORD"):
            out.append(brec)
        elif brec.atom_id in inherited:
            rec, where = inherited[brec.atom_id]
            rec = AtomRecord(**{**rec.__dict__})
            rec.destination = f"{rec.destination} (inherited by paths: {', '.join(where)})"
            if retired_in.get(brec.atom_id):
                rec.justification += f"; retired by reconciliation in: {', '.join(retired_in[brec.atom_id])}"
            out.append(rec)
        elif brec.atom_id in retired_in:
            out.append(AtomRecord(**{**brec.__dict__, "fate": DROPPED_WITH_JUSTIFICATION, "destination": "reconciliation record",
                                     "justification": f"retired by reconciliation in every path ({', '.join(retired_in[brec.atom_id])})"}))
        else:
            out.append(AtomRecord(**{**brec.__dict__, "fate": DROPPED_WITH_JUSTIFICATION, "destination": "path records",
                                     "justification": f"overridden by a path-scoped value in every path ({', '.join(path_ids)}); the path atoms carry the meaning"}))
    out += list(scope_records.values())
    for p in paths:
        out.append(AtomRecord(atom_id=f"path:{p.id}|sourcing_path[0]", concept="sourcing_path", scope=f"path:{p.id}", value=f"{p.id} ({p.strategy}): {p.label}",
                              provenance=_prov(p), strength=None, proficiency=None, relationship=None, fate=ENFORCED,
                              destination=f"paths[{p.id}].filter_tree",
                              justification="compiled as its own independent provider plan (an alternative, never ANDed with another path)"))
    audit: List[CompiledConstraint] = []
    for c in compiled:
        audit += c.audit
    return CompiledPlan(
        filter_tree={"op": "or", "conditions": [{"op": "and", "conditions": c.filter_tree["conditions"]} for c in compiled]},
        audit=audit, retrieval_title_family=compiled[0].retrieval_title_family, taxonomy_version=tax.TAXONOMY_VERSION,
        warnings=_dedupe([w for c in compiled for w in c.warnings]), normalizations=_dedupe([n for c in compiled for n in c.normalizations]),
        atom_audit=out, paths=compiled)


def canonicalize(tree: Dict[str, Any]) -> Any:
    """Order-insensitive canonical form of a boolean filter tree, so semantic
    equality can be asserted regardless of condition ordering."""
    if isinstance(tree, dict) and "op" in tree:
        children = sorted((canonicalize(c) for c in tree["conditions"]), key=lambda x: repr(x))
        return (tree["op"], tuple(children))
    return ("leaf", tree.get("field"), tree.get("type"), repr(tree.get("value")))


def semantic_diff(old_tree: Dict[str, Any], new_tree: Dict[str, Any]) -> List[str]:
    """Compare two provider filter trees at the leaf level and report what
    changed, in plain language — for shadow-mode review."""
    def leaves(tree, acc):
        if isinstance(tree, dict) and "op" in tree:
            for c in tree["conditions"]:
                leaves(c, acc)
        elif isinstance(tree, dict):
            acc.append((tree.get("field"), tree.get("type"), repr(tree.get("value"))))
        return acc
    old = set(leaves(old_tree, []))
    new = set(leaves(new_tree, []))
    out = []
    for f, t, v in sorted(old - new):
        out.append(f"REMOVED: {f} {t} {v}")
    for f, t, v in sorted(new - old):
        out.append(f"ADDED:   {f} {t} {v}")
    if not out:
        out.append("no leaf-level differences")
    return out
