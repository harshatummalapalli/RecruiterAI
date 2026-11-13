"""One JSON-returning LLM call that works across providers, chosen by model name:
`claude-*` -> Anthropic, everything else -> OpenAI. This is the single seam the
reader / judge / proposer call, so swapping models or providers is config, not
code (the point of getting off the retiring gpt-4 line).

Clients are lazy + cached; both read keys from .env via backend.config.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

_clients: Dict[str, Any] = {}

# --- cost ledger (opt-in: RECRUITER_COST_LEDGER=1) --------------------------
# Records real token usage per LLM call so a search's Claude spend can be
# measured instead of estimated. Off by default so production never accumulates.
_usage_lock = threading.Lock()
_usage_log: List[Dict[str, Any]] = []


def _ledger_on() -> bool:
    return os.environ.get("RECRUITER_COST_LEDGER", "").strip().lower() in ("1", "true", "yes")


def reset_usage() -> None:
    with _usage_lock:
        _usage_log.clear()


def usage_log() -> List[Dict[str, Any]]:
    with _usage_lock:
        return list(_usage_log)


def _record(model: str, usage: Any) -> None:
    if not _ledger_on() or usage is None:
        return
    def _i(name: str) -> int:
        try:
            return int(getattr(usage, name, 0) or 0)
        except (TypeError, ValueError):
            return 0
    with _usage_lock:
        _usage_log.append({
            "model": model,
            "input_tokens": _i("input_tokens"),
            "output_tokens": _i("output_tokens"),
            "cache_read_input_tokens": _i("cache_read_input_tokens"),
            "cache_creation_input_tokens": _i("cache_creation_input_tokens"),
        })


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
    """Tolerant JSON parse. Strips code fences / prose, then repairs malformed
    JSON (unescaped quotes/newlines in values, trailing commas, truncation) —
    OpenAI's json_object format guarantees valid JSON, but Claude's raw output
    does not, especially on quote-heavy payloads like the Judge's."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1:
        t = t[i:j + 1]
    try:
        return json.loads(t)
    except Exception:
        from json_repair import repair_json
        return json.loads(repair_json(t))


def complete_json(system: str, user: str, model: str, *, max_tokens: int = 1024, client: Any = None) -> Dict[str, Any]:
    """Return the model's JSON reply as a dict. Raises on transport/parse errors
    (callers decide how to fail — e.g. the proposer falls back to broad).

    `client` is an optional injected OpenAI-shaped double (``client.responses.create``)
    used only by tests: when given, it REPLACES provider routing and is called
    directly, so a caller that threads its own injected client (e.g. RequirementJudge,
    whose ``client=`` is documented as test-injectable) actually reaches it. Production
    passes ``client=None`` and nothing changes."""
    if client is not None:
        resp = client.responses.create(
            model=model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            text={"format": {"type": "json_object"}},
        )
        return _loads(resp.output_text)
    if model.startswith("claude"):
        # Cache the (large, identical-across-candidates) system prompt. Within a
        # search the Judge/career/screener system is reused across many calls, so
        # after the first call the rest read it from cache at ~1/10th the input
        # price. Anthropic ignores caching when the block is below the min size, so
        # small prompts (intake) are unaffected. Same model, same output — no
        # quality change, just stops re-billing the instructions each call.
        resp = _anthropic().messages.create(
            model=model, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        _record(model, getattr(resp, "usage", None))
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
        _record(model, getattr(resp, "usage", None))
        text = resp.output_text
    return _loads(text)
