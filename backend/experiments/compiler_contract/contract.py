"""Expected fates (pre-registered in CONTRACT_EXPECTATIONS.md section 2) and gap-type rules (section 6). Nothing here looks at compiler output."""

from __future__ import annotations

from typing import Optional, Set, Tuple

E, V, P, N, U, J, D = ("ENFORCED", "VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT", "NORMALIZED", "UNRESOLVED", "DROPPED_WITH_JUSTIFICATION", "SILENTLY_DROPPED")

SPLIT_BY_STRENGTH = {"company", "education.degree", "education.stream", "experience.min", "experience.max", "location.entry", "location.radius", "domain", "evidence_signal"}
SPLIT_BY_STRENGTH_REL = {"skill", "skill_any_of"}


def concept_key(a: dict) -> str:
    c = a["concept"]
    if a["scope"] != "global":
        c += " (in path)"
    if a["concept"] in SPLIT_BY_STRENGTH_REL:
        return f"{c} [{a['strength']}, {a['relationship']}]"
    if a["concept"] in SPLIT_BY_STRENGTH:
        return f"{c} [{a['strength']}]"
    return c


def expected(a: dict) -> Tuple[Set[str], str]:
    """(acceptable fates, why). A path-scoped atom expects the same fate as its global concept, but scoped to its path."""
    c, st, rel = a["concept"], a.get("strength"), a.get("relationship")
    if c == "role_family":
        return {E, N}, "title filter; taxonomy expansion where an entry exists"
    if c == "seniority.value":
        return {V}, "admission gate; unknown level carried verbatim"
    if c in ("seniority.leadership", "seniority.alternatives"):
        return {V}, "evidence / admission text"
    if c in ("skill", "skill_any_of"):
        if st == "required":
            return ({E, N}, "required current/past use is provider-searchable") if rel in ("current", "past") else ({V, E}, "required, time-unscoped: provider if mapped, else downstream")
        return {P, V}, "a preference is never a hard filter"
    if c == "skill.proficiency":
        return {V}, "depth must travel with the skill requirement; no provider field states depth"
    if c == "company":
        return ({E}, "required company is a provider filter") if st == "required" else ({P}, "a company preference is never a filter")
    if c == "company_scale":
        return ({E} if st == "required" else {P}), "scale"
    if c in ("education.degree", "education.stream"):
        return ({E, N}, "required education is a provider filter") if st == "required" else ({P}, "a preferred qualification stays visible as a preference")
    if c in ("experience.min", "experience.max"):
        return ({E}, "required years are a provider filter") if st == "required" else ({P}, "a preferred range is not a hard filter")
    if c in ("location.entry", "location.radius"):
        return ({E, N}, "place filter") if st == "required" else ({P}, "a preferred place is not a hard filter")
    if c == "location.country":
        return {E}, "a country-wide area is a country filter"
    if c == "location.remote":
        return {P, V}, "an allowance that widens scope: audited, never silent"
    if c == "location.work_mode":
        return {V}, "capability map: no work-mode filter on person search -> disclose / downstream"
    if c.startswith("exclusion."):
        return {E}, "explicit company/title exclusion"
    if c == "semantic_exclusion":
        return {V}, "negative check by the Judge; never a company/title filter"
    if c == "domain":
        return ({V}, "required domain verified downstream") if st == "required" else ({P, V}, "domain preference")
    if c == "evidence_signal":
        return {V, P}, "verified downstream with its tier"
    if c == "sourcing_path":
        return {E, V, U}, "an OR over per-path plans, or at least an audited unresolved row; never silent"
    if c == "reconciliation":
        return {J, U, V}, "a decision record: an audit reason, or surfaced if unresolved"
    if c == "provenance.basis":
        return {J, V}, "audit row carries the claiming source, or the record is bound to the intent by hash"
    if c == "role_archetype":
        return {J}, "classification metadata with an audit reason"
    return {V}, "unspecified"


def matches(current: str, exp: Set[str]) -> bool:
    cur = {current} | ({E, N} if current in (E, N) else set())
    return bool(cur & exp)


def gap_type(a: dict, current: str, exp: Set[str]) -> Optional[str]:
    """Why a mismatch is a mismatch. Rules fixed in CONTRACT_EXPECTATIONS.md section 6."""
    if matches(current, exp):
        return None
    c = a["concept"]
    if c == "provenance.basis":
        return "PROVENANCE / VALIDATION"
    if c == "role_family":
        return "TAXONOMY"
    return "COMPILER LOGIC"
