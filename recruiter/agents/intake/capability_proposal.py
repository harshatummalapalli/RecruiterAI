"""Propose the role-defining capability group — memory first, LLM on a miss.

Flow (per org):
  1. normalise the identity to a key.
  2. memory hit  -> use the learned set (broad marker -> no group). No LLM.
  3. memory miss -> ask the injectable LLM proposer; cache the result (a real
     group, or a 'broad' marker); use it.
  4. no LLM configured -> stay broad (honest: no capability until one is learned).

The LLM proposer is injected (lazy real impl lands with the reader), so this is
fully testable offline.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple, Union

from recruiter.agents.intake.capability_memory import (
    CapabilityDimension,
    CapabilityMemory,
    LearnedCapability,
    normalise_key,
)
from recruiter.role_model import CapabilityGroup

# A proposer returns, for a given role:
#   - None / ()            -> broad (no defining capability)
#   - a LearnedCapability  -> a single-dimension capability (closed-book proposer)
#   - a tuple of
#     CapabilityDimension  -> a COMPOSITION, domain-first (grounded proposer)
# The union keeps the old single-capability proposers working unchanged while the
# grounded proposer emits several required dimensions.
ProposerResult = Union[None, LearnedCapability, Sequence[CapabilityDimension]]
# identity, posted_title, requirement_texts -> ProposerResult.
LlmProposer = Callable[[str, Optional[str], List[str]], ProposerResult]

# Craft/base titles that commit to a craft but NOT to any domain specialization.
# A narrow learned capability (e.g. "ML Platform") must not be FORCED onto these
# from one past JD — one payments backend role and one ML backend role share the
# key "backend engineer". For these, a cached narrow group is only applied when the
# CURRENT role's own requirements corroborate it (see propose). Specific identities
# like "ai engineer" or "salesforce developer" are NOT here — they name a domain,
# so their learned capability still applies directly. Replace this hardcoded set
# with taxonomy-driven breadth detection (ROLE_UNDERSTANDING_PLAN.md Thread B).
_GENERIC_BASE_TITLES = frozenset({
    "engineer", "software engineer", "backend engineer", "frontend engineer",
    "full stack engineer", "fullstack engineer", "developer", "software developer",
    "programmer", "web developer",
    "analyst", "associate", "consultant", "specialist", "coordinator", "manager",
})


def _corroborated(cap: LearnedCapability, requirement_texts: Sequence[str]) -> bool:
    """True when the current role's own requirements name any of the learned
    terms (or the label) — evidence that THIS role really is that specialization,
    not just a title collision."""
    hay = " ".join(requirement_texts).lower()
    needles = [t.lower() for t in cap.terms if t] + ([cap.label.lower()] if cap.label else [])
    return any(n in hay for n in needles)


def _group(label: str, terms: Sequence[str], qualifier: str) -> CapabilityGroup:
    rationale = (
        f"This is {label} work — requiring evidence of it (any of: "
        f"{', '.join(terms)}) keeps the shortlist on genuine {label} "
        f"candidates, not look-alikes who share only the base title."
    )
    return CapabilityGroup(label=label, terms=tuple(terms),
                           source_qualifier=qualifier or label, rationale=rationale)


def _to_groups(cap: LearnedCapability) -> Tuple[CapabilityGroup, ...]:
    """One hard keyword group per required dimension: the primary (label/terms)
    plus any extra dimensions. Briefing AND-s them, so a composition role
    ('Relativity' AND '.NET/SQL development') filters to builders, not users."""
    groups = [_group(cap.label, cap.terms, cap.source_qualifier)]
    for d in cap.extra_dimensions:
        if d.terms:
            groups.append(_group(d.label, d.terms, d.source_qualifier))
    return tuple(groups)


def _fold(result: "ProposerResult") -> Optional[LearnedCapability]:
    """Normalize a proposer's return into a single LearnedCapability (primary
    dimension in label/terms, the rest in extra_dimensions), or None for broad."""
    if result is None:
        return None
    if isinstance(result, LearnedCapability):
        return result if result.terms else None
    dims = [d for d in result if getattr(d, "terms", None)]
    if not dims:
        return None
    primary = dims[0]
    return LearnedCapability(
        key="", label=primary.label, terms=tuple(primary.terms),
        source_qualifier=primary.source_qualifier or primary.label, is_broad=False,
        extra_dimensions=tuple(dims[1:]),
    )


class CapabilityProposer:
    def __init__(self, memory: CapabilityMemory, llm_proposer: Optional[LlmProposer] = None) -> None:
        self._memory = memory
        self._llm = llm_proposer

    def propose(
        self,
        org: str,
        identity: str,
        posted_title: Optional[str] = None,
        requirement_texts: Sequence[str] = (),
    ) -> Tuple[CapabilityGroup, ...]:
        key = normalise_key(identity)
        if not key:
            # An identity that normalizes to nothing (all seniority words, or empty)
            # teaches no capability — never match or store under an empty key. A bad
            # "" row once matched unrelated roles with a stale "Data and AI Platforms".
            return ()

        cached = self._memory.get(org, key)
        if cached is not None:
            if cached.is_broad:
                return ()
            # A generic craft/base title must not INHERIT a narrow learned
            # capability from a past role unless this role's own requirements
            # corroborate it — prevents "backend engineer -> ML Platform" from one
            # JD being forced onto every backend search (ROLE_UNDERSTANDING_PLAN.md).
            if key in _GENERIC_BASE_TITLES and not _corroborated(cached, requirement_texts):
                return ()
            return _to_groups(cached)

        if self._llm is None:
            return ()  # nothing learned yet, no proposer -> stay broad

        folded = _fold(self._llm(identity, posted_title, list(requirement_texts)))
        if folded is None:
            self._memory.put(org, LearnedCapability(key, "", (), "", is_broad=True))
            return ()

        learned = LearnedCapability(
            key=key, label=folded.label, terms=tuple(folded.terms),
            source_qualifier=folded.source_qualifier, is_broad=False,
            extra_dimensions=folded.extra_dimensions,
        )
        self._memory.put(org, learned)
        return _to_groups(learned)
