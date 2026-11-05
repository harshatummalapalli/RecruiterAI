"""Role/title *level* — used only to FLAG fit and to pick default title
exclusions. Never gates a candidate (years do that; see seniority.py).

Two questions, kept separate:
  * What level is the ROLE being hired?        -> classify_role_level()
      drives default title exclusions + the flag's reference point.
  * How does a CANDIDATE's current title read?  -> level_note()
      an informational note for the recruiter, never an exclusion.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Coarse level bands. IC collapses junior..principal (years carry the real
# seniority); architect is a distinct IC-track shape; management is its own track.
IC = "ic"
ARCHITECT = "architect"
MANAGER = "manager"
DIRECTOR_PLUS = "director+"   # director, VP/AVP/SVP/EVP, head of, chief/CxO, founder, president

_ARCHITECT_RE = re.compile(r"\barchitect\b", re.I)
_MANAGER_RE = re.compile(r"\bmanager\b", re.I)
_DIRECTOR_PLUS_RE = re.compile(
    r"\b(?:director|managing director|vice president|vp|svp|evp|avp|assistant vice president|"
    r"head of|chief|ceo|cto|cio|cfo|coo|cpo|cmo|cro|caio|cdo|cxo|founder|co-?founder|president)\b",
    re.I,
)

# Default-excluded current titles for an ordinary IC role. Suppressed entirely
# when the role itself is architect/manager/director+ (you'd be excluding exactly
# who you're hiring). Stored onto RoleModel.exclude_titles by Intake, so the
# recruiter sees and can edit them.
_DEFAULT_EXEC_EXCLUSIONS: Tuple[str, ...] = (
    "Founder", "Co-Founder", "President",
    "CEO", "Chief Executive Officer", "CTO", "Chief Technology Officer",
    "CIO", "Chief Information Officer", "CFO", "COO", "CPO", "Chief Product Officer",
    "CMO", "CRO", "CAIO", "Chief AI Officer", "CDO", "Chief Data Officer",
    "EVP", "SVP", "VP", "AVP", "Vice President", "Assistant Vice President",
    "Managing Director", "Director", "Manager", "Head of",
)


def classify_role_level(identity: Optional[str], stated_label: Optional[str] = None) -> str:
    text = " ".join(part for part in (identity, stated_label) if part)
    if _DIRECTOR_PLUS_RE.search(text):
        return DIRECTOR_PLUS
    if _MANAGER_RE.search(text):
        return MANAGER
    if _ARCHITECT_RE.search(text):
        return ARCHITECT
    return IC


def role_suppresses_default_exclusions(role_level: str) -> bool:
    """A role that IS architect/manager/director+ must not default-exclude those
    titles — they are exactly who it's hiring."""
    return role_level in (ARCHITECT, MANAGER, DIRECTOR_PLUS)


def default_title_exclusions(role_level: str) -> Tuple[str, ...]:
    return () if role_suppresses_default_exclusions(role_level) else _DEFAULT_EXEC_EXCLUSIONS


# Coarse ordering for the informational flag only.
_FLAG_RANK = {IC: 1, ARCHITECT: 2, MANAGER: 3, DIRECTOR_PLUS: 4}


def candidate_role_level(current_title: Optional[str]) -> str:
    return classify_role_level(current_title)


# Opt-in "tighten to this role's track" exclusions (C1). NEVER applied by default
# — a role at these bands suppresses the default exclusions, so off-track titles
# can leak in; the recruiter turns this on in the brief. Reuses exclude_titles (a
# verified keyword filter). Conservative: a band excludes clearly off-track titles,
# never the role's own.
_OFF_TRACK: dict = {
    ARCHITECT: ("Manager", "Director", "Vice President", "VP", "Head of"),   # IC-technical: drop people-managers
    MANAGER: ("Director", "Vice President", "VP", "Chief", "Head of"),        # line manager: drop higher execs
    DIRECTOR_PLUS: ("Manager",),                                             # director+: drop non-director managers
}

_OFF_TRACK_LABEL = {
    ARCHITECT: "people-managers (Manager / Director / VP)",
    MANAGER: "higher-level executives (Director / VP / Chief)",
    DIRECTOR_PLUS: "non-director managers",
}


def off_track_titles(role_level: str) -> Tuple[str, ...]:
    return _OFF_TRACK.get(role_level, ())


def off_track_label(role_level: str) -> Optional[str]:
    return _OFF_TRACK_LABEL.get(role_level)


def level_note(current_title: Optional[str], role_level: str) -> Optional[str]:
    """How the candidate's current title reads against the role's level — a note
    the recruiter sees ("reads above the role's ic level (architect)"), never an
    exclusion. None when they read as the same band."""
    cand = candidate_role_level(current_title)
    c, r = _FLAG_RANK.get(cand, 1), _FLAG_RANK.get(role_level, 1)
    if c == r:
        return None
    direction = "above" if c > r else "below"
    return f"Current title reads {direction} the role's {role_level} level (candidate reads {cand})."
