"""Seniority — and the experience-derived floor that fixes the live bug where
a 15+ year "AI Solutions Architect" was scoped to "senior" and then excluded
by the eligibility gate as "above target".

The level is derived from years ONCE, here, and stored on the RoleModel, so
the ranking gate reads it instead of re-deriving (or ignoring) it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from recruiter.role_model.provenance import Provenance

# The one seniority ladder, lowest to highest. Downstream gating compares ranks
# on this ladder and nowhere else.
LADDER = ("intern", "junior", "mid", "senior", "staff/lead", "principal", "director")
_RANK = {label: i for i, label in enumerate(LADDER)}

# Common title words → a ladder label (so a stated label can be normalised).
_ALIASES = {
    "intern": "intern", "trainee": "intern",
    "junior": "junior", "jr": "junior", "entry": "junior", "graduate": "junior",
    "mid": "mid", "intermediate": "mid",
    "senior": "senior", "sr": "senior",
    "staff": "staff/lead", "lead": "staff/lead", "architect": "staff/lead",
    "principal": "principal", "distinguished": "principal", "fellow": "principal",
    "director": "director", "vp": "director", "head": "director", "chief": "director",
}


def normalise_label(label: Optional[str]) -> Optional[str]:
    """A free-text seniority word → a ladder label, or None if it names none."""
    if not label:
        return None
    low = label.strip().lower()
    if low in _RANK:
        return low
    for word, mapped in _ALIASES.items():
        if word in low:
            return mapped
    return None


def rank_of(label: Optional[str]) -> Optional[int]:
    norm = normalise_label(label)
    return _RANK.get(norm) if norm else None


def floor_from_years(min_years: Optional[int]) -> Optional[str]:
    """The LOWEST ladder level a minimum-years requirement implies. Conservative
    and tunable — validated by the golden-set. A 15+ role implies principal, so
    senior..principal candidates stay eligible and only director+ reads as
    'above'. None when no minimum was stated."""
    if not min_years or min_years < 0:
        return None
    if min_years >= 15:
        return "principal"
    if min_years >= 10:
        return "staff/lead"
    if min_years >= 6:
        return "senior"
    if min_years >= 3:
        return "mid"
    return "junior"


@dataclass(frozen=True)
class Seniority:
    """What the recruiter asked for, plus the years-derived floor. `effective`
    is the single value the gate should use: the higher of the stated label and
    the experience floor, so a mis-stated low label can never under-scope a
    high-experience role."""

    stated_label: Optional[str]
    min_years: Optional[int]
    max_years: Optional[int]
    provenance: Provenance

    @property
    def derived_floor(self) -> Optional[str]:
        return floor_from_years(self.min_years)

    @property
    def effective(self) -> Optional[str]:
        stated_rank = rank_of(self.stated_label)
        floor = self.derived_floor
        floor_rank = _RANK.get(floor) if floor else None
        if stated_rank is None:
            return floor
        if floor_rank is None or stated_rank >= floor_rank:
            return normalise_label(self.stated_label)
        return floor
