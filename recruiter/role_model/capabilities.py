"""Derive the role-defining capability group from the role identity.

Fires ONLY when a recognised specialization qualifier is genuinely part of the
role identity (the "AI" in "AI Solutions Architect") — never on a capability
merely mentioned in the notes. Emits one `CapabilityGroup` (OR'd synonym set)
the Briefing agent can enforce as an any-of filter.

NOTE (open decision): families are hand-seeded (AI/ML only today). Generalising
beyond this — so every specialization is covered without hand-adding a family —
is the one design decision still open before this scales. Kept data-driven so
adding a validated family is a data edit, not code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from recruiter.role_model.model import CapabilityGroup


@dataclass(frozen=True)
class _Family:
    label: str
    qualifiers: Sequence[str]      # tokens in the identity that mark this family
    synonyms: Sequence[str]        # whole-word surface terms OR'd into the group
    extra_terms: Sequence[str] = field(default_factory=tuple)  # folded in only if present


_FAMILIES: Tuple[_Family, ...] = (
    _Family(
        label="AI / ML",
        qualifiers=("ai", "ml", "genai", "a.i.", "artificial intelligence", "machine learning", "generative ai"),
        synonyms=("AI", "ML", "machine learning", "LLM", "generative", "GenAI", "agentic", "deep learning", "NLP"),
        extra_terms=("RAG", "LLMs", "fine-tuning", "transformer", "computer vision", "MLOps",
                     "PyTorch", "TensorFlow", "embeddings", "vector", "Langchain"),
    ),
)


def _whole_word(haystack: str, needle: str) -> bool:
    needle = needle.strip().lower()
    if not needle:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", haystack) is not None


def derive_capability_groups(
    identity: Optional[str],
    posted_title: Optional[str] = None,
    requirement_texts: Optional[Sequence[str]] = None,
) -> Tuple[CapabilityGroup, ...]:
    """Zero or one role-defining group. Empty for the common case (most roles
    are not specialization-defined and must stay broad)."""
    scopes = [s.lower() for s in (identity, posted_title) if s]
    for family in _FAMILIES:
        qualifier = next((q for s in scopes for q in family.qualifiers if _whole_word(s, q)), None)
        if qualifier is None:
            continue
        terms: List[str] = []
        seen = set()
        for term in family.synonyms:
            if term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)
        blob = " ".join(t.lower() for t in (requirement_texts or []))
        for term in family.extra_terms:
            if term.lower() not in seen and _whole_word(blob, term):
                seen.add(term.lower())
                terms.append(term)
        rationale = (
            f"This is {('an' if family.label[:1].lower() in 'aeiou' else 'a')} {family.label} role — "
            f"requiring evidence of {family.label} work (any of: {', '.join(terms)}) keeps the shortlist on "
            f"genuine {family.label} candidates, not look-alikes who share only the base title."
        )
        return (CapabilityGroup(label=family.label, terms=tuple(terms), source_qualifier=qualifier, rationale=rationale),)
    return ()
