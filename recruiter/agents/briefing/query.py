"""Build the natural-language retrieval query from the RoleModel.

Two bugs from the legacy builder are fixed here by construction:
  * ALL cities are named (legacy named only the first -> the Hyderabad-only
    collapse). A strong, location-naming query is also what makes CrustData
    actually bind the hard filters (weak queries leaked out-of-geo).
  * Capability phrases are joined cleanly behind ONE prefix (legacy appended
    whole requirement sentences behind a template -> "experience with
    Experience with RAG…").

Years are NOT put in the query — they are an exact structured filter, not a
search term.
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

    # Name the experience in the query, not just as a structured filter: on
    # CrustData's hybrid search, naming a constraint is what makes it bind and
    # skews relevance toward seniors (same lesson as the location geo-leak). The
    # role's own seniority word already rides in the identity/title.
    if model.seniority.min_years:
        parts.append(f"with {model.seniority.min_years}+ years of experience")

    # Current/any-time cores are present demands; past cores are background
    # (acceptable, not required) — phrased so retrieval doesn't over-weight them.
    current_core = [r.text for r in model.core if r.when != "past"]
    past_core = [r.text for r in model.core if r.when == "past"]
    if current_core:
        parts.append("with experience in " + _join(current_core))
    if past_core:
        parts.append("with a background in " + _join(past_core))

    supporting = [r.text for r in model.tier("supporting")]
    if supporting:
        parts.append("ideally " + _join(supporting))

    parts.append(_location_phrase(model))

    sentence = ". ".join(p for p in parts if p).strip()
    return sentence + "." if sentence and not sentence.endswith(".") else sentence


def _location_phrase(model: RoleModel) -> str:
    loc = model.location
    if loc.cities:
        return "based in " + _join_or(list(loc.cities))
    # Soft city preference: name them as a boost, scope stays the country/states.
    if loc.preferred_cities:
        scope = (list(loc.countries) or list(loc.states) or [""])[0]
        lead = f"based in {scope}, " if scope else "based "
        return lead + "preferably " + _join_or(list(loc.preferred_cities))
    places = list(loc.states) or list(loc.countries)
    return "based in " + _join_or(places) if places else ""
