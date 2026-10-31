"""RoleModel <-> plain dict, for JSON persistence (the OCI SearchStore writes
`json.dumps(record, default=str)` and reads `json.loads`). `to_dict` is just
`dataclasses.asdict`; `from_dict` rebuilds the frozen dataclass spine from the
loaded JSON (tuples come back as lists, so every sequence is re-tupled).

Pure — no I/O, no backend import — so it round-trips offline in tests and the
bridge layer can store a confirmed model and load it back byte-for-byte.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

from recruiter.role_model import (
    INFERRED,
    CapabilityGroup,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def to_dict(model: RoleModel) -> Dict[str, Any]:
    return dataclasses.asdict(model)


def _prov(data: Optional[Dict[str, Any]]) -> Provenance:
    if not data:
        return Provenance(INFERRED)
    return Provenance(data.get("source") or INFERRED, data.get("evidence"))


def from_dict(data: Dict[str, Any]) -> RoleModel:
    loc = data.get("location") or {}
    sen = data.get("seniority") or {}
    co = data.get("companies") or {}
    return RoleModel(
        identity=data["identity"],
        seniority=Seniority(sen.get("min_years"), sen.get("max_years"), _prov(sen.get("provenance"))),
        role_level=data.get("role_level"),
        location=Location(
            countries=tuple(loc.get("countries") or ()),
            states=tuple(loc.get("states") or ()),
            cities=tuple(loc.get("cities") or ()),
            preferred_cities=tuple(loc.get("preferred_cities") or ()),
            radius_place=loc.get("radius_place"),
            radius_miles=loc.get("radius_miles"),
            work_mode=loc.get("work_mode"),
        ),
        requirements=tuple(
            Requirement(r["text"], r["tier"], _prov(r.get("provenance")),
                        bool(r.get("hard", False)), r.get("when", "any"))
            for r in (data.get("requirements") or ())
        ),
        capability_groups=tuple(
            CapabilityGroup(g["label"], tuple(g.get("terms") or ()),
                            g.get("source_qualifier", ""), g.get("rationale", ""))
            for g in (data.get("capability_groups") or ())
        ),
        companies=CompanyRules(
            exclude_current=tuple(co.get("exclude_current") or ()),
            exclude_ever=tuple(co.get("exclude_ever") or ()),
            prefer_current=tuple(co.get("prefer_current") or ()),
            prefer_ever=tuple(co.get("prefer_ever") or ()),
        ),
        exclude_titles=tuple(data.get("exclude_titles") or ()),
        industries=tuple(data.get("industries") or ()),
        disqualifiers=tuple(data.get("disqualifiers") or ()),
        posted_title=data.get("posted_title"),
        posted_title_source=data.get("posted_title_source"),
        employment_type=data.get("employment_type"),
        hiring_company=data.get("hiring_company"),
        limitations=tuple(data.get("limitations") or ()),
        model_id=data.get("model_id"),
    )
