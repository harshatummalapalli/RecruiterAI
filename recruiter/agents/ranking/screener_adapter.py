"""Tier-1 admission screener (cheap, CrustData-only).

Scores a BATCH of candidates on the thin provider data — title, headline, recent
past titles, skills, years, location — to decide who is worth the paid Harvest
enrichment + the Tier-2 Judge. One LLM call per batch on a cheap model. Coarse and
high-recall by default: it drops only clear mismatches and never reads an enriched
profile (that is the Judge's job). It tightens to a SELECTIVE gate only when
recruiter validation examples are supplied (campaign cycles). Fails OPEN — a
screener error keeps everyone, so the gate can never silently empty a search.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from recruiter.agents.ranking.judge_adapter import _to_intent
from recruiter.agents.ranking.model import ScreenResult
from recruiter.candidates import CandidateRecord
from recruiter.config import SCREEN_MODEL
from recruiter.role_model import RoleModel

logger = logging.getLogger(__name__)

_HEADER = """You are a fast first-pass recruiting screener. For each candidate you see only thin directory data — their current title, a headline, a few recent past titles, listed skills, approximate years, and location. You do NOT see their full profile."""

# Default: high-recall. Tier-1 is a cheap gate; the accurate, paid Tier-2 (Harvest
# + Judge + career-fit) does precision, so Tier-1 must not drop a plausible fit.
_RECALL = """Decide, per candidate, whether they are plausibly worth a deeper, paid look for THIS role. Be high-recall: KEEP anyone who could reasonably fit; DROP only clear mismatches (wrong field entirely, far too junior, unrelated discipline). When unsure, keep. Judge the kind of work and seniority, not exact keywords; you are gating who to read in depth, not verifying requirements."""

# Selective: used ONLY once the recruiter has validated examples (campaign cycles),
# where their shortlist/reject signal justifies tightening and saving enrichment.
_SELECTIVE = """Decide whether each candidate is a close match worth Harvest enrichment for THIS role. The confirmed role requirements remain primary. Use the supplied recruiter validation examples: shortlisted profiles as positive examples, rejection reasons and rejected profiles as negative examples, and maybes as uncertain examples. Generalize from role and work evidence; do not copy a person's company, identity, or exact title as a requirement. Keep only likely close fits consistent with the role and recruiter feedback. Drop weak or uncertain fits so they remain in the un-enriched reserve. This is a relevance gate, not a final hiring decision."""

_FOOTER = """For each candidate give keep (true/false) and score (0..1 = how strong the thin signal is, for ordering who to read first).

Return only JSON: {"results":[{"i":<number>,"keep":true|false,"score":<0..1>}]}. Include every candidate exactly once."""

_SYSTEM_RECALL = f"{_HEADER}\n\n{_RECALL}\n\n{_FOOTER}"
_SYSTEM_SELECTIVE = f"{_HEADER}\n\n{_SELECTIVE}\n\n{_FOOTER}"


def _has_feedback(feedback_context: Dict[str, Any]) -> bool:
    """True only when recruiter validation examples are actually present. A first
    search has none -> stay high-recall; a campaign cycle after the recruiter has
    shortlisted/rejected does -> switch to the selective gate."""
    return bool(feedback_context) and any(feedback_context.get(k) for k in feedback_context)

MAX_SKILLS = 12
MAX_PAST_TITLES = 4
MAX_HEADLINE_CHARS = 240
# Screen in chunks so each JSON reply stays small and reliable (a 30-wide batch with a
# tight token budget truncates; chunking + a generous per-candidate budget avoids it).
CHUNK = 20
TOKENS_PER_CANDIDATE = 40
TOKENS_BASE = 120


def _thin_profile(record: CandidateRecord, intent) -> Dict[str, Any]:
    """CrustData-only fields, via the keeper evidence builder with NO harvest — the
    same normalization the rest of the engine trusts, minus the enrichment."""
    from backend.models.candidate import Candidate
    from backend.services.candidate_evidence_builder import build_candidate_evidence

    cand = Candidate(candidate_id=record.candidate_id or None, name=record.name, title=record.title,
                     company=record.company, location=record.location, profile_url=record.profile_url,
                     source="crustdata", raw_data=record.raw if isinstance(record.raw, dict) else {})
    try:
        ev = build_candidate_evidence(cand, intent)
        headline = (ev.headline or "")[:MAX_HEADLINE_CHARS]
        past_titles = [r.title for r in (ev.past_roles or [])[:MAX_PAST_TITLES] if getattr(r, "title", None)]
        skills = [s for s in (ev.skills or [])[:MAX_SKILLS] if s]
        years = getattr(ev, "derived_experience_years", None)
    except Exception:
        headline, past_titles, skills, years = "", [], [], None
    return {
        "title": record.title or "",
        "headline": headline,
        "past_titles": past_titles,
        "skills": skills,
        "years": years,
        "location": record.location or "",
    }


class ScreenerAdapter:
    def __init__(self, model: str = SCREEN_MODEL) -> None:
        self._model = model

    def screen(self, role: RoleModel, records: Tuple[CandidateRecord, ...],
               feedback_context: Dict[str, Any] | None = None) -> Tuple[ScreenResult, ...]:
        if not records:
            return ()
        intent = _to_intent(role)
        role_payload = {
            "identity": role.identity,
            "min_years": role.seniority.min_years,
            "core_requirements": [r.text for r in role.tier("core")],
            "supporting_requirements": [r.text for r in role.tier("supporting")],
        }
        feedback_context = feedback_context or {}
        out: List[ScreenResult] = []
        for start in range(0, len(records), CHUNK):
            out.extend(self._screen_chunk(role_payload, records[start:start + CHUNK], intent, feedback_context))
        return tuple(out)

    def _screen_chunk(self, role_payload: Dict[str, Any], chunk: Tuple[CandidateRecord, ...], intent,
                      feedback_context: Dict[str, Any]) -> List[ScreenResult]:
        selective = _has_feedback(feedback_context)
        payload: Dict[str, Any] = {"role": role_payload,
                   "candidates": [{"i": k, **_thin_profile(record, intent)} for k, record in enumerate(chunk)]}
        if selective:
            payload["recruiter_validation"] = feedback_context
        try:
            from recruiter.llm import complete_json
            system = _SYSTEM_SELECTIVE if selective else _SYSTEM_RECALL
            data = complete_json(system, json.dumps(payload, ensure_ascii=False), self._model,
                                 max_tokens=min(TOKENS_BASE + TOKENS_PER_CANDIDATE * len(chunk), 4096))
            rows: List[Dict[str, Any]] = data.get("results") or []
            by_index = {int(row["i"]): row for row in rows if isinstance(row, dict) and "i" in row}
        except Exception:
            # A broken gate must NEVER silently drop candidates — fail OPEN and
            # let the (accurate, paid) Tier-2 decide. Dropping here loses good
            # people whenever the cheap model hiccups (common on the small box).
            logger.warning("Tier-1 screener chunk failed; keeping it (fail-open)", exc_info=True)
            return [ScreenResult(keep=True, score=0.5, reason="screen_failed") for _ in chunk]

        out: List[ScreenResult] = []
        for k in range(len(chunk)):
            row = by_index.get(k)
            if row is None:
                out.append(ScreenResult(keep=True, score=0.5))  # unanswered = keep (fail-open)
                continue
            try:
                score = float(row.get("score", 0.5))
            except (TypeError, ValueError):
                score = 0.5
            out.append(ScreenResult(keep=bool(row.get("keep", True)), score=max(0.0, min(1.0, score))))
        return out
