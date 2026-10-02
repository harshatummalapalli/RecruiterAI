"""Phase 1 — the CrustData capability map (code-owned source of truth).

The compiler reads this to decide how each signal may be executed. It is NOT
the catalog of every documented field; it records what we have *established*
about the fields we actually use, on three independent axes:

  filter_status   verified | unverified | unavailable
      Can the provider actually constrain retrieval on this field, on OUR plan?
      (verified = we ran it live and it worked.)
  response_status returned | response_gated
      Can we read the value back in the result? ('response_gated' = filterable
      but blank/absent in responses — e.g. description, education.field_of_study.)
  data_confidence high | unknown
      Do we have evidence the provider data is complete/reliable enough to lean
      on? ('unknown' is NOT a veto — see the routing rule below.)

Routing rule (the consensus, incl. the agreed refinement):
  - filter_status unavailable/unverified  -> NEVER a silent hard filter.
        -> 'judge' if the signal is verifiable downstream, else 'disclose'.
  - filter_status verified + preferred     -> a provider boost is created ONLY
        if a VERIFIED provider preference mechanism exists. CrustData has none
        (NL injection proven inert, 2026-10-01), so preferred -> context/evidence.
  - filter_status verified + required:
        data_confidence high                      -> 'enforce'
        data_confidence unknown + response_gated   -> 'enforce_but_not_verifiable'
              (filterable server-side but not displayable; disclose / Harvest-verify)
        data_confidence unknown (returned)         -> 'enforce_with_warning'
              (use it — it is experimentally validated — but warn on completeness
               and verify downstream where possible)

Seeded from live probes on 2026-10-01 (see memory: crustdata-verified-capabilities).
Refresh with the `backend/experiments/structured_playground` probes when CrustData drifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# No VERIFIED provider-side soft-preference mechanism exists on our plan.
# Natural-language company injection was measured to be inert (arm C == arm D,
# 2026-10-01). Flip to True only if a real boost mechanism is later verified.
PREFERENCE_MECHANISM_AVAILABLE = False

# CrustData's `(.)` operator matches WHOLE WORDS, not substrings
# (verified: `(.) "Java"` excludes JavaScript-only profiles).
FUZZY_IS_WHOLE_WORD = True

FILTER_VERIFIED = "verified"
FILTER_UNVERIFIED = "unverified"
FILTER_UNAVAILABLE = "unavailable"
RESP_RETURNED = "returned"
RESP_GATED = "response_gated"
CONF_HIGH = "high"
CONF_UNKNOWN = "unknown"


@dataclass(frozen=True)
class FieldCapability:
    field: str
    filter_status: str
    response_status: str
    data_confidence: str
    downstream_verifiable: bool  # can Harvest/the judge confirm it per-candidate?
    note: str = ""


def _c(field, fs, rs, dc, dv, note=""):
    return FieldCapability(field, fs, rs, dc, dv, note)

# Fields we actually use, with established status. Anything not listed resolves
# to a conservative UNVERIFIED default via get().
_MAP: Dict[str, FieldCapability] = {c.field: c for c in [
    # --- company ---
    _c("experience.employment_details.current.company_name", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("experience.employment_details.company_name", FILTER_VERIFIED, RESP_RETURNED, CONF_UNKNOWN, True,
       "any-time; result ordering skews to PAST employees, not current-preferred"),
    _c("experience.employment_details.past.company_name", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    # --- titles ---
    _c("experience.employment_details.current.title", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("experience.employment_details.past.title", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    # --- descriptions / headline / summary (keyword skill retrieval) ---
    _c("experience.employment_details.current.description", FILTER_VERIFIED, RESP_GATED, CONF_UNKNOWN, True,
       "filterable server-side, NOT returned; lower recall (~1.4% populated) -> OR with headline/summary"),
    _c("experience.employment_details.past.description", FILTER_VERIFIED, RESP_GATED, CONF_UNKNOWN, True),
    _c("basic_profile.headline", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True,
       "populated; main skill-bearing field available at retrieval time"),
    _c("basic_profile.summary", FILTER_VERIFIED, RESP_GATED, CONF_UNKNOWN, True),
    # --- numeric / geo / experience ---
    _c("years_of_experience_raw", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("basic_profile.location.country", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("basic_profile.location.state", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("basic_profile.location.city", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True),
    _c("basic_profile.location", FILTER_VERIFIED, RESP_RETURNED, CONF_HIGH, True, "geo_distance"),
    # --- company scale ---
    _c("experience.employment_details.current.company_headcount_latest", FILTER_VERIFIED, RESP_RETURNED, CONF_UNKNOWN, False,
       "verified filter; populated for large firms, completeness unestablished; NOT in profile text so judge cannot re-verify -> warn"),
    # --- education ---
    _c("education.schools.degree", FILTER_VERIFIED, RESP_RETURNED, CONF_UNKNOWN, True,
       "degree populated/returned (B.Tech/B.E/M.Tech)"),
    _c("education.schools.field_of_study", FILTER_VERIFIED, RESP_GATED, CONF_UNKNOWN, True,
       "stream filterable server-side but returned BLANK -> enforce-only; verify via Harvest if needed"),
    # --- unavailable ---
    _c("skills.professional_network_skills", FILTER_UNAVAILABLE, RESP_GATED, CONF_UNKNOWN, True,
       "skills LIST filter unavailable on our plan; use description/headline keyword + Harvest skills"),
    _c("work_mode", FILTER_UNAVAILABLE, RESP_GATED, CONF_UNKNOWN, False,
       "no work_mode filter on person_search (job_search only) -> disclose context-only"),
]}


def get(field: str) -> FieldCapability:
    """Known field -> its capability; unknown field -> a conservative UNVERIFIED
    default so the compiler never hard-filters on something unestablished."""
    return _MAP.get(field, _c(field, FILTER_UNVERIFIED, RESP_GATED, CONF_UNKNOWN, False,
                              "field not in capability map -> treated as unverified (never a silent hard filter)"))


def can_hard_filter(field: str):
    """(allowed, warning). Verified only; warning set when data_confidence unknown."""
    cap = get(field)
    if cap.filter_status != FILTER_VERIFIED:
        return False, None
    if cap.data_confidence == CONF_UNKNOWN:
        return True, f"{field}: filter verified but data completeness unestablished"
    return True, None


def is_displayable(field: str) -> bool:
    return get(field).response_status == RESP_RETURNED


def recommend_routing(field: str, strength: str) -> str:
    """Map (field capability x recruiter-intent strength) to a routing token.
    Returns one of: enforce | enforce_with_warning | enforce_but_not_verifiable
    | context_or_evidence | judge | disclose. Matches the regression-suite vocabulary."""
    cap = get(field)

    if cap.filter_status in (FILTER_UNAVAILABLE, FILTER_UNVERIFIED):
        return "judge" if cap.downstream_verifiable else "disclose"

    # verified below
    if strength == "preferred":
        if PREFERENCE_MECHANISM_AVAILABLE:
            return "enforce"  # a real, verified boost
        return "context_or_evidence"  # no inert pretending

    # required + verified
    if cap.data_confidence == CONF_HIGH:
        return "enforce"
    if cap.response_status == RESP_GATED:
        return "enforce_but_not_verifiable"
    return "enforce_with_warning"
