"""Semantic pairing for dual-source reconciliation (feature A).

The deterministic `token_matcher` pairs requirements by shared words, so it
UNDER-MERGES when the same requirement is phrased differently or at a different
specificity — e.g. "Marketo administration" (HM) vs "marketing automation
platforms" (JD) share no tokens, yet they are the same requirement. This module
adds a semantic matcher: ONE cheap LLM call pairs the two lists by meaning, then
hands `reconcile` a pairwise matcher over the precomputed pairs.

Two safety properties:
  * FAIL-OPEN. Any error — no API key, transport, bad JSON — falls back to the
    deterministic `token_matcher`. Reconciliation must never break intake.
  * UNION, not replace. The returned matcher accepts a pair if the LLM paired it
    OR the token matcher would — the semantic pass only ever ADDS matches the
    deterministic one missed; it can't drop an obvious lexical match.

No CrustData credits are involved — this is a text-only LLM call, like the
existing intake reader. The recruiter still validates every pairing inline.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.intake.reconcile import Matcher, token_matcher

Complete = Callable[[str, str, str], Dict[str, Any]]

_SYSTEM = (
    "You reconcile two lists of hiring requirements for the SAME role: one from a "
    "published job description, one from the hiring manager's own notes. Pair items "
    "that mean the SAME underlying requirement, even when worded differently or at a "
    "different level of specificity — a named tool is the same requirement as its "
    "general category when it is clearly an instance of it (e.g. 'Marketo' is a "
    "'marketing automation platform'; 'Relativity' is an 'eDiscovery platform'). Do "
    "NOT pair merely related or adjacent skills. Each JD item and each HM item may be "
    "used at most once. Reply ONLY with JSON: {\"pairs\": [[jd_index, hm_index], ...]}."
)


def _default_complete(system: str, user: str, model: str) -> Dict[str, Any]:
    from recruiter.llm.core import complete_json
    return complete_json(system, user, model)


def _pair(
    jd_reqs: List[ReadRequirement],
    hm_reqs: List[ReadRequirement],
    *,
    model: str,
    complete: Complete,
) -> Set[Tuple[str, str]]:
    jd_lines = "\n".join(f"J{i}: {r.text}" for i, r in enumerate(jd_reqs))
    hm_lines = "\n".join(f"H{j}: {r.text}" for j, r in enumerate(hm_reqs))
    user = (
        f"JD requirements:\n{jd_lines}\n\nHiring-manager requirements:\n{hm_lines}\n\n"
        "Return the pairs that refer to the same requirement."
    )
    data = complete(_SYSTEM, user, model)
    pairs: Set[Tuple[str, str]] = set()
    for pair in (data or {}).get("pairs", []) or []:
        try:
            i, j = int(pair[0]), int(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= i < len(jd_reqs) and 0 <= j < len(hm_reqs):
            pairs.add((jd_reqs[i].text, hm_reqs[j].text))
    return pairs


def make_semantic_matcher(
    jd: Understanding,
    hm: Understanding,
    *,
    model: str = "gpt-4o-mini",
    complete: Optional[Complete] = None,
) -> Matcher:
    """Build a pairwise matcher for these two reads. One LLM call up front; the
    result is a closure `reconcile` can call per pair. Fail-open to token_matcher."""
    jd_reqs = list(jd.requirements)
    hm_reqs = list(hm.requirements)
    if not jd_reqs or not hm_reqs:
        return token_matcher
    try:
        pairs = _pair(jd_reqs, hm_reqs, model=model, complete=complete or _default_complete)
    except Exception:
        return token_matcher  # never break intake over a reconciliation nicety

    def matcher(a: str, b: str) -> bool:
        return (a, b) in pairs or token_matcher(a, b)

    return matcher
