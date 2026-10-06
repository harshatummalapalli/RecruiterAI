"""Experimental extractor: same model, same reasoning effort, same call shape as production (EXPERIMENT ONLY).

Only two things differ from `structured_intent_extractor.extract_structured_intent`: the prompt (prompt_v2.txt) and the
schema the reply is parsed into (ExperimentalHiringIntent). The model and effort are IMPORTED from production, never
re-declared, so the comparison with the baseline cannot drift. Production is not modified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent, parse_experimental_intent
from backend.services.structured_intent_extractor import (
    _INTAKE_MODEL,
    _INTAKE_REASONING_EFFORT,
    _extract_text,
    _normalize,
)

PROMPT_V2 = Path(__file__).parent / "prompt_v2.txt"


def build_prompt(job_description: str, recruiter_brief: Optional[str] = None) -> str:
    text = PROMPT_V2.read_text(encoding="utf-8")
    text = text.replace("{job_description}", job_description or "(none provided)")
    return text.replace("{recruiter_brief}", recruiter_brief or "(none provided)")


def extract_experimental_intent(job_description: str, recruiter_brief: Optional[str], client: Any) -> ExperimentalHiringIntent:
    response = client.responses.create(
        model=_INTAKE_MODEL,
        input=[{"role": "user", "content": build_prompt(job_description, recruiter_brief)}],
        text={"format": {"type": "json_object"}},
        reasoning={"effort": _INTAKE_REASONING_EFFORT},
    )
    try:
        raw = json.loads(_extract_text(response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
    return parse_experimental_intent(json.dumps(_normalize(raw)))
