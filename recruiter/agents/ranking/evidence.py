"""Candidate evidence — small and focused (the anti-1196-line-builder).

Two cheap signals used before the Judge runs (title relevance + a light
requirement-term overlap), and the verified coverage read from the Judge's
own judgments after it runs. Past requirements count less (they're background).
"""

from __future__ import annotations

import re
from typing import Dict

from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel

# Tier weights, shared by the regex (pre-judge) and verified (post-judge) coverage.
TIER_WEIGHT: Dict[str, float] = {"core": 1.0, "supporting": 0.6, "differentiator": 0.3}

_WORD = re.compile(r"[a-z0-9+#.]+")
_GENERIC = {"engineer", "engineering", "developer", "senior", "lead", "principal",
            "staff", "the", "of", "and", "a", "an", "for", "with", "in", "experience"}


def _terms(text: str, min_len: int = 2) -> set:
    return {w for w in _WORD.findall((text or "").lower()) if len(w) >= min_len and w not in _GENERIC}


def _distinctive(text: str) -> str:
    for w in _WORD.findall((text or "").lower()):
        if len(w) >= 3 and w not in _GENERIC:
            return w
    return ""


def candidate_text(record: CandidateRecord) -> str:
    raw = record.raw if isinstance(record.raw, dict) else {}
    bp = raw.get("basic_profile") or {}
    parts = [record.title or "", bp.get("headline") or "", bp.get("summary") or "", raw.get("_enriched_text") or ""]
    return " ".join(parts).lower()


def title_relevance(role: RoleModel, record: CandidateRecord) -> str:
    target = _terms(role.identity)
    bp = record.raw.get("basic_profile") if isinstance(record.raw, dict) else None
    headline = (bp or {}).get("headline") if isinstance(bp, dict) else ""
    cand = _terms(f"{record.title or ''} {headline or ''}")
    if not target or not cand:
        return "unclear"
    ratio = len(target & cand) / len(target)
    if ratio >= 0.6:
        return "direct"
    return "adjacent" if ratio > 0 else "unclear"


def regex_coverage(role: RoleModel, record: CandidateRecord) -> float:
    """Cheap pre-judge coverage: a requirement counts if its distinctive term
    appears in the candidate's text. Past requirements are halved (background)."""
    blob = candidate_text(record)
    total = 0.0
    for req in role.requirements:
        key = _distinctive(req.text)
        if key and key in blob:
            total += TIER_WEIGHT.get(req.tier, 0.0) * (0.5 if req.when == "past" else 1.0)
    return total


def verified_coverage(record: CandidateRecord) -> float:
    """Post-judge coverage from the Judge's own 'met' verdicts."""
    if not record.judgments:
        return 0.0
    return sum(TIER_WEIGHT.get(j.get("tier"), 0.0) for j in record.judgments if j.get("verdict") == "met")
