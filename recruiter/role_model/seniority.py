"""Seniority = years of experience. That's the whole gate.

Years are objective, portable across companies, and the only seniority signal
CrustData can actually hard-filter on. A title *label* ("Senior" vs "Lead") is
company-relative noise — a 5-year "Senior" at one firm is a "Lead" at another —
so no label ever excludes a candidate here. The role's target *level* is kept
separately (see levels.py) only to FLAG fit in ranking and to decide default
title exclusions — never to gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from recruiter.role_model.provenance import Provenance


@dataclass(frozen=True)
class Seniority:
    min_years: Optional[int]
    max_years: Optional[int]
    provenance: Provenance

    @property
    def is_specified(self) -> bool:
        return self.min_years is not None


def needs_years_clarification(min_years: Optional[int]) -> bool:
    """The Intake agent must ASK the recruiter for a minimum when the hiring
    notes state none — years are required before a search can run."""
    return min_years is None
