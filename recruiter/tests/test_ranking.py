"""Agent 5 (Ranking) — offline (fake Judge/enricher). Proves the fixes to the
original pain: evidence-aware admission, verified ranking, the failure-floor,
and evidence-based explanations."""

from recruiter.agents.ranking import RankingAgent
from recruiter.agents.ranking.score import baseline_score
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
            Requirement("Java", "core", Provenance(JD), when="past"),
        ),
    )


def _rec(cid, title, headline="", mq=("natural_language",)):
    return CandidateRecord(candidate_id=cid, name=cid, title=title,
                           raw={"basic_profile": {"headline": headline}}, matched_queries=mq)


def test_baseline_is_evidence_aware_not_a_coinflip():
    role = _role()
    strong = _rec("strong", "AI Architect", "built Agentic Systems with Python")
    bare = _rec("bare", "AI Architect")      # same title, no requirement evidence
    assert baseline_score(role, strong) > baseline_score(role, bare)


class _FakeJudge:
    """Marks a requirement met when its first word appears in the headline."""
    def judge(self, role, record):
        hl = ((record.raw.get("basic_profile") or {}).get("headline") or "").lower()
        return tuple(
            {"tier": r.tier, "signal_text": r.text, "verdict": "met" if r.text.split()[0].lower() in hl else "not_evidenced",
             "quote": r.text if r.text.split()[0].lower() in hl else ""}
            for r in role.requirements
        )


def test_verified_ranking_surfaces_the_real_match_first():
    role = _role()
    cands = [
        _rec("weak", "AI Architect", "generalist"),
        _rec("real", "AI Architect", "Agentic Systems and Python in production"),
    ]
    result = RankingAgent(judge=_FakeJudge(), admit_n=25, show=2).rank(role, cands)
    assert result.shown[0].record.candidate_id == "real"
    assert "Evidence:" in result.shown[0].fit
    assert result.judged == 2 and result.judge_failures == 0


class _FlakyJudge:
    def judge(self, role, record):
        return None if record.candidate_id == "top" else ()   # fails only for 'top'


def test_failure_floor_keeps_a_judge_failed_candidate_afloat():
    role = _role()
    top = _rec("top", "AI Architect", "Agentic Systems, Python, production")   # strongest evidence
    others = [_rec(f"o{i}", "AI Architect", "generalist") for i in range(3)]
    result = RankingAgent(judge=_FlakyJudge(), admit_n=25, show=5).rank(role, [top] + others)
    ids = [rc.record.candidate_id for rc in result.ranked]
    # Judge failed for 'top', but the regex floor keeps it ahead of the empty-evidence others.
    assert ids[0] == "top"
    assert result.judge_failures == 1


def test_admission_caps_and_enrich_only_admitted():
    role = _role()
    cands = [_rec(f"c{i}", "AI Architect", "Agentic Python" if i < 2 else "") for i in range(30)]

    class _Counter:
        def __init__(self): self.n = 0
        def enrich(self, record): self.n += 1

    enricher = _Counter()
    result = RankingAgent(enricher=enricher, admit_n=25, show=5).rank(role, cands)
    assert result.admitted == 25
    assert enricher.n == 25                 # only the admitted were enriched
    assert len(result.shown) == 5
    assert all(rc.record.enriched for rc in result.ranked)


def test_explanation_falls_back_without_a_judge():
    role = _role()
    result = RankingAgent(admit_n=25, show=1).rank(role, [_rec("a", "AI Architect")])
    assert "not deep-verified" in result.shown[0].fit
