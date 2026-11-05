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

from typing import Callable, List, Optional, Sequence, Tuple

from recruiter.agents.intake.capability_memory import (
    CapabilityMemory,
    LearnedCapability,
    normalise_key,
)
from recruiter.role_model import CapabilityGroup

# identity, posted_title, requirement_texts -> a proposal, or None for a broad role.
LlmProposer = Callable[[str, Optional[str], List[str]], Optional[LearnedCapability]]

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


def _to_group(cap: LearnedCapability) -> CapabilityGroup:
    rationale = (
        f"This is {cap.label} work — requiring evidence of it (any of: "
        f"{', '.join(cap.terms)}) keeps the shortlist on genuine {cap.label} "
        f"candidates, not look-alikes who share only the base title."
    )
    return CapabilityGroup(label=cap.label, terms=tuple(cap.terms),
                           source_qualifier=cap.source_qualifier, rationale=rationale)


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
            return (_to_group(cached),)

        if self._llm is None:
            return ()  # nothing learned yet, no proposer -> stay broad

        proposal = self._llm(identity, posted_title, list(requirement_texts))
        if proposal is None or not proposal.terms:
            self._memory.put(org, LearnedCapability(key, "", (), "", is_broad=True))
            return ()

        learned = LearnedCapability(
            key=key, label=proposal.label, terms=tuple(proposal.terms),
            source_qualifier=proposal.source_qualifier, is_broad=False,
        )
        self._memory.put(org, learned)
        return (_to_group(learned),)
