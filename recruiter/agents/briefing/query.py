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

    core = [r.text for r in model.core]
    if core:
        parts.append("with experience in " + _join(core))

    supporting = [r.text for r in model.tier("supporting")]
    if supporting:
        parts.append("ideally " + _join(supporting))

    places = list(model.location.cities) or list(model.location.states) or list(model.location.countries)
    if places:
        parts.append("based in " + _join_or(places))

    sentence = ". ".join(p for p in parts if p).strip()
    return sentence + "." if sentence and not sentence.endswith(".") else sentence
