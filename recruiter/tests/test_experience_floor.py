"""Verified experience floor — derive years from dated roles, drop below-floor."""

from recruiter.agents.ranking import RankingAgent
from recruiter.agents.ranking.experience import below_floor, derived_years
from recruiter.candidates import CandidateRecord
from recruiter.role_model import ARCHITECT, JD, Location, Provenance, Requirement, RoleModel, Seniority


def _rec(cid, years_of_roles):
    """years_of_roles: list of (start, end) ISO strings; end None = current."""
    past = [{"start_date": s, "end_date": e} for s, e in years_of_roles if e]
    current = [{"start_date": s} for s, e in years_of_roles if e is None]
    return CandidateRecord(cid, name=cid, title="Engineer",
                           raw={"basic_profile": {"headline": "x"}, "experience": {"employment_details": {"current": current, "past": past}}})


def test_derived_years_sums_dated_roles():
    r = _rec("a", [("2016-01-01", "2020-01-01"), ("2020-01-01", "2024-01-01")])  # 8 years
    assert 7.5 <= derived_years(r) <= 8.5


def test_unknown_dates_are_not_below_floor():
    r = CandidateRecord("x", raw={"experience": {"employment_details": {"current": [{}], "past": []}}})
    assert derived_years(r) is None
    assert below_floor(r, 8) is False      # unknown -> kept


def test_below_floor_detects_juniors():
    junior = _rec("j", [("2021-01-01", "2024-06-01")])          # ~3.4 years
    senior = _rec("s", [("2014-01-01", "2024-01-01")])          # ~10 years
    assert below_floor(junior, 8) is True
    assert below_floor(senior, 8) is False


def _role(min_years):
    return RoleModel(identity="Lead Engineer", seniority=Seniority(min_years, None, Provenance(JD)),
                     role_level=ARCHITECT, location=Location(countries=("India",)),
                     requirements=(Requirement("Python", "core", Provenance(JD)),))


def test_ranking_excludes_below_floor_candidates():
    cands = [_rec("junior1", [("2021-01-01", "2024-06-01")]),   # ~3.4y -> out
             _rec("junior2", [("2022-01-01", "2024-06-01")]),   # ~2.4y -> out
             _rec("senior", [("2013-01-01", "2024-01-01")])]    # ~11y  -> in
    result = RankingAgent(admit_n=25, show=5).rank(_role(8), cands)
    assert result.experience_excluded == 2
    assert {rc.record.candidate_id for rc in result.ranked} == {"senior"}


def test_no_min_years_keeps_everyone():
    cands = [_rec("junior", [("2022-01-01", "2024-06-01")])]
    result = RankingAgent(admit_n=25, show=5).rank(_role(None), cands)
    assert result.experience_excluded == 0 and len(result.ranked) == 1
