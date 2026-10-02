"""Phase 2 — Structured Hiring Intent (the compiler's input).

This is what the LLM (evolved Task A/B) emits: **what the recruiter means**,
never how to execute it. The compiler (Phase 3) decides enforcement; this model
must never carry a provider field name, operator, or routing decision. A
model-level validator enforces that boundary.

Logical composition is deliberately capped at two levels (consensus scoping
guard): the whole intent is an implicit AND of dimensions; OR lives *inside* a
dimension (location entries, education degrees/streams, and explicit
`skill_any_of` groups). There is no general expression tree — this is a hiring
intent, not a query DSL.

Additive and shadow-safe: a NEW model + NEW prompt, run alongside the existing
RoleUnderstanding/Task A-B path, which is left untouched until the compiler is
proven.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Strength = str      # "required" | "preferred" | "context"
Relationship = str  # "current" | "past" | "any"
Archetype = str     # "title_defined" | "skill_defined" | "hybrid"

_STRENGTHS = {"required", "preferred", "context"}
_RELATIONSHIPS = {"current", "past", "any"}
_ARCHETYPES = {"title_defined", "skill_defined", "hybrid"}

# Substrings that betray provider mechanics leaking into intent. The LLM must
# describe meaning; if any of these appears in a string value, Task A/B smuggled
# in execution detail and the intent is rejected.
_PROVIDER_LEAK_TOKENS = (
    "employment_details", "basic_profile", "company_headcount", "years_of_experience_raw",
    "professional_network", "field_of_study", "geo_distance", "not_in", "crustdata",
    ".title", ".description", ".company_name", "(.)", "(!)", "[.]",
)


class RoleArchetype(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Archetype
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=300)  # one tiny sentence; not a reasoning artifact

    @field_validator("value")
    @classmethod
    def _archetype(cls, v: str) -> str:
        if v not in _ARCHETYPES:
            raise ValueError(f"archetype must be one of {_ARCHETYPES}")
        return v


class _Strengthed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: Strength = "required"

    @field_validator("strength")
    @classmethod
    def _strength(cls, v: str) -> str:
        if v not in _STRENGTHS:
            raise ValueError(f"strength must be one of {_STRENGTHS}")
        return v


class SkillReq(_Strengthed):
    name: str
    relationship: Relationship = "current"

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v: str) -> str:
        if v not in _RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {_RELATIONSHIPS}")
        return v


class SkillAnyOf(_Strengthed):
    """An OR group of skills — the brief's 'X and/or Y' / 'X or Y'."""
    any_of: List[str] = Field(min_length=2)
    relationship: Relationship = "current"

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v: str) -> str:
        if v not in _RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {_RELATIONSHIPS}")
        return v


class CompanyReq(_Strengthed):
    name: str
    relationship: Relationship = "any"

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v: str) -> str:
        if v not in _RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {_RELATIONSHIPS}")
        return v


class CompanyScale(_Strengthed):
    minimum_employees: int = Field(gt=0)
    relationship: Relationship = "current"

    @field_validator("relationship")
    @classmethod
    def _rel(cls, v: str) -> str:
        if v not in _RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {_RELATIONSHIPS}")
        return v


class Education(_Strengthed):
    degrees: List[str] = Field(default_factory=list)   # OR
    streams: List[str] = Field(default_factory=list)   # OR


class Seniority(_Strengthed):
    value: str  # "Junior" | "Mid" | "Senior" | "Lead" | "Principal" | "Director" ... (recruiter's word)


class Experience(_Strengthed):
    minimum_years: Optional[int] = None
    maximum_years: Optional[int] = None


class Radius(BaseModel):
    """A commute radius anchored on a place, kept distinct from a plain city
    match ("Hyderabad" vs "within 25 miles of Hyderabad"). The anchor is
    preserved so the compiler never has to guess what the radius is around."""
    model_config = ConfigDict(extra="forbid")
    value: int = Field(gt=0)
    unit: str = "miles"   # "miles" | "km"
    around: str           # the anchor place, e.g. "Hyderabad, Telangana, India"


class LocationReq(_Strengthed):
    entries: List[str] = Field(default_factory=list)   # OR (e.g. "Hyderabad, Telangana, India")
    radius: Optional[Radius] = None


# Exclusion is its own explicit list because exclude is NOT the inverse of a
# required include. kind: company exclusions carry a relationship
# ("exclude_current_company" | "exclude_past_company" | "exclude_any_company"),
# plus "exclude_title" | "current_company" (legacy alias for exclude_current_company).
class Exclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    value: str


class EvidenceSignal(_Strengthed):
    """A capability/narrative signal verified downstream (judge) and used for
    relevance context — never a hard provider filter."""
    name: str


class StructuredHiringIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_archetype: RoleArchetype
    # The role(s) the recruiter ACTUALLY expressed (source), normalized only for
    # wording with seniority stripped into `seniority`. This is NOT the broad
    # retrieval title family — the compiler (Phase 3) expands this into an
    # approved retrieval family via the role-family taxonomy. Extraction
    # preserves meaning; compilation expands representation.
    role_family: List[str] = Field(min_length=1)
    seniority: Optional[Seniority] = None
    skills: List[SkillReq] = Field(default_factory=list)
    skill_any_of: List[SkillAnyOf] = Field(default_factory=list)
    companies: List[CompanyReq] = Field(default_factory=list)
    company_scale: Optional[CompanyScale] = None
    education: Optional[Education] = None
    experience: Optional[Experience] = None
    location: Optional[LocationReq] = None
    exclusions: List[Exclusion] = Field(default_factory=list)
    evidence_signals: List[EvidenceSignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_provider_leak(self) -> "StructuredHiringIntent":
        """Boundary enforcement: meaning only, never provider mechanics."""
        def scan(value) -> None:
            if isinstance(value, str):
                low = value.lower()
                for tok in _PROVIDER_LEAK_TOKENS:
                    if tok in low:
                        raise ValueError(
                            f"provider mechanics leaked into intent: {tok!r} found in {value!r}. "
                            "Task A/B must emit meaning, not routing/fields."
                        )
            elif isinstance(value, BaseModel):
                for v in value.__dict__.values():
                    scan(v)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    scan(v)
        scan(self)
        return self


def parse_structured_intent(raw_json: str) -> StructuredHiringIntent:
    """Parse + validate LLM JSON into a StructuredHiringIntent (raises on invalid)."""
    return StructuredHiringIntent.model_validate_json(raw_json)
