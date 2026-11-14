"""Per-org learned capability taxonomy.

Replaces the hand-seeded family table: the first time a role shape is seen, the
LLM proposes its capability + synonyms and the recruiter confirms; that is
stored here and reused, so seen shapes cost zero LLM calls. A "broad" marker is
stored too, so a role with no defining specialization is never re-proposed.

Shared per ORG (synonym sets aren't sensitive and sharing warms the cache
faster). File-backed for real use; in-memory for tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Tuple

_SENIORITY = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "mid",
    "intermediate", "entry", "chief", "head", "vp", "svp", "evp", "avp",
    "director", "manager", "of", "the", "a", "an",
}


def normalise_key(identity: Optional[str]) -> str:
    """A stable key for a role shape: lowercased, seniority words stripped."""
    tokens = re.findall(r"[a-z0-9+.#/]+", (identity or "").lower())
    return " ".join(t for t in tokens if t not in _SENIORITY)


@dataclass(frozen=True)
class CapabilityDimension:
    """One required dimension of a role (e.g. the DOMAIN 'Relativity platform',
    or the CRAFT '.NET/SQL development'). A composition role has several; each
    becomes its own hard keyword group, AND-ed with the others. The primary
    dimension lives on LearnedCapability.label/terms for backward compatibility;
    any additional dimensions ride in LearnedCapability.extra_dimensions."""
    label: str
    terms: Tuple[str, ...]
    source_qualifier: str = ""


@dataclass(frozen=True)
class LearnedCapability:
    key: str
    label: str
    terms: Tuple[str, ...]
    source_qualifier: str
    is_broad: bool = False   # True = this role shape has no defining capability
    # Additional REQUIRED dimensions beyond the primary (label/terms). Empty for a
    # single-axis role — so nothing about the single-dimension path changes. Each
    # extra dimension is AND-ed as its own keyword group (Slice 1: composition).
    extra_dimensions: Tuple[CapabilityDimension, ...] = ()


class CapabilityMemory(Protocol):
    def get(self, org: str, key: str) -> Optional[LearnedCapability]: ...
    def put(self, org: str, cap: LearnedCapability) -> None: ...


class InMemoryCapabilityMemory:
    def __init__(self) -> None:
        self._store: Dict[Tuple[str, str], LearnedCapability] = {}

    def get(self, org: str, key: str) -> Optional[LearnedCapability]:
        return self._store.get((org, key))

    def put(self, org: str, cap: LearnedCapability) -> None:
        self._store[(org, cap.key)] = cap


class FileCapabilityMemory:
    """One JSON file per org: {key: {label, terms, source_qualifier, is_broad}}."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, org: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", org or "default")
        return self._root / f"{safe}.json"

    def _load(self, org: str) -> Dict[str, dict]:
        path = self._path(org)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def get(self, org: str, key: str) -> Optional[LearnedCapability]:
        row = self._load(org).get(key)
        if not isinstance(row, dict):
            return None
        extra = tuple(
            CapabilityDimension(
                label=(e.get("label") or "").strip(),
                terms=tuple(e.get("terms", []) or []),
                source_qualifier=e.get("source_qualifier", ""),
            )
            for e in (row.get("extra_dimensions") or [])
            if isinstance(e, dict) and (e.get("terms") or [])
        )
        return LearnedCapability(
            key=key,
            label=row.get("label", ""),
            terms=tuple(row.get("terms", []) or []),
            source_qualifier=row.get("source_qualifier", ""),
            is_broad=bool(row.get("is_broad", False)),
            extra_dimensions=extra,
        )

    def put(self, org: str, cap: LearnedCapability) -> None:
        data = self._load(org)
        row = {
            "label": cap.label,
            "terms": list(cap.terms),
            "source_qualifier": cap.source_qualifier,
            "is_broad": cap.is_broad,
        }
        if cap.extra_dimensions:
            row["extra_dimensions"] = [
                {"label": d.label, "terms": list(d.terms), "source_qualifier": d.source_qualifier}
                for d in cap.extra_dimensions
            ]
        data[cap.key] = row
        self._path(org).write_text(json.dumps(data, indent=2), encoding="utf-8")
