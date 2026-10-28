"""Derive an enforceable keyword GROUP from a role's defining capability.

This is the "brain" that turns the reframed intake (Phase A, step B — which
now preserves a role-defining qualifier like the "AI" in "AI Data Engineer"
inside primary_candidate_identity) into a *proposed* hard capability group that
retrieval can enforce as any-of-synonyms (see
backend/models/search_plan.py's must_have_keyword_groups and
CAPABILITY_AWARE_AGENT_ARCHITECTURE.md §1(C)).

It is deliberately CONSERVATIVE and HONEST:

  - It fires ONLY when a recognized specialization qualifier is genuinely part
    of the role identity (the title the candidate would carry) — never on a
    capability merely mentioned in a JD. Keying off primary_candidate_identity
    is reliable precisely because the reframed Task A only keeps the qualifier
    there when it is role-defining (a Full Stack Developer role gets nothing).
  - It only PROPOSES. Whether the group is enforced is the recruiter's call
    (default-on, visible, removable on the Search Brief) — this module decides
    nothing about enforcement, it just supplies the terms + a plain rationale.

The synonym sets are the surface spellings CrustData's whole-word (.) keyword
match needs to catch the same capability however a profile phrases it. Keep
them capability-evidence terms, not job titles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class CapabilityFamily:
    """A specialization that can define a role. `qualifiers` are the tokens that,
    when they lead/qualify the role identity, mark the role as belonging to this
    family; `synonyms` are the whole-word surface terms OR'd into the enforced
    group; `extra_terms` are strong, more specific evidence terms we fold in
    only when they actually appear in the role's capabilities text."""

    label: str
    qualifiers: Sequence[str]
    synonyms: Sequence[str]
    extra_terms: Sequence[str] = field(default_factory=tuple)


# Ordered by specificity — the first family whose qualifier matches wins.
# Seeded with the AI family (the validated case); add families here as each is
# validated. Every term is matched/emitted as a whole word by CrustData's (.).
_FAMILIES: List[CapabilityFamily] = [
    CapabilityFamily(
        label="AI / ML",
        qualifiers=("ai", "ml", "genai", "a.i.", "artificial intelligence",
                    "machine learning", "generative ai"),
        synonyms=("AI", "ML", "machine learning", "LLM", "generative",
                  "GenAI", "agentic", "deep learning", "NLP"),
        extra_terms=("RAG", "LLMs", "fine-tuning", "transformer", "diffusion",
                     "computer vision", "recommender", "MLOps", "PyTorch",
                     "TensorFlow", "embeddings", "vector"),
    ),
]


@dataclass(frozen=True)
class CapabilityGroupProposal:
    """A proposed hard capability group, for the recruiter to confirm/remove."""

    label: str              # recruiter-facing name, e.g. "AI / ML"
    terms: List[str]        # OR'd whole-word keywords -> one must_have_keyword_group
    source_qualifier: str   # the identity token that triggered it, e.g. "AI"
    rationale: str          # one plain sentence for the Search Brief


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def _contains_whole_word(haystack: str, needle: str) -> bool:
    """Whole-word / whole-phrase membership, case-insensitive. Mirrors the
    discriminating behavior of CrustData's (.) so detection and enforcement
    agree (so 'ai' matches 'AI Data Engineer' but never 'maintainability')."""
    needle = needle.strip().lower()
    if not needle:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", haystack) is not None


def _match_family(identity: str, posted_title: str) -> Optional[tuple]:
    """Return (family, matched_qualifier) when a family's qualifier is genuinely
    part of the role identity/title, else None. The identity is authoritative;
    the posted title is a fallback for the same signal."""
    for scope in (identity, posted_title):
        if not scope:
            continue
        for family in _FAMILIES:
            for qualifier in family.qualifiers:
                if _contains_whole_word(scope, qualifier):
                    return family, qualifier
    return None


def derive_capability_group(
    primary_candidate_identity: Optional[str],
    posted_title: Optional[str] = None,
    capability_texts: Optional[Sequence[str]] = None,
) -> Optional[CapabilityGroupProposal]:
    """Propose one hard capability group for the role's defining capability, or
    None when the role has no recognized defining specialization (the common
    case — most roles are not specialization-defined and must stay broad).

    `capability_texts` are the role's core/supporting capability sentences; we
    only use them to *fold in* more-specific evidence terms (e.g. RAG) that are
    actually present — never to trigger the proposal on their own.
    """
    identity = _norm(primary_candidate_identity)
    title = _norm(posted_title)

    matched = _match_family(identity, title)
    if matched is None:
        return None
    family, qualifier = matched

    # Start from the family's canonical synonym set (order-preserving, unique).
    terms: List[str] = []
    seen = set()
    for term in family.synonyms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            terms.append(term)

    # Fold in specific evidence terms only when they actually appear in the
    # role's capabilities text — this widens the OR (never narrows it), so a
    # profile saying "RAG" but not "AI" still satisfies the group.
    blob = " ".join(_norm(t) for t in (capability_texts or []))
    if blob:
        for term in family.extra_terms:
            if term.lower() not in seen and _contains_whole_word(blob, term):
                seen.add(term.lower())
                terms.append(term)

    display_qualifier = (primary_candidate_identity or posted_title or "").strip()
    rationale = (
        f"This is {('an' if family.label[:1].lower() in 'aeiou' else 'a')} "
        f"{family.label} role — requiring evidence of {family.label} work "
        f"(any of: {', '.join(terms)}) keeps the shortlist on genuine "
        f"{family.label} candidates instead of look-alikes who only share the base title."
    )
    return CapabilityGroupProposal(
        label=family.label,
        terms=terms,
        source_qualifier=qualifier,
        rationale=rationale,
    )
