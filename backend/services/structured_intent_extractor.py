"""Phase 2 — extract a StructuredHiringIntent from a JD via the LLM.

Thin and shadow-safe: reuses the existing OpenAI call pattern and the new
`prompts/structured_intent.txt`, parses into the StructuredHiringIntent schema.
It does not touch the production Task A/B path. The compiler (Phase 3) consumes
the returned intent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.config import get_openai_api_key
from backend.models.structured_intent import StructuredHiringIntent, parse_structured_intent

logger = logging.getLogger(__name__)

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "structured_intent.txt"

# Intake extraction model. gpt-6.1-sol (reasoning=medium) was adopted after a
# controlled 5x2 Phase-2 experiment: it is stable 5/5 on both anchors and fixed
# every semantic failure gpt-4o-mini produced (required/preferred, temporal,
# option conservation, no invented seniority/company_scale). Intake is the cheap
# once-per-search call — the sanctioned place for a stronger model.
_INTAKE_MODEL = "gpt-6.1-sol"
_INTAKE_REASONING_EFFORT = "medium"


def _extract_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    # Fallback to the responses-API nested shape.
    chunks = []
    for item in getattr(response, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            t = getattr(part, "text", None)
            if t:
                chunks.append(t)
    return "".join(chunks)


def extract_structured_intent(job_description: str, client: Optional[Any] = None) -> StructuredHiringIntent:
    api_key = get_openai_api_key()
    if client is None:
        if not api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

    # The prompt contains literal JSON braces, so a plain placeholder swap —
    # never str.format (which would try to interpret the braces).
    prompt = _PROMPT.read_text(encoding="utf-8").replace("{job_description}", job_description)
    response = client.responses.create(
        model=_INTAKE_MODEL,
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
        reasoning={"effort": _INTAKE_REASONING_EFFORT},
    )
    content = _extract_text(response)
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
    raw = _normalize(raw)
    return parse_structured_intent(json.dumps(raw))


_STRENGTHS = {"required", "preferred", "context"}
_RELATIONSHIPS = {"current", "past", "any"}


def _fix_strength_relationship(entry: dict) -> None:
    """Repair the common model slip of writing a strength word into the
    `relationship` field (and vice versa). Preserves MEANING, fixes placement."""
    if not isinstance(entry, dict):
        return
    rel = entry.get("relationship")
    if rel is not None and rel not in _RELATIONSHIPS:
        if rel in _STRENGTHS and not entry.get("strength"):
            entry["strength"] = rel
        entry["relationship"] = "any"
    st = entry.get("strength")
    if st is not None and st not in _STRENGTHS and st in _RELATIONSHIPS:
        # strength holds a relationship word; move it if relationship is empty.
        if not entry.get("relationship") or entry.get("relationship") == "any":
            entry["relationship"] = st
        entry["strength"] = "required"


def _normalize(raw: dict) -> dict:
    """Thin, bounded repair of known LLM shape slips — never changes meaning.
      - collapse a single-item skill_any_of into a plain skill
      - fix strength/relationship field confusion on skills/companies/scale
    """
    if not isinstance(raw, dict):
        return raw
    skills = raw.get("skills") or []
    groups = raw.get("skill_any_of") or []
    kept_groups = []
    for g in groups:
        if isinstance(g, dict):
            any_of = [x for x in (g.get("any_of") or []) if x]
            if len(any_of) < 2:
                if any_of:
                    skills.append({"name": any_of[0],
                                   "relationship": g.get("relationship", "current"),
                                   "strength": g.get("strength", "required")})
                continue
            g["any_of"] = any_of
            kept_groups.append(g)
    raw["skills"] = skills
    raw["skill_any_of"] = kept_groups
    for key in ("skills", "skill_any_of", "companies"):
        for entry in raw.get(key) or []:
            _fix_strength_relationship(entry)
    for key in ("company_scale", "education", "experience", "location", "seniority"):
        if isinstance(raw.get(key), dict):
            _fix_strength_relationship(raw[key])
    return raw

