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
        model="gpt-4o-mini",
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
    )
    content = _extract_text(response)
    # Validate JSON up front for a clearer error than pydantic's.
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
    return parse_structured_intent(content)
