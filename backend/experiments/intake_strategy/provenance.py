"""Deterministic provenance report for an extracted intent (EXPERIMENT ONLY).

Reuses the lexical "is this stated" check the repo already trusts (requirement_provenance.stated_evidence: nearly all
of a claim's meaningful words in ONE sentence). The model's own claims are never trusted. Each atom is classified:

    JD        stated in the job description
    BRIEF     stated in the recruiter brief
    APPROVED  introduced by an existing versioned taxonomy entry (role_family_taxonomy)
    INFERRED  none of the above: recorded for understanding, must not become a hard constraint

Known limit, reported rather than hidden: the check is lexical, so a faithful paraphrase is reported INFERRED
(a false drop). The false-drop rate is a result of the experiment, not something this module tunes away.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.models.structured_intent import StructuredHiringIntent
from backend.services import role_family_taxonomy as taxonomy
from backend.services.requirement_provenance import _sentences, stated_evidence


def _atoms(intent: StructuredHiringIntent) -> List[Dict[str, str]]:
    atoms: List[Dict[str, str]] = []
    for s in intent.skills:
        atoms.append({"kind": "skill", "value": s.name, "strength": s.strength})
    for g in intent.skill_any_of:
        for option in g.any_of:
            atoms.append({"kind": "skill_any_of", "value": option, "strength": g.strength})
    for e in intent.evidence_signals:
        atoms.append({"kind": "evidence_signal", "value": e.name, "strength": e.strength})
    for r in intent.role_family:
        atoms.append({"kind": "role_family", "value": r, "strength": "required"})
    for c in intent.companies:
        atoms.append({"kind": "company", "value": c.name, "strength": c.strength})
    for x in intent.exclusions:
        atoms.append({"kind": f"exclusion:{x.kind}", "value": x.value, "strength": "negative"})
    if intent.education:
        for d in intent.education.degrees:
            atoms.append({"kind": "degree", "value": d, "strength": intent.education.strength})
        for s in intent.education.streams:
            atoms.append({"kind": "stream", "value": s, "strength": intent.education.strength})
    if intent.location:
        for e in intent.location.entries:
            atoms.append({"kind": "location", "value": e, "strength": intent.location.strength})
    if intent.seniority:
        atoms.append({"kind": "seniority", "value": intent.seniority.value, "strength": intent.seniority.strength})
    return atoms


def provenance_report(intent: StructuredHiringIntent, jd_text: str, brief_text: str) -> Dict[str, Any]:
    jd_sentences, brief_sentences = _sentences(jd_text), _sentences(brief_text)
    rows: List[Dict[str, Any]] = []
    for atom in _atoms(intent):
        # Locations and degrees are normalised ("City, State, Country"), so match on the head term only.
        probe = atom["value"].split(",")[0] if atom["kind"] == "location" else atom["value"]
        in_jd = stated_evidence(probe, jd_sentences)
        in_brief = stated_evidence(probe, brief_sentences)
        if in_jd and in_brief:
            source = "JD+BRIEF"
        elif in_jd:
            source = "JD"
        elif in_brief:
            source = "BRIEF"
        elif atom["kind"] == "role_family" and taxonomy.lookup(atom["value"]):
            source = "APPROVED"
        else:
            source = "INFERRED"
        rows.append({**atom, "source": source, "evidence": in_jd or in_brief})
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    hard_inferred = [r for r in rows if r["source"] == "INFERRED" and r["strength"] == "required"]
    return {
        "atoms": rows,
        "counts": counts,
        "inferred_but_required": hard_inferred,
        "note": "lexical check; a faithful paraphrase reads INFERRED (false drop)",
    }
