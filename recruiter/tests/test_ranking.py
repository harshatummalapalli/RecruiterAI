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
        def __init__(self):
            self.n = 0
            self._lock = __import__("threading").Lock()
        def enrich(self, record):
            with self._lock:   # enrichment now runs on a thread pool
                self.n += 1

    enricher = _Counter()
    result = RankingAgent(enricher=enricher, admit_n=25, show=5).rank(role, cands)
    assert result.admitted == 25
    assert enricher.n == 25                 # only the admitted were enriched
    assert len(result.shown) == 5
    assert all(rc.record.enriched for rc in result.ranked)


def test_judging_runs_concurrently():
    # A barrier that only releases once all N judge calls are in flight at the same
    # time. If judging were sequential the first wait() would never be joined and the
    # barrier would break on timeout -> judged would not reach N. It does, so the
    # calls run concurrently.
    import threading
    role = _role()
    n = 4
    barrier = threading.Barrier(n, timeout=5)

    class _BarrierJudge:
        def judge(self, role, record):
            barrier.wait()
            return ()

    cands = [_rec(f"c{i}", "AI Architect", "Agentic Python") for i in range(n)]
    result = RankingAgent(judge=_BarrierJudge(), admit_n=n, show=n, max_judge_workers=n).rank(role, cands)
    assert result.judged == n and result.judge_failures == 0


def test_sequential_when_single_worker():
    role = _role()
    cands = [_rec(f"c{i}", "AI Architect", "Agentic Python") for i in range(3)]
    result = RankingAgent(judge=_FakeJudge(), admit_n=25, show=3, max_judge_workers=1).rank(role, cands)
    assert result.judged == 3 and result.judge_failures == 0


def test_explanation_falls_back_without_a_judge():
    role = _role()
    result = RankingAgent(admit_n=25, show=1).rank(role, [_rec("a", "AI Architect")])
    assert "not deep-verified" in result.shown[0].fit


def test_reserve_holds_the_unadmitted_pool_unjudged():
    # judge-N / show-few hedge: with admit_n=8 of 20 eligible, only 8 are judged and
    # the other 12 sit in reserve — baseline-ranked, never Judge-touched — so the
    # first view pays the Judge for 8, not 20, and nothing is discarded.
    role = _role()
    cands = [_rec(f"c{i}", "AI Architect", "Agentic Python" if i % 2 == 0 else "") for i in range(20)]
    judge = _FakeJudge()
    result = RankingAgent(judge=judge, enricher=None, admit_n=8, show=5).rank(role, cands)
    assert result.admitted == 8 and result.judged == 8 and len(result.shown) == 5
    assert len(result.reserve) == 12
    # reserve is the baseline tail: un-judged, so no Judge verdicts attached
    assert all(rec.judgments is None for rec in result.reserve)
    # the whole eligible pool is accounted for (admitted + reserve), nothing dropped
    assert len(result.ranked) + len(result.reserve) == 20
