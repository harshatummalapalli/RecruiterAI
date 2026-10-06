"""EXPERIMENTAL extension of StructuredHiringIntent for the Role 1 intake experiment (EXPERIMENT ONLY).

Not a new contract: `ExperimentalHiringIntent` IS a `StructuredHiringIntent` (a subclass). Every field of the production
model is unchanged and still validates, and an existing intent JSON validates as an experimental one with the new
fields empty. Production code does not import this module; deleting the experiment directory removes it entirely.

Each addition exists because a baseline assertion failed without it (see DESIGN.md, which records the field-by-field
justification and the alternatives rejected). In short:

    sourcing_paths        alternative legitimate ways to source the role; each carries ONLY what differs from the
                          global intent (override semantics, see `effective_view`)
    domain                the work domain a candidate's evidence should show, with its own strength
    semantic_exclusions   a negative CONCEPT (work type), not a company or a title
    reconciliations       explicit JD-vs-brief decisions that leave no surviving atom (a dropped/narrowed/waived
                          JD item, or an unresolved conflict)
    basis (on each atom)  who claims the atom: sources + a short verbatim quote. The model's claim only; code verifies
    proficiency           on a skill: hands_on | working_knowledge (strength says how much it is wanted, not how well)
    leadership            on seniority: which kinds of leadership satisfy "Lead" (people / technical)

Nothing here names a provider field, an operator or a routing decision, and the production leak validator still runs
over every new string.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.structured_intent import (
    CompanyReq,
    Education,
    EvidenceSignal,
    Exclusion,
    Experience,
    LocationReq,
    Seniority,
    SkillAnyOf,
    SkillReq,
    StructuredHiringIntent,
    _Strengthed,
)

SOURCES = ("jd", "recruiter_brief", "approved_knowledge", "inferred")
PROFICIENCIES = ("hands_on", "working_knowledge")
STRATEGIES = ("domain_led", "capability_led", "hybrid")
LEADERSHIP_MODES = ("people", "technical")
# What a reconciliation says the recruiter brief did to a JD item. "unresolved" = the sources conflict and the brief
# does not settle it: surfaced, never silently resolved.
RECONCILIATION_ACTIONS = ("narrowed", "waived", "contradicted", "unresolved")


def _member(value: str, allowed: tuple, label: str) -> str:
    if value not in allowed:
        raise ValueError(f"{label} must be one of {allowed}")
    return value


class Basis(BaseModel):
    """What the MODEL claims supports an atom. Never trusted: code checks the quote against the supplied text."""
    model_config = ConfigDict(extra="forbid")
    sources: List[str] = Field(min_length=1)
    quote: Optional[str] = Field(default=None, max_length=300)  # short verbatim excerpt; no line numbers

    @field_validator("sources")
    @classmethod
    def _sources(cls, v: List[str]) -> List[str]:
        for s in v:
            _member(s, SOURCES, "source")
        return v


class _Based(BaseModel):
    basis: Optional[Basis] = None


# --- the production atoms, each plus a `basis` -----------------------------------------------------------------


class XSkillReq(SkillReq, _Based):
    proficiency: Optional[str] = None

    @field_validator("proficiency")
    @classmethod
    def _prof(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _member(v, PROFICIENCIES, "proficiency")


class XSkillAnyOf(SkillAnyOf, _Based):
    pass


class XCompanyReq(CompanyReq, _Based):
    pass


class XEducation(Education, _Based):
    pass


class XSeniority(Seniority, _Based):
    # Which kinds of leadership satisfy the level. ["people","technical"] means people OR technical.
    leadership: List[str] = Field(default_factory=list)

    @field_validator("leadership")
    @classmethod
    def _lead(cls, v: List[str]) -> List[str]:
        for m in v:
            _member(m, LEADERSHIP_MODES, "leadership mode")
        return v


class XExperience(Experience, _Based):
    pass


class XLocationReq(LocationReq, _Based):
    pass


class XEvidenceSignal(EvidenceSignal, _Based):
    pass


class XExclusion(Exclusion, _Based):
    pass


# --- new concepts ----------------------------------------------------------------------------------------------


class DomainReq(_Strengthed, _Based):
    """The work domain / problem space a candidate's evidence should show (not a skill, not a company)."""
    name: str


class SemanticExclusion(_Based):
    """A work type to screen out, stated as meaning. `includes` are the examples the recruiter named. What a provider
    can enforce, and what needs evidence verification, is a later compiler decision."""
    model_config = ConfigDict(extra="forbid")
    concept: str
    includes: List[str] = Field(default_factory=list)


class SourcingPath(_Based):
    """One alternative way to source the role. Inherits the global intent; fields set here REPLACE the global value for
    this path (singletons) or the same-named entry (lists), and anything else is added."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=24)
    label: str
    strategy: str
    seniority: Optional[XSeniority] = None
    experience: Optional[XExperience] = None
    location: Optional[XLocationReq] = None
    skills: List[XSkillReq] = Field(default_factory=list)
    domain: List[DomainReq] = Field(default_factory=list)

    @field_validator("strategy")
    @classmethod
    def _strategy(cls, v: str) -> str:
        return _member(v, STRATEGIES, "strategy")


class Reconciliation(BaseModel):
    """A JD-vs-brief decision that leaves no surviving atom to carry it."""
    model_config = ConfigDict(extra="forbid")
    topic: str
    action: str
    jd_quote: Optional[str] = Field(default=None, max_length=300)
    brief_quote: Optional[str] = Field(default=None, max_length=300)
    result: str = Field(max_length=300)   # what the intent now says, in one sentence
    path_id: Optional[str] = None         # None = global

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        return _member(v, RECONCILIATION_ACTIONS, "reconciliation action")


class ExperimentalHiringIntent(StructuredHiringIntent):
    seniority: Optional[XSeniority] = None
    skills: List[XSkillReq] = Field(default_factory=list)
    skill_any_of: List[XSkillAnyOf] = Field(default_factory=list)
    companies: List[XCompanyReq] = Field(default_factory=list)
    education: Optional[XEducation] = None
    experience: Optional[XExperience] = None
    location: Optional[XLocationReq] = None
    exclusions: List[XExclusion] = Field(default_factory=list)
    evidence_signals: List[XEvidenceSignal] = Field(default_factory=list)

    domain: List[DomainReq] = Field(default_factory=list)
    semantic_exclusions: List[SemanticExclusion] = Field(default_factory=list)
    sourcing_paths: List[SourcingPath] = Field(default_factory=list)
    reconciliations: List[Reconciliation] = Field(default_factory=list)


def parse_experimental_intent(raw_json: str) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate_json(raw_json)


# --- override semantics (pure data resolution; this is NOT compiler support) -------------------------------------


def effective_view(intent: ExperimentalHiringIntent, path_id: str) -> Dict[str, object]:
    """What one path means once the global intent and the path's overrides are resolved. Singletons the path sets
    replace the global value; same-named skills/domains are replaced; anything else is added."""
    path = next((p for p in intent.sourcing_paths if p.id == path_id), None)
    if path is None:
        raise KeyError(path_id)

    def merge(global_items: List, path_items: List, key) -> List:
        by_key = {key(i): i for i in global_items}
        for item in path_items:
            by_key[key(item)] = item
        return list(by_key.values())

    return {
        "path": path,
        "seniority": path.seniority or intent.seniority,
        "experience": path.experience or intent.experience,
        "location": path.location or intent.location,
        "skills": merge(intent.skills, path.skills, lambda s: s.name.strip().lower()),
        "domain": merge(intent.domain, path.domain, lambda d: d.name.strip().lower()),
        "semantic_exclusions": list(intent.semantic_exclusions),  # global in Role 1; no path-scoped negative observed
    }


def schema_concepts() -> Dict[str, bool]:
    """Which strategy concepts the EXPERIMENTAL schema has a typed place for (introspection, not model output)."""
    fields = set(ExperimentalHiringIntent.model_fields)
    path_fields = set(SourcingPath.model_fields)
    return {
        "sourcing_paths": "sourcing_paths" in fields,
        "path_strategy": "strategy" in path_fields,
        "path_scoped_location": "location" in path_fields,
        "path_scoped_requirements": bool({"skills", "domain", "experience", "seniority"} & path_fields),
        "proficiency": "proficiency" in XSkillReq.model_fields,
        "semantic_exclusions": "semantic_exclusions" in fields,
        "leadership": "leadership" in XSeniority.model_fields,
        "domain": "domain" in fields,
        "provenance": "basis" in XSkillReq.model_fields and "basis" in SourcingPath.model_fields,
        "reconciliations": "reconciliations" in fields,
    }
