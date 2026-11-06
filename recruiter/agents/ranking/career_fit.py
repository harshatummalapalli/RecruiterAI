"""Tier-2 career-fit assessor (holistic, on the enriched profile).

Rates how well a candidate's WHOLE career fits the role — the arc, the kind of
work, seniority, projects, skills — WITHOUT demanding a verbatim quote per
requirement. Not everyone writes their LinkedIn like a résumé, so a strong but
sparsely-described career must not be buried. This complements (never replaces)
the Judge: the Judge proves individual requirements with quotes for transparency;
this scores overall fit, and is the primary ranking driver (see score.py).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from recruiter.agents.ranking.judge_adapter import _to_intent
from recruiter.candidates import CandidateRecord
from recruiter.config import CAREER_MODEL
from recruiter.role_model import RoleModel

logger = logging.getLogger(__name__)

_SYSTEM = """You are an experienced technical recruiter judging OVERALL CAREER FIT for one role.

You get the role and a candidate's full career — their titles, how long in each, the kind of work they describe, projects, skills, and education. Judge the SUBSTANCE and ARC of the career: reading everything they have actually done, how strong a fit are they for THIS role?

Important: do NOT require the profile to spell out each requirement. Many strong people write sparse profiles — weigh the trajectory, seniority, and the kind of work, not how thoroughly it is written up. Reward a coherent, on-point, appropriately-senior career; discount one that is adjacent-but-off, too junior, or in a different field. Employer name or prestige is never a reason on its own.

Return only JSON: {"score": <0..1>, "rationale": "<one sentence naming the strongest reason>"}. Guide: 1.0 = exceptional, direct fit; 0.6 = solid; 0.4 = plausible/adjacent; 0.1 = clear mismatch."""

MAX_ROLES = 10
MAX_DESC_CHARS = 300
MAX_ABOUT_CHARS = 600
MAX_SKILLS = 15


def _career_payload(record: CandidateRecord, intent) -> Dict[str, Any]:
    """The enriched career, compactly — built via the keeper evidence builder WITH
    harvest so role descriptions / about / skills are included (the whole point)."""
    from backend.models.candidate import Candidate
    from backend.services.candidate_evidence_builder import build_candidate_evidence

    raw = record.raw if isinstance(record.raw, dict) else {}
    harvest = raw.get("_harvest_evidence")
    cand = Candidate(candidate_id=record.candidate_id or None, name=record.name, title=record.title,
                     company=record.company, location=record.location, profile_url=record.profile_url,
                     source="crustdata", raw_data=raw)
    try:
        ev = build_candidate_evidence(cand, intent, harvest_evidence=harvest if getattr(harvest, "success", False) else None)
    except Exception:
        ev = None
    roles = []
    for entry in (getattr(ev, "career", None) or [])[:MAX_ROLES]:
        dates = " - ".join(d for d in [entry.start, ("present" if entry.current else entry.end)] if d)
        roles.append({"title": entry.title, "company": entry.company, "dates": dates,
                      "what": (entry.description or "")[:MAX_DESC_CHARS]})
    return {
        "current_title": record.title or "",
        "headline": (getattr(ev, "headline", "") or "")[:240],
        "about": (getattr(ev, "harvest_about", None) or "")[:MAX_ABOUT_CHARS],
        "years": getattr(ev, "derived_experience_years", None),
        "skills": (getattr(ev, "skills", None) or [])[:MAX_SKILLS],
        "roles": roles,
    }


class CareerFitAssessor:
    def __init__(self, model: str = CAREER_MODEL) -> None:
        self._model = model

    def assess(self, role: RoleModel, record: CandidateRecord) -> Dict[str, Any]:
        intent = _to_intent(role)
        payload = {
            "role": {"identity": role.identity, "min_years": role.seniority.min_years,
                     "requirements": [r.text for r in role.requirements]},
            "candidate": _career_payload(record, intent),
        }
        from recruiter.llm import complete_json
        data = complete_json(_SYSTEM, json.dumps(payload, ensure_ascii=False), self._model, max_tokens=256)
        try:
            score = float(data.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        return {"score": max(0.0, min(1.0, score)), "rationale": str(data.get("rationale", ""))[:300]}
