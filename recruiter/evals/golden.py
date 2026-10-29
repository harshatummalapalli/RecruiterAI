"""The golden-set: real roles, each with the hiring notes + boundary the
recruiter would enter, and the expectations every stage must satisfy.

A fixture is plain data. The Intake agent (when built) turns `notes`+`boundary`
into a RoleModel; `assertions.check_role_model` verifies it meets `expect`.
Until then the fixtures also serve as the contract Intake must meet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class GoldenRole:
    name: str
    notes: str                       # raw hiring notes / JD
    boundary: Dict[str, Any]         # recruiter-owned facts (mirrors the intake form)
    expect: Dict[str, Any] = field(default_factory=dict)


def all_roles() -> Tuple[GoldenRole, ...]:
    """Every golden role. Grows as we validate more; kept small and real."""
    from recruiter.evals.fixtures import ai_solutions_architect

    return (ai_solutions_architect.ROLE,)
