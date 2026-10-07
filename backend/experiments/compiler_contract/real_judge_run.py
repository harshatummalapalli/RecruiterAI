"""Runs the REAL production Judge (gpt-4o-mini via the production RequirementJudge, unchanged requirement prompt, temperature 0) on the SYNTHETIC scenarios of
`real_judge_scenarios.py`, N times each, with no tuning between runs, and analyses the outputs semantically.

    python -m backend.experiments.compiler_contract.real_judge_run run [--runs 3] [--only R1,R2,R3,CONFLICT]
    python -m backend.experiments.compiler_contract.real_judge_run analyze

Only OpenAI is called (the Judge's own model). No CrustData, no Harvest, no retrieval, no real candidate data. Every request the model receives is captured and
scanned for provider syntax, compiler implementation details and legacy sentences.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.compiler_contract import downstream_verify as dv
from backend.experiments.compiler_contract import real_judge_scenarios as sc
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services import consumer_input as ci
from backend.services.downstream_context import build_downstream_contexts
from backend.services.requirement_judge import JUDGE_MODEL, RequirementJudge
from backend.services.search_compiler import compile_intent
from backend.services.source_provenance import SourceTexts

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "real_judge"
RAW = RESULTS / "raw"
RAW_V2 = RESULTS / "raw_v2"          # the exclusion-pass revision (v2), run on the exclusion-bearing groups only; v1 stays untouched in RAW
BRIEF = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"]}

# tokens that must never reach the model: provider query syntax / provider field names / compiler implementation details
LEAK_TOKENS = ("basic_profile", "experience.employment_details", "current_employers", "years_of_experience_raw", "crustdata", "geo_distance", "filter_tree",
               "provider_plan", "(.)", "person_search", "past_employers", "atom_id", "VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT", "ENFORCED", "NORMALIZED",
               "UNRESOLVED", "DROPPED_WITH_JUSTIFICATION", "provenance", "sourcing_path", "downstream_evidence", "global|", "path:")


class RecordingClient:
    """Wraps the OpenAI client: forwards every call unchanged and records exactly what the model was sent."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.responses = self
        self.calls: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def create(self, **kw):
        resp = self._inner.responses.create(**kw)
        with self._lock:
            self.calls.append({"model": kw.get("model"), "temperature": kw.get("temperature"), "system": kw["input"][0]["content"], "user": kw["input"][1]["content"],
                               "response": getattr(resp, "output_text", None)})
        return resp


def openai_client():
    from openai import OpenAI
    # the sandbox's proxy injects the credential for api.openai.com; the SDK only needs a non-empty placeholder
    from backend.config import get_openai_api_key
    return OpenAI(api_key=get_openai_api_key() or "proxy-injected", max_retries=3, timeout=120)


def build_profile(p: sc.Profile) -> Tuple[Candidate, HarvestEvidence]:
    cand = Candidate(candidate_id=f"synthetic-{p.key}", name=f"Synthetic {p.key}", title=p.title, company="Synthetic Co",
                     raw_data={"basic_profile": {"headline": p.headline},
                               "experience": {"employment_details": {"current": [{"start_date": f"{p.start_year}-01-01T00:00:00"}], "past": []}},
                               "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"}})
    harvest = HarvestEvidence(success=True, raw={"element": {"experience": [{"position": p.title, "companyName": "Synthetic Co", "description": d} for d in p.passages], "skills": [{"name": n} for n in getattr(p, "skills", ())]}})
    return cand, harvest


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# the contexts under test
# ---------------------------------------------------------------------------------------------------------------------------------------------------------


def conflict_context(quote: str, **atom) -> Any:
    data = copy.deepcopy(BRIEF)
    data.update(atom)
    plan = compile_intent(ExperimentalHiringIntent.model_validate(data), SourceTexts(jd="We are hiring a Probe Role. " + quote))
    return build_downstream_contexts(plan)[0]


def scenario_table() -> Dict[str, Dict[str, Any]]:
    """role -> {profiles, contexts{label: SearchIntent}}"""
    r1 = dv.contexts_for("R1", 3)
    r2 = dv.contexts_for("R2", 1)
    r3 = dv.contexts_for("R3", 1)
    py = conflict_context(sc.CONFLICT_QUOTE, skills=[{"name": "Python", "strength": "required", "basis": {"sources": ["jd"], "quote": sc.CONFLICT_QUOTE}}])
    co = conflict_context(sc.CONFLICT_COMPANY_QUOTE, companies=[{"name": "Quuxcorp", "strength": "preferred", "relationship": "any",
                                                              "basis": {"sources": ["jd"], "quote": sc.CONFLICT_COMPANY_QUOTE}}])
    legacy_py = SearchIntent(core_signals=list(sc.CONFLICT_LEGACY_SIGNALS))
    legacy_co = SearchIntent(core_signals=list(sc.CONFLICT_COMPANY_LEGACY))
    return {
        "R1": {"profiles": sc.PROFILES_R1, "contexts": {str(c.path_id): ci.search_intent_for_context(c) for c in r1}},
        "R2": {"profiles": sc.PROFILES_R2, "contexts": {"ctx": ci.search_intent_for_context(r2[0])}},
        "R3": {"profiles": sc.PROFILES_R3, "contexts": {"ctx": ci.search_intent_for_context(r3[0])}},
        # compiled meaning + a CONFLICTING legacy intent (the legacy signals ride on the same SearchIntent) versus the legacy-only control
        "CONFLICT": {"profiles": sc.CONFLICT_PROFILES, "contexts": {"compiled_vs_legacy": ci.search_intent_for_context(py, legacy_py), "legacy_only_control": legacy_py}},
        "CONFLICT_CO": {"profiles": sc.CONFLICT_COMPANY_PROFILES, "contexts": {"compiled_vs_legacy": ci.search_intent_for_context(co, legacy_co), "legacy_only_control": legacy_co}},
    }


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# running
# ---------------------------------------------------------------------------------------------------------------------------------------------------------


def run_one(group: str, profile: sc.Profile, ctx_label: str, intent: SearchIntent, run: int) -> Dict[str, Any]:
    cand, harvest = build_profile(profile)
    last: Optional[Dict[str, Any]] = None
    for attempt in range(3):                                   # infrastructure retries only (an API error); a verdict is never retried
        rc = RecordingClient(openai_client())
        t0 = time.time()
        out = RequirementJudge(client=rc).judge_detailed(cand, intent, harvest)
        last = {
            "group": group, "candidate": profile.key, "context": ctx_label, "run": run, "attempt": attempt + 1, "model": JUDGE_MODEL,
            "judgments": out.judgments, "failed": out.failed, "review_failed": out.review_failed, "downgraded_by_review": out.downgraded_by_review,
            "re_asked_missing": out.re_asked_missing, "exclusion_judgments": out.exclusion_judgments, "exclusion_failed": out.exclusion_failed,
            "input_source": out.input_source, "checklist": out.checklist, "disagreements": out.disagreements,
            "checks": out.checks, "retries": out.retries, "binding_discards": out.binding_discards,
            "calls": out.calls, "input_tokens": out.input_tokens, "output_tokens": out.output_tokens, "estimated_cost_usd": round(out.estimated_cost_usd, 5),
            "seconds": round(time.time() - t0, 1),
            "requests": rc.calls,
        }
        if out.judgments is not None and not out.failed and not out.exclusion_failed:
            break
    return last


def job_path(j: Dict[str, Any], raw: Path = RAW) -> Path:
    return raw / f"{j['group']}__{j['candidate']}__{re.sub(r'[^A-Za-z0-9]+', '_', j['context'])}__run{j['run']}.json"


DIAG = RESULTS / "diagnostics"


def diagnose(group: str, candidate: str, n: int, workers: int = 6) -> List[Dict[str, Any]]:
    """NOT part of the validation: re-runs one scenario n times with the model's raw responses kept, to find out WHY a run behaved as it did. Never feeds the results."""
    DIAG.mkdir(parents=True, exist_ok=True)
    spec = scenario_table()[group]
    profile = next(p for p in spec["profiles"] if p.key == candidate)
    label, intent = next(iter(spec["contexts"].items()))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = list(pool.map(lambda k: run_one(group, profile, label, intent, k), range(1, n + 1)))
    for j in jobs:
        (DIAG / f"{group}__{candidate}__run{j['run']}.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return jobs


def run(runs: int, only: Optional[List[str]], workers: int = 6, raw: Path = RAW) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    table = scenario_table()
    tasks = []
    for group, spec in table.items():
        if only and group not in only:
            continue
        for profile in spec["profiles"]:
            for label, intent in spec["contexts"].items():
                if group == "R1" and profile.key not in {p.key for p in sc.PROFILES_R1}:
                    continue
                for k in range(1, runs + 1):
                    if (raw / f"{group}__{profile.key}__{re.sub(r'[^A-Za-z0-9]+', '_', label)}__run{k}.json").exists():
                        continue                               # resumable: a finished job is never re-run (and so never re-tuned)
                    tasks.append((group, profile, label, intent, k))
    print(f"{len(tasks)} judge runs to do", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run_one, *t): t for t in tasks}
        for f in as_completed(futs):
            j = f.result()
            job_path(j, raw).write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            done += 1
            print(f"[{done}/{len(tasks)}] {j['group']} {j['candidate']} {j['context']} run{j['run']} failed={j['failed'] or j['exclusion_failed']} {j['seconds']}s ${j['estimated_cost_usd']}", flush=True)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------------------------------------------------------------------------------------


def load_jobs(raw: Path = RAW) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(raw.glob("*.json"))]


def verdicts(job: Dict[str, Any]) -> Dict[str, str]:
    """item text -> best verdict (met > partly > not_evidenced) for the positive requirements and judged preferences."""
    rank = {"met": 2, "partly": 1, "not_evidenced": 0}
    out: Dict[str, str] = {}
    for j in job["judgments"] or []:
        t = j["signal_text"]
        if t not in out or rank[j["verdict"]] > rank[out[t]]:
            out[t] = j["verdict"]
    return out


def asked_texts(job: Dict[str, Any]) -> List[str]:
    asked: List[str] = []
    for r in job["requests"]:
        if r["system"].startswith("You verify whether a candidate's profile shows evidence"):
            for q in json.loads(r["user"])["requirements"]:
                if q["text"] not in asked:
                    asked.append(q["text"])
    return asked


def exclusions_asked(job: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for r in job["requests"]:
        if r["system"].startswith("You check whether a candidate's profile shows an EXCLUDED profile"):
            out += [x["text"] for x in json.loads(r["user"])["exclusions"]]
    return out


def _find(verd: Dict[str, str], item: str) -> Optional[str]:
    if item in verd:
        return verd[item]
    return None


def _requirement_texts(job: Dict[str, Any]) -> set:
    return {i["text"] for i in (job.get("checklist") or {}).get("requirements", []) if i["judged"]}


def check(e: sc.Expect, job: Dict[str, Any], by_key: Dict[Tuple[str, str, int], Dict[str, Any]]) -> Tuple[bool, str]:
    v = verdicts(job)
    if e.kind in ("req_met", "pref_met"):
        hit = {t: x for t, x in v.items() if t == e.item} or {t: x for t, x in v.items() if t.casefold() == e.item.casefold()}
        if not hit:
            return False, "item was not judged"
        got = next(iter(hit.values()))
        return got == "met", got
    if e.kind == "req_not_met":
        hit = {t: x for t, x in v.items() if t == e.item}
        if not hit:
            return False, "item was not judged"
        got = next(iter(hit.values()))
        return got != "met", got
    if e.kind in ("asked", "not_asked"):
        present = any(e.item.casefold() in t.casefold() for t in asked_texts(job))
        return (present if e.kind == "asked" else not present), ("asked" if present else "not asked")
    if e.kind in ("excl_present", "excl_not_present"):
        hit = [x for x in (job["exclusion_judgments"] or []) if x["text"].startswith(e.item)]
        if not hit:
            return False, "exclusion not evaluated"
        got = hit[0]["verdict"]
        return (got == "present") == (e.kind == "excl_present"), got
    if e.kind == "same_verdicts_as":
        other = by_key.get((job["group"], e.other, job["run"], job["context"]))
        if other is None:
            return False, "other candidate not run"
        # the expectation is about REQUIREMENT verdicts (a preference item may legitimately differ: a preferred-company background evidences a preference)
        reqs = _requirement_texts(job)
        a, b = {t: x for t, x in v.items() if t in reqs}, {t: x for t, x in verdicts(other).items() if t in reqs}
        diff = sorted(t for t in set(a) | set(b) if (a.get(t) == "met") != (b.get(t) == "met"))
        return not diff, ("identical" if not diff else f"{len(diff)} requirement item(s) differ: " + "; ".join(diff))
    raise ValueError(e.kind)


def analyze(raw: Path = RAW, out_name: str = "analysis.json", only_kinds: Optional[Tuple[str, ...]] = None, write: bool = True) -> Dict[str, Any]:
    jobs = load_jobs(raw)
    idx = {(j["group"], j["candidate"], j["run"], j["context"]): j for j in jobs}
    by_key = {(g, c, r, ctx): j for (g, c, r, ctx), j in idx.items()}
    groups = {"R1": sc.EXPECT_R1, "R2": sc.EXPECT_R2, "R3": sc.EXPECT_R3, "CONFLICT": [e for e in sc.EXPECT_CONFLICT if not e.eid.startswith("CO-")],
              "CONFLICT_CO": [e for e in sc.EXPECT_CONFLICT if e.eid.startswith("CO-")]}
    results: List[Dict[str, Any]] = []
    for group, exps in groups.items():
        for e in exps:
            if only_kinds and e.kind not in only_kinds:
                continue
            ctxs = [e.context] if e.context else ["ctx"]
            runs = sorted((j for j in jobs if j["group"] == group and j["candidate"] == e.candidate and j["context"] in ctxs), key=lambda j: j["run"])
            outcomes = [check(e, j, by_key) for j in runs]
            ok = [o[0] for o in outcomes]
            status = "NOT RUN" if not ok else "PASS" if all(ok) else "FAIL" if not any(ok) else "UNSTABLE"
            downgrades = 0
            if e.kind in ("req_met", "pref_met"):
                downgrades = sum(1 for j in runs for x in (j["judgments"] or []) if x["signal_text"] == e.item and x.get("review") == "not_supported_by_quote_alone")
            results.append({"review_downgrades": downgrades, "group": group, "eid": e.eid, "candidate": e.candidate, "context": e.context or "ctx", "kind": e.kind, "item": e.item or e.other, "why": e.why,
                            "status": status, "runs": len(ok), "passed_runs": sum(ok), "observed": [o[1] for o in outcomes]})
    # semantic stability: a (candidate, context, item) whose met / not-met category differs between runs
    flips: List[Dict[str, Any]] = []
    cells: Dict[Tuple[str, str, str, str], List[str]] = {}
    for j in jobs:
        for t, v in verdicts(j).items():
            cells.setdefault((j["group"], j["candidate"], j["context"], t), []).append(v)
    items = 0
    for (g, c, ctx, t), vs in sorted(cells.items()):
        items += 1
        if len(vs) > 1 and len(set(v == "met" for v in vs)) > 1:
            flips.append({"group": g, "candidate": c, "context": ctx, "item": t, "verdicts": vs, "kind": "semantic (met vs not met)"})
    minor = sum(1 for (g, c, ctx, t), vs in cells.items() if len(vs) > 1 and len(set(vs)) > 1 and len(set(v == "met" for v in vs)) == 1)
    excl_flips = []
    ecells: Dict[Tuple[str, str, str, str], List[str]] = {}
    for j in jobs:
        for x in j["exclusion_judgments"] or []:
            ecells.setdefault((j["group"], j["candidate"], j["context"], x["text"]), []).append(x["verdict"])
    exclusion_tally = [{"group": k[0], "candidate": k[1], "context": k[2], "exclusion": k[3], "present_runs": sum(1 for v in vs if v == "present"), "runs": len(vs)} for k, vs in sorted(ecells.items())]
    for k, vs in sorted(ecells.items()):
        if len(vs) > 1 and len(set(vs)) > 1:
            excl_flips.append({"group": k[0], "candidate": k[1], "context": k[2], "item": k[3], "verdicts": vs})
    # what the model was sent: leak scan over every captured request
    leaks: List[Dict[str, str]] = []
    legacy_leaks: List[Dict[str, str]] = []
    for j in jobs:
        for r in j["requests"]:
            blob = (r["user"]).casefold()
            for tok in LEAK_TOKENS:
                if tok.casefold() in blob:
                    leaks.append({"job": f"{j['group']}/{j['candidate']}/{j['context']}/run{j['run']}", "token": tok})
            if j["context"] == "compiled_vs_legacy":
                for s in sc.CONFLICT_LEGACY_SIGNALS + sc.CONFLICT_COMPANY_LEGACY:
                    if s.casefold() in blob:
                        legacy_leaks.append({"job": f"{j['group']}/{j['candidate']}/run{j['run']}", "sentence": s})
    # unresolved items and exclusions must never be asked as positive requirements; a preference with no evidence route must not be asked either
    unresolved_asked: List[Dict[str, str]] = []
    checked = 0
    for j in jobs:
        cl = j.get("checklist")
        if not cl:
            continue
        asked = asked_texts(j)
        banned = {i["text"]: "unresolved" for i in cl["unresolved"]}
        banned.update({i["text"]: "exclusion" for i in cl["exclusions"]})
        banned.update({i["text"]: "context-only preference" for i in cl["preferences"] if not i["judged"]})
        positives = {i["text"] for k in ("requirements", "preferences") for i in cl[k] if i["judged"]}
        checked += 1
        for t in asked:
            if t in banned and t not in positives:
                unresolved_asked.append({"job": f"{j['group']}/{j['candidate']}/{j['context']}/run{j['run']}", "text": t, "was": banned[t]})
        extra = [t for t in asked if t not in positives]
        if extra:
            unresolved_asked.append({"job": f"{j['group']}/{j['candidate']}/{j['context']}/run{j['run']}", "text": "; ".join(extra), "was": "not on the checklist"})
    totals = {"jobs": len(jobs), "calls": sum(j["calls"] for j in jobs), "input_tokens": sum(j["input_tokens"] for j in jobs), "output_tokens": sum(j["output_tokens"] for j in jobs),
              "estimated_cost_usd": round(sum(j["estimated_cost_usd"] for j in jobs), 3), "failed_jobs": sum(1 for j in jobs if j["failed"] or j["exclusion_failed"]),
              "retried_jobs": sum(1 for j in jobs if j["attempt"] > 1), "review_failed": sum(1 for j in jobs if j["review_failed"]), "models": sorted({j["model"] for j in jobs}),
              "temperatures": sorted({str(r["temperature"]) for j in jobs for r in j["requests"]}), "input_sources": sorted({j["input_source"] for j in jobs})}
    # ---- collapse events (post-hoc, objective): a run with ZERO verified `met` while the same candidate+context has >= 5 in a majority of its other runs.
    def met_n(j: Dict[str, Any]) -> int:
        return sum(1 for x in (j["judgments"] or []) if x["verdict"] == "met")

    groups_runs: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for j in jobs:
        groups_runs.setdefault((j["group"], j["candidate"], j["context"]), []).append(j)
    collapses: List[Dict[str, Any]] = []
    for (g, c, ctx), js in sorted(groups_runs.items()):
        for j in js:
            others = [met_n(o) for o in js if o is not j]
            if met_n(j) == 0 and others and sum(1 for n in others if n >= 5) * 2 > len(others):
                said = None
                ellipsis = None
                first = next((r for r in j["requests"] if r["system"].startswith("You verify") and r.get("response")), None)
                if first:
                    parsed = [x for x in json.loads(first["response"]).get("results", []) if isinstance(x, dict)]
                    said = sum(1 for x in parsed if x.get("verdict") == "met")
                    ellipsis = sum(1 for x in parsed if x.get("verdict") == "met" and ("..." in str(x.get("quote")) or "\u2026" in str(x.get("quote"))))
                collapses.append({"job": f"{g}/{c}/{ctx}/run{j['run']}", "verified_met": 0, "other_runs_met": others, "model_said_met": said, "of_which_quotes_with_ellipsis": ellipsis})
    collapsed = {(x["job"].split("/")[0], x["job"].split("/")[1], x["job"].split("/")[2], int(x["job"].split("/run")[1])) for x in collapses}

    def _diff(a_: Dict[str, Any], b_: Dict[str, Any]) -> int:
        reqs_ = _requirement_texts(a_)
        va, vb = {t_: x_ for t_, x_ in verdicts(a_).items() if t_ in reqs_}, {t_: x_ for t_, x_ in verdicts(b_).items() if t_ in reqs_}
        return sum(1 for t_ in set(va) | set(vb) if (va.get(t_) == "met") != (vb.get(t_) == "met"))

    baseline: List[Dict[str, Any]] = []
    for e in groups["R3"]:
        if e.kind != "same_verdicts_as":
            continue
        def healthy(cand_key: str) -> List[Dict[str, Any]]:
            """runs whose verified `met` count is at least 60% of the best run of that candidate: a run that lost most of its quotes to the quote gate is not a reading of the candidate"""
            rs = [j for j in jobs if j["group"] == "R3" and j["candidate"] == cand_key]
            top = max((met_n(j) for j in rs), default=0)
            return [j for j in rs if met_n(j) >= 0.6 * top]
        ca, cb = healthy(e.candidate), healthy(e.other)
        within = [_diff(x_, y_) for i_, x_ in enumerate(cb) for y_ in cb[i_ + 1:]]
        across = [_diff(x_, y_) for x_ in ca for y_ in cb]
        same_run = [_diff(x_, y_) for x_ in ca for y_ in cb if x_["run"] == y_["run"]]
        mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
        baseline.append({"eid": e.eid, "candidate": e.candidate, "other": e.other, "runs_used": [len(ca), len(cb)], "rule": "healthy runs only: verified met >= 60% of that candidate's best run", "mean_items_differing_between_two_runs_of_the_SAME_candidate": mean(within),
                         "mean_items_differing_between_the_two_candidates": mean(across), "same_run_pairs": mean(same_run),
                         "zero_difference_pairs": sum(1 for x_ in across if x_ == 0), "pairs": len(across)})
    summary = {"exclusion_tally": exclusion_tally, "collapses": collapses, "invariance_baseline": baseline, "expectations": results, "flips": flips, "minor_flips": minor, "exclusion_flips": excl_flips, "cells": items, "leaks": leaks, "legacy_leaks": legacy_leaks, "totals": totals,
               "asked_only_what_the_checklist_judges": {"jobs_checked": checked, "violations": unresolved_asked}}
    summary["conflict"] = conflict_analysis(jobs)
    summary["verdict_tables"] = verdict_tables(jobs)
    if not write:
        return summary
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / out_name).write_text(json.dumps(summary, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def conflict_analysis(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for group, item_compiled, item_legacy in (("CONFLICT", "Python", sc.CONFLICT_LEGACY_SIGNALS[0]), ("CONFLICT_CO", None, sc.CONFLICT_COMPANY_LEGACY[0])):
        rows = []
        for j in sorted((x for x in jobs if x["group"] == group), key=lambda x: (x["candidate"], x["context"], x["run"])):
            v = verdicts(j)
            rows.append({"candidate": j["candidate"], "context": j["context"], "run": j["run"], "asked": asked_texts(j), "verdicts": v, "input_source": j["input_source"],
                         "disagreements": j["disagreements"]})
        out[group] = rows
    return out


def verdict_tables(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """per group/context/candidate: met counts per run (compact evidence for the report)."""
    out: Dict[str, Any] = {}
    for j in jobs:
        v = verdicts(j)
        k = f"{j['group']}|{j['context']}|{j['candidate']}"
        out.setdefault(k, []).append({"run": j["run"], "asked": len(v), "met": sum(1 for x in v.values() if x == "met"), "partly": sum(1 for x in v.values() if x == "partly"),
                                      "exclusions_present": [x["text"][:60] for x in (j["exclusion_judgments"] or []) if x["verdict"] == "present"]})
    return {k: sorted(v, key=lambda r: r["run"]) for k, v in sorted(out.items())}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze", "diagnose", "run_v2", "analyze_v2"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "diagnose":
        g, c = a.only.split(":")
        for j in diagnose(g, c, a.runs):
            first = next(r for r in j["requests"] if r["system"].startswith("You verify"))
            parsed = json.loads(first["response"] or "{}").get("results", [])
            print(j["run"], "met", sum(1 for x in j["judgments"] if x["verdict"] == "met"), "model said met:", sum(1 for x in parsed if x.get("verdict") == "met"),
                  "partly:", sum(1 for x in parsed if x.get("verdict") == "partly"), "answers:", len(parsed))
    elif a.cmd == "run":
        run(a.runs, [x for x in a.only.split(",") if x] or None, a.workers)
    elif a.cmd == "run_v2":
        run(a.runs, [x for x in a.only.split(",") if x] or ["R1", "R3"], a.workers, RAW_V2)
    elif a.cmd == "analyze_v2":
        s = analyze(RAW_V2, "analysis_v2.json", ("excl_present", "excl_not_present"))
        for r in s["expectations"]:
            print(f"{r['status']:9} {r['eid']:32} {r['passed_runs']}/{r['runs']} {r['observed']}")
    else:
        s = analyze()
        print(json.dumps({k: s[k] for k in ("totals", "leaks", "legacy_leaks")}, indent=1))
        for r in s["expectations"]:
            print(f"{r['status']:9} {r['eid']:32} {r['passed_runs']}/{r['runs']} {r['observed']}")


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# admission (deterministic: the gate itself is unchanged; this shows which compiled facts it was given and what it decided)
# ---------------------------------------------------------------------------------------------------------------------------------------------------------

_ADM_LEVELS = [("lead", "Lead Engineer", "Lead Engineer"), ("senior", "Senior Engineer", "Senior Engineer"), ("director", "Director of Engineering", "Engineering leadership"),
               ("junior", "Junior Engineer", "Junior Engineer"), ("no_level", "Engineer", "Engineer")]


def _adm_candidate(key: str, title: str, headline: str, start_year: int) -> Candidate:
    return Candidate(candidate_id=f"adm-{key}", name=f"Synthetic {key}", title=title, company="Synthetic Co",
                     raw_data={"basic_profile": {"headline": headline}, "metadata": {"updated_at": "2026-09-01T00:00:00+00:00"},
                               "experience": {"employment_details": {"current": [{"start_date": f"{start_year}-01-01T00:00:00", "title": title}], "past": []}}})


def _decide(intent: SearchIntent, cand: Candidate) -> Dict[str, Any]:
    from backend.services.admission import evaluate_eligibility
    from backend.services.candidate_evidence_builder import build_candidate_evidence
    ra = build_candidate_evidence(cand, intent).role_alignment
    ok, reason = evaluate_eligibility(ra.level_fit, ra.experience_floor)
    return {"level_fit": ra.level_fit, "experience_floor": ra.experience_floor, "admitted": ok, "reason": reason}


def _syn_ctx(quote: str, **atom) -> Any:
    return conflict_context(quote, **atom)


def admission_report() -> Dict[str, Any]:
    from backend.models.search_intent import Experience, Role
    out: Dict[str, Any] = {"cases": []}

    def case(name: str, intent: SearchIntent, legacy: Optional[SearchIntent], cands: List[Tuple[str, str, str, int]], note: str) -> None:
        facts = ci.admission_facts_for(intent.compiled_context).to_dict()
        rows = []
        for key, title, headline, start in cands:
            c = _adm_candidate(key, title, headline, start)
            row = {"candidate": key, "title": title, "start_year": start, "compiled": _decide(intent, c)}
            if legacy is not None:
                row["legacy_would"] = _decide(legacy, c)
            rows.append(row)
        out["cases"].append({"case": name, "note": note, "facts": {k: facts[k] for k in ("target_level", "accepted_levels", "minimum_years")}, "ungated": [f"{u['text']} ({u['fate']})" for u in facts["ungated"]], "rows": rows})

    r1 = {c.path_id: c for c in dv.contexts_for("R1", 3)}
    ladder = [(k, t, h, s) for k, t, h, s in sc.ADMISSION_R1]
    legacy_lead = SearchIntent(role=Role(seniority="Lead"), experience=Experience(minimum_years=6))
    case("R1 PATH A: Lead (+Senior alternative) are PREFERRED", ci.search_intent_for_context(r1["PATH A"]), legacy_lead, ladder,
         "a preferred level never gates admission: every candidate is admitted; the legacy reading of the same level would have excluded some")
    case("R1 PATH B: Lead is REQUIRED, 6+ years", ci.search_intent_for_context(r1["PATH B"]), legacy_lead, ladder, "the required level and floor gate, with the unchanged rule")
    q = "We need a Senior engineer; Lead is also fine."
    case("synthetic: Senior required, Lead accepted as an alternative (OR)", ci.search_intent_for_context(_syn_ctx(q, seniority={"value": "Senior", "strength": "required", "alternatives": ["Lead"],
         "basis": {"sources": ["jd"], "quote": q}})), SearchIntent(role=Role(seniority="Senior")), [(k, t, h, 2012) for k, t, h in _ADM_LEVELS],
         "OR semantics: a Lead is aligned (not 'above'); a Senior is aligned; a Director is above both and is excluded; a Junior is below both")
    q = "A Senior engineer would be preferred."
    case("synthetic: Senior is PREFERRED", ci.search_intent_for_context(_syn_ctx(q, seniority={"value": "Senior", "strength": "preferred", "basis": {"sources": ["jd"], "quote": q}})),
         SearchIntent(role=Role(seniority="Senior")), [(k, t, h, 2012) for k, t, h in _ADM_LEVELS], "preferred never rejects")
    q = "We need a Staff engineer."
    case("synthetic: Staff (no approved level mapping) is UNRESOLVED", ci.search_intent_for_context(_syn_ctx(q, seniority={"value": "Staff", "strength": "required", "basis": {"sources": ["jd"], "quote": q}})),
         SearchIntent(role=Role(seniority="Staff")), [(k, t, h, 2012) for k, t, h in _ADM_LEVELS], "an unresolved level is not invented: nobody is gated on it, and it stays visible (ungated)")
    return out
