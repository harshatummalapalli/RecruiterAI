"""Intake-strategy experiment (Role 1): evaluator, provenance report and baseline harness.

Credit-free and model-free: the harness runs against a fake client. These tests pin what the gold evaluator means so
the experiment's verdicts cannot silently drift, and prove the harness cannot reach a provider.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.experiments.intake_strategy import gold_assertions as gold
from backend.experiments.intake_strategy import run_baseline as harness
from backend.experiments.intake_strategy.provenance import provenance_report
from backend.models.structured_intent import StructuredHiringIntent
from backend.services.search_compiler import compile_intent

PKG = Path(harness.__file__).parent


def _intent(**overrides) -> dict:
    base = {
        "role_archetype": {"value": "hybrid", "confidence": 0.7, "rationale": "analyst plus domain"},
        "role_family": ["Data Analyst"],
        "seniority": {"value": "Lead", "strength": "required"},
        "skills": [
            {"name": "SQL", "relationship": "current", "strength": "required"},
            {"name": "Python", "relationship": "current", "strength": "required"},
            {"name": "Power Query", "relationship": "current", "strength": "required"},
        ],
        "experience": {"minimum_years": 6, "strength": "required"},
        "location": {"entries": ["India"], "strength": "required"},
        "evidence_signals": [
            {"name": "leading teams and mentoring analysts", "strength": "required"},
            {"name": "security monitoring", "strength": "preferred"},
        ],
    }
    base.update(overrides)
    return base


def _evaluate(raw: dict):
    intent = StructuredHiringIntent.model_validate(raw)
    return intent, {r["id"]: r for r in gold.evaluate(intent, compile_intent(intent))["critical"]}


def test_current_schema_has_no_place_for_the_strategy_concepts() -> None:
    supports = gold.schema_supports()
    assert supports == {
        "sourcing_paths": False, "proficiency": False, "hard_negatives": False, "leadership": False,
        "domain": False, "provenance": False, "domain_led_archetype": False,
    }


def test_flat_baseline_style_intent_fails_the_expected_assertions() -> None:
    _, r = _evaluate(_intent())
    assert (r["two_paths_preserved"]["status"], r["two_paths_preserved"]["failure_class"]) == (gold.FAIL, gold.REPRESENTATION)
    # Power Query required with no path scope: Path A inherits it.
    assert (r["pq_not_mandatory_path_a"]["status"], r["pq_not_mandatory_path_a"]["failure_class"]) == (gold.FAIL, gold.REPRESENTATION)
    # JD wording promoted to a positive requirement against the brief: a reconciliation failure, not the schema's fault.
    assert (r["cyber_review_not_secops"]["status"], r["cyber_review_not_secops"]["failure_class"]) == (gold.FAIL, gold.RECONCILIATION)
    assert (r["lead_people_or_technical"]["status"], r["lead_people_or_technical"]["failure_class"]) == (gold.FAIL, gold.RECONCILIATION)
    assert r["sql_hands_on"]["status"] == gold.PARTIAL and r["python_hands_on"]["status"] == gold.PARTIAL
    assert r["no_invented_radius"]["status"] == gold.PASS
    assert r["provenance_preserved"]["failure_class"] == gold.REPRESENTATION


def test_clean_extraction_still_cannot_pass_representation_dependent_assertions() -> None:
    raw = _intent(
        skills=[
            {"name": "SQL", "relationship": "current", "strength": "required"},
            {"name": "Python", "relationship": "current", "strength": "required"},
            {"name": "Power Query", "relationship": "current", "strength": "preferred"},
        ],
        evidence_signals=[{"name": "cyber incident review or data breach analysis experience", "strength": "preferred"}],
    )
    _, r = _evaluate(raw)
    assert (r["cyber_review_not_secops"]["status"], r["cyber_review_not_secops"]["failure_class"]) == (gold.PARTIAL, gold.REPRESENTATION)
    assert r["lead_people_or_technical"]["status"] == gold.PARTIAL
    assert r["pq_not_mandatory_path_a"]["status"] == gold.PARTIAL
    assert r["hard_negative_secops_preserved"]["status"] == gold.FAIL


def test_title_exclusion_counts_only_as_a_partial_hard_negative() -> None:
    raw = _intent(exclusions=[{"kind": "exclude_title", "value": "Security Analyst"}])
    _, r = _evaluate(raw)
    assert r["hard_negative_secops_preserved"]["status"] == gold.PARTIAL
    assert r["hard_negative_secops_preserved"]["failure_class"] == gold.REPRESENTATION


def test_missing_domain_is_an_extraction_failure() -> None:
    raw = _intent(evidence_signals=[])
    _, r = _evaluate(raw)
    assert (r["cyber_review_not_secops"]["status"], r["cyber_review_not_secops"]["failure_class"]) == (gold.FAIL, gold.EXTRACTION)


def test_invented_radius_and_company_filter_fail() -> None:
    raw = _intent(
        location={"entries": ["Hyderabad, Telangana, India"], "strength": "required", "radius": {"value": 25, "unit": "miles", "around": "Hyderabad, Telangana, India"}},
        companies=[{"name": "Acme Legal", "relationship": "current", "strength": "required"}],
    )
    _, r = _evaluate(raw)
    assert r["no_invented_radius"]["status"] == gold.FAIL
    assert r["no_invented_company_filter"]["status"] == gold.FAIL


def test_compiler_checks_flag_country_as_city_and_collapsed_multi_location() -> None:
    country_only = StructuredHiringIntent.model_validate(_intent())
    checks = {c.id: c for c in gold.evaluate_compiler(country_only, compile_intent(country_only))}
    assert checks["compiler_country_not_city"].status == gold.FAIL
    assert checks["compiler_country_not_city"].failure_class == gold.COMPILER

    mixed = StructuredHiringIntent.model_validate(
        _intent(location={"entries": ["India", "Hyderabad, Telangana, India", "Pune, Maharashtra, India"], "strength": "required"})
    )
    checks = {c.id: c for c in gold.evaluate_compiler(mixed, compile_intent(mixed))}
    assert checks["compiler_multi_location_keeps_country"].status == gold.FAIL


def test_jd_retention_reports_survivors_without_judging_them() -> None:
    intent = StructuredHiringIntent.model_validate(
        _intent(evidence_signals=[{"name": "Relativity platform experience", "strength": "preferred"}],
                education={"degrees": [], "streams": ["Cybersecurity", "Computer Science"], "strength": "preferred"})
    )
    report = gold.jd_retention(intent)
    assert report["items"]["Relativity"] is True and report["items"]["Canopy"] is False
    assert report["degree_streams"]["Cybersecurity"] is True and report["degree_streams"]["Data Analytics"] is False


def test_provenance_separates_stated_from_inferred() -> None:
    inputs = harness.load_inputs()
    raw = _intent(
        skills=[
            {"name": "SQL", "relationship": "current", "strength": "required"},
            {"name": "Tableau", "relationship": "current", "strength": "required"},
        ],
        evidence_signals=[{"name": "Relativity", "strength": "preferred"}],
    )
    report = provenance_report(StructuredHiringIntent.model_validate(raw), inputs["jd"], inputs["brief"])
    source = {a["value"]: a["source"] for a in report["atoms"]}
    assert source["SQL"] == "JD+BRIEF"
    assert source["Relativity"] == "JD"
    assert source["Tableau"] == "INFERRED"
    assert [a["value"] for a in report["inferred_but_required"]] == ["Tableau"]


# ---------------------------------------------------------------------------- harness


class _FakeClient:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.responses = self

    def create(self, **kwargs):
        return SimpleNamespace(output_text=self._payload, usage=SimpleNamespace(input_tokens=11, output_tokens=7))


def test_harness_captures_raw_text_intent_compile_and_gold() -> None:
    inputs = harness.load_inputs()
    record = harness.run_once(1, lambda: _FakeClient(json.dumps(_intent())), inputs["jd"], inputs["brief"])
    assert record["error"] is None
    assert record["model_calls"][0]["raw_text"] and record["model_calls"][0]["input_tokens"] == 11
    assert inputs["jd"][:40] in record["model_calls"][0]["prompt"][0]["content"]
    assert record["compiled"]["filter_tree"]["op"] == "and"
    assert record["gold"]["critical"] and record["provenance"]["atoms"]


def test_harness_records_an_invalid_model_reply_as_a_result() -> None:
    inputs = harness.load_inputs()
    record = harness.run_once(1, lambda: _FakeClient("not json"), inputs["jd"], inputs["brief"])
    assert record["error"] and "intent" not in record


def test_stability_reports_agreement_per_semantic_component() -> None:
    inputs = harness.load_inputs()
    a = harness.run_once(1, lambda: _FakeClient(json.dumps(_intent())), inputs["jd"], inputs["brief"])
    b = harness.run_once(2, lambda: _FakeClient(json.dumps(_intent())), inputs["jd"], inputs["brief"])
    c = harness.run_once(3, lambda: _FakeClient(json.dumps(_intent(location={"entries": ["Hyderabad, Telangana, India"], "strength": "required"}))), inputs["jd"], inputs["brief"])
    result = harness.stability([a, b, c])
    assert result["parsed"] == 3
    assert result["components"]["geography"]["agreement"] == "2/3"
    assert result["components"]["archetype"]["agreement"] == "3/3"


def test_harness_refuses_to_run_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert harness.main(["--runs", "1"]) == 2


def test_inputs_are_the_supplied_texts() -> None:
    inputs = harness.load_inputs()
    assert "Relativity and Canopy" in inputs["jd"] and "security monitoring" in inputs["jd"]
    assert "Hyderabad OR Pune" in inputs["brief"] and "NOT SOC" in inputs["brief"]
    # Engineering directives were left out of the brief on purpose; only the recruiter's own statements are in it.
    assert "Do NOT flatten" not in inputs["brief"]


def test_experiment_cannot_reach_a_provider_or_production_search() -> None:
    forbidden = ("providers.crustdata", "providers.harvest", "search_pipeline", "requirement_judge", "search_translator", "backend.api")
    for path in PKG.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        imports = [line for line in text.splitlines() if line.startswith(("import ", "from "))]
        for line in imports:
            assert not any(name in line for name in forbidden), f"{path.name}: {line}"
