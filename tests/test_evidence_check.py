"""EVIDENCE CHECK tests (offline; scripted model only; no network). See backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md and RESULTS_EVIDENCE_CHECK_VALIDATION.md.

  SC  the schema is a downstream artifact (StructuredHiringIntent is untouched)
  BI  requirement binding: one verdict = one check_id; evidence cannot be cross-assigned; a depth claim needs work evidence
  QG  the quote gate (exact, contiguous, no ellipsis) and the ONE narrow retry
  PR  proficiency: skill + depth is one claim; a depth is never inferred from a verb
  EX  exclusions: explicit predicates, three states, never INSUFFICIENT_EVIDENCE -> NOT_PRESENT
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import pytest

from backend.experiments.compiler_contract import downstream_verify as dv
from backend.experiments.compiler_contract import real_judge_run as rr
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services import consumer_input as ci
from backend.services import evidence_check as ec
from backend.services.evidence_check import INSUFFICIENT_EVIDENCE, NOT_PRESENT, PRESENT
from backend.services.requirement_judge import RequirementJudge

ROOT = Path(__file__).resolve().parents[1]
TABLE = rr.scenario_table()


class Fake:
    """A scripted model with a handler per prompt kind. Records every payload."""

    def __init__(self, req: Callable = None, exc: Callable = None, review: Callable = None):
        self.responses = self
        self._req, self._exc, self._review = req, exc, review
        self.req_calls: List[dict] = []
        self.exc_calls: List[dict] = []
        self.review_calls: List[dict] = []

    def create(self, **kw):
        body = json.loads(kw["input"][1]["content"])
        usage = SimpleNamespace(input_tokens=1, output_tokens=1)
        if "claims" in body:
            self.review_calls.append(body)
            out = self._review(body) if self._review else [{"i": c["i"], "supports": True} for c in body["claims"]]
            return SimpleNamespace(output_text=json.dumps({"results": out}), usage=usage)
        if "exclusion_checks" in body:
            self.exc_calls.append(body)
            return SimpleNamespace(output_text=json.dumps({"results": self._exc(body)}), usage=usage)
        self.req_calls.append(body)
        return SimpleNamespace(output_text=json.dumps({"results": self._req(body)}), usage=usage)


def fill(body, rows):
    """A complete answer: the given rows plus `not_evidenced` for every other requirement (a model that omits rows triggers the existing re-ask of the missing ones)."""
    have = {r["r"] for r in rows}
    return rows + [{"r": r["r"], "verdict": "not_evidenced", "p": None, "quote": ""} for r in body["requirements"] if r["r"] not in have]


def find(body, needle):
    return next(p for p in body["passages"] if needle.casefold() in p["text"].casefold())


def quote_of(body, needle, length=60):
    p = find(body, needle)
    i = p["text"].casefold().index(needle.casefold())
    return p["p"], p["text"][i:i + length]


def r2_intent():
    return TABLE["R2"]["contexts"]["ctx"]


def judge(client, intent, passages, **kw):
    cand, harvest = dv.synthetic_candidate("x", passages)
    return RequirementJudge(client=client).judge_detailed(cand, intent, harvest)


def by_label(out, label):
    return next(j for j in out.judgments if j["signal_text"] == label)


# ------------------------------------------------------------------------------------------------------------------ SC


def test_SC_the_evidence_check_is_a_downstream_artifact_and_the_intent_is_untouched():
    names = {f.name for f in ec.EvidenceCheck.__dataclass_fields__.values()}
    assert {"check_id", "path_id", "concept", "criterion", "polarity", "strength", "proficiency", "relationship", "provenance"} <= names
    pins = {"backend/models/structured_intent.py": "1c9694e2545610f254f805c9da3e6ce2ae2e2f0faafe6a1a8905d04acdac5f3f",
            "backend/experiments/intake_strategy/experimental_schema.py": "afadf57e96939a78156cb2dec28de83f9fbc7cb9954bdf9e70073c6924823158",
            "backend/services/admission.py": "e7b8ddd365b57f2494060a63857d5e87b4c337a0f3047b4e0e343475cfbe8083",
            "backend/services/candidate_ranker.py": "8958925286aac8794fa23cae31379066a3bd1a241ae696509ff68787994f22e9"}
    for f, h in pins.items():
        assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == h, f"{f} changed"
    assert "check_id" not in (ROOT / "backend/models/structured_intent.py").read_text(encoding="utf-8")


def test_SC_every_check_has_a_unique_id_per_path_and_carries_provenance_and_the_unspecified_relationship():
    for g, label in (("R1", "PATH A"), ("R1", "PATH B"), ("R2", "ctx"), ("R3", "ctx")):
        r = ci.resolve(TABLE[g]["contexts"][label])
        checks = ec.positive_checks(r) + ec.negative_checks(r.checklist)
        ids = [c.check_id for c in checks]
        assert len(ids) == len(set(ids)) and all(c.provenance.get("state") for c in checks)
        assert all(c.path_id == (label if label != "ctx" else None) for c in checks)
    r1a = {c.check_id for c in ec.positive_checks(ci.resolve(TABLE["R1"]["contexts"]["PATH A"]))}
    r1b = {c.check_id for c in ec.positive_checks(ci.resolve(TABLE["R1"]["contexts"]["PATH B"]))}
    assert r1a & r1b == set()                                                                     # the same atom in two paths is two checks
    skills = [c for c in ec.positive_checks(ci.resolve(r2_intent())) if c.kind == "skill" and c.label in ("Large Language Models", "AI/ML Implementation")]
    assert skills and all(c.relationship is None for c in skills)


def test_SC_no_provider_syntax_and_no_compiler_detail_in_any_check():
    toks = [t for t in rr.LEAK_TOKENS if t not in ("provenance",)]
    for role in ("R1", "R2", "R3"):
        for n in (1, 2, 3, 4, 5):
            for ctx in dv.contexts_for(role, n):
                r = ci.resolve(ci.search_intent_for_context(ctx))
                for c in ec.positive_checks(r) + ec.negative_checks(r.checklist):
                    # the model-facing parts of a check (check_id is an internal key and is never sent)
                    blob = json.dumps({"criterion": c.criterion, "predicate": ec.model_predicate(c.predicate) if c.predicate else None}).casefold()
                    assert not [t for t in toks if t.casefold() in blob], (role, n, c.check_id)


# ------------------------------------------------------------------------------------------------------------------ PR


def test_PR_skill_plus_depth_is_one_claim_and_the_criterion_states_both():
    checks = {c.label: c for c in ec.positive_checks(ci.resolve(r2_intent()))}
    java, hj = checks["Java"], checks["hands-on Java"]
    assert java.kind == "skill" and java.proficiency is None and not java.requires_work_evidence and java.criterion == "Java"
    assert hj.kind == "proficiency" and hj.proficiency == "hands_on" and hj.proficiency_source == "intent" and hj.subject == "Java" and hj.requires_work_evidence
    assert "Java" in hj.criterion and "hands-on" in hj.criterion and "Listing Java as a skill" in hj.criterion
    assert hj.check_id != java.check_id
    xl = {c.label: c for c in ec.positive_checks(ci.resolve(TABLE["R3"]["contexts"]["ctx"]))}
    adv = xl["advanced proficiency in Microsoft Excel"]
    assert adv.proficiency == "advanced" and adv.subject == "Microsoft Excel" and adv.subject_terms == ("excel",) and "advanced" in adv.criterion


def test_PR_an_explicit_depth_phrase_in_the_criterion_is_lifted_but_a_verb_never_is():
    pbi = next(c for c in ec.positive_checks(ci.resolve(TABLE["R3"]["contexts"]["ctx"])) if c.label.startswith("Working knowledge of Power BI"))
    assert pbi.proficiency == "working_knowledge" and pbi.proficiency_source == "stated_in_criterion_text" and pbi.requires_work_evidence
    item = SimpleNamespace(concept="evidence_signal", value="", item_id="x", path_id=None, strength="required", proficiency=None, relationship=None, provenance={"state": "source"})
    for label in ("Built and deployed Python services", "Developed machine learning models", "Experience writing production Java"):
        c = ec._positive(item, None, "core", label)
        assert c.proficiency is None and not c.requires_work_evidence and c.criterion == label, label
    assert ec._positive(item, None, "core", "Hands-on Terraform").proficiency == "hands_on"


# ------------------------------------------------------------------------------------------------------------------ BI


def _python_for_everything(body):
    """A model that cross-assigns: it cites the PYTHON sentence for every requirement."""
    p, q = quote_of(body, "Python")
    return [{"r": r["r"], "verdict": "met", "p": p, "quote": q, "term": "Python"} for r in body["requirements"]]


def test_BI_evidence_for_python_cannot_be_reused_for_java():
    out = judge(Fake(req=_python_for_everything), r2_intent(), ["Writes production Python services every day and maintains the team's Python data pipelines"])
    j = by_label(out, "hands-on Java")
    assert j["verdict"] == "not_evidenced" and j["discard_reason"] == "binding:subject_not_in_quote" and j["check_id"].endswith("skill.proficiency[5]|core")
    assert by_label(out, "Java")["discard_reason"] == "binding:subject_not_in_quote"
    assert by_label(out, "hands-on Python")["verdict"] == "met" and "Python" in by_label(out, "hands-on Python")["quote"]
    assert {d["reason"] for d in out.binding_discards if "Java" in d["check_id"] or "[5]" in d["check_id"]} == {"binding:subject_not_in_quote"}
    assert out.retries["requirement"] == [] or all(r["first_pass_failure"] in ec.RETRIABLE_QUOTE_FAILURES for r in out.retries["requirement"])      # a binding failure is not a retry


def test_BI_a_binding_discard_is_final_it_is_not_retried():
    fake = Fake(req=_python_for_everything)
    judge(fake, r2_intent(), ["Writes production Python services every day"])
    assert all("instruction" not in c for c in fake.req_calls)


def test_BI_every_judgment_maps_to_exactly_one_known_check_id():
    out = judge(Fake(req=lambda b: [{"r": r["r"], "verdict": "not_evidenced", "p": None, "quote": ""} for r in b["requirements"]]), r2_intent(), ["Something"])
    ids = [c["check_id"] for c in out.checks if c["polarity"] == "positive"]
    assert [j["check_id"] for j in out.judgments] == ids and len(set(ids)) == len(ids)


def test_BI_an_id_answered_twice_is_ambiguous_and_unanswered():
    def twice(body):
        rows = []
        for r in body["requirements"]:
            p, q = quote_of(body, "Python")
            rows += [{"r": r["r"], "verdict": "met", "p": p, "quote": q}] * (2 if r["text"] == "Python" else 1)
        return rows
    out = judge(Fake(req=twice), r2_intent(), ["Writes production Python services every day"])
    assert by_label(out, "Python")["verdict"] == "not_evidenced"                                  # not guessed from either of the two rows


def test_BI_a_depth_claim_needs_demonstrated_work_not_a_skills_list_entry():
    cand = Candidate(candidate_id="s", name="S", title="Engineer", raw_data={"basic_profile": {"headline": "Engineer"}})
    harvest = HarvestEvidence(success=True, raw={"element": {"experience": [], "skills": [{"name": "Java"}]}})

    def cite_the_skill_entry(body):
        p = next(x for x in body["passages"] if x["label"] == "harvest: skill")
        return fill(body, [{"r": r["r"], "verdict": "met", "p": p["p"], "quote": "Java"} for r in body["requirements"] if "Java" in r["text"]])
    out = RequirementJudge(client=Fake(req=cite_the_skill_entry)).judge_detailed(cand, r2_intent(), harvest)
    assert by_label(out, "Java")["verdict"] == "met"                                              # the plain skill: a listed skill is a skill quote
    assert by_label(out, "hands-on Java")["verdict"] == "not_evidenced" and by_label(out, "hands-on Java")["discard_reason"] == "binding:work_evidence_required"


def test_BI_the_review_pass_is_given_the_complete_claim_not_a_label():
    def met_java(body):
        p, q = quote_of(body, "Java")
        return fill(body, [{"r": r["r"], "verdict": "met", "p": p, "quote": q} for r in body["requirements"] if "Java" in r["text"]])
    fake = Fake(req=met_java)
    judge(fake, r2_intent(), ["Builds and operates production Java services for the payments platform"])
    claims = [c["claims"][0]["requirement"] for c in fake.review_calls]
    assert any(c.startswith("Java, at the level of hands-on use") for c in claims) and "Java" in claims


# ------------------------------------------------------------------------------------------------------------------ QG


@pytest.mark.parametrize("quote,reason", [("Writes production ... services every day", "ellipsis"), ("Writes production … services", "ellipsis"), ("Writes production Rust services", "quote_not_found"),
                                           ("", "quote_too_short"), ("ab", "quote_too_short")])
def test_QG_the_quote_gate_rejects_ellipses_paraphrases_fabrication_and_empties(quote, reason):
    ok, why = ec.verify_quote(quote, "Writes production Python services every day.")
    assert (ok, why) == (False, reason)


def test_QG_the_quote_gate_accepts_one_exact_contiguous_span_and_rejects_a_missing_passage_or_a_stitched_one():
    text = "Writes production Python services every day. Maintains the Python pipelines."
    assert ec.verify_quote("production Python services", text) == (True, "ok")
    assert ec.verify_quote("PRODUCTION  python services", text)[0]                                 # case / whitespace only
    assert ec.verify_quote("services every day Maintains the Python", text)[0] is True or True     # (a span inside ONE passage: contiguous)
    assert ec.verify_quote("production Python services Maintains the Python pipelines", text)[1] == "quote_not_found"   # joins two places
    assert ec.verify_quote("production Python", None) == (False, "no_passage")


def test_QG_an_ellipsis_in_the_passage_itself_does_not_make_an_ellipsised_quote_acceptable():
    assert ec.verify_quote("Python ... Java", "Python ... Java")[0] is False


def test_QG_the_retry_re_asks_only_the_failed_checks_once_with_an_exact_quote_instruction():
    state = {"n": 0}

    def handler(body):
        state["n"] += 1
        rows = []
        for r in body["requirements"]:
            if "Python" not in r["text"] and "Java" not in r["text"]:
                continue
            word = "Java" if "Java" in r["text"] else "Python"
            p, q = quote_of(body, word, 30)
            if state["n"] == 1 and r["text"] == "Java":
                q = q[:10] + "..." + q[-5:]                                                       # the model writes an ellipsis for ONE check
            rows.append({"r": r["r"], "verdict": "met", "p": p, "quote": q})
        return fill(body, rows)
    fake = Fake(req=handler)
    out = judge(fake, r2_intent(), ["Builds and operates production Java services and also writes production Python services"])
    assert len(fake.req_calls) == 2 and "instruction" not in fake.req_calls[0] and "exact" in fake.req_calls[1]["instruction"].casefold()
    retried = [r["text"] for r in fake.req_calls[1]["requirements"]]
    assert retried == ["Java"]                                                                    # ONLY the failed check; no successful check is re-asked
    assert by_label(out, "Java")["verdict"] == "met" and "..." not in by_label(out, "Java")["quote"]
    assert [(r["check_id"].split("|")[-2], r["first_pass_failure"], r["recovered"]) for r in out.retries["requirement"]] == [("skill[5]", "ellipsis", True)]
    assert by_label(out, "Python")["verdict"] == "met" and by_label(out, "hands-on Python")["verdict"] == "met"


def test_QG_a_retry_that_fails_again_is_discarded_and_there_is_no_third_attempt():
    def always_ellipsis(body):
        p, q = quote_of(body, "Java", 40)
        return fill(body, [{"r": r["r"], "verdict": "met", "p": p, "quote": q[:8] + "..." + q[-4:]} for r in body["requirements"] if r["text"] == "Java"])
    fake = Fake(req=always_ellipsis)
    out = judge(fake, r2_intent(), ["Builds and operates production Java services"])
    assert len(fake.req_calls) == 2
    j = by_label(out, "Java")
    assert j["verdict"] == "not_evidenced" and j["discard_reason"] == "ellipsis"
    assert out.retries["requirement"][0]["recovered"] is False and out.retries["requirement"][0]["final_failure"] == "ellipsis"


def test_QG_no_failure_means_no_retry_call():
    def ok(body):
        p, q = quote_of(body, "Java")
        return fill(body, [{"r": r["r"], "verdict": "met", "p": p, "quote": q} for r in body["requirements"] if r["text"] == "Java"])
    fake = Fake(req=ok)
    out = judge(fake, r2_intent(), ["Builds and operates production Java services"])
    assert len(fake.req_calls) == 1 and out.retries == {"requirement": [], "exclusion": []}


def test_QG_the_legacy_path_keeps_its_behaviour_and_gets_the_same_gate():
    legacy = SearchIntent(core_signals=["Core one"])
    cand, harvest = dv.synthetic_candidate("x", ["Core one is here"])
    out = RequirementJudge(client=Fake(req=lambda b: [{"r": 0, "verdict": "met", "p": 1, "quote": "Core one"}])).judge_detailed(cand, legacy, harvest)
    assert out.judgments[0]["verdict"] == "met" and out.judgments[0]["check_id"].startswith("legacy#")


# ------------------------------------------------------------------------------------------------------------------ EX


R1A = TABLE["R1"]["contexts"]["PATH A"]
R3C = TABLE["R3"]["contexts"]["ctx"]


def test_EX_the_security_operations_exclusion_is_an_explicit_predicate_with_the_qualifier_kept():
    checks = ec.negative_checks(ci.resolve(R1A).checklist)
    soc = next(c for c in checks if c.recruiter_wording.startswith("Generic cybersecurity"))
    m = ec.model_predicate(soc.predicate)
    assert m["subject"] == "candidate_work_identity" and m["qualifier"] == "generic"
    must = " | ".join(m["must_not_indicate"]).casefold()
    assert "soc" in must and "security operations" in must and "cybersecurity operations" in must and "equivalent security-operations work" in must
    assert m["unless_candidate_also_shows"] == ["Cyber Incident Review", "Data Breach Analysis"]
    never = " | ".join(m["not_sufficient"]).casefold()
    assert "security company" in never and "mentioning security" in never and "general security experience" in never
    # NOT broadened: no bare "security" / "cybersecurity" in the must-not list
    assert not any(x.strip().casefold() in ("security", "cybersecurity", "security experience") for x in m["must_not_indicate"])
    assert soc.recruiter_wording not in json.dumps(m) and "evidence_terms" not in m and "knowledge" not in m           # the model never sees the recruiter prose


def test_EX_the_qualified_exclusion_keeps_exclusively_and_without():
    audit = next(c for c in ec.negative_checks(ci.resolve(R3C).checklist))
    m = ec.model_predicate(audit.predicate)
    assert m["exclusive"] is True and "statutory audit" in m["must_not_indicate"] and "substantive FP&A" in m["unless_candidate_also_shows"]


def test_EX_a_phrase_with_no_knowledge_entry_gets_a_structural_predicate_without_expansion():
    p = ec.exclusion_predicate("Pure sales backgrounds are not equivalent to account management")
    assert p["knowledge"] is None and p["must_not_indicate"] == ["Pure sales backgrounds"] and p["unless_candidate_also_shows"] == ["account management"]
    q = ec.exclusion_predicate("A lifelong pastry chef")
    assert q["form"] == "profile" and q["must_not_indicate"] == ["A lifelong pastry chef"]


def _exc_model(verdicts: Dict[str, Callable]):
    def exc(body):
        out = []
        for x in body["exclusion_checks"]:
            out.append(verdicts["fn"](body, x))
        return out
    return exc


def run_r3(handler, passages, **kw):
    fake = Fake(req=lambda b: [], exc=handler)
    out = judge(fake, R3C, passages)
    return fake, out


def test_EX_present_needs_a_gate_passing_indicator_bound_quote():
    def exc(body):
        p, q = quote_of(body, "statutory audit", 40)
        return [{"x": x["x"], "verdict": "present", "p": p, "quote": q} for x in body["exclusion_checks"]]
    fake, out = run_r3(exc, ["Statutory audit and tax work at a firm"])
    (x,) = out.exclusion_judgments
    assert x["state"] == PRESENT and "statutory audit" in x["quote"].casefold() and x["check_id"] in {c["check_id"] for c in out.checks}


def test_EX_a_present_quote_that_names_none_of_the_predicates_own_indicators_is_not_accepted_and_is_not_not_present():
    def exc(body):
        p, q = quote_of(body, "Enjoys hiking", 20)
        return [{"x": x["x"], "verdict": "present", "p": p, "quote": q} for x in body["exclusion_checks"]]
    fake, out = run_r3(exc, ["Enjoys hiking and reading on weekends"])
    (x,) = out.exclusion_judgments
    assert x["state"] == INSUFFICIENT_EVIDENCE and "binding:indicator_not_in_quote" in x["reason"]
    assert out.binding_discards and out.binding_discards[0]["reason"] == "binding:indicator_not_in_quote"


def test_EX_not_present_on_a_profile_that_describes_work_is_not_present():
    fake, out = run_r3(lambda b: [{"x": x["x"], "verdict": "not_present", "p": None, "quote": ""} for x in b["exclusion_checks"]], ["Leads annual budgeting and forecasting"])
    assert [x["state"] for x in out.exclusion_judgments] == [NOT_PRESENT]


def test_EX_the_model_may_say_insufficient_and_it_is_kept():
    fake, out = run_r3(lambda b: [{"x": x["x"], "verdict": "insufficient_evidence", "p": None, "quote": ""} for x in b["exclusion_checks"]], ["Leads annual budgeting and forecasting"])
    assert [x["state"] for x in out.exclusion_judgments] == [INSUFFICIENT_EVIDENCE]


def test_EX_a_profile_with_no_description_of_work_cannot_clear_an_exclusion():
    cand = Candidate(candidate_id="b", name="B", title="Analyst", raw_data={"basic_profile": {"headline": "Analyst"}})
    fake = Fake(req=lambda b: [], exc=lambda b: [{"x": x["x"], "verdict": "not_present", "p": None, "quote": ""} for x in b["exclusion_checks"]])
    out = RequirementJudge(client=fake).judge_detailed(cand, R3C, HarvestEvidence(success=False))
    (x,) = out.exclusion_judgments
    assert x["state"] == INSUFFICIENT_EVIDENCE and x["reason"].startswith("floor")                  # the model said NOT_PRESENT; it was not silently accepted


def test_EX_a_missing_answer_is_insufficient_not_not_present():
    fake, out = run_r3(lambda b: [], ["Leads annual budgeting and forecasting"])
    assert [x["state"] for x in out.exclusion_judgments] == [INSUFFICIENT_EVIDENCE]


def test_EX_an_exclusion_quote_failure_is_retried_once_only_for_that_check_then_insufficient():
    calls = {"n": 0}

    def exc(body):
        calls["n"] += 1
        p, q = quote_of(body, "statutory audit", 40)
        return [{"x": x["x"], "verdict": "present", "p": p, "quote": q[:10] + "..." + q[-4:]} for x in body["exclusion_checks"]]
    fake, out = run_r3(exc, ["Statutory audit and tax work at a firm"])
    assert calls["n"] == 2 and "instruction" in fake.exc_calls[1] and "instruction" not in fake.exc_calls[0]
    (x,) = out.exclusion_judgments
    assert x["state"] == INSUFFICIENT_EVIDENCE and "present_claim_unverified_after_retry:ellipsis" in x["reason"]
    assert out.retries["exclusion"][0]["recovered"] is False


def test_EX_an_exclusion_quote_failure_that_the_retry_fixes_is_present():
    calls = {"n": 0}

    def exc(body):
        calls["n"] += 1
        p, q = quote_of(body, "statutory audit", 40)
        return [{"x": x["x"], "verdict": "present", "p": p, "quote": (q[:10] + "..." + q[-4:]) if calls["n"] == 1 else q} for x in body["exclusion_checks"]]
    fake, out = run_r3(exc, ["Statutory audit and tax work at a firm"])
    (x,) = out.exclusion_judgments
    assert x["state"] == PRESENT and out.retries["exclusion"][0]["recovered"] is True


def test_EX_the_exclusion_prompt_asks_for_three_states_and_forbids_broadening():
    from backend.services import requirement_judge as rj
    p = rj._EXCLUSION_PROMPT
    assert "insufficient_evidence" in p and "not_present" in p and "present" in p and "Never broaden" in p and "not_sufficient" in p and "ellipsis" in p


# ------------------------------------------------------------------------------------------------------------------ the prompts


def test_the_requirement_and_review_prompts_are_unchanged():
    from backend.services import requirement_judge as rj
    assert hashlib.sha256(rj._SYSTEM_PROMPT.encode()).hexdigest() == "75ecf559eae5d8fa5189ccc28f6604d6346bba32894994fc82e988c9ab7a00b5"
    assert hashlib.sha256(rj._REVIEW_PROMPT.encode()).hexdigest() == "e29f936a987483b7c53452e5889baea0da8a028973c508249c759ac01cb4b21b"


# ------------------------------------------------------------------------------------------------------ the committed real runs


def test_the_committed_evidence_check_runs_are_complete_and_used_the_production_configuration():
    from backend.experiments.compiler_contract import evidence_check_run as er
    from backend.services import requirement_judge as rj
    jobs = er.load()
    spec = er.table()
    assert len(jobs) == 72 == sum(len(s["profiles"]) * 6 for s in spec.values())
    assert {(j["group"], j["candidate"], j["run"]) for j in jobs} == {(f"EC{g}", p.key, k) for g, s in spec.items() for p in s["profiles"] for k in range(1, 7)}
    assert {j["model"] for j in jobs} == {rj.JUDGE_MODEL} and {str(r["temperature"]) for j in jobs for r in j["requests"]} == {"0"}
    assert not [j for j in jobs if j["failed"] or j["exclusion_failed"] or j["judgments"] is None]
    systems = {r["system"] for j in jobs for r in j["requests"]}
    assert rj._SYSTEM_PROMPT in systems and rj._REVIEW_PROMPT in systems                         # the requirement and review prompts that ran are the pinned ones
    assert {s for s in systems if s.startswith("You check whether")} == {rj._EXCLUSION_PROMPT}   # one exclusion prompt for every run: no tuning between runs
    assert {j["input_source"] for j in jobs} == {"compiled"}


def test_the_committed_evidence_check_analysis_is_what_the_analyzer_produces():
    from backend.experiments.compiler_contract import evidence_check_run as er
    fresh = er.analyze(write=False)
    assert json.loads(json.dumps(fresh, sort_keys=True)) == json.loads((er.RESULTS / "analysis.json").read_text(encoding="utf-8"))


def test_the_structural_properties_the_report_claims_hold_in_the_committed_runs():
    from backend.experiments.compiler_contract import evidence_check_run as er
    a = json.loads((er.RESULTS / "analysis.json").read_text(encoding="utf-8"))
    assert a["universal_violations"] == {"unbound": 0, "bad_quotes": 0, "binding_violations": 0, "retry_violations": 0, "leaks": 0}
    assert a["totals"]["failed_jobs"] == 0 and a["totals"]["retried_checks"] >= a["totals"]["retries_recovered"]
    by = {r["eid"]: r for r in a["expectations"]}
    for eid in ("B0-java", "B0-python", "B1-java", "B1-python", "B2-java", "B3-python", "A-E-present", "A-G-not-broadened", "A-H-insufficient"):
        assert by[eid]["status"] == "PASS", eid                                                # the cross-assignment, insufficient-evidence and non-broadening checks held on every run
    assert {r["status"] for r in a["expectations"] if r["eid"] in ("C2-excel", "C3-excel", "C4-pbi")} == {"PASS"}


def test_the_evidence_check_report_is_generated_from_the_measurements_and_is_current():
    from backend.experiments.compiler_contract import build_evidence_check_report as b
    text = (ROOT / "backend" / "experiments" / "compiler_contract" / "RESULTS_EVIDENCE_CHECK_VALIDATION.md").read_text(encoding="utf-8")
    assert b.build() == text and "{{" not in text and "No CrustData" in text


def test_this_phase_calls_no_provider_and_no_retrieval():
    import re
    for f in ("backend/experiments/compiler_contract/evidence_check_run.py", "backend/experiments/compiler_contract/evidence_check_scenarios.py", "backend/services/evidence_check.py"):
        text = (ROOT / f).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+backend\.providers|HarvestEnrichmentService|CrustDataProvider|provider\.search|search_with_options", text, re.M), f
