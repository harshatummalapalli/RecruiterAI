"""The downstream consumers' input: the compiled context is the source of truth (offline; no provider, no model call, no scoring).

Before this module the Judge, the evidence builder and admission read the LEGACY `SearchIntent` (core / supporting / differentiator strings, `role.seniority`,
`experience.minimum_years`, `role.title`, `titles.include_titles`) even though the compiler had already decided what every atom means. Now a consumer asks ONE
function, `resolve(intent)`:

    intent.compiled_context is a DownstreamContext  ->  source "compiled": every semantic fact comes from the context. The legacy fields are NOT read for
                                                        meaning; where they differ from the compiled meaning the difference is RECORDED (never reconciled).
    intent.compiled_context is None                 ->  source "legacy": today's behaviour, unchanged.

Nothing here scores, ranks or thresholds. The Judge interface carries no provider syntax (no filter tree, no provider field name).

  JudgeChecklist      what the Judge receives for ONE path: requirements (must have), exclusions (must NOT have), preferences, unresolved items, with tier,
                      proficiency, relationship, provenance and the path. Nothing is flattened across paths.
  AdmissionFacts      the facts admission gates on (target level, accepted levels, experience floor) read from the compiled atoms. Admission's own rules and
                      thresholds are untouched; only the SOURCE of the facts changes.
  Disagreement        a legacy value that differs from the compiled meaning. The compiled meaning wins and the difference is kept.
  PathAttribution     which paths' checklists a candidate's judgments satisfy (a flag per path, no score, no rank, no weight).

See backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.models.search_intent import SearchIntent
from backend.services.downstream_context import (ADMISSION, JUDGE_EXCLUSION, JUDGE_REQUIREMENT, PREFERENCE, PROVIDER_ENFORCED, UNRESOLVED_ITEM, ContextEntry,
                                                 DownstreamContext)

SOURCE_COMPILED, SOURCE_LEGACY = "compiled", "legacy"
MUST_HAVE, MUST_NOT_HAVE, PREFER, UNDECIDED = "must_have", "must_not_have", "prefer", "undecided"
POLARITIES = (MUST_HAVE, MUST_NOT_HAVE, PREFER, UNDECIDED)
_TIERS = ("core", "supporting", "differentiator")


# ======================================================================================================================
# The Judge interface
# ======================================================================================================================


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str                                  # the compiled atom id(s) behind this item ("a + b" when alternatives are grouped)
    concept: str                                  # the atom's concept (skill, seniority.leadership, location.work_mode, semantic_exclusion, ...)
    text: str                                     # the recruiter-meaning text (never a provider expression)
    polarity: str                                 # one of POLARITIES
    tier: Optional[str]                           # core | supporting | differentiator
    judged: bool                                  # the Judge evaluates it against the profile (a positive claim). False = carried and visible, not evaluated
    strength: Optional[str]
    proficiency: Optional[str]
    relationship: Optional[str]                   # None = UNSPECIFIED. It is never read as "current".
    fate: str
    path_id: Optional[str]
    inherited: bool
    provenance: Dict[str, Any]                    # state | sources | quote
    reason: str = ""                              # why it is a preference / unresolved / not judged
    alternatives: Tuple[str, ...] = ()            # an "A or B" group (leadership kinds): satisfying ANY one satisfies the item
    unsupported_qualifiers: Tuple[Dict[str, Any], ...] = ()   # claims the source did not support (not used), with the reason
    value: str = ""                               # the compiled atom's own value (a skill name, "Skill = depth", "A | B"): the Evidence Check reads its subject from it

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["alternatives"] = list(self.alternatives)
        d["unsupported_qualifiers"] = [dict(u) for u in self.unsupported_qualifiers]
        return d


@dataclass(frozen=True)
class JudgeChecklist:
    path_id: Optional[str]
    strategy: Optional[str]
    label: Optional[str]
    provenance_mode: str
    requirements: Tuple[ChecklistItem, ...]       # must have (core tier). Every VERIFIED_DOWNSTREAM atom of this path is here
    exclusions: Tuple[ChecklistItem, ...]         # must NOT have
    preferences: Tuple[ChecklistItem, ...]        # preferred, never required
    unresolved: Tuple[ChecklistItem, ...]         # visible, not decided, each with the reason
    already_enforced: Tuple[ChecklistItem, ...]   # the provider enforced these; informational, not re-required by the Judge

    @property
    def judged(self) -> List[ChecklistItem]:
        """The items the Judge evaluates, requirements first, then judged preferences, in context order."""
        return [i for i in (*self.requirements, *self.preferences) if i.judged]

    @property
    def work_mode(self) -> List[ChecklistItem]:
        return [i for i in self.all_items if i.concept == "location.work_mode"]

    @property
    def proficiencies(self) -> List[ChecklistItem]:
        return [i for i in self.all_items if i.proficiency]

    @property
    def all_items(self) -> List[ChecklistItem]:
        return [*self.requirements, *self.exclusions, *self.preferences, *self.unresolved, *self.already_enforced]

    def signals(self) -> Dict[str, List[str]]:
        """The judged items in the legacy `{core, supporting, differentiator}` text shape (what the Judge asks the model)."""
        out: Dict[str, List[str]] = {t: [] for t in _TIERS}
        for i in self.judged:
            bucket = out[i.tier or "differentiator"]
            if i.text not in bucket:
                bucket.append(i.text)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"path_id": self.path_id, "strategy": self.strategy, "label": self.label, "provenance_mode": self.provenance_mode,
                **{k: [i.to_dict() for i in getattr(self, k)] for k in ("requirements", "exclusions", "preferences", "unresolved", "already_enforced")}}


def _item(e: ContextEntry, ctx: DownstreamContext, polarity: str, judged: bool, reason: str = "") -> ChecklistItem:
    tier = e.tier
    if polarity == PREFER and tier == "core":
        # a preference is never in the core tier (e.g. the allowance "remote is fine" inside a REQUIRED place carries that place's strength): it is carried as a
        # preference with no tier if it is not judged, and judged at the lowest above-differentiator tier if it is
        tier = "supporting" if judged else None
    return ChecklistItem(
        item_id=e.atom_id, concept=e.concept, text=e.text, polarity=polarity, tier=tier, judged=judged, strength=e.strength, proficiency=e.proficiency,
        relationship=e.relationship, fate=e.fate, path_id=ctx.path_id, inherited=e.inherited, provenance=dict(e.provenance), reason=reason, value=e.value,
        unsupported_qualifiers=tuple(dict(u) for u in e.unsupported_qualifiers))


def _group_alternatives(items: List[ChecklistItem]) -> List[ChecklistItem]:
    """Leadership kinds the source accepts as ALTERNATIVES ("people OR technical") are one item: satisfying either satisfies it. (Each kind is its own
    atom in the context; asking the Judge for both as separate requirements would turn an OR into an AND.)"""
    groups: Dict[Tuple[str, str, str, Optional[str]], List[ChecklistItem]] = {}
    order: List[Any] = []
    for i in items:
        if i.concept == "seniority.leadership":
            key = (i.concept, i.polarity, i.tier or "", i.path_id)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(i)
        else:
            order.append(i)
    out: List[ChecklistItem] = []
    for o in order:
        if isinstance(o, ChecklistItem):
            out.append(o)
            continue
        g = groups[o]
        if len(g) == 1:
            out.append(g[0])
            continue
        texts = tuple(x.text for x in g)
        out.append(dataclasses.replace(g[0], item_id=" + ".join(x.item_id for x in g), text=" or ".join(texts).capitalize(), alternatives=texts))
    return out


def judge_checklist_for(ctx: DownstreamContext) -> JudgeChecklist:
    """The Judge's input for ONE path, built only from that path's own context entries (never merged across paths)."""
    req: List[ChecklistItem] = []
    exc: List[ChecklistItem] = []
    pref: List[ChecklistItem] = []
    unres: List[ChecklistItem] = []
    enforced: List[ChecklistItem] = []
    for e in ctx.entries:
        if e.kind == JUDGE_REQUIREMENT:
            req.append(_item(e, ctx, MUST_HAVE, judged=e.route == "downstream_evidence"))
        elif e.kind == JUDGE_EXCLUSION:
            # never part of the positive requirements: the Judge evaluates it in its own exclusion pass (present / not_present, with a verified quote)
            exc.append(_item(e, ctx, MUST_NOT_HAVE, judged=False, reason="a semantic exclusion: the candidate must NOT have this profile (evaluated by the Judge's exclusion pass, separately from the requirements)"))
        elif e.kind == PREFERENCE:
            pref.append(_item(e, ctx, PREFER, judged=e.route == "downstream_evidence", reason=e.justification))
        elif e.kind == UNRESOLVED_ITEM:
            unres.append(_item(e, ctx, UNDECIDED, judged=False, reason=e.justification))
        elif e.kind == PROVIDER_ENFORCED:
            enforced.append(_item(e, ctx, MUST_HAVE, judged=False, reason="enforced upstream by the provider; not re-required by the Judge"))
        # ADMISSION entries belong to AdmissionFacts; records, justified drops and the path entry are not Judge input
    return JudgeChecklist(ctx.path_id, ctx.strategy, ctx.label, ctx.provenance_mode, tuple(_group_alternatives(req)), tuple(exc), tuple(_group_alternatives(pref)),
                          tuple(unres), tuple(enforced))


# ======================================================================================================================
# The admission facts
# ======================================================================================================================


@dataclass(frozen=True)
class AdmissionFacts:
    """What admission's inputs are computed FROM. Admission's rules (level ladder, `evaluate_eligibility`, thresholds) are unchanged: only where the target
    level and the experience floor come from changes."""
    source: str                                   # compiled | legacy
    target_level: Optional[str] = None            # the level the gate compares against (None: no level gating)
    accepted_levels: Tuple[str, ...] = ()         # accepted alternative levels (compiled only)
    minimum_years: Optional[int] = None           # the experience floor (None: no floor)
    atom_ids: Tuple[str, ...] = ()
    provenance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # facts that are visible and deliberately NOT gated on: a preferred level, a level with no approved mapping, an unsupported bound. Never invented.
    ungated: Tuple[Dict[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "target_level": self.target_level, "accepted_levels": list(self.accepted_levels), "minimum_years": self.minimum_years,
                "atom_ids": list(self.atom_ids), "provenance": self.provenance, "ungated": [dict(u) for u in self.ungated]}


_YEARS = re.compile(r"^\s*(\d+)\+ years\s*$")


def _ungated(e: ContextEntry) -> Dict[str, Any]:
    return {"atom_id": e.atom_id, "concept": e.concept, "text": e.text, "fate": e.fate, "kind": e.kind, "reason": e.justification, "provenance": dict(e.provenance)}


def admission_facts_for(ctx: DownstreamContext) -> AdmissionFacts:
    level: Optional[str] = None
    accepted: List[str] = []
    years: Optional[int] = None
    ids: List[str] = []
    prov: Dict[str, Dict[str, Any]] = {}
    ungated: List[Dict[str, Any]] = []
    for e in ctx.entries:
        if e.concept in ("seniority.value", "seniority.alternatives"):
            if e.kind == ADMISSION:
                if e.concept == "seniority.value":
                    level = e.value
                else:
                    accepted.append(e.value)
                ids.append(e.atom_id)
                prov[e.atom_id] = dict(e.provenance)
            else:
                ungated.append(_ungated(e))
        elif e.concept == "experience.min":
            m = _YEARS.match(e.value)
            if e.kind in (PROVIDER_ENFORCED, ADMISSION, JUDGE_REQUIREMENT) and m:
                years = int(m.group(1))
                ids.append(e.atom_id)
                prov[e.atom_id] = dict(e.provenance)
            else:
                ungated.append(_ungated(e))
    return AdmissionFacts(SOURCE_COMPILED, level, tuple(accepted), years, tuple(ids), prov, tuple(ungated))


def _legacy_facts(intent: SearchIntent) -> AdmissionFacts:
    return AdmissionFacts(SOURCE_LEGACY, intent.role.seniority or None, (), intent.experience.minimum_years or None)


# ======================================================================================================================
# Conflicts between the legacy intent and the compiled meaning
# ======================================================================================================================


@dataclass(frozen=True)
class Disagreement:
    """A legacy value that differs from the compiled meaning. The compiled meaning is what the consumer used; the legacy value is kept here so the difference
    is visible and auditable. It is NEVER silently reconciled (no merging, no taking the stricter of two)."""
    field: str
    legacy: Any
    compiled: Any
    winner: str = SOURCE_COMPILED

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "legacy": self.legacy, "compiled": self.compiled, "winner": self.winner}


def _fold(s: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in (s or "").casefold()).split())


def find_disagreements(intent: SearchIntent, facts: AdmissionFacts, judged: Dict[str, List[str]]) -> List[Disagreement]:
    out: List[Disagreement] = []
    legacy_level = (intent.role.seniority or None)
    if _fold(legacy_level or "") != _fold(facts.target_level or ""):
        out.append(Disagreement("seniority", legacy_level, facts.target_level))
    legacy_years = intent.experience.minimum_years or None
    if legacy_years != facts.minimum_years:
        out.append(Disagreement("experience.minimum_years", legacy_years, facts.minimum_years))
    for tier, attr in (("core", "core_signals"), ("supporting", "supporting_signals"), ("differentiator", "differentiator_signals")):
        legacy = list(getattr(intent, attr) or [])
        compiled = judged.get(tier, [])
        compiled_all = {_fold(t) for ts in judged.values() for t in ts}
        for t in legacy:
            if _fold(t) not in compiled_all:
                out.append(Disagreement(f"signal.{tier}", t, None))           # a legacy requirement the compiled context does not carry: NOT used
        legacy_all = {_fold(t) for a in ("core_signals", "supporting_signals", "differentiator_signals") for t in (getattr(intent, a) or [])}
        for t in compiled:
            if _fold(t) not in legacy_all:
                out.append(Disagreement(f"signal.{tier}", None, t))           # a compiled requirement the legacy intent does not state: used
    return out


# ======================================================================================================================
# The single resolver every consumer calls
# ======================================================================================================================


@dataclass
class ConsumerInput:
    source: str                                   # compiled | legacy
    judged: List[Tuple[str, str]]                 # (tier, text) in the order the Judge asks them
    judged_items: List[Optional[ChecklistItem]]   # the checklist item behind each judged text (None in legacy mode)
    facts: AdmissionFacts
    role_title: Optional[str]
    include_titles: List[str]
    checklist: Optional[JudgeChecklist] = None
    disagreements: List[Disagreement] = field(default_factory=list)

    def signals(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {t: [] for t in _TIERS}
        for tier, text in self.judged:
            out[tier].append(text)
        return out


def _titles_for(ctx: DownstreamContext) -> Tuple[Optional[str], List[str]]:
    role: Optional[str] = None
    family: List[str] = []
    for e in ctx.entries:
        if e.concept == "role_family" and e.kind == PROVIDER_ENFORCED:
            role = role or e.value
            family += [c["value"] for c in e.components if c.get("component") == "retrieval_title"]
    return role, family


def resolve(intent: SearchIntent) -> ConsumerInput:
    """What a downstream consumer reads. Compiled when `intent.compiled_context` is present, legacy when it is absent. A present-but-wrong-typed value is an
    error, never a silent fall back to the legacy meaning."""
    ctx = getattr(intent, "compiled_context", None)
    if ctx is None:
        legacy = [(t, s) for t, ss in (("core", intent.core_signals), ("supporting", intent.supporting_signals), ("differentiator", intent.differentiator_signals)) for s in ss]
        return ConsumerInput(SOURCE_LEGACY, legacy, [None] * len(legacy), _legacy_facts(intent), intent.role.title, list(intent.titles.include_titles))
    if not isinstance(ctx, DownstreamContext):
        raise TypeError(f"SearchIntent.compiled_context must be a DownstreamContext or None, not {type(ctx).__name__}")
    checklist = judge_checklist_for(ctx)
    items = checklist.judged
    judged = [(i.tier or "differentiator", i.text) for i in items]
    # one (tier, text) is asked once
    seen, jd, ji = set(), [], []
    for pair, it in zip(judged, items):
        if pair not in seen:
            seen.add(pair)
            jd.append(pair)
            ji.append(it)
    facts = admission_facts_for(ctx)
    title, family = _titles_for(ctx)
    ci = ConsumerInput(SOURCE_COMPILED, jd, ji, facts, title, family, checklist)
    ci.disagreements = find_disagreements(intent, facts, ci.signals())
    return ci


def judged_signals(intent: SearchIntent) -> Dict[str, List[str]]:
    """The tiered requirement texts the Judge asks about (compiled when available, else the legacy lists)."""
    return resolve(intent).signals()


def role_facts_for(intent: SearchIntent) -> AdmissionFacts:
    return resolve(intent).facts


# ======================================================================================================================
# Adapters: compiled plan -> per-path search intents; path attribution
# ======================================================================================================================


def search_intent_for_context(ctx: DownstreamContext, base: Optional[SearchIntent] = None) -> SearchIntent:
    """A `SearchIntent` whose downstream meaning is `ctx`. `base` (the production-shaped legacy intent, which still drives the provider search and the
    natural-language query) is kept as is; only `compiled_context` is added. Without a base the legacy fields are EMPTY (nothing is reconstructed)."""
    return dataclasses.replace(base, compiled_context=ctx) if base is not None else SearchIntent(compiled_context=ctx)


def search_intents_from_contexts(contexts: Iterable[DownstreamContext], base: Optional[SearchIntent] = None) -> List[SearchIntent]:
    return [search_intent_for_context(c, base) for c in contexts]


@dataclass(frozen=True)
class PathAttribution:
    """Which of a path's checklist items a candidate's judgments evidence. A flag, not a score: no rank, no weight, no path ordering."""
    path_id: Optional[str]
    met: Tuple[str, ...]
    partly: Tuple[str, ...]
    not_evidenced: Tuple[str, ...]
    satisfies_required: bool                      # every judged must-have item of THIS path has a verified `met`

    def to_dict(self) -> Dict[str, Any]:
        return {"path_id": self.path_id, "met": list(self.met), "partly": list(self.partly), "not_evidenced": list(self.not_evidenced), "satisfies_required": self.satisfies_required}


def attribute_path(path_id: Optional[str], checklist: JudgeChecklist, judgments: List[Dict[str, Any]]) -> PathAttribution:
    by = {(j.get("tier"), j.get("signal_text")): j.get("verdict") for j in judgments or []}
    met: List[str] = []
    partly: List[str] = []
    no: List[str] = []
    for i in checklist.requirements:
        if not i.judged:
            continue
        v = by.get((i.tier or "differentiator", i.text), "not_evidenced")
        (met if v == "met" else partly if v == "partly" else no).append(i.text)
    return PathAttribution(path_id, tuple(met), tuple(partly), tuple(no), not partly and not no)


def attribute_paths(candidate: Any, intents: List[SearchIntent], judge: Any, harvest_evidence: Any = None) -> List[PathAttribution]:
    """Judge ONE candidate against EACH path's own checklist (never a union) and say which paths it satisfies: A, B, both or neither."""
    out: List[PathAttribution] = []
    for intent in intents:
        ci = resolve(intent)
        assert ci.checklist is not None, "path attribution needs a compiled context"
        out.append(attribute_path(ci.checklist.path_id, ci.checklist, judge.judge(candidate, intent, harvest_evidence) or []))
    return out
