"""Infer whether a requirement is PAST background, a CURRENT demand, or ANY.

A light deterministic backstop over the hiring notes (the keeper reader doesn't
emit tense yet). Reads the words around the requirement's distinctive term:
"came from a Java background" -> past; "right now working on Agentic" ->
current; no marker -> any. Conservative: only flips off 'any' on a clear signal.
"""

from __future__ import annotations

import re

_PAST = (
    "came from", "come from", "coming from", "background in", "previously", "prior ",
    "ex-", "ex ", "used to", "formerly", "earlier in", "transitioned from",
    "moved from", "started as", "roots in", "originally",
)
_CURRENT = (
    "currently", "right now", "now working", "now building", "presently",
    "at present", "these days", "today", "now on", "currently working",
)
_GENERIC = {
    "experience", "development", "systems", "system", "strong", "and", "or",
    "with", "in", "the", "work", "working", "build", "building", "able",
}


def _distinctive(text: str) -> str:
    for token in re.findall(r"[a-z0-9+#.]+", (text or "").lower()):
        if len(token) >= 3 and token not in _GENERIC:
            return token
    return ""


def infer_when(notes: str, requirement_text: str) -> str:
    low = (notes or "").lower()
    key = _distinctive(requirement_text)
    if not key or key not in low:
        return "any"
    # Check only the CLAUSE the term sits in — tense markers in a neighbouring
    # clause ("...background but right now working on...") must not bleed across.
    clause = next((c for c in re.split(r"[.,;]| but | and | however | though ", low) if key in c), None)
    if clause is None:
        return "any"
    past = any(p in clause for p in _PAST)
    current = any(c in clause for c in _CURRENT)
    if past and not current:
        return "past"
    if current and not past:
        return "current"
    return "any"
