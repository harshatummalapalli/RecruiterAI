"""Agent 4 (Search) — merge + geo net, offline (fake provider, no credits)."""

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.search import SearchAgent
from recruiter.agents.search.merge import (
    enforce_cities,
    enforce_company_exclusions,
    enforce_geo,
    merge,
)
from recruiter.candidates import CandidateRecord


def _city_rec(cid, city_text):
    return CandidateRecord(cid, name=cid, location=city_text,
                           raw={"basic_profile": {"location": {"city": city_text.split(",")[0], "full_location": city_text}}})


def test_city_gate_drops_other_city_and_country_only():
    recs = [_city_rec("blr", "Bengaluru, Karnataka, India"),
            _city_rec("pune", "Pune, Maharashtra, India"),
            _city_rec("delhi", "New Delhi, Delhi, India"),
            _city_rec("noida", "Noida, Uttar Pradesh, India"),
            _city_rec("country", "India")]
    kept, dropped = enforce_cities(recs, ("Bengaluru", "Hyderabad", "Pune"))
    assert {r.candidate_id for r in kept} == {"blr", "pune"}
    assert {r.candidate_id for r in dropped} == {"delhi", "noida", "country"}


def test_city_gate_alias_bangalore_matches_bengaluru():
    recs = [_city_rec("b", "Bangalore, Karnataka, India")]
    kept, _ = enforce_cities(recs, ("Bengaluru",))
    assert len(kept) == 1          # alias match


def test_city_gate_keeps_unknown_location():
    kept, dropped = enforce_cities([CandidateRecord("x", location=None, raw={})], ("Pune",))
    assert len(kept) == 1 and dropped == []


def _co_rec(cid, company):
    return CandidateRecord(cid, name=cid, company=company)


def test_company_exclusion_drops_the_hiring_company_and_keeps_unknown():
    recs = [_co_rec("insider", "Epiq Global"), _co_rec("other", "Consilio LLC"),
            _co_rec("unknown", None)]
    kept, dropped = enforce_company_exclusions(recs, ("Epiq",))
    assert {r.candidate_id for r in kept} == {"other", "unknown"}   # substring + keep-unknown
    assert {r.candidate_id for r in dropped} == {"insider"}


def test_search_agent_enforces_company_exclusions():
    provider = _FakeProvider([_co_rec("a", "Epiq"), _co_rec("b", "Morae")])
    query = ProviderQuery(natural_language="x", countries=("India",),
                          exclude_current_companies=("Epiq",))
    result = SearchAgent(provider, page_size=50).run(query)
    assert {r.candidate_id for r in result.candidates} == {"b"}
    assert result.excluded_dropped == 1


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


def test_search_agent_enforces_hard_cities():
    provider = _FakeProvider([
        _city_rec("blr", "Bengaluru, Karnataka, India"),
        _city_rec("delhi", "New Delhi, Delhi, India"),
        _city_rec("country", "India"),
    ])
    query = ProviderQuery(natural_language="x", countries=("India",), cities=("Bengaluru", "Pune"))
    result = SearchAgent(provider, page_size=50).run(query)
    assert {r.candidate_id for r in result.candidates} == {"blr"}
    assert result.geo_dropped == 2


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
