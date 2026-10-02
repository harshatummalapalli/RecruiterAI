"""Phase 3 — role-family taxonomy (small, versioned, evidence-backed).

The compiler expands a SOURCE role (what the recruiter said) into an approved
RETRIEVAL title family. This is deliberately NOT a general job-title ontology and
NOT a synonym dictionary: each entry is a set of *search-equivalent* titles for a
specific role shape, backed by evidence, versioned, with provenance. We add a
family only when we have evidence for it.

Extraction preserves meaning; this taxonomy is how compilation expands
REPRESENTATION — never meaning. If a source role has no taxonomy entry, the
compiler uses the source title(s) verbatim (no manufacture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

TAXONOMY_VERSION = "v1-2026-10-02"


@dataclass(frozen=True)
class RoleFamily:
    canonical_role: str
    role_shape: str
    approved_retrieval_titles: List[str]
    version: str
    provenance: str


# Keyed by lowercased canonical/source title. Only the two validated anchors.
_FAMILIES = {
    "software engineer": RoleFamily(
        canonical_role="Software Engineer",
        role_shape="skill_defined/backend",
        approved_retrieval_titles=["Software Engineer", "Backend Engineer", "Backend Developer", "Python Developer"],
        version=TAXONOMY_VERSION,
        provenance="Validated live 2026-10-01: generic engineering titles + language keyword retrieval surfaced on-brief Python/Java backend engineers. Python Developer included for THIS backend shape only — not a universal Software-Engineer synonym.",
    ),
    "product owner": RoleFamily(
        canonical_role="Product Owner",
        role_shape="product",
        approved_retrieval_titles=["Product Owner", "Product Manager", "Product Lead"],
        version=TAXONOMY_VERSION,
        provenance="Validated by the Epiq role-first experiment 2026-10-01: this title family took the 2.0 tie-mass to 0 and product density to 95-100%. A validated retrieval family, not a generic synonym set.",
    ),
}


def lookup(source_title: str) -> Optional[RoleFamily]:
    return _FAMILIES.get(source_title.strip().lower())


def expand_retrieval_titles(source_role_family: List[str]) -> tuple:
    """Expand source role(s) into the approved retrieval title family.
    Returns (titles, used_taxonomy, provenance_notes). If no entry exists, falls
    back to the source titles verbatim (never manufactures)."""
    titles: List[str] = []
    notes: List[str] = []
    used = False
    for src in source_role_family:
        fam = lookup(src)
        if fam:
            used = True
            notes.append(f"{src!r} -> {fam.canonical_role} [{fam.role_shape}] ({fam.version})")
            for t in fam.approved_retrieval_titles:
                if t not in titles:
                    titles.append(t)
        else:
            notes.append(f"{src!r} -> no taxonomy entry; used source title verbatim (no expansion)")
            if src not in titles:
                titles.append(src)
    return titles, used, notes
