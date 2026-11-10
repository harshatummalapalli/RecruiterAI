"""Deterministic candidate attributes — offline, no credits. Records are shaped
like the real CrustData person payload (verified live 2026-11)."""

from datetime import datetime, timezone

from backend.services.candidate_attributes import (
    COMPANY_ENTERPRISE,
    COMPANY_GCC,
    COMPANY_PRODUCT,
    COMPANY_SERVICES,
    COMPANY_STARTUP,
    COMPANY_UNKNOWN,
    derive_attributes,
)

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _person(current, *, country="India", normalized_title=None, past=None, updated_at="2026-11-05T08:00:01+00:00"):
    return {
        "basic_profile": {"name": "X", "current_title": current.get("title"),
                           "location": {"country": country}, "normalized_title": normalized_title or {}},
        "experience": {"employment_details": {"current": [current], "past": past or []}},
        "metadata": {"updated_at": updated_at},
    }


def _role(**kw):
    return kw


def test_gcc_foreign_hq_large_india_presence():
    p = _person(_role(title="Senior Machine Learning Engineer", seniority_level="Senior",
                      function_category="Engineering", name="Atlassian",
                      company_industries=["Software Development"], company_headcount_latest=16916,
                      company_headquarters_country="Australia", start_date="2022-08-01T00:00:00",
                      years_at_company="3 to 5 years"))
    a = derive_attributes(p, now=NOW)
    assert a.company_type == COMPANY_GCC and "Australia" in a.company_type_basis
    assert a.seniority_band == "Senior" and a.ic_level == "Senior" and a.function == "Engineering"


def test_it_services_by_industry():
    p = _person(_role(title="Senior ML Engineer", name="Quantiphi",
                      company_industries=["IT Services and IT Consulting", "Professional Services"],
                      company_headcount_latest=4491, company_headquarters_country="United States"))
    a = derive_attributes(p, now=NOW)
    assert a.company_type == COMPANY_SERVICES  # industry wins over the GCC size test


def test_startup_by_headcount():
    p = _person(_role(title="ML Engineer", name="Blossom Social",
                      company_industries=["Software Development"], company_headcount_latest=40,
                      company_headquarters_country="India"))
    assert derive_attributes(p, now=NOW).company_type == COMPANY_STARTUP


def test_enterprise_same_country_large():
    p = _person(_role(title="Staff Engineer", name="Reliance",
                      company_industries=["Conglomerate"], company_headcount_latest=120000,
                      company_headquarters_country="India"))
    a = derive_attributes(p, now=NOW)
    assert a.company_type == COMPANY_ENTERPRISE and a.ic_level == "Staff"


def test_product_mid_size():
    p = _person(_role(title="Senior Software Engineer", name="Postman",
                      company_industries=["Software Development"], company_headcount_latest=800,
                      company_headquarters_country="United States"), country="United States")
    # same country as HQ, mid headcount, software -> product (not GCC, not startup, not enterprise)
    assert derive_attributes(p, now=NOW).company_type == COMPANY_PRODUCT


def test_unknown_when_no_company_data():
    p = _person(_role(title="ML Engineer"))
    assert derive_attributes(p, now=NOW).company_type == COMPANY_UNKNOWN


def test_recency_and_derived_years():
    p = _person(_role(title="Senior ML Engineer", name="Acme", company_headcount_latest=300,
                      company_headquarters_country="India", start_date="2026-09-01T00:00:00"),
                past=[{"start_date": "2016-07-01T00:00:00"}, {"start_date": "2020-01-01T00:00:00"}])
    a = derive_attributes(p, now=NOW)
    assert a.recently_started is True              # started 2026-09, now 2026-11
    assert a.years_experience is not None and 10.0 <= a.years_experience <= 11.0  # since 2016


def test_ic_level_parsing_prefers_higher_rung():
    p = _person(_role(title="Principal / Staff Engineer", name="N", company_headcount_latest=5000,
                      company_headquarters_country="India"))
    assert derive_attributes(p, now=NOW).ic_level == "Principal"


def test_normalized_role_only_when_confident():
    confident = _person(_role(title="MLE", name="N", company_headcount_latest=300, company_headquarters_country="India"),
                        normalized_title={"sub_department": "Machine Learning & AI Engineering", "confident": True})
    unsure = _person(_role(title="MLE", name="N", company_headcount_latest=300, company_headquarters_country="India"),
                     normalized_title={"sub_department": "Something", "confident": False})
    assert derive_attributes(confident, now=NOW).role_normalized == "Machine Learning & AI Engineering"
    assert derive_attributes(unsure, now=NOW).role_normalized is None
