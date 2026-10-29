"""RoleModel — the one canonical, immutable description of a role.

Built once by the Intake agent; read (never re-derived) by every agent after
it. Frozen on purpose: a stage that needs a different value builds a new model
with provenance, it never mutates this one. See recruiter/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from recruiter.role_model.provenance import Provenance
from recruiter.role_model.seniority import Seniority

TIERS = ("core", "supporting", "differentiator")
# When in the career the requirement must hold. 'past' = acceptable background,
# not required now (e.g. "came from a Java background"); 'current' = must be
# doing it now; 'any' = anytime in the career.
WHEN = ("past", "current", "any")


@dataclass(frozen=True)
class Requirement:
    """One capability the role needs, in its own tier. `hard` means the
    recruiter/role marks it a precise must-have the Briefing agent may try to
    enforce as a filter; otherwise it is a soft signal for retrieval + ranking.
    `when` separates present demands from acceptable background."""

    text: str
    tier: str
    provenance: Provenance
    hard: bool = False
    when: str = "any"

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown requirement tier: {self.tier!r}")
        if self.when not in WHEN:
            raise ValueError(f"unknown requirement 'when': {self.when!r}")


@dataclass(frozen=True)
class CapabilityGroup:
    """One role-defining capability expressed as interchangeable surface terms
    (OR'd), e.g. AI → (AI, ML, machine learning, LLM, …). Enforced as a single
    any-of filter by Briefing. `rationale` is one plain sentence for the human."""

    label: str
    terms: Tuple[str, ...]
    source_qualifier: str
    rationale: str


@dataclass(frozen=True)
class Location:
    """Geography is multi-value from the start — cities is first-class, so a
    three-city role never collapses to one. work_mode is recorded for the
    recruiter but is a known non-filter on the provider (see limitations)."""

    countries: Tuple[str, ...] = ()
    states: Tuple[str, ...] = ()
    cities: Tuple[str, ...] = ()
    # Soft preference: cities to PREFER (named in the NL query for a relevance
    # boost) without excluding anyone — e.g. "ok anywhere in India, prefer these
    # three". Never a hard filter; the hard scope stays countries/states/cities.
    preferred_cities: Tuple[str, ...] = ()
    radius_place: Optional[str] = None
    radius_miles: Optional[float] = None
    work_mode: Optional[str] = None

    @property
    def is_multi_city(self) -> bool:
        return len(self.cities) > 1


@dataclass(frozen=True)
class CompanyRules:
    exclude_current: Tuple[str, ...] = ()
    exclude_ever: Tuple[str, ...] = ()
    prefer_current: Tuple[str, ...] = ()
    prefer_ever: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleModel:
    identity: str                      # title-shaped candidate identity
    seniority: Seniority               # years only — the gate
    # The role's target level (ic | architect | manager | director+). Derived
    # once by Intake (see levels.classify_role_level); read by ranking (to flag
    # above/below fit) and by Intake (to pick default title exclusions). Never
    # gates a candidate.
    role_level: Optional[str]
    location: Location
    requirements: Tuple[Requirement, ...] = ()
    capability_groups: Tuple[CapabilityGroup, ...] = ()
    companies: CompanyRules = field(default_factory=CompanyRules)
    exclude_titles: Tuple[str, ...] = ()
    posted_title: Optional[str] = None
    posted_title_source: Optional[str] = None
    employment_type: Optional[str] = None
    hiring_company: Optional[str] = None
    # Things recorded but NOT enforceable downstream — shown to the recruiter,
    # never silently dropped (the honesty guarantee).
    limitations: Tuple[str, ...] = ()
    # Stable id of the confirmed model (set at confirmation).
    model_id: Optional[str] = None

    def tier(self, name: str) -> Tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if r.tier == name)

    @property
    def core(self) -> Tuple[Requirement, ...]:
        return self.tier("core")

    @property
    def hard_requirements(self) -> Tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if r.hard)
