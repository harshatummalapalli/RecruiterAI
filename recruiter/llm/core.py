"""One JSON-returning LLM call that works across providers, chosen by model name:
`claude-*` -> Anthropic, everything else -> OpenAI. This is the single seam the
reader / judge / proposer call, so swapping models or providers is config, not
code (the point of getting off the retiring gpt-4 line).

Clients are lazy + cached; both read keys from .env via backend.config.
"""

from __future__ import annotations

import json
from typing import Any, Dict

_clients: Dict[str, Any] = {}


def _openai():
    if "openai" not in _clients:
        from openai import OpenAI
        from backend.config import get_openai_api_key
        _clients["openai"] = OpenAI(api_key=get_openai_api_key())
    return _clients["openai"]


def _anthropic():
    if "anthropic" not in _clients:
        import os
        import backend.config  # noqa: F401  (loads .env into os.environ)
        import anthropic
        _clients["anthropic"] = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _clients["anthropic"]


def _loads(text: str) -> Dict[str, Any]:
    """Tolerant JSON parse — strips code fences and surrounding prose."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1:
        t = t[i:j + 1]
    return json.loads(t)


def complete_json(system: str, user: str, model: str, *, max_tokens: int = 1024) -> Dict[str, Any]:
    """Return the model's JSON reply as a dict. Raises on transport/parse errors
    (callers decide how to fail — e.g. the proposer falls back to broad)."""
    if model.startswith("claude"):
        resp = _anthropic().messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    else:
        kwargs = dict(
            model=model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            text={"format": {"type": "json_object"}},
        )
        try:
            resp = _openai().responses.create(temperature=0, **kwargs)
        except Exception as exc:  # some models reject temperature
            if "temperature" in str(exc).lower():
                resp = _openai().responses.create(**kwargs)
            else:
                raise
        text = resp.output_text
    return _loads(text)
