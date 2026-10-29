"""Pure checks over a RoleModel. Each returns a failure message, or None when
it passes. No I/O — these run on every change, instantly, for free.

These encode the bugs the live experiment found, so they can never silently
come back: multi-city collapse, seniority under-scoping, a lost role-defining
capability, and a silently-dropped (vs disclosed) work-mode.
"""

from __future__ import annotations

from typing import List, Optional

from recruiter.role_model import RoleModel, rank_of


def multi_city_preserved(model: RoleModel, expected_cities) -> Optional[str]:
    got = {c.lower() for c in model.location.cities}
    missing = [c for c in expected_cities if c.lower() not in got]
    if missing:
        return f"cities dropped from the role: {missing} (have {sorted(got)})"
    return None


def seniority_floor_for_experience(model: RoleModel, min_level: str) -> Optional[str]:
    """A high-experience role must not be under-scoped. The effective seniority
    rank must be at least `min_level` on the ladder."""
    effective = model.seniority.effective
    want = rank_of(min_level)
    got = rank_of(effective)
    if want is None:
        return f"test error: unknown min_level {min_level!r}"
    if got is None or got < want:
        return (
            f"seniority under-scoped: effective={effective!r} "
            f"(< {min_level!r}); stated={model.seniority.stated_label!r} "
            f"min_years={model.seniority.min_years}"
        )
    return None


def role_defining_capability(model: RoleModel, label_contains: str) -> Optional[str]:
    hit = any(label_contains.lower() in g.label.lower() for g in model.capability_groups)
    if not hit:
        labels = [g.label for g in model.capability_groups]
        return f"role-defining capability {label_contains!r} not enforced (groups: {labels})"
    return None


def work_mode_disclosed(model: RoleModel) -> Optional[str]:
    """If a work mode was recorded, it must be disclosed as a limitation (the
    provider cannot filter on it) — never silently present and unenforced."""
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
    if "min_seniority" in expect:
        record(seniority_floor_for_experience(model, expect["min_seniority"]))
    if "capability" in expect:
        record(role_defining_capability(model, expect["capability"]))
    if expect.get("work_mode_disclosed"):
        record(work_mode_disclosed(model))
    if expect.get("has_core"):
        record(has_core_requirements(model))

    return failures
