"""Explain why a candidate fits — from verified evidence, not keywords.

Prefers the Judge's own met verdicts (with their quotes); falls back to a plain
title-relevance note when the profile wasn't deep-verified.
"""

from __future__ import annotations

from recruiter.agents.ranking.evidence import title_relevance
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


def explain_fit(role: RoleModel, record: CandidateRecord) -> str:
    if record.judgments:
        met = [j for j in record.judgments if j.get("verdict") == "met"]
        if met:
            bits = []
            for j in met[:4]:
                claim = j.get("signal_text") or j.get("term") or j.get("tier", "")
                quote = j.get("quote")
                bits.append(f"{claim} — “{quote}”" if quote else claim)
            return "Evidence: " + "; ".join(bits)
    return f"Title reads {title_relevance(role, record)} to the role; not deep-verified."
