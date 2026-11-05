"""The grounded evidence summary — one paragraph from verified judgments, never
the line-by-line dump, never a score/rank/percentage."""

import re

from recruiter.agents.ranking.summary import evidence_summary
from recruiter.candidates import CandidateRecord
from recruiter.role_model import ARCHITECT, JD, Location, Provenance, Requirement, RoleModel, Seniority


def _role():
    return RoleModel(
        identity="AI Architect",
        seniority=Seniority(12, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("India",)),
        requirements=(
            Requirement("Agentic Systems", "core", Provenance(JD)),
            Requirement("Python", "core", Provenance(JD)),
            Requirement("Kafka", "supporting", Provenance(JD)),
        ),
    )


def _rec(judgments=None):
    return CandidateRecord(candidate_id="c1", name="Asha", title="AI Architect",
                           raw={"basic_profile": {"headline": "builds agentic systems"}}, judgments=judgments)


def test_summary_leads_on_core_coverage_and_names_the_strongest():
    judgments = (
        {"tier": "core", "signal_text": "Agentic Systems", "verdict": "met", "quote": "Built agentic pipelines in production"},
        {"tier": "core", "signal_text": "Python", "verdict": "met", "quote": "10 years of Python"},
        {"tier": "supporting", "signal_text": "Kafka", "verdict": "met", "quote": "Kafka at scale"},
    )
    s = evidence_summary(_role(), _rec(judgments))
    assert s.startswith("Evidenced 2 of 2 core requirements")
    assert "Agentic Systems" in s and "Python" in s
    assert "plus 1 supporting signal" in s          # supporting counted, not listed
    assert "“Built agentic pipelines in production”" in s  # one grounding quote
    # never a score / rank / percentage
    assert not re.search(r"\d+%|match score|rank(ed|ing)?\b", s)


def test_summary_is_honest_when_partly_evidenced():
    judgments = (
        {"tier": "core", "signal_text": "Agentic Systems", "verdict": "met", "quote": "agentic work"},
        {"tier": "core", "signal_text": "Python", "verdict": "not_evidenced"},
    )
    s = evidence_summary(_role(), _rec(judgments))
    assert s.startswith("Evidenced 1 of 2 core requirements")


def test_summary_falls_back_without_judgments():
    s = evidence_summary(_role(), _rec(None))
    assert "not read in depth" in s


def test_summary_says_nothing_evidenced_when_all_missed():
    judgments = ({"tier": "core", "signal_text": "Agentic Systems", "verdict": "not_evidenced"},)
    s = evidence_summary(_role(), _rec(judgments))
    assert "none of the stated requirements were evidenced" in s
