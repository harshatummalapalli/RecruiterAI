"""Real-Judge validation: the OFFLINE half (no network, no model). See backend/experiments/compiler_contract/RESULTS_REAL_JUDGE_VALIDATION.md.

The real-model runs themselves are executed by `real_judge_run.py` (they call only OpenAI, never a provider) and their outputs are committed under
`results/real_judge/`. These tests pin everything that does NOT need a model: the scenarios are synthetic and well-formed, every expectation names a real item of the
frozen compiled context, no request the model could receive carries provider syntax / compiler detail / a legacy sentence, the admission decisions, the shadow
receives the JD AND the brief, and the committed report is generated from the committed measurements.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from backend.experiments.compiler_contract import downstream_verify as dv
from backend.experiments.compiler_contract import real_judge_run as rr
from backend.experiments.compiler_contract import real_judge_scenarios as sc
from backend.models.search_intent import Experience, Role, SearchIntent
from backend.services import consumer_input as ci
from backend.services.requirement_judge import RequirementJudge

ROOT = Path(__file__).resolve().parents[1]
TABLE = rr.scenario_table()
GROUPS = {"R1": sc.EXPECT_R1, "R2": sc.EXPECT_R2, "R3": sc.EXPECT_R3, "CONFLICT": [e for e in sc.EXPECT_CONFLICT if not e.eid.startswith("CO-")],
          "CONFLICT_CO": [e for e in sc.EXPECT_CONFLICT if e.eid.startswith("CO-")]}


def test_every_profile_is_labelled_synthetic_and_names_no_real_data():
    seen = 0
    for group, spec in TABLE.items():
        for p in spec["profiles"]:
            assert p.passages[0].startswith("SYNTHETIC PROFILE"), (group, p.key)                      # the profile is labelled (its first passage carries the label)
            for passage in p.passages:
                seen += 1
                assert not re.search(r"https?://|linkedin|@\w+\.\w+", passage, re.I)
            assert re.search(r"fictional|Synthetic", " ".join(p.passages) + p.key, re.I) or p.key in ("F",)
    assert seen > 20


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_every_expectation_names_a_real_item_of_the_frozen_context(group):
    keys = {p.key for p in TABLE[group]["profiles"]}
    for e in GROUPS[group]:
        assert e.candidate in keys and (not e.other or e.other in keys), e.eid
        r = ci.resolve(TABLE[group]["contexts"][e.context or "ctx"])
        texts = [t for _tier, t in r.judged]
        exclusions = [i.text for i in r.checklist.exclusions] if r.checklist is not None else []
        if e.kind in ("req_met", "req_not_met", "pref_met"):
            assert e.item in texts, (e.eid, e.item)
        elif e.kind in ("excl_present", "excl_not_present"):
            assert any(x.startswith(e.item) for x in exclusions), (e.eid, e.item)
        elif e.kind == "asked":
            assert any(e.item.casefold() in t.casefold() for t in texts), e.eid
        elif e.kind == "not_asked":
            assert not any(e.item.casefold() in t.casefold() for t in texts), e.eid     # the deterministic half of "not asked" holds before the model is even called


def test_what_the_model_could_receive_carries_no_provider_syntax_no_compiler_detail_and_no_legacy_sentence():
    """The same leak scan the real run applies, here over a scripted run of every scenario (the requests are built by the production Judge either way)."""
    legacy = [s.casefold() for s in sc.CONFLICT_LEGACY_SIGNALS + sc.CONFLICT_COMPANY_LEGACY]
    for group, spec in TABLE.items():
        for p in spec["profiles"]:
            for label, intent in spec["contexts"].items():
                cand, harvest = rr.build_profile(p)
                rc = rr.RecordingClient(dv.ScriptedModel())
                RequirementJudge(client=rc).judge_detailed(cand, intent, harvest)
                for call in rc.calls:
                    blob = call["user"].casefold()
                    assert not [t for t in rr.LEAK_TOKENS if t.casefold() in blob], (group, p.key, label)
                    if label == "compiled_vs_legacy":
                        assert not any(s in blob for s in legacy), (group, p.key)


def test_the_requirement_prompt_is_unchanged_and_the_exclusion_prompt_is_separate():
    import hashlib
    from backend.services import requirement_judge as rj
    assert hashlib.sha256(rj._SYSTEM_PROMPT.encode()).hexdigest() == "75ecf559eae5d8fa5189ccc28f6604d6346bba32894994fc82e988c9ab7a00b5"
    assert hashlib.sha256(rj._REVIEW_PROMPT.encode()).hexdigest() == "e29f936a987483b7c53452e5889baea0da8a028973c508249c759ac01cb4b21b"
    assert rj.JUDGE_MODEL == "gpt-4o-mini"
    assert "EXCLUDED" in rj._EXCLUSION_PROMPT and "EXCLUDED" not in rj._SYSTEM_PROMPT


# ------------------------------------------------------------------------------------------------------------ admission


def test_a_preferred_experience_range_never_gates_admission():
    q = "5+ years would be preferred."
    ctx = rr.conflict_context(q, experience={"minimum_years": 5, "strength": "preferred", "basis": {"sources": ["jd"], "quote": q}})
    facts = ci.admission_facts_for(ctx)
    assert facts.minimum_years is None and any(u["concept"] == "experience.min" for u in facts.ungated)
    decision = rr._decide(ci.search_intent_for_context(ctx), rr._adm_candidate("short", "Engineer", "Engineer", 2025))
    assert decision["experience_floor"] is None and decision["admitted"] is True
    legacy = rr._decide(SearchIntent(experience=Experience(minimum_years=5)), rr._adm_candidate("short", "Engineer", "Engineer", 2025))
    assert legacy["admitted"] is False                                                       # what the legacy reading would have done


def test_the_admission_report_matches_the_committed_results_and_the_decisions_hold():
    a = rr.admission_report()
    committed = json.loads((rr.RESULTS / "admission.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(a, sort_keys=True)) == committed
    by = {c["case"]: c for c in a["cases"]}
    pref_a = by["R1 PATH A: Lead (+Senior alternative) are PREFERRED"]
    assert pref_a["facts"]["target_level"] is None and all(r["compiled"]["admitted"] for r in pref_a["rows"])           # decision 1
    assert any(not r["legacy_would"]["admitted"] for r in pref_a["rows"])                                               # and it differs from reading it as required
    req_b = by["R1 PATH B: Lead is REQUIRED, 6+ years"]
    assert {r["candidate"]: r["compiled"]["admitted"] for r in req_b["rows"]} == {"lead": True, "senior": False, "director": False, "junior": False, "no_level": True, "short_tenure": False}
    alt = by["synthetic: Senior required, Lead accepted as an alternative (OR)"]
    got = {r["candidate"]: (r["compiled"]["level_fit"], r["compiled"]["admitted"]) for r in alt["rows"]}
    assert got["lead"] == ("aligned", True) and got["senior"] == ("aligned", True) and got["director"] == ("above", False) and got["junior"] == ("below", False)   # decision 2: OR
    assert all(r["compiled"]["admitted"] for r in by["synthetic: Staff (no approved level mapping) is UNRESOLVED"]["rows"])                                      # not invented
    assert any("UNRESOLVED" in u for u in by["synthetic: Staff (no approved level mapping) is UNRESOLVED"]["ungated"])


# ------------------------------------------------------------------------------------------------------------ the shadow


def test_the_shadow_receives_the_jd_and_the_recruiter_brief(monkeypatch, tmp_path):
    from backend.models.structured_intent import parse_structured_intent
    from backend.services import search_compiler_shadow as shadow
    import backend.services.structured_intent_extractor as ex
    seen = {}
    golden = (ROOT / "tests" / "fixtures" / "structured_intent" / "epiq_product_owner.expected.json").read_text(encoding="utf-8")

    def fake(jd, recruiter_brief=None, **k):
        seen["jd"], seen["brief"] = jd, recruiter_brief
        return parse_structured_intent(golden)

    monkeypatch.setenv("SEARCH_COMPILER_SHADOW_ENABLED", "true")
    monkeypatch.setattr(ex, "extract_structured_intent", fake)
    monkeypatch.setattr(shadow, "SHADOW_DIR", tmp_path)

    class _Plan:
        searches = []

    rec = shadow.run_shadow("s-brief", "THE JD TEXT", _Plan(), recruiter_brief="THE BRIEF TEXT")
    assert seen == {"jd": "THE JD TEXT", "brief": "THE BRIEF TEXT"}
    assert rec["source_texts"] == {"jd": True, "recruiter_brief": True} and rec["sources_supplied"] is True
    rec2 = shadow.run_shadow("s-nobrief", "THE JD TEXT", _Plan())
    assert rec2["source_texts"] == {"jd": True, "recruiter_brief": False}


def test_the_pipeline_forwards_the_brief_to_the_shadow_and_the_api_supplies_it():
    pipeline = (ROOT / "backend" / "services" / "search_pipeline.py").read_text(encoding="utf-8")
    api = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    assert "recruiter_brief: Optional[str] = None" in pipeline and "recruiter_brief=recruiter_brief" in pipeline
    assert 'recruiter_brief=snapshot.get("recruiter_brief")' in api and '"recruiter_brief": snapshot.get("recruiter_brief")' in api


def test_this_phase_calls_no_provider_and_no_retrieval():
    for f in ("real_judge_run.py", "real_judge_scenarios.py"):
        text = (ROOT / "backend" / "experiments" / "compiler_contract" / f).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+backend\.providers|HarvestEnrichmentService|CrustDataProvider|provider\.search|search_with_options", text, re.M), f
    for f in ("services/requirement_judge.py", "services/consumer_input.py"):
        assert "backend.providers" not in (ROOT / "backend" / f).read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------------ the committed runs


def _jobs(raw):
    return rr.load_jobs(raw)


def test_the_committed_real_runs_are_complete_and_used_the_production_model_configuration():
    import hashlib
    from backend.services import requirement_judge as rj
    runs = 6
    expected = sum(len(spec["profiles"]) * len(spec["contexts"]) * runs for spec in TABLE.values())
    jobs = _jobs(rr.RAW)
    assert len(jobs) == expected == 186
    assert {(j["group"], j["candidate"], j["context"], j["run"]) for j in jobs} == {(g, p.key, c, k) for g, spec in TABLE.items() for p in spec["profiles"] for c in spec["contexts"] for k in range(1, runs + 1)}
    assert {j["model"] for j in jobs} == {rj.JUDGE_MODEL}
    assert {str(r["temperature"]) for j in jobs for r in j["requests"]} == {"0"} and {r["model"] for j in jobs for r in j["requests"]} == {rj.JUDGE_MODEL}
    assert not [j for j in jobs if j["failed"] or j["exclusion_failed"]]
    # a run with nothing to ask (only a context-only preference: the company case) makes no model call and has no judgments; every other run has them
    assert {(j["group"], j["context"]) for j in jobs if j["judgments"] is None} <= {("CONFLICT_CO", "compiled_vs_legacy")}
    prompts = {r["system"] for j in jobs for r in j["requests"]}
    assert hashlib.sha256(rj._SYSTEM_PROMPT.encode()).hexdigest() in {hashlib.sha256(p.encode()).hexdigest() for p in prompts}          # the requirement prompt that ran is the pinned one
    assert {j["input_source"] for j in jobs if j["context"] == "legacy_only_control"} == {"legacy"} and {j["input_source"] for j in jobs if j["context"] != "legacy_only_control"} == {"compiled"}
    v2 = _jobs(rr.RAW_V2)
    assert len(v2) == sum(len(TABLE[g]["profiles"]) * len(TABLE[g]["contexts"]) * runs for g in ("R1", "R3"))
    # the exclusion prompt has since been replaced (Evidence Check phase); the historical v1 / v2 prompts are verifiable from the requests they ran with
    excl = lambda js: {r["system"] for j in js for r in j["requests"] if r["system"].startswith("You check whether")}
    assert all("An exclusion describes a kind of" in p and "worded either as the profile itself" not in p for p in excl(jobs))
    assert all("worded either as the profile itself" in p for p in excl(v2))
    assert rj._EXCLUSION_PROMPT not in excl(jobs) | excl(v2)


def test_the_committed_analyses_are_what_the_analyzer_produces_from_the_committed_runs():
    for raw, name, kinds in ((rr.RAW, "analysis.json", None), (rr.RAW_V2, "analysis_v2.json", ("excl_present", "excl_not_present"))):
        fresh = rr.analyze(raw, name, kinds, write=False)
        assert json.loads(json.dumps(fresh, sort_keys=True)) == json.loads((rr.RESULTS / name).read_text(encoding="utf-8")), name


def test_what_the_report_claims_about_what_reached_the_model_holds():
    a = json.loads((rr.RESULTS / "analysis.json").read_text(encoding="utf-8"))
    assert a["leaks"] == [] and a["legacy_leaks"] == []                                           # no provider syntax, compiler detail or legacy sentence reached the model
    assert a["asked_only_what_the_checklist_judges"]["violations"] == []                          # unresolved / exclusions / context-only preferences were never asked
    assert a["asked_only_what_the_checklist_judges"]["jobs_checked"] > 100
    assert a["totals"]["failed_jobs"] == 0


def test_the_real_judge_report_is_generated_from_the_measurements_and_is_current():
    from backend.experiments.compiler_contract import build_real_judge_report as b
    text = (ROOT / "backend" / "experiments" / "compiler_contract" / "RESULTS_REAL_JUDGE_VALIDATION.md").read_text(encoding="utf-8")
    assert b.build() == text and "{{" not in text
    assert "Hard stop" in text and "No CrustData" in text
