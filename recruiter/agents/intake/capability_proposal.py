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

        cached = self._memory.get(org, key)
        if cached is not None:
            return () if cached.is_broad else (_to_group(cached),)

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
