"""A grounded, recruiter-readable summary of why a candidate fits — ONE short
paragraph composed only from the Judge's verified 'met' judgments, replacing the
line-by-line "Evidence: a; b; c" dump that overwhelmed the record. The per-
requirement detail still lives in the ledger (one click away); this is the lead.

Grounded means: every number and name here traces to a verified judgment on this
candidate. Nothing is scored, ranked, or phrased as a percentage.
"""

from __future__ import annotations

from recruiter.agents.ranking.evidence import title_relevance
from recruiter.candidates import CandidateRecord
from recruiter.role_model import RoleModel


def _names(judgments, limit: int = 2) -> list:
    out = []
    for j in judgments:
        name = (j.get("signal_text") or j.get("term") or "").strip()
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def evidence_summary(role: RoleModel, record: CandidateRecord) -> str:
    """One or two plain sentences, grounded in the verified judgments."""
    judgments = record.judgments or ()
    if not judgments:
        # Not deep-read (Judge failed or skipped) — say so honestly.
        return f"The title reads {title_relevance(role, record)} to the role; the profile was not read in depth."

    met = [j for j in judgments if j.get("verdict") == "met"]
    core = [j for j in judgments if j.get("tier") == "core"]
    core_met = [j for j in core if j.get("verdict") == "met"]

    if not met:
        return "Read in depth — none of the stated requirements were evidenced on the profile."

    # Lead on core coverage, naming the one or two strongest verified requirements.
    if core:
        lead = f"Evidenced {len(core_met)} of {len(core)} core requirement{'s' if len(core) != 1 else ''}"
        highlights = _names(core_met) or _names(met)
    else:
        lead = f"Evidenced {len(met)} requirement{'s' if len(met) != 1 else ''}"
        highlights = _names(met)
    if highlights:
        lead += " — " + " and ".join(highlights)

    # Count the rest (supporting + differentiator) as a tail, without listing them.
    extra = len([j for j in met if j.get("tier") in ("supporting", "differentiator")])
    tail = f", plus {extra} supporting signal{'s' if extra != 1 else ''}" if extra else ""

    # One grounding quote from the strongest verified claim.
    quote = next((j.get("quote") for j in (core_met or met) if j.get("quote")), None)
    quoted = f' In their own words: “{quote.strip()}”.' if quote else ""

    return f"{lead}{tail}.{quoted}"
