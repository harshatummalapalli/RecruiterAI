"""Geographic safety net — deterministic, conservative, no network.

Pins the GUARANTEE that a location-constrained search never surfaces a candidate
whose KNOWN current country/state is outside scope, while never dropping unknowns.
Regression anchor: the 2026-10-05 Hyderabad search that returned US/Thailand/etc.
when the provider degraded to an unfiltered global response.
"""
from __future__ import annotations

from backend.models.candidate import Candidate
from backend.services.geo_enforcement import enforce_location, is_enabled


def _cand(cid: str, country=None, state=None, city=None, raw=None) -> Candidate:
    loc = {"country": country, "state": state, "city": city, "raw": raw}
    return Candidate(candidate_id=cid, name=cid, location=raw, raw_data={"basic_profile": {"location": loc}})


HYD = _cand("hyd", country="India", state="Telangana", city="Hyderabad", raw="Hyderabad, Telangana, India")
BLR = _cand("blr", country="India", state="Karnataka", city="Bengaluru", raw="Bengaluru, Karnataka, India")
US = _cand("us", country="United States", state=None, city=None, raw="United States")
TH = _cand("th", country="Thailand", state="Bangkok", city="Bangkok", raw="Bangkok, Bangkok City, Thailand")
UNKNOWN = _cand("unk", country=None, state=None, city=None, raw=None)


def test_country_scope_drops_other_countries_keeps_india_and_unknown():
    res = enforce_location([HYD, US, TH, UNKNOWN], countries=["India"])
    kept = {c.candidate_id for c in res.kept}
    assert kept == {"hyd", "unk"}, kept            # US + Thailand dropped; unknown kept
    assert {c.candidate_id for c in res.dropped} == {"us", "th"}
    assert res.dropped_count == 2


def test_regression_hyderabad_search_excludes_global_leakage():
    # The exact failure mode: a worldwide pool returned for an India/Hyderabad brief.
    pool = [HYD, US, TH, _cand("il", country="Israel", raw="Center District, Israel"),
            _cand("au", country="Australia", state="New South Wales", raw="Sydney, NSW, Australia")]
    res = enforce_location(pool, countries=["India"], states=["Telangana"])
    assert {c.candidate_id for c in res.kept} == {"hyd"}
    assert res.dropped_count == 4


def test_state_scope_drops_other_state_within_country():
    # India + Telangana: a Bengaluru (Karnataka) candidate is in-country but out-of-state.
    res = enforce_location([HYD, BLR], countries=["India"], states=["Telangana"])
    assert {c.candidate_id for c in res.kept} == {"hyd"}
    assert {c.candidate_id for c in res.dropped} == {"blr"}


def test_unknown_state_within_right_country_is_kept():
    in_country_no_state = _cand("x", country="India", state=None, raw="India")
    res = enforce_location([in_country_no_state], countries=["India"], states=["Telangana"])
    assert {c.candidate_id for c in res.kept} == {"x"}  # never drop the unclear


def test_empty_scope_is_a_noop():
    pool = [HYD, US, TH, UNKNOWN]
    res = enforce_location(pool, countries=[], states=[])
    assert res.kept == pool and res.dropped_count == 0


def test_missing_raw_data_is_kept():
    bare = Candidate(candidate_id="bare", name="bare")
    res = enforce_location([bare, US], countries=["India"])
    assert "bare" in {c.candidate_id for c in res.kept}  # no location known => kept
    assert "us" in {c.candidate_id for c in res.dropped}


def test_matching_is_case_and_whitespace_insensitive():
    messy = _cand("m", country=" india ", state=" telangana ", raw="x")
    res = enforce_location([messy], countries=["India"], states=["Telangana"])
    assert {c.candidate_id for c in res.kept} == {"m"}


def test_kill_switch(monkeypatch):
    monkeypatch.delenv("SEARCH_GEO_ENFORCEMENT_ENABLED", raising=False)
    assert is_enabled() is True                       # default ON
    monkeypatch.setenv("SEARCH_GEO_ENFORCEMENT_ENABLED", "false")
    assert is_enabled() is False
    monkeypatch.setenv("SEARCH_GEO_ENFORCEMENT_ENABLED", "true")
    assert is_enabled() is True
