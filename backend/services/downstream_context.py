"""The downstream execution context: what survives the compiler boundary (offline; no provider, no model, no scoring).

The compiled plan is for the PROVIDER (a filter tree) and for the audit. Everything the compiler did NOT make a provider filter is meaning that
a downstream consumer (the Judge, the admission gate, the recruiter UI) must still receive: the semantic exclusions, the proficiencies, the work mode,
the leadership kinds, the domain, the preferences, the unresolved items, the provenance, the path. This module turns a `CompiledPlan` into explicit,
per-path `DownstreamContext` objects with ONE entry per intent atom and its fate.

Nothing here ranks, scores or thresholds. A context is NEVER flattened across paths: each path has its own, and an atom stated globally appears in each
path's context marked `inherited`, an atom stated in a path appears only in that path's context.

`to_judge_signals` renders a context in the shape the existing RequirementJudge consumes (`core` / `supporting` / `differentiator` strings).
`legacy_consumer_gaps` lists, atom by atom, what the CURRENT consumers cannot accept (DOWNSTREAM CONTRACT GAP): they stay in the context, never discarded.
See backend/services/RUNTIME_INTEGRATION_CONTRACT.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from backend.services.compiler_audit import _STRENGTH_TIER
from backend.services.search_compiler import (CompiledPlan, AtomRecord, DROPPED_WITH_JUSTIFICATION, ENFORCED, NORMALIZED, PREFERENCE_CONTEXT, UNRESOLVED,
                                              VERIFIED_DOWNSTREAM)

# entry kinds
PROVIDER_ENFORCED = "provider_enforced"
JUDGE_REQUIREMENT = "judge_requirement"
JUDGE_EXCLUSION = "judge_exclusion"
ADMISSION = "admission"
PREFERENCE = "preference"
UNRESOLVED_ITEM = "unresolved"
JUSTIFIED_DROP = "justified_drop"
RECORD = "record"
PATH = "path"
KINDS = (PROVIDER_ENFORCED, JUDGE_REQUIREMENT, JUDGE_EXCLUSION, ADMISSION, PREFERENCE, UNRESOLVED_ITEM, JUSTIFIED_DROP, RECORD, PATH)


@dataclass(frozen=True)
class ContextEntry:
    atom_id: str
    concept: str
    value: str                       # the intent atom's own value (the text below is what a consumer reads)
    kind: str                        # one of KINDS
    scope: str                       # where the atom was STATED: "global" or "path:<id>"
    inherited: bool                  # stated globally and applied in this context (never True for an atom stated in a path)
    text: str                        # the recruiter-meaning text a consumer reads
    tier: Optional[str]              # core | supporting | differentiator (from the atom's strength)
    strength: Optional[str]
    proficiency: Optional[str]
    relationship: Optional[str]
    fate: str
    destination: str
    justification: str
    route: str
    provenance: Dict[str, Any]
    components: List[Dict[str, Any]] = field(default_factory=list)
    unsupported_qualifiers: List[Dict[str, Any]] = field(default_factory=list)   # claims the intent made that its cited source does not support (not used)


def _kind(a: AtomRecord) -> str:
    if a.concept == "sourcing_path":
        return PATH
    if a.fate in (ENFORCED, NORMALIZED):
        return PROVIDER_ENFORCED
    if a.fate == VERIFIED_DOWNSTREAM:
        return {"downstream_exclusion": JUDGE_EXCLUSION, "admission_level_fit": ADMISSION}.get(a.route, JUDGE_REQUIREMENT)
    if a.fate == PREFERENCE_CONTEXT:
        return PREFERENCE
    if a.fate == UNRESOLVED:
        return UNRESOLVED_ITEM
    if a.fate == DROPPED_WITH_JUSTIFICATION:
        return RECORD if a.kind in ("RECORD", "METADATA") else JUSTIFIED_DROP
    return JUDGE_REQUIREMENT


def _entry(a: AtomRecord) -> ContextEntry:
    return ContextEntry(atom_id=a.atom_id, concept=a.concept, value=a.value, kind=_kind(a), scope=a.scope, inherited=(a.scope == "global" and a.kind == "MEANING"),
                        text=a.downstream_text or a.value, tier=_STRENGTH_TIER.get(a.strength) if a.strength else None, strength=a.strength,
                        proficiency=a.proficiency, relationship=a.relationship, fate=a.fate, destination=a.destination, justification=a.justification,
                        route=a.route, provenance=dict(a.provenance), components=list(a.components),
                        unsupported_qualifiers=list(a.unsupported_qualifiers))


@dataclass
class DownstreamContext:
    path_id: Optional[str]           # None = the intent has no sourcing paths (one global context)
    strategy: Optional[str]
    label: Optional[str]
    provider_plan: Dict[str, Any]    # THIS path's own provider filter tree
    entries: List[ContextEntry]      # ONE per atom that applies here, each with its fate
    provenance_mode: str = "legacy"
    sources_supplied: bool = False
    warnings: List[str] = field(default_factory=list)

    def of_kind(self, *kinds: str) -> List[ContextEntry]:
        return [e for e in self.entries if e.kind in kinds]

    @property
    def inherited(self) -> List[ContextEntry]:
        return [e for e in self.entries if e.inherited]

    @property
    def path_specific(self) -> List[ContextEntry]:
        return [e for e in self.entries if e.scope.startswith("path:")]

    @property
    def requirements(self) -> List[ContextEntry]:
        return self.of_kind(JUDGE_REQUIREMENT)

    @property
    def exclusions(self) -> List[ContextEntry]:
        return self.of_kind(JUDGE_EXCLUSION)

    @property
    def preferences(self) -> List[ContextEntry]:
        return self.of_kind(PREFERENCE)

    @property
    def unresolved(self) -> List[ContextEntry]:
        return self.of_kind(UNRESOLVED_ITEM)

    @property
    def location(self) -> Dict[str, List[Dict[str, str]]]:
        """The place this context applies to, as stated (entries, countries, radius, remote, work mode), each with its fate. Geography and work mode stay separate."""
        out: Dict[str, List[Dict[str, str]]] = {}
        for e in self.entries:
            if e.concept.startswith("location."):
                out.setdefault(e.concept.split(".", 1)[1], []).append({"text": e.text, "fate": e.fate, "scope": e.scope})
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"path_id": self.path_id, "strategy": self.strategy, "label": self.label, "provider_plan": self.provider_plan,
                "provenance_mode": self.provenance_mode, "sources_supplied": self.sources_supplied, "warnings": list(self.warnings),
                "entries": [asdict(e) for e in self.entries]}


def build_downstream_contexts(plan: CompiledPlan) -> List[DownstreamContext]:
    """One context per sourcing path (each from that path's OWN atoms), or one global context. Never merged."""
    shared = [a for a in plan.atom_audit if a.kind in ("METADATA", "RECORD")]
    if not plan.paths:
        return [DownstreamContext(None, None, None, plan.filter_tree, [_entry(a) for a in plan.atom_audit], plan.provenance_mode, plan.sources_supplied, list(plan.warnings))]
    out: List[DownstreamContext] = []
    for p in plan.paths:
        scope = f"path:{p.path_id}"
        own = [a for a in plan.atom_audit if a.concept == "sourcing_path" and a.scope == scope]
        applicable_records = [a for a in shared if a.scope in ("global", scope)]
        atoms = own + list(p.atom_audit) + applicable_records
        out.append(DownstreamContext(p.path_id, p.strategy, p.label, p.filter_tree, [_entry(a) for a in atoms], plan.provenance_mode, plan.sources_supplied, list(p.warnings)))
    return out


def to_judge_signals(ctx: DownstreamContext) -> Dict[str, List[str]]:
    """The context rendered as the existing Judge's input shape (positive signals by tier). It is an ADAPTER: it adds no signal the compiler did not
    route to the Judge and it scores nothing. Negatives, unresolved items, provenance and the path are NOT representable here (see legacy_consumer_gaps)."""
    out: Dict[str, List[str]] = {"core": [], "supporting": [], "differentiator": []}
    for e in ctx.entries:
        if e.route == "downstream_evidence" and e.kind in (JUDGE_REQUIREMENT, PREFERENCE):
            bucket = out[e.tier or "differentiator"]
            if e.text not in bucket:
                bucket.append(e.text)
    return out


# What the CURRENT consumers cannot accept. Each code is a DOWNSTREAM CONTRACT GAP / LEGACY DOWNSTREAM CONSUMER finding.
GAPS = {
    "NO_NEGATIVE_SLOT": "the Judge's input (SearchIntent core/supporting/differentiator strings) has no way to say 'the candidate must NOT have this profile'",
    "NO_UNRESOLVED_SLOT": "no consumer has a place for an unresolved item (an unknown level, a work mode no provider can filter); it would be dropped",
    "ADMISSION_READS_LEGACY_INTENT": "admission reads RoleAlignment from the legacy `intent.role.seniority` / `experience`, not from the compiled plan",
    "PREFERENCE_NOT_FORWARDED": "a preference the compiler kept as context (a company, an education, a place) is not forwarded to any Judge signal or ranking input",
}
STRUCTURAL_GAPS = {
    "NO_PROVENANCE_FIELD": "SearchIntent signals are bare strings: provenance (source, quote, state) cannot travel with them",
    "NO_PATH_CONTEXT": "SearchIntent has no path: one intent is one search, so per-path requirements cannot be expressed in it",
}


def legacy_consumer_gaps(ctx: DownstreamContext) -> List[Dict[str, str]]:
    """Per atom: why the current Judge / admission input cannot accept it. The entry stays in the context (it is never discarded)."""
    gaps: List[Dict[str, str]] = []
    for e in ctx.entries:
        code = None
        if e.kind == JUDGE_EXCLUSION:
            code = "NO_NEGATIVE_SLOT"
        elif e.kind == UNRESOLVED_ITEM:
            code = "NO_UNRESOLVED_SLOT"
        elif e.kind == ADMISSION:
            code = "ADMISSION_READS_LEGACY_INTENT"
        elif e.kind == PREFERENCE and e.route != "downstream_evidence":
            code = "PREFERENCE_NOT_FORWARDED"
        if code:
            gaps.append({"atom_id": e.atom_id, "concept": e.concept, "kind": e.kind, "gap": code, "reason": GAPS[code]})
    return gaps
