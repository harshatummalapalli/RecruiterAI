"""Agent 4 (Search) — merge + geo net, offline (fake provider, no credits)."""

from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.briefing.model import ProviderQuery
from recruiter.agents.search import SearchAgent
from recruiter.agents.search.merge import (
    enforce_cities,
    enforce_company_exclusions,
    enforce_geo,
    enforce_title_exclusions,
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


def test_company_exclusion_ever_scope_also_checks_past_employers():
    # Currently at Consilio, but a PAST role at Epiq. Current scope keeps them;
    # Ever scope drops them (checks the full employment history).
    rec = CandidateRecord("switcher", name="switcher", company="Consilio",
                          raw={"experience": {"current": {"company_name": "Consilio"},
                                              "past": [{"company_name": "Epiq Global"}]}})
    kept_current, _ = enforce_company_exclusions([rec], ("Epiq",))
    assert {r.candidate_id for r in kept_current} == {"switcher"}   # current scope: past Epiq is fine
    _, dropped_ever = enforce_company_exclusions([rec], ("Epiq",), include_history=True)
    assert {r.candidate_id for r in dropped_ever} == {"switcher"}   # ever scope: drops a past Epiq employee


_EXEC = ("Founder", "VP", "Director", "Head of", "Manager")


def _title_rec(cid, title, headline=""):
    return CandidateRecord(cid, name=cid, title=title,
                           raw={"basic_profile": {"headline": headline}})


def test_title_net_drops_leadership_but_spares_manager_with_capability():
    recs = [
        _title_rec("vp", "VP Legal Operations"),
        _title_rec("dir", "Associate Director"),
        _title_rec("edm", "Associate Manager", "eDiscovery | RelativityOne Processing"),
        _title_rec("esim", "ESI Manager", "eDiscovery professional"),
        _title_rec("peoplem", "Manager", "Operations team lead"),       # no capability -> drop
        _title_rec("ic", "Senior Analyst", "Relativity certified"),
    ]
    kept, dropped = enforce_title_exclusions(recs, _EXEC, capability_terms=("eDiscovery", "Relativity"))
    assert {r.candidate_id for r in kept} == {"edm", "esim", "ic"}
    assert {r.candidate_id for r in dropped} == {"vp", "dir", "peoplem"}


def test_title_that_leads_with_manager_drops_despite_capability():
    # CoWork round 3: "Manager Solutions Architect" + "AWS" in the headline was spared.
    # A title that LEADS with the ambiguous term is a manager first.
    recs = [
        _title_rec("lead", "Manager Solutions Architect", "5x AWS Certified | Cloud Adoption"),
        _title_rec("suffix", "Solutions Manager", "AWS cloud"),   # Manager not leading -> spared
    ]
    kept, dropped = enforce_title_exclusions(recs, _EXEC, capability_terms=("AWS",))
    assert {r.candidate_id for r in dropped} == {"lead"}
    assert {r.candidate_id for r in kept} == {"suffix"}


def test_title_net_does_not_false_match_management_word():
    kept, dropped = enforce_title_exclusions(
        [_title_rec("x", "Management Consultant")], _EXEC, capability_terms=("eDiscovery",))
    assert len(kept) == 1 and dropped == []     # \bmanager\b != "management"


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
