"""Where a fact on the RoleModel came from.

Every field the recruiter sees can be traced to its origin — this is the
honesty guarantee carried over from the legacy product, made first-class on
the spine so no downstream stage has to re-derive or guess it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# The only valid origins for a fact on the model.
RECRUITER = "recruiter"   # the recruiter stated it (authoritative, verbatim)
JD = "jd"                 # read from the hiring notes and verified present
INFERRED = "inferred"     # the intake agent judged it; not stated outright
BACKSTOP = "backstop"     # a deterministic floor supplied it (e.g. seniority)

_VALID = {RECRUITER, JD, INFERRED, BACKSTOP}


@dataclass(frozen=True)
class Provenance:
    source: str
    # The JD span or rule text that produced the fact, when there is one.
    evidence: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in _VALID:
            raise ValueError(f"unknown provenance source: {self.source!r}")

    @property
    def is_stated(self) -> bool:
        """True when the recruiter or the JD actually said it (vs inferred)."""
        return self.source in (RECRUITER, JD)
