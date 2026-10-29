"""Intake's own small data shapes: the LLM's structured read of the notes
(`Understanding`), a clarification `Question`, and the `IntakeOutcome`.

`Understanding` is deliberately provider-agnostic and boundary-blind — it is
what the reader got from the hiring notes alone. The boundary (recruiter facts)
is applied later, in assemble.py, so the two readings stay independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from recruiter.role_model import RoleModel


@dataclass(frozen=True)
class ReadRequirement:
    text: str
    tier: str                      # core | supporting | differentiator
    evidence: Optional[str] = None  # the notes span, when stated
    when: str = "any"              # past | current | any (see temporal.py)


@dataclass(frozen=True)
class Understanding:
    identity: str
    requirements: Tuple[ReadRequirement, ...] = ()
    posted_title: Optional[str] = None
    posted_title_source: Optional[str] = None   # "recruiter" | "jd" | None
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    employment_type: Optional[str] = None
    work_mode_in_notes: Optional[str] = None


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    kind: str                      # min_years | capability_confirm | multi_select | rank | choice | free_text | confirm
    routing: str = ""              # how the answer is used: filter | query | judge | ranking | confirm (+combos)
    required: bool = False         # blocks the search until answered (only years today)
    options: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IntakeOutcome:
    """A ready RoleModel plus any optional refinement questions, OR the required
    clarifications that block the search until answered."""

    model: Optional[RoleModel] = None
    clarifications: Tuple[Question, ...] = ()   # required/blocking (e.g. missing years)
    refinements: Tuple[Question, ...] = ()      # optional, surfaced on the brief

    @property
    def ready(self) -> bool:
        return self.model is not None and not self.clarifications
