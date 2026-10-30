"""Build the natural-language retrieval query from the RoleModel.

The NL query is a RANKING signal ONLY. We run CrustData in `mode: "exact"`, so the
structured `filters` define the candidate SET; the NL `search.query` just orders
that set by relevance. So we name the discriminating signals — the identity, the
role-defining capability, the core requirements, and any SOFT location preference
— and we deliberately leave the hard filters (years, country/state/city,
exclusions) OUT of the NL text:
  * naming a hard filter here does nothing for the set (the filter already binds),
  * and a longer NL query only dilutes the ranking vector — and, if the mode were
    ever "managed", would swamp the filters entirely (probe 2026-10-30: managed +
    long NL = ~60M near-global pool vs exact = 557k).
"""

from __future__ import annotations

from typing import List

from recruiter.role_model import RoleModel


def _join(items: List[str]) -> str:
    return ", ".join(items)


def _join_or(items: List[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} or {items[-1]}"


def build_nl_query(model: RoleModel) -> str:
    parts: List[str] = [model.identity.strip()]

    # The role-defining capability is the strongest ranking signal.
    for group in model.capability_groups:
        if group.terms:
            shown = _join_or(list(group.terms[:5]))
            parts.append(f"with hands-on {group.label} experience ({shown})")

    # Core requirements discriminate quality. Current/any-time cores are present
    # demands; past cores are background (ranked, not required).
    current_core = [r.text for r in model.core if r.when != "past"]
    past_core = [r.text for r in model.core if r.when == "past"]
    if current_core:
        parts.append("with experience in " + _join(current_core))
    if past_core:
        parts.append("with a background in " + _join(past_core))

    # SOFT location preference is a legitimate ranking boost (it is NOT a hard
    # filter). Hard countries/states/cities are omitted — they bind in `filters`.
    soft = _soft_location_phrase(model)
    if soft:
        parts.append(soft)

    sentence = ". ".join(p for p in parts if p).strip()
    return sentence + "." if sentence and not sentence.endswith(".") else sentence


def _soft_location_phrase(model: RoleModel) -> str:
    loc = model.location
    if loc.preferred_cities and not loc.cities:
        scope = (list(loc.countries) or list(loc.states) or [""])[0]
        lead = f"based in {scope}, " if scope else "based "
        return lead + "preferably " + _join_or(list(loc.preferred_cities))
    return ""
