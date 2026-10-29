"""CandidateRecord — the one per-candidate object the back half shares.

Unlike the RoleModel (immutable), this is an accumulator: Search fills the
provider fields, enrichment adds profile detail, the Judge attaches verified
requirement judgments, and Ranking writes the score. Agents read/write only
this and the RoleModel — nothing re-derives a candidate's identity elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class CandidateRecord:
    candidate_id: str
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    provider_score: Optional[float] = None
    # Raw provider payload, kept so evidence can be rebuilt without re-fetching.
    raw: Dict[str, Any] = field(default_factory=dict)
    # Which discovery queries surfaced this candidate (convergence signal).
    matched_queries: Tuple[str, ...] = ()
    # Filled downstream.
    enriched: bool = False
    judgments: Optional[Tuple[Dict[str, Any], ...]] = None  # verified requirement judgments
    final_score: Optional[float] = None
