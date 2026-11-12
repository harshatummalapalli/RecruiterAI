"""Feature A — dual-source intake reconciliation (pure, offline, no LLM)."""

from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.intake.reconcile import (
    SOURCE_BOTH,
    SOURCE_HM,
    SOURCE_JD,
    experience_flag,
    reconcile,
    token_matcher,
)


def _u(reqs, **kw):
    return Understanding(identity=kw.pop("identity", "Software Engineer"), requirements=tuple(reqs), **kw)


def _r(text, tier="core", when="any", evidence=None):
    return ReadRequirement(text=text, tier=tier, when=when, evidence=evidence)


# --- the matcher ------------------------------------------------------------

def test_token_matcher_pairs_differently_phrased_but_matches_subset():
    assert token_matcher("Payment systems", "payment systems integration")  # subset
    assert token_matcher("Kubernetes orchestration", "orchestration with Kubernetes")  # strong overlap
    assert not token_matcher("React frontend", "Kafka streaming")  # unrelated
    assert not token_matcher("experience with strong skills", "years of proven work")  # all stopwords -> no match


# --- the A1 tiering rule ----------------------------------------------------

def test_agreed_requirement_becomes_core_and_tagged_both():
    rec = reconcile(_u([_r("Kubernetes", tier="supporting")]), _u([_r("Kubernetes", tier="differentiator")]))
    assert len(rec.requirements) == 1
    row = rec.requirements[0]
    assert row.source == SOURCE_BOTH and row.tier == "core"          # both-mentioned -> core
    assert row.jd_tier == "supporting" and row.hm_tier == "differentiator"


def test_hm_only_requirement_is_promoted_to_core():
    # The JD never mentioned payments; the HM call surfaced it -> the real nuance.
    rec = reconcile(_u([_r("Go")]), _u([_r("Go"), _r("Payments infrastructure", tier="supporting")]))
    hm_only = rec.hm_only
    assert [r.text for r in hm_only] == ["Payments infrastructure"]
    assert hm_only[0].source == SOURCE_HM and hm_only[0].tier == "core"


def test_jd_only_requirement_is_demoted_to_non_core():
    # In the JD as a "must have" but the HM never raised it -> boilerplate -> non-core.
    rec = reconcile(_u([_r("Agile methodology", tier="core")]), _u([_r("Go")]))
    jd_only = rec.jd_only
    assert [r.text for r in jd_only] == ["Agile methodology"]
    assert jd_only[0].source == SOURCE_JD and jd_only[0].tier == "supporting"   # demoted from core


def test_merged_understanding_carries_the_reconciled_tiers():
    rec = reconcile(
        _u([_r("Go"), _r("Agile", tier="core")]),
        _u([_r("Go"), _r("Payments", tier="supporting")]),
    )
    merged = {r.text: r.tier for r in rec.merged.requirements}
    assert merged == {"Go": "core", "Agile": "supporting", "Payments": "core"}


# --- years is a HARD FILTER, never reconciled from the JD --------------------

def test_reconcile_never_nudges_years_from_the_jd():
    # JD says 3, HM prose says 8 — but minimum years is the recruiter's boundary
    # filter, not a JD-derived value, so reconciliation raises NO conflict here.
    rec = reconcile(_u([_r("Go")], min_years=3), _u([_r("Go")], min_years=8))
    assert not hasattr(rec, "conflicts") or getattr(rec, "conflicts", ()) == ()


def test_experience_flag_catches_recruiter_slip_vs_hm_prose():
    # Recruiter's filter is 3; the HM's notes said 5 -> surface it to confirm/fix.
    hm = _u([_r("Go")], min_years=5)
    flag = experience_flag(hm, boundary_min_years=3)
    assert flag is not None and flag.boundary_years == 3 and flag.hm_mentioned_years == 5


def test_experience_flag_silent_when_hm_has_no_years_or_they_agree():
    assert experience_flag(_u([_r("Go")]), boundary_min_years=3) is None          # HM gave none
    assert experience_flag(_u([_r("Go")], min_years=3), boundary_min_years=3) is None  # agree
    assert experience_flag(_u([_r("Go")], min_years=5), boundary_min_years=None) is None  # no filter yet


# --- provenance / merge preferences -----------------------------------------

def test_both_source_prefers_hm_phrasing_and_when():
    rec = reconcile(
        _u([_r("payment systems", when="any")]),
        _u([_r("payment systems integration", when="current", evidence="HM: must be doing it now")]),
    )
    row = rec.agree[0]
    assert row.text == "payment systems integration"       # HM phrasing
    assert row.when == "current" and row.evidence == "HM: must be doing it now"


def test_posted_title_prefers_the_published_jd():
    rec = reconcile(
        _u([_r("Go")], posted_title="Senior Backend Engineer", posted_title_source="jd"),
        _u([_r("Go")], posted_title="Backend person", posted_title_source="recruiter"),
    )
    assert rec.merged.posted_title == "Senior Backend Engineer"
