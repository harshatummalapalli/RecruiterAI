"""Pure checks over a RoleModel. Each returns a failure message, or None when
it passes. No I/O — these run on every change, instantly, for free.

They encode the bugs the live run found, so they can never silently return:
multi-city collapse, missing years, mis-classified role level, default
exec-title exclusions firing on an architect/leadership role, a lost
role-defining capability, and a silently-dropped (vs disclosed) work mode.
"""

from __future__ import annotations

from typing import List, Optional

from recruiter.role_model import RoleModel, default_title_exclusions


def multi_city_preserved(model: RoleModel, expected_cities) -> Optional[str]:
    got = {c.lower() for c in model.location.cities}
    missing = [c for c in expected_cities if c.lower() not in got]
    if missing:
        return f"cities dropped from the role: {missing} (have {sorted(got)})"
    return None


def min_years_is(model: RoleModel, expected: int) -> Optional[str]:
    if model.seniority.min_years != expected:
        return f"min_years {model.seniority.min_years!r} != expected {expected!r}"
    return None


def role_level_is(model: RoleModel, expected: str) -> Optional[str]:
    if model.role_level != expected:
        return f"role_level {model.role_level!r} != expected {expected!r}"
    return None


def default_exec_exclusions_suppressed(model: RoleModel) -> Optional[str]:
    """An architect/manager/director+ role must NOT default-exclude exec titles —
    they are who it's hiring."""
    exec_set = {t.lower() for t in default_title_exclusions("ic")}
    present = [t for t in model.exclude_titles if t.lower() in exec_set]
    if present:
        return f"role should not default-exclude exec/leadership titles, but excludes: {present}"
    return None


def role_defining_capability(model: RoleModel, label_contains: str) -> Optional[str]:
    hit = any(label_contains.lower() in g.label.lower() for g in model.capability_groups)
    if not hit:
        labels = [g.label for g in model.capability_groups]
        return f"role-defining capability {label_contains!r} not enforced (groups: {labels})"
    return None


def work_mode_disclosed(model: RoleModel) -> Optional[str]:
    if not model.location.work_mode:
        return None
    mode = model.location.work_mode.lower()
    if not any(mode in lim.lower() for lim in model.limitations):
        return f"work_mode {model.location.work_mode!r} set but not disclosed in limitations"
    return None


def has_core_requirements(model: RoleModel) -> Optional[str]:
    if not model.core:
        return "model has no core requirements"
    return None


def check_role_model(model: RoleModel, expect: dict) -> List[str]:
    """Run the applicable checks for a golden role's `expect` block. Returns the
    list of failure messages (empty = pass)."""
    failures: List[str] = []

    def record(msg: Optional[str]) -> None:
        if msg:
            failures.append(msg)

    if "cities" in expect:
        record(multi_city_preserved(model, expect["cities"]))
    if "min_years" in expect:
        record(min_years_is(model, expect["min_years"]))
    if "role_level" in expect:
        record(role_level_is(model, expect["role_level"]))
    if expect.get("no_default_exec_exclusions"):
        record(default_exec_exclusions_suppressed(model))
    if "capability" in expect:
        record(role_defining_capability(model, expect["capability"]))
    if expect.get("work_mode_disclosed"):
        record(work_mode_disclosed(model))
    if expect.get("has_core"):
        record(has_core_requirements(model))

    return failures
