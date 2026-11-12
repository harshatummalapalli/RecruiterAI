"""Feature A — IntakeAgent dual-source wiring (fake reader, no OpenAI)."""

import pytest

from recruiter.agents.intake.agent import IntakeAgent
from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.intake.reconcile import token_matcher


def _reader(mapping):
    def reader(notes, posted_title=None):
        return mapping[notes.strip()]
    return reader


# Deterministic pairing keeps these wiring tests hermetic (no LLM); the semantic
# matcher is exercised separately in test_reconcile_semantic.py.
def _agent(mapping):
    return IntakeAgent(reader=_reader(mapping), matcher_factory=lambda jd, hm: token_matcher)


def _u(reqs, **kw):
    return Understanding(identity="Software Engineer", requirements=tuple(reqs), **kw)


def test_read_dual_reconciles_requirements_not_the_years_filter():
    jd = _u([ReadRequirement("Go", "core"), ReadRequirement("Agile", "core")], min_years=3)
    hm = _u([ReadRequirement("Go", "core"), ReadRequirement("Payments", "supporting")], min_years=8)
    agent = _agent({"JD": jd, "HM": hm})

    merged, rec = agent.read_dual("JD", "HM")

    assert rec is not None
    # Only REQUIREMENTS are reconciled (HM-only -> core, JD-only -> supporting).
    assert {r.text: r.tier for r in merged.requirements} == {"Go": "core", "Agile": "supporting", "Payments": "core"}
    # Years is a hard boundary filter — reconciliation raises no conflict over it.
    assert getattr(rec, "conflicts", ()) == ()


def test_read_dual_single_source_is_byte_identical_and_no_diff():
    jd = _u([ReadRequirement("Go", "core"), ReadRequirement("Agile", "core")])
    agent = _agent({"JD": jd})

    merged, rec = agent.read_dual("JD", "   ")        # blank HM brief

    assert rec is None
    assert merged is jd                               # same object -> unchanged (A2)


def test_read_dual_requires_at_least_one_source():
    agent = _agent({})
    with pytest.raises(ValueError):
        agent.read_dual("", None)
