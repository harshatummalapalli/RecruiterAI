"""Agent 4 (Search) — merge + geo net, offline (fake provider, no credits)."""

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.search import SearchAgent
from recruiter.agents.search.merge import enforce_geo, merge
from recruiter.candidates import CandidateRecord


class _FakeProvider:
    def __init__(self, records):
        self._records = records
        self.calls = 0

    def search(self, query, page_size):
        self.calls += 1
        self.page_size = page_size
        return list(self._records)


def _rec(cid, loc=None, mq=()):
    return CandidateRecord(candidate_id=cid, location=loc, matched_queries=mq)


def test_merge_dedupes_and_unions_matched_queries():
    merged = merge([
        _rec("a", mq=("natural_language",)),
        _rec("a", mq=("title_expansion",)),
        _rec("b", mq=("natural_language",)),
    ])
    assert [r.candidate_id for r in merged] == ["a", "b"]
    assert set(merged[0].matched_queries) == {"natural_language", "title_expansion"}


def test_geo_keeps_unknown_drops_out_of_scope():
    kept, dropped = enforce_geo(
        [_rec("a", "Hyderabad, India"), _rec("b", "Berlin, Germany"), _rec("c", None)],
        countries=("India",),
    )
    assert {r.candidate_id for r in kept} == {"a", "c"}        # unknown kept
    assert {r.candidate_id for r in dropped} == {"b"}


def test_no_geo_scope_keeps_everyone():
    kept, dropped = enforce_geo([_rec("a", "Berlin")], countries=(), states=())
    assert len(kept) == 1 and dropped == []


def test_search_agent_runs_offline_and_reports_credits():
    provider = _FakeProvider([
        _rec("a", "Pune, India", ("natural_language",)),
        _rec("a", "Pune, India", ("title_expansion",)),   # dup
        _rec("b", "London, UK", ("natural_language",)),    # out of geo
        _rec("c", None, ("natural_language",)),             # unknown -> kept
    ])
    query = ProviderQuery(natural_language="…", countries=("India",))
    result = SearchAgent(provider, page_size=50).run(query)

    assert provider.calls == 1 and provider.page_size == 50
    assert result.pulled == 4
    assert result.est_credits == 0.12                      # 4 * 0.03
    assert result.geo_dropped == 1
    assert {r.candidate_id for r in result.candidates} == {"a", "c"}
    assert set(next(r for r in result.candidates if r.candidate_id == "a").matched_queries) == {
        "natural_language", "title_expansion",
    }
