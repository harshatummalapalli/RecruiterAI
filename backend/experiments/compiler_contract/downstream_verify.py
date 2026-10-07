"""Downstream-consumer verification harness (offline; SYNTHETIC candidates only; a scripted stand-in for the Judge's model; no provider, no retrieval).

It runs the REAL `RequirementJudge` (its verified-quote gate, its review pass, its evidence builder) against synthetic candidates whose profile text is built from a
path's own checklist, so what is measured is the WIRING (which requirements the Judge was given, which path a candidate is attributed to), never candidate quality
and never a real model's judgement. The scripted model answers deterministically: a requirement is "met" iff its own text appears in a passage of the profile.

  Candidate A  profile states what ONLY Path A asks (plus what both paths ask)      -> satisfies A, not B
  Candidate B  ... what ONLY Path B asks (plus what both ask)                      -> satisfies B, not A
  Candidate C  ... what A or B ask                                                 -> satisfies both
  Candidate D  ... nothing that either asks                                        -> satisfies neither

Roles 2 and 3 declare no sourcing paths (one global context). For them the matrix is run twice: on the real single context (the paths-less case) and on a
SYNTHETIC two-path overlay (two extra skills, one per path, stated in an extended source), which exercises the path contract without inventing any role content.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.compiler_contract import loader
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services.consumer_input import (ChecklistItem, JudgeChecklist, PathAttribution, attribute_path, judge_checklist_for, resolve,
                                             search_intents_from_contexts)
from backend.services.downstream_context import DownstreamContext, build_downstream_contexts
from backend.services.requirement_judge import RequirementJudge
from backend.services.search_compiler import compile_intent
from backend.services.source_provenance import SourceTexts

PASSAGE_BUDGET = 820          # characters of requirement text per synthetic role description (the Judge truncates a passage at 900)
OVERLAY_SKILLS = {"PATH A": "Synthetic Alpha Tool", "PATH B": "Synthetic Beta Tool"}


def _needles(criterion: str) -> List[str]:
    """What the scripted stand-in looks for: the claim's label (a depth clause is dropped), or any one alternative of an "any one of" claim."""
    if criterion.startswith("Any one of: "):
        return [a.strip() for a in criterion[len("Any one of: "):].split(";") if a.strip()]
    return [criterion.split(", at the level of ")[0]]


class ScriptedModel:
    """Stands in for the Judge's model. Deterministic. `met` iff the requirement's own text is in a passage of the profile; the review pass affirms every claim."""

    def __init__(self) -> None:
        self.responses = self
        self.asked: List[List[str]] = []          # the requirement texts of each first-pass call, as the Judge sent them
        self.payloads: List[Dict[str, Any]] = []
        self.exclusion_asked: List[List[str]] = []
        self.depth_asked: List[List[str]] = []

    def create(self, **kwargs):
        body = json.loads(kwargs["input"][1]["content"])
        usage = SimpleNamespace(input_tokens=1, output_tokens=1)
        if "claims" in body:
            return SimpleNamespace(output_text=json.dumps({"results": [{"i": c["i"], "supports": True} for c in body["claims"]]}), usage=usage)
        if "exclusion_checks" in body:                # the exclusion pass: PRESENT iff a must_not_indicate phrase is in a passage and no `unless` phrase is
            self.exclusion_asked.append([x["predicate"] for x in body["exclusion_checks"]])
            out = []
            for x in body["exclusion_checks"]:
                pred = x["predicate"]
                low = [p_ for p_ in body["passages"]]
                hit = next(((p_, ph) for p_ in low for ph in pred["must_not_indicate"] if ph.casefold() in p_["text"].casefold()), None)
                unless = any(u.casefold() in p_["text"].casefold() for p_ in low for u in pred.get("unless_candidate_also_shows", []))
                if hit is None or unless:
                    out.append({"x": x["x"], "verdict": "not_present", "p": None, "quote": ""})
                else:
                    p_, ph = hit
                    start = p_["text"].casefold().index(ph.casefold())
                    out.append({"x": x["x"], "verdict": "present", "p": p_["p"], "quote": p_["text"][start:start + len(ph)]})
            return SimpleNamespace(output_text=json.dumps({"results": out}), usage=usage)
        if "skills" in body:                           # the depth pass: the scripted stand-in reports `advanced` iff the skill is named in a passage (it meets any depth)
            self.depth_asked.append([x["skill"] for x in body["skills"]])
            out = []
            for x in body["skills"]:
                needles = [x["skill"]] + [part.strip() for part in x["skill"].split(" or ") if part.strip()]
                found = next(((p_, n) for p_ in body["passages"] for n in needles if n.casefold() in p_["text"].casefold()), None)
                if found is None:
                    out.append({"d": x["d"], "observed_depth": "unspecified", "p": None, "quote": ""})
                else:
                    p_, n = found
                    start = p_["text"].casefold().index(n.casefold())
                    out.append({"d": x["d"], "observed_depth": "advanced", "p": p_["p"], "quote": p_["text"][start:start + len(n)]})
            return SimpleNamespace(output_text=json.dumps({"results": out}), usage=usage)
        self.payloads.append(body)
        self.asked.append([r["text"] for r in body["requirements"]])
        out = []
        for r in body["requirements"]:
            needles = _needles(r["text"])
            found = next(((p, n) for p in body["passages"] for n in needles if n.casefold() in p["text"].casefold()), None)
            if found is None:
                out.append({"r": r["r"], "verdict": "not_evidenced", "p": None, "quote": "", "term": ""})
            else:
                hit, n = found
                start = hit["text"].casefold().index(n.casefold())
                out.append({"r": r["r"], "verdict": "met", "p": hit["p"], "quote": hit["text"][start:start + len(n)], "term": n[:30]})
        return SimpleNamespace(output_text=json.dumps({"results": out}), usage=usage)


def synthetic_candidate(name: str, statements: List[str]) -> Tuple[Candidate, HarvestEvidence]:
    """A synthetic profile whose role descriptions state exactly `statements` (packed into as few descriptions as fit a passage). No real person, no real data."""
    chunks: List[str] = []
    cur = ""
    for s in statements:
        s = s.strip().rstrip(".")
        if cur and len(cur) + len(s) + 3 > PASSAGE_BUDGET:
            chunks.append(cur)
            cur = ""
        cur = f"{cur} {s}." if cur else f"{s}."
    if cur:
        chunks.append(cur)
    cand = Candidate(candidate_id=f"synthetic-{name}", name=f"Synthetic {name}", title="Synthetic Engineer", company="Synthetic Co",
                     raw_data={"basic_profile": {"headline": "Synthetic profile"},
                               "experience": {"employment_details": {"current": [{"start_date": "2018-01-01T00:00:00"}], "past": []}},
                               "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"}})
    harvest = HarvestEvidence(success=True, raw={"element": {"experience": [{"position": "Engineer", "companyName": "Synthetic Co", "description": c} for c in chunks], "skills": []}})
    return cand, harvest


def judged_texts(ctx: DownstreamContext) -> List[str]:
    out: List[str] = []
    for i in judge_checklist_for(ctx).judged:
        if i.text not in out:
            out.append(i.text)
    return out


def with_overlay(intent: ExperimentalHiringIntent, sources: SourceTexts) -> Tuple[ExperimentalHiringIntent, SourceTexts]:
    """The real intent plus two synthetic sourcing paths, each stating ONE extra skill that the other path does not. The extended source states both skills."""
    data = copy.deepcopy(intent.model_dump())
    sentences = {pid: f"Path {pid[-1]} also asks for {skill}." for pid, skill in OVERLAY_SKILLS.items()}
    data["sourcing_paths"] = [{"id": pid, "label": f"synthetic {pid.lower()}", "strategy": "domain_led" if pid.endswith("A") else "capability_led",
                               "skills": [{"name": skill, "strength": "required", "relationship": "any", "basis": {"sources": ["jd"], "quote": sentences[pid]}}]}
                              for pid, skill in OVERLAY_SKILLS.items()]
    extended = SourceTexts(jd=(sources.jd + "\n" + " ".join(sentences.values())).strip(), recruiter_brief=sources.recruiter_brief)
    return ExperimentalHiringIntent.model_validate(data), extended


def contexts_for(role: str, run: int = 1, overlay: bool = False) -> List[DownstreamContext]:
    intent = loader.load_intent(role, run)
    sources = loader.sources_for(role)
    if overlay:
        intent, sources = with_overlay(intent, sources)
    return build_downstream_contexts(compile_intent(intent, sources))


def candidate_statements(contexts: List[DownstreamContext]) -> Dict[str, List[str]]:
    """What each synthetic candidate's profile states. `only[p]` = the judged items path `p` asks that no OTHER path asks."""
    per = {c.path_id: judged_texts(c) for c in contexts}
    if len(contexts) == 1:
        (only,) = per.values()
        return {"A": list(only), "B": [], "C": list(only), "D": []}
    ids = list(per)
    others = {p: {t for q, ts in per.items() if q != p for t in ts} for p in ids}
    only = {p: [t for t in per[p] if t not in others[p]] for p in ids}
    common = [t for t in per[ids[0]] if all(t in per[q] for q in ids)]
    a, b = ids[0], ids[1]
    return {"A": common + only[a], "B": common + only[b], "C": common + only[a] + only[b], "D": []}


def run_matrix(contexts: List[DownstreamContext], base: Optional[SearchIntent] = None) -> Dict[str, Any]:
    """Judge each synthetic candidate against EACH path's own checklist (never a union). Returns the per-candidate attribution and the evidence of the wiring."""
    intents = search_intents_from_contexts(contexts, base)
    stmts = candidate_statements(contexts)
    result: Dict[str, Any] = {"paths": [c.path_id for c in contexts], "candidates": {}}
    for name, lines in stmts.items():
        cand, harvest = synthetic_candidate(name, lines)
        per_path: List[PathAttribution] = []
        outcomes = []
        for intent in intents:
            model = ScriptedModel()
            outcome = RequirementJudge(client=model).judge_detailed(cand, intent, harvest)
            outcomes.append((outcome, model))
            per_path.append(attribute_path(resolve(intent).checklist.path_id, resolve(intent).checklist, outcome.judgments or []))
        result["candidates"][name] = {
            "satisfies": [a.path_id for a in per_path if a.satisfies_required],
            "attribution": [a.to_dict() for a in per_path],
            "judge_inputs": [{"path_id": o.checklist["path_id"], "input_source": o.input_source, "asked": len({t for call in m.asked for t in call}) + len({t for call in m.depth_asked for t in call}),
                              "exclusions": len(o.checklist["exclusions"]), "preferences": len(o.checklist["preferences"]),
                              "unresolved": len(o.checklist["unresolved"]), "proficiencies": sum(1 for k in ("requirements", "preferences") for i in o.checklist[k] if i["proficiency"]),
                              "work_mode": sum(1 for k in ("requirements", "preferences", "unresolved") for i in o.checklist[k] if i["concept"] == "location.work_mode")}
                             for o, m in outcomes],
        }
    return result


def required_texts(ctx: DownstreamContext) -> List[str]:
    return list(dict.fromkeys(i.text for i in judge_checklist_for(ctx).requirements if i.judged))


def expected_satisfaction(contexts: List[DownstreamContext]) -> Dict[str, List[Optional[str]]]:
    """Plain set logic, independent of the Judge: a candidate satisfies a path iff its profile states every REQUIRED (must-have, judged) item of THAT path.
    (When one path's requirements are a subset of the other's, a candidate that satisfies the larger also satisfies the smaller: that is what the requirements say.)"""
    stmts = candidate_statements(contexts)
    return {name: [c.path_id for c in contexts if set(required_texts(c)) <= set(lines)] for name, lines in stmts.items()}


# ======================================================================================================================
# Measurements (written to results/downstream/summary.json; the report is generated from them)
# ======================================================================================================================

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "downstream"
MATRIX_CASES = [("R1", 3, False), ("R1", 1, True), ("R2", 1, False), ("R3", 1, False), ("R2", 1, True), ("R3", 1, True)]


def qualifier_audit() -> Dict[str, Any]:
    """Across the 15 frozen intents: which qualifiers the source did not support (not used), by role and kind."""
    out: Dict[str, Dict[str, int]] = {}
    for role in ("R1", "R2", "R3"):
        for n in loader.RUNS:
            plan = compile_intent(loader.load_intent(role, n), loader.sources_for(role))
            for a in plan.atom_audit:
                for u in a.unsupported_qualifiers:
                    d = out.setdefault(role, {})
                    d[u["qualifier"]] = d.get(u["qualifier"], 0) + 1
    return out


def checklist_coverage() -> Dict[str, Any]:
    from backend.services.consumer_input import admission_facts_for
    from backend.services.downstream_context import ADMISSION, JUDGE_EXCLUSION, JUDGE_REQUIREMENT
    rows: Dict[str, Dict[str, int]] = {}
    for role in ("R1", "R2", "R3"):
        r = rows.setdefault(role, {k: 0 for k in ("contexts", "verified_atoms", "verified_reaching_a_consumer", "judged", "preferences", "exclusions", "unresolved", "already_enforced",
                                                  "proficiency_items", "work_mode_items", "unsupported_qualifiers", "admission_level", "admission_floor", "admission_ungated")})
        for n in loader.RUNS:
            for ctx in build_downstream_contexts(compile_intent(loader.load_intent(role, n), loader.sources_for(role))):
                c, f = judge_checklist_for(ctx), admission_facts_for(ctx)
                r["contexts"] += 1
                ids = " ".join(i.item_id for i in c.judged) + " " + " ".join(i.item_id for i in c.exclusions) + " " + " ".join(f.atom_ids)
                for e in ctx.entries:
                    if e.fate == "VERIFIED_DOWNSTREAM":
                        r["verified_atoms"] += 1
                        r["verified_reaching_a_consumer"] += 1 if e.atom_id in ids else 0
                    r["unsupported_qualifiers"] += len(e.unsupported_qualifiers)
                r["judged"] += len(c.judged)
                r["preferences"] += len(c.preferences)
                r["exclusions"] += len(c.exclusions)
                r["unresolved"] += len(c.unresolved)
                r["already_enforced"] += len(c.already_enforced)
                r["proficiency_items"] += len(c.proficiencies)
                r["work_mode_items"] += len(c.work_mode)
                r["admission_level"] += 1 if f.target_level else 0
                r["admission_floor"] += 1 if f.minimum_years else 0
                r["admission_ungated"] += len(f.ungated)
    return rows


def conflict_cases() -> List[Dict[str, Any]]:
    import dataclasses as dc
    from backend.services.consumer_input import resolve
    from backend.models.search_intent import SearchIntent
    out = []
    # 1. legacy "current Python required" vs compiled "relationship unspecified"
    intent = ExperimentalHiringIntent.model_validate({"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"],
                                                      "skills": [{"name": "Python", "strength": "required", "basis": {"sources": ["jd"], "quote": "Python experience is required."}}]})
    ctx = build_downstream_contexts(compile_intent(intent, SourceTexts(jd="We are hiring a Probe Role. Python experience is required.")))[0]
    legacy = SearchIntent(core_signals=["Currently works with Python (required)"])
    r = resolve(dc.replace(legacy, compiled_context=ctx))
    out.append({"case": "legacy: current Python required   |   compiled: Python relationship UNSPECIFIED",
                "legacy_input": legacy.core_signals, "judge_was_asked": [t for _tier, t in r.judged], "relationship_carried": [i.relationship for i in r.checklist.requirements if "Python" in i.text],
                "winner": "compiled", "disagreements": [d.to_dict() for d in r.disagreements],
                "current_python_enforced_or_asked": any("current" in t.casefold() for _tier, t in r.judged)})
    # 2. legacy company hard filter vs compiled company preference
    intent = ExperimentalHiringIntent.model_validate({"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"],
                                                      "companies": [{"name": "Quuxcorp", "strength": "preferred", "relationship": "any", "basis": {"sources": ["jd"], "quote": "People from Quuxcorp are preferred."}}]})
    ctx = build_downstream_contexts(compile_intent(intent, SourceTexts(jd="We are hiring a Probe Role. People from Quuxcorp are preferred.")))[0]
    legacy = SearchIntent(core_signals=["Works at Quuxcorp"])
    r = resolve(dc.replace(legacy, compiled_context=ctx))
    out.append({"case": "legacy: company is a hard (core) requirement   |   compiled: company is a PREFERENCE",
                "legacy_input": legacy.core_signals, "judge_was_asked": [t for _tier, t in r.judged],
                "carried_as": [(i.polarity, i.text) for i in r.checklist.preferences if "Quuxcorp" in i.text], "winner": "compiled",
                "disagreements": [d.to_dict() for d in r.disagreements], "company_required": any("Quuxcorp" in t for tier, t in r.judged if tier == "core")})
    return out


def measure() -> Dict[str, Any]:
    cases = []
    for role, run, overlay in MATRIX_CASES:
        ctxs = contexts_for(role, run, overlay=overlay)
        res = run_matrix(ctxs)
        exp = expected_satisfaction(ctxs)
        cases.append({"role": role, "run": run, "overlay": overlay, "paths": res["paths"], "candidates": res["candidates"], "expected": {k: v for k, v in exp.items()},
                      "match": {k: res["candidates"][k]["satisfies"] == exp[k] for k in exp},
                      "required_items_by_path": {str(c.path_id): len(required_texts(c)) for c in ctxs},
                      "path_only_required": ({str(ctxs[0].path_id): len(set(required_texts(ctxs[0])) - set(required_texts(ctxs[1]))),
                                              str(ctxs[1].path_id): len(set(required_texts(ctxs[1])) - set(required_texts(ctxs[0])))} if len(ctxs) == 2 else None)})
    return {"matrix": cases, "qualifiers_not_supported": qualifier_audit(), "coverage": checklist_coverage(), "conflicts": conflict_cases()}


if __name__ == "__main__":
    out = RESULTS
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(measure(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", out / "summary.json")
