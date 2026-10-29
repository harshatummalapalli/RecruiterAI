"""Briefing's output: the provider query, what couldn't be enforced
(disclosures), and the requirements the Judge verifies downstream.

`ProviderQuery` is the clean, provider-shaped intermediate the Search agent
hands to the CrustData adapter. It carries only fields the capability model
says are genuinely enforceable — anything else is a disclosure, not a filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from recruiter.role_model import Requirement


@dataclass(frozen=True)
class ProviderQuery:
    natural_language: str
    countries: Tuple[str, ...] = ()
    states: Tuple[str, ...] = ()
    cities: Tuple[str, ...] = ()
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    radius_place: Optional[str] = None
    radius_miles: Optional[float] = None
    employment_type: Optional[str] = None
    exclude_titles: Tuple[str, ...] = ()
    exclude_current_companies: Tuple[str, ...] = ()
    must_have_keyword_groups: Tuple[Tuple[str, ...], ...] = ()
    industries: Tuple[str, ...] = ()


@dataclass(frozen=True)
class BriefingPlan:
    query: ProviderQuery
    disclosures: Tuple[str, ...] = ()
    judge_signals: Tuple[Requirement, ...] = field(default_factory=tuple)
