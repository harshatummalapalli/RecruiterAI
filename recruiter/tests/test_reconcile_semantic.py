"""Feature A — the semantic matcher (fake `complete`, no network/LLM)."""

from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.intake.reconcile import reconcile
from recruiter.agents.intake.reconcile_semantic import make_semantic_matcher


def _u(reqs):
    return Understanding(identity="Marketing Automation Lead", requirements=tuple(reqs))


def _fake_complete(pairs):
    """A complete() double that returns a fixed pair list regardless of prompt."""
    def complete(system, user, model):
        return {"pairs": pairs}
    return complete


def test_semantic_matcher_pairs_tool_with_its_category():
    jd = _u([ReadRequirement("Marketing automation platforms", "core")])
    hm = _u([ReadRequirement("Marketo administration", "core")])
    # Token matcher alone would MISS this (no shared words) -> two separate rows.
    matcher = make_semantic_matcher(jd, hm, complete=_fake_complete([[0, 0]]))
    rec = reconcile(jd, hm, matcher=matcher)

    assert len(rec.requirements) == 1                         # merged, not split
    assert rec.agree[0].source == "both" and rec.agree[0].tier == "core"
    assert rec.agree[0].text == "Marketo administration"      # HM phrasing kept


def test_semantic_matcher_still_honours_obvious_lexical_matches():
    # Even if the LLM returns nothing, the union with token_matcher keeps the
    # plain lexical pairing.
    jd = _u([ReadRequirement("Email marketing", "core")])
    hm = _u([ReadRequirement("Email marketing", "supporting")])
    matcher = make_semantic_matcher(jd, hm, complete=_fake_complete([]))
    rec = reconcile(jd, hm, matcher=matcher)
    assert rec.agree and rec.agree[0].source == "both"


def test_semantic_matcher_fails_open_on_llm_error():
    jd = _u([ReadRequirement("Marketing automation platforms", "core")])
    hm = _u([ReadRequirement("Marketo administration", "core")])

    def boom(system, user, model):
        raise RuntimeError("no api key")

    matcher = make_semantic_matcher(jd, hm, complete=boom)
    # Fell back to token_matcher: these two don't share tokens -> stay separate,
    # but nothing crashed and reconciliation still produced a result.
    rec = reconcile(jd, hm, matcher=matcher)
    assert {r.source for r in rec.requirements} == {"jd", "hm"}


def test_semantic_matcher_ignores_out_of_range_indices():
    jd = _u([ReadRequirement("A", "core")])
    hm = _u([ReadRequirement("B", "core")])
    matcher = make_semantic_matcher(jd, hm, complete=_fake_complete([[5, 9], ["x", 0]]))
    rec = reconcile(jd, hm, matcher=matcher)
    assert {r.source for r in rec.requirements} == {"jd", "hm"}   # no bogus pairing
