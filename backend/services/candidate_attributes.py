"""Deterministic candidate attributes derived from the CrustData person record.

Pure functions, no LLM, no network, no credits. Everything here is read straight
off the thin CrustData payload we ALREADY fetch (``experience.employment_details``
and ``basic_profile.normalized_title``) — the signals the product used to discard.

Produces a structured read a recruiter can filter and rank on:
  * company classification  — Startup / Product / Enterprise / GCC / Services
  * seniority               — CrustData's normalized band + an IC level parsed
                              from the title (Senior/Lead/Staff/Principal/…)
  * function + normalized role
  * recency / tenure / derived years of experience
  * data freshness (when CrustData last refreshed the record)

CrustData has NO built-in startup/GCC/product/services label — `company_type` is
only LinkedIn's org form (Public/Private/…). We DERIVE the kind from industry +
headcount + HQ-vs-candidate country. Funding / founded-year would sharpen Startup
vs mid-size but need a paid company lookup, so they are left for an optional pass.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --- company classification -------------------------------------------------

COMPANY_STARTUP = "Startup"
COMPANY_PRODUCT = "Product"
COMPANY_ENTERPRISE = "Enterprise"
COMPANY_GCC = "GCC / captive"
COMPANY_SERVICES = "IT Services"
COMPANY_UNKNOWN = "Unknown"

# headcount cut-offs (latest total); ranges are used when the exact count is absent.
_STARTUP_MAX = 200
_ENTERPRISE_MIN = 10000
_GCC_MIN_HEADCOUNT = 2000  # a captive centre is a BIG foreign company with local staff

_SERVICES_RE = re.compile(r"it services|information technology (and|&) services|consulting|outsourc|business process|staffing", re.I)
_SMALL_RANGES = {"1-10", "11-50", "51-200", "self-employed", "0-1"}
_LARGE_RANGES = {"10001+", "5001-10000"}

# --- seniority (IC ladder parsed from the raw title) ------------------------

# Ordered high → low; the first that appears in the title wins.
_IC_LEVELS = [
    ("Distinguished", r"\bdistinguished\b"),
    ("Fellow", r"\bfellow\b"),
    ("Principal", r"\bprincipal\b"),
    ("Staff", r"\bstaff\b"),
    ("Architect", r"\barchitect\b"),
    ("Lead", r"\blead\b|\bleads?\b"),
    ("Senior", r"\bsenior\b|\bsr\.?\b"),
    ("Mid", r"\b(engineer|developer|analyst|scientist|manager)\b"),
    ("Junior", r"\bjunior\b|\bjr\.?\b|\bassociate\b|\bintern(ship)?\b|\btrainee\b"),
]

_COUNTRY_ALIASES = {
    "usa": "united states", "us": "united states", "u.s.": "united states", "u.s.a.": "united states",
    "united states of america": "united states",
    "uk": "united kingdom", "u.k.": "united kingdom", "great britain": "united kingdom",
    "ind": "india", "uae": "united arab emirates",
}


def _norm_country(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    return _COUNTRY_ALIASES.get(v, v)


@dataclass
class CandidateAttributes:
    company_type: str = COMPANY_UNKNOWN
    company_type_basis: str = ""
    seniority_band: Optional[str] = None       # CrustData's normalized seniority_level
    ic_level: Optional[str] = None             # parsed from the title
    function: Optional[str] = None             # function_category
    role_normalized: Optional[str] = None      # normalized_title (when confident)
    tenure_label: Optional[str] = None         # years_at_company string
    recently_started: bool = False             # current role began within ~12 months
    years_experience: Optional[float] = None   # derived from earliest dated role
    data_updated_at: Optional[str] = None      # when CrustData last refreshed the record
    company_industries: List[str] = field(default_factory=list)
    company_headcount: Optional[int] = None
    company_hq_country: Optional[str] = None


def _m(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _current_role(raw: Dict[str, Any]) -> Dict[str, Any]:
    cur = (_m(_m(_m(raw).get("experience")).get("employment_details")).get("current")) or []
    return _m(cur[0] if cur else None)


def _classify_company(role: Dict[str, Any], candidate_country: Optional[str]) -> tuple[str, str]:
    industries = [i for i in (role.get("company_industries") or []) if isinstance(i, str)]
    ind_blob = " ".join(industries)
    headcount = role.get("company_headcount_latest")
    headcount = headcount if isinstance(headcount, int) else None
    hc_range = (role.get("company_headcount_range") or "").strip()
    hq = _norm_country(role.get("company_headquarters_country"))
    cand = _norm_country(candidate_country)

    if not industries and headcount is None and not hc_range and not hq:
        return COMPANY_UNKNOWN, "no company data on the record"

    if _SERVICES_RE.search(ind_blob):
        return COMPANY_SERVICES, f"industry: {industries[0] if industries else 'IT services'}"

    big = (headcount is not None and headcount >= _GCC_MIN_HEADCOUNT) or hc_range in _LARGE_RANGES
    if hq and cand and hq != cand and big:
        return COMPANY_GCC, f"HQ {role.get('company_headquarters_country')}, large presence in {candidate_country}"

    if (headcount is not None and headcount <= _STARTUP_MAX) or hc_range in _SMALL_RANGES:
        return COMPANY_STARTUP, f"~{headcount or hc_range} headcount (funding/founded not checked)"

    if (headcount is not None and headcount >= _ENTERPRISE_MIN) or hc_range in _LARGE_RANGES:
        return COMPANY_ENTERPRISE, f"~{headcount or hc_range} headcount"

    return COMPANY_PRODUCT, f"~{headcount or hc_range or '?'} headcount, not services/captive"


def _ic_level(title: Optional[str]) -> Optional[str]:
    t = (title or "").lower()
    for label, pattern in _IC_LEVELS:
        if re.search(pattern, t):
            return label
    return None


def _year(date_str: Optional[str]) -> Optional[int]:
    if not isinstance(date_str, str) or len(date_str) < 4 or not date_str[:4].isdigit():
        return None
    return int(date_str[:4])


def _derived_years(raw: Dict[str, Any], now: datetime) -> Optional[float]:
    ed = _m(_m(_m(raw).get("experience")).get("employment_details"))
    starts: List[int] = []
    for bucket in ("current", "past"):
        for role in (ed.get(bucket) or []):
            y = _year(_m(role).get("start_date"))
            if y:
                starts.append(y)
    if not starts:
        return None
    return round(max(0.0, now.year - min(starts) + (now.month - 1) / 12.0), 1)


def derive_attributes(raw: Dict[str, Any], *, candidate_country: Optional[str] = None,
                      now: Optional[datetime] = None) -> CandidateAttributes:
    raw = _m(raw)
    now = now or datetime.now(timezone.utc)
    role = _current_role(raw)
    basic = _m(raw.get("basic_profile"))
    nt = _m(basic.get("normalized_title"))
    if candidate_country is None:
        candidate_country = _m(basic.get("location")).get("country")

    company_type, basis = _classify_company(role, candidate_country)
    start = role.get("start_date")
    start_year = _year(start)
    recently = bool(start_year and (now.year - start_year) * 12 + (now.month - _month(start)) <= 12)

    headcount = role.get("company_headcount_latest")
    return CandidateAttributes(
        company_type=company_type,
        company_type_basis=basis,
        seniority_band=role.get("seniority_level") or None,
        ic_level=_ic_level(role.get("title") or basic.get("current_title")),
        function=role.get("function_category") or None,
        role_normalized=(nt.get("sub_department") or nt.get("matched_title")) if nt.get("confident") else None,
        tenure_label=role.get("years_at_company") or None,
        recently_started=recently,
        years_experience=_derived_years(raw, now),
        data_updated_at=_m(raw.get("metadata")).get("updated_at"),
        company_industries=[i for i in (role.get("company_industries") or []) if isinstance(i, str)][:3],
        company_headcount=headcount if isinstance(headcount, int) else None,
        company_hq_country=role.get("company_headquarters_country") or None,
    )


def _month(date_str: Optional[str]) -> int:
    if isinstance(date_str, str) and len(date_str) >= 7 and date_str[5:7].isdigit():
        return int(date_str[5:7])
    return 1


def attributes_dict(raw: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    return asdict(derive_attributes(raw, **kwargs))
