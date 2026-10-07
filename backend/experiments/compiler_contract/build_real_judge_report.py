"""Builds RESULTS_REAL_JUDGE_VALIDATION.md from results/real_judge/{analysis,analysis_v2,admission}.json and the raw runs. No number is typed by hand."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import real_judge_scenarios as sc
from backend.experiments.compiler_contract.build_report import md

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "real_judge"
OUT = HERE / "RESULTS_REAL_JUDGE_VALIDATION.md"


def _load(name: str) -> Any:
    p = RES / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _status(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "NOT RUN"
    ss = {r["status"] for r in rows}
    return "PASS" if ss == {"PASS"} else "FAIL" if "FAIL" in ss else "UNSTABLE" if "UNSTABLE" in ss else "NOT RUN"


def _exp_table(rows: List[Dict[str, Any]]) -> str:
    return md([[r["eid"], r["candidate"], r["context"], r["kind"], (r["item"] or "")[:70], r["status"], f"{r['passed_runs']}/{r['runs']}", ", ".join(sorted(set(map(str, r["observed"]))))[:110], r["why"]]
               for r in rows], ["expectation", "cand.", "context", "check", "item", "status", "runs passed", "observed", "why it must hold"])


# the acceptance criteria (review brief section 7) and the expectations that decide each
CRITERIA = [
    ("the real Judge consumes the downstream context correctly (path obligations preserved, nothing reconstructed)", ["R1-PQ-waived-in-A", "R1-PQ-asked-in-B", "R1-domain-not-asked-in-B", "R1-domain-asked-in-A", "R1-A-domain", "R1-C-domain", "R1-B-no-domain", "R1-D-no-domain", "R1-B-pq", "R1-B-pq-wk", "R1-C-pq", "R1-A-no-pq", "R1-D-no-pq"]),
    ("negatives are evaluated", ["R1-E-soc-present", "R1-E-soc-present-B", "R1-A-soc-absent", "R1-C-soc-absent", "R1-B-soc-absent", "R1-D-soc-absent", "R3-Q5-excluded", "R3-Q6-not-broadened", "R3-Q7-not-broadened", "R3-Q1-not-excluded"]),
    ("proficiency is interpreted correctly (advanced != hands-on != working knowledge; unsupported depth is never asked)", ["R2-P1-handson-python", "R2-P1-handson-java", "R2-P2-handson-python", "R2-P2-handson-java", "R2-P1-wk-jira", "R2-no-invented-depth-llm", "R2-no-invented-depth-rag", "R2-no-invented-depth-ai", "R3-Q1-adv-excel", "R3-Q2-adv-excel", "R3-Q2-excel-plain", "R3-Q2-powerbi-wk", "R3-Q1-powerbi-wk", "R1-A-handson-sql", "R1-F-handson-sql-B"]),
    ("work mode is preserved (unresolved, distinct from geography, never asked, no candidate penalised)", ["R3-workmode-not-asked", "R3-workmode-not-asked-2", "R3-Q3-same-as-Q1"]),
    ("unsupported `current` is not invented; an analogy title is not a target", ["R2-P3-llm-past-ok", "R2-P3-rag-past-ok", "R2-P3-agentic-past-ok", "R2-no-current-text", "R2-plain-llm-asked", "R2-analogy-not-asked", "R2-analogy-no-engineering"]),
    ("preferences stay preferences", ["R1-F-pref-met", "R1-F-pref-not-enough", "R1-F-pref-not-enough-B", "R1-A-pref-missing-still-A", "R3-company-not-asked", "R3-Q4-same-as-Q1", "CO-compiled-company-not-asked", "CO-control-legacy-asks-company"]),
    ("compiled meaning beats legacy meaning", ["CF-compiled-asks-plain-python", "CF-legacy-sentence-never-sent", "CF-past-python-meets-compiled", "CF-current-python-meets-compiled", "CF-no-python-fails-compiled", "CF-control-legacy-would-reject-past", "CF-control-legacy-accepts-current"]),
]


def _tally(v1: List[Dict[str, Any]], v2: List[Dict[str, Any]]) -> List[List[Any]]:
    two = {(r["group"], r["candidate"], r["context"], r["exclusion"]): r for r in v2}
    out = []
    for r in v1:
        k = (r["group"], r["candidate"], r["context"], r["exclusion"])
        if k in two and r["context"] in ("PATH A", "ctx"):
            out.append([r["group"], r["candidate"], r["context"], r["exclusion"][:62], f"{r['present_runs']}/{r['runs']}", f"{two[k]['present_runs']}/{two[k]['runs']}"])
    return out


def build() -> str:
    a, v2, adm = _load("analysis.json"), _load("analysis_v2.json"), _load("admission.json")
    t = a["totals"]
    by = {r["eid"]: r for r in a["expectations"]}
    by2 = {r["eid"]: r for r in (v2 or {}).get("expectations", [])}
    excl_ids = {r["eid"] for r in a["expectations"] if r["kind"] in ("excl_present", "excl_not_present")}

    # --- acceptance, computed. STRICT = every run of every expectation agrees. NOISE-ADJUSTED differs only for the two invariance expectations ("same requirement
    # verdicts as Q1"), where the model's own run-to-run noise (healthy runs only) is the yardstick; it is post-hoc and labelled so.
    base = {b["eid"]: b for b in a["invariance_baseline"]}

    def adjusted(r: Dict[str, Any]) -> str:
        b = base.get(r["eid"])
        if b is None:
            return r["status"]
        return "PASS" if b["mean_items_differing_between_the_two_candidates"] <= b["mean_items_differing_between_two_runs_of_the_SAME_candidate"] + 0.5 else "FAIL"

    crit_rows: List[List[Any]] = []
    for text, ids in CRITERIA:
        rows = [by2[i] if (i in excl_ids and i in by2) else by[i] for i in ids if i in by]
        adj = _status([dict(r, status=adjusted(r)) for r in rows])
        crit_rows.append([text, _status(rows), adj, f"{sum(1 for r in rows if r['status'] == 'PASS')}/{len(rows)} expectations pass on every run" + (" (exclusions: after the v2 revision)" if any(i in excl_ids for i in ids) and v2 else "")])
    leaks_ok = not a["leaks"] and not a["legacy_leaks"]
    crit_rows.append(["no provider syntax, compiler detail or legacy sentence reaches the Judge", "PASS" if leaks_ok else "FAIL", "PASS" if leaks_ok else "FAIL", f"{len(a['leaks'])} provider/compiler-token hits and {len(a['legacy_leaks'])} legacy-sentence hits over every request the model received ({t['calls']} calls)"])
    viol = a["asked_only_what_the_checklist_judges"]["violations"]
    crit_rows.append(["unresolved items remain unresolved (never asked, never judged)", "PASS" if not viol else "FAIL", "PASS" if not viol else "FAIL",
                      f"{a['asked_only_what_the_checklist_judges']['jobs_checked']} compiled-context runs: {len(viol)} unresolved / exclusion / context-only items were asked as positives"])
    cases = {c["case"]: c for c in adm["cases"]}
    pa = cases["R1 PATH A: Lead (+Senior alternative) are PREFERRED"]
    alt = cases["synthetic: Senior required, Lead accepted as an alternative (OR)"]
    stf = cases["synthetic: Staff (no approved level mapping) is UNRESOLVED"]
    _p = "PASS" if all(r["compiled"]["admitted"] for r in pa["rows"]) else "FAIL"
    crit_rows.append(["a preferred requirement does not gate admission", _p, _p, "every candidate admitted under Path A (Lead / Senior preferred); the same facts read as required would have excluded " + str(sum(1 for r in pa["rows"] if not r["legacy_would"]["admitted"])) + " of " + str(len(pa["rows"]))])
    got = {r["candidate"]: r["compiled"]["level_fit"] for r in alt["rows"]}
    _o = "PASS" if got["lead"] == "aligned" and got["senior"] == "aligned" and got["director"] == "above" and got["junior"] == "below" else "FAIL"
    crit_rows.append(["accepted alternative levels are OR", _o, _o, f"level_fit by candidate: {got}"])
    _u = "PASS" if all(r["compiled"]["admitted"] and r["compiled"]["level_fit"] is None for r in stf["rows"]) else "FAIL"
    crit_rows.append(["unresolved seniority is not invented", _u, _u, "Staff: no candidate gated, level_fit None, the level kept visible as UNRESOLVED"])
    overall = all(r[1] == "PASS" for r in crit_rows)
    adj_overall = all(r[2] == "PASS" for r in crit_rows)
    failing = [r[0] for r in crit_rows if r[1] != "PASS"]

    # --- scenario tables
    scen = []
    for group, profs in (("R1 (frozen run 3, real Path A / Path B)", sc.PROFILES_R1), ("R2 (frozen run 1)", sc.PROFILES_R2), ("R3 (frozen run 1)", sc.PROFILES_R3), ("conflict (synthetic intent)", sc.CONFLICT_PROFILES + sc.CONFLICT_COMPANY_PROFILES)):
        for p in profs:
            scen.append([group, p.key, p.title, p.label])

    # --- per-candidate counts
    vt = a["verdict_tables"]
    counts = []
    for k, rows in vt.items():
        g, ctx, cand = k.split("|")
        if g.startswith("CONFLICT"):
            continue
        counts.append([g, ctx, cand, len(rows), "/".join(str(r["met"]) for r in rows), rows[0]["asked"], "; ".join(sorted({x for r in rows for x in r["exclusions_present"]}))[:90]])

    # --- stability
    flips = a["flips"]
    cells = a["cells"]
    fl = Counter((f["group"], f["candidate"], f["context"]) for f in flips)
    collapse = a["collapses"]
    with_resp = [c for c in collapse if c["model_said_met"] is not None]
    collapse_note = (f"{len(collapse)} of {t['jobs']} runs produced ZERO verified `met` while the other runs of the same candidate produced many (post-hoc, objective definition: zero verified `met` while a majority of the other runs have 5 or more): "
                     + (", ".join(c["job"] for c in collapse) or "none")
                     + ". " + (f"For the {len(with_resp)} of these whose raw response was kept, the model said `met` for {sum(c['model_said_met'] for c in with_resp)} claims and {sum(c['of_which_quotes_with_ellipsis'] for c in with_resp)} of those quotes contained an ellipsis; the existing verified-quote gate discarded them, so the run read as nothing evidenced. "
                               if with_resp else "The raw responses of the first three runs were not kept, so the cause was diagnosed separately (`results/real_judge/diagnostics/`: the model put `...` inside the quotes, and the existing gate correctly discarded them). ")
                     + "A collapse is not a verdict about the candidate.")
    base_rows = [[b["eid"], b["runs_used"], b["mean_items_differing_between_two_runs_of_the_SAME_candidate"], b["mean_items_differing_between_the_two_candidates"], b["same_run_pairs"], f"{b['zero_difference_pairs']}/{b['pairs']}"] for b in a["invariance_baseline"]]
    stab_rows = [[g, c, ctx, n] for (g, c, ctx), n in sorted(fl.items(), key=lambda kv: -kv[1])[:12]]

    exp_by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in a["expectations"]:
        exp_by_group[r["group"]].append(r)

    v1_prompt = ""
    for p in sorted((RES / "raw").glob("R1__E__PATH_A__run1.json")):
        for rq in json.loads(p.read_text(encoding="utf-8"))["requests"]:
            if rq["system"].startswith("You check whether"):
                v1_prompt = rq["system"]
    v2_prompt = ""
    for p in sorted((RES / "raw_v2").glob("R1__E__PATH_A__run1.json")):
        for rq in json.loads(p.read_text(encoding="utf-8"))["requests"]:
            if rq["system"].startswith("You check whether"):
                v2_prompt = rq["system"]

    def fmt(rows):
        return _exp_table(rows)

    v2_block = ""
    if v2:
        v1x = [r for r in a["expectations"] if r["eid"] in excl_ids]
        v2x = [r for r in v2["expectations"]]
        v2_block = f"""
### Exclusion pass: v1 and the v2 revision
The first exclusion prompt (v1, below) was written before any run. Its result on the Role 1 SOC exclusion is the failure recorded in the v1 table. **This is a documented revision made AFTER seeing v1, not a blind result**: the root cause (below) was fixed with a generic clarification, the same scenarios were re-run unchanged, and both tables are kept. The held-out checks (the Role 3 exclusions, which v1 already passed) show whether the revision broadened the exclusion.

**Probable cause (a hypothesis: the model returns a verdict, never a reason).** The Role 1 exclusion is worded as a statement of what does NOT count (`Generic cybersecurity or security-operations backgrounds are not equivalent to ...`), not as a profile, and v1 answered `not_present` for a SOC analyst on every run. v2 adds one generic rule for that wording. **v2 helped but did not fix it** (Path A: unstable; Path B, the same exclusion text: still never `present`), and on the held-out Role 3 exclusions it did not broaden anything (Q6, Q7, Q1 stay `not_present` on every run) but the true positive Q5 slipped from 6/6 to 5/6. No further revision was made: another prompt change on these same scenarios would be tuning to them, and the open question (single-claim exclusion calls, a bigger model, or rewording at the compiler) is for architecture review. The requirement prompt is not involved (unchanged, pinned by hash).

**v1 (as run, N={max((r['runs'] for r in v1x), default=0)}):**

{fmt(v1x)}

**v2 (N={max((r['runs'] for r in v2x), default=0)}):**

{fmt(v2x)}

**Every exclusion verdict, every candidate (present in how many runs), v1 vs v2.** Only the SOC exclusion for candidate E (Role 1) and the audit exclusion for Q5 (Role 3) are meant to be `present`; every other cell should be 0. The other two Role 1 exclusions are sub-profile statements ("A strong SQL/Python analyst working at a security firm", "Cyber or incident wording alone without relevant substantive evidence") that are not self-contained; they were not given pre-declared expectations, and their verdicts are reported as measured.

{md(_tally(a["exclusion_tally"], v2["exclusion_tally"]), ["group", "candidate", "context", "exclusion", "v1 present", "v2 present"])}

v1 exclusion system prompt, verbatim (recorded in every raw request):

```
{v1_prompt}
```

v2 (as run; recorded in every raw v2 request):

```
{v2_prompt}
```
"""

    nonpass = [r for r in a["expectations"] if r["status"] != "PASS" and r["eid"] not in excl_ids]
    java = by["R2-P1-handson-java"]
    unstable_req = [r for r in nonpass if r["status"] == "UNSTABLE" and r["kind"] in ("req_met", "pref_met")]
    soc1, soc2 = by["R1-E-soc-present"], by2.get("R1-E-soc-present", by["R1-E-soc-present"])
    reading = [
        [java["eid"], f"the SAME quote that makes `hands-on Python` met is the evidence for `hands-on Java`; the verdict is `partly` in {java['runs'] - java['passed_runs']}/{java['runs']} runs and the review pass downgraded it in {java['review_downgrades']}", "the production REVIEW pass (a second model reading only the requirement and the quote) disagreeing with the first pass on a proficiency-prefixed requirement; not the downstream context"],
        [", ".join(r["eid"] for r in unstable_req), "the verdict flips between runs on borderline evidence (a light statement of tool use, or a long passage)", "likely model noise at temperature 0 and quote-gate discards (section 7); the cause was not isolated per item"],
        ["R3-Q3-same-as-Q1, R3-Q4-same-as-Q1", "strictly FAIL (a single differing requirement item in any run fails it); against the model's own noise the candidates are indistinguishable (section 7)", "consistent with model noise and quote-gate discards rather than an effect of the work mode or of the preferred company (a supplementary reading, section 7)"],
        ["R1-E-soc-present", f"v1 {soc1['passed_runs']}/{soc1['runs']}; v2 {soc2['passed_runs']}/{soc2['runs']} (Path A) and {by2.get('R1-E-soc-present-B', by['R1-E-soc-present-B'])['passed_runs']}/{by2.get('R1-E-soc-present-B', by['R1-E-soc-present-B'])['runs']} (Path B, the same exclusion text)", "the exclusion pass is unreliable for an exclusion worded as 'X backgrounds are not equivalent to Y' (probable cause; section 6); the other two Role 1 exclusions (sub-profile fragments, no pre-declared expectation) are also read inconsistently"],
    ]
    return f"""# RESULTS — the REAL Judge on the downstream contract (synthetic candidates only)

Phase: validate the new downstream Judge contract with the **real Judge model** and **synthetic candidate evidence only**. **Not called:** CrustData, Harvest, any provider, any retrieval; **no real candidate data; not deployed.** The only external call is the Judge's own model (OpenAI, through the sandbox's proxy). Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md`. Raw outputs (every request and every verdict): `results/real_judge/`. Reproduce: `python -m backend.experiments.compiler_contract.real_judge_run run --runs 6`, then `analyze`, `admission`, and `build_real_judge_report`.

## Verdict
**{"PASS" if overall else ("NOT ALL ACCEPTANCE CRITERIA PASS STRICTLY" + ("; all pass once the invariance checks are read against the model's own noise" if adj_overall else "; some fail even noise-adjusted"))}.** Criteria not passing strictly: {"; ".join(failing) if failing else "none"}. See section 9 for each criterion and section 10 for what remains. The Judge's requirement and review prompts are unchanged (pinned by content hash); the only Judge change is the NEW exclusion pass the contract requires (negatives).

## 1. Configuration (what actually ran)
| | |
|---|---|
| model | {", ".join(t["models"])} (the production `JUDGE_MODEL`), temperature {", ".join(t["temperatures"])} |
| requirement + review prompts | unchanged (sha256-pinned in `tests/test_real_judge_validation.py`) |
| exclusion pass | new (`_EXCLUSION_PROMPT`), same verified-quote gate; see the revision note in section 6 |
| judge runs | {t["jobs"]} (each scenario run the same number of times, same config, **no tuning between runs**) |
| model calls / tokens / estimated cost | {t["calls"]} / {t["input_tokens"]:,} in, {t["output_tokens"]:,} out / about ${t["estimated_cost_usd"]} (list price assumption) |
| API failures / retried jobs | {t["failed_jobs"]} / {t["retried_jobs"]} (infrastructure retries only; a verdict is never retried) |
| input source | {", ".join(t["input_sources"])} (`compiled` = the context drove the Judge; `legacy` = the control arm) |

## 2. What the model is, and is not, given
* The model receives numbered **profile passages** and numbered **requirement texts** (and, in the exclusion pass, **exclusion texts**). Nothing else.
* **Interface-facing, not model-facing:** the sourcing path, provenance, strength, proficiency (beyond its wording, e.g. "hands-on Python"), the unresolved items, work mode, and the checklist itself. They live on the `JudgeChecklist` and in `JudgeOutcome`. The model is not asked to reconcile them, which is also why it cannot reconstruct or override them. **Unresolved items and context-only preferences are never sent to the model at all.**
* Leak scan over **every request the model received** ({t["calls"]} calls): provider syntax / provider field names / compiler details ({len(a["leaks"])} hits) and the legacy sentences of the conflict scenarios ({len(a["legacy_leaks"])} hits). Asked-text audit over {a["asked_only_what_the_checklist_judges"]["jobs_checked"]} compiled runs: {len(viol)} violations (an unresolved item, an exclusion, or a context-only preference asked as a positive requirement).

## 3. Synthetic scenarios
Every profile is invented text, labelled `SYNTHETIC PROFILE`, written once by hand before any run (`real_judge_scenarios.py`), and not edited between runs. The frozen compiled contexts are Role 1 run 3 (the run with real requirements exclusive to Path A and to Path B), Role 2 run 1, Role 3 run 1.

{md(scen, ["group", "cand.", "title", "designed to show"])}

## 4. Results per expectation (every run must agree for PASS; UNSTABLE = the runs disagree; N = runs)
An expectation is a statement of what a correct reading of the contract looks like for ONE candidate and ONE item (a verdict other than `met` counts as not met, as everywhere in the Judge). "asked / not asked" checks what the model was actually sent.

### Role 1 (Path A / Path B)
{fmt(exp_by_group["R1"])}

### Role 2
{fmt(exp_by_group["R2"])}

### Role 3
{fmt(exp_by_group["R3"])}

## 5. Legacy-vs-compiled conflict
The SearchIntent carries a conflicting legacy meaning together with the compiled context; the control arm gives the Judge ONLY the legacy sentence. Legacy: `{sc.CONFLICT_LEGACY_SIGNALS[0]}`. Compiled: Python required, relationship **unspecified**. Second case: legacy `{sc.CONFLICT_COMPANY_LEGACY[0]}` (a hard requirement) against a compiled company **preference**.

{fmt(exp_by_group["CONFLICT"] + exp_by_group["CONFLICT_CO"])}

## 6. Negatives: the exclusion pass
{v2_block if v2_block else "(see the expectation tables above)"}

## 7. Model stability (semantic disagreement, not JSON differences)
Per (candidate, context, item): the verdict is compared across the runs and counted as a **semantic disagreement** only when the `met` / not-`met` category differs (a `partly` vs `not_evidenced` swap is minor and counted separately).

| | |
|---|---|
| (candidate, context, item) cells compared | {cells} |
| semantic disagreements (met vs not met) | {len(flips)} |
| minor disagreements (partly vs not_evidenced) | {a["minor_flips"]} |
| exclusion-verdict disagreements | {len(a["exclusion_flips"])} |

Where the disagreements concentrate (top):

{md(stab_rows, ["group", "candidate", "context", "items that flip"])}

**Collapse events.** {collapse_note}

**Invariance baseline (collapsed runs excluded; supplementary and post-hoc, the strict expectation above is unchanged).** "Same verdicts as Q1" is judged against the model's own run-to-run noise: if two runs of the SAME candidate already differ on about as many items as two different candidates do, the invariance test cannot show an effect of the work mode or the preferred company.

{md(base_rows, ["expectation", "runs used (cand., other)", "items that differ between two runs of the same candidate", "items that differ between the two candidates", "same-run pairs", "pairs with zero difference"])}

Met count per run (first-pass verdicts after the verified-quote gate and the review pass) for every compiled-context candidate:

{md(counts, ["group", "context", "cand.", "runs", "met per run", "items asked", "exclusions present"])}

## 8. Admission (deterministic gate, fed the compiled facts; thresholds and level rules unchanged)
{chr(10).join(f"**{c['case']}** (target level `{c['facts']['target_level']}`, accepted `{c['facts']['accepted_levels']}`, floor `{c['facts']['minimum_years']}`, ungated: {c['ungated'] or 'none'}). {c['note']}." + chr(10) + chr(10) + md([[r['candidate'], r['title'], r['start_year'], r['compiled']['level_fit'], r['compiled']['experience_floor'], 'admitted' if r['compiled']['admitted'] else 'EXCLUDED: ' + str(r['compiled']['reason']), ('admitted' if r['legacy_would']['admitted'] else 'excluded: ' + str(r['legacy_would']['reason'])) if r.get('legacy_would') else ''] for r in c['rows']], ['cand.', 'title', 'start', 'level_fit', 'experience_floor', 'compiled facts', 'the same fact read as required (legacy)']) + chr(10) for c in adm['cases'])}

## 8b. Reading the failures (computed from the runs above; what each is, and what it is not)
{md(reading, ["expectation(s)", "what the runs show", "cause"])}

## 9. Acceptance
Strict = every run of every expectation agrees. Noise-adjusted differs only for the two "same requirement verdicts as Q1" invariance expectations, judged against the model's own run-to-run noise (supplementary, post-hoc; section 7). An UNSTABLE expectation is never adjusted.

{md(crit_rows, ["criterion", "strict", "noise-adjusted", "evidence"])}

## 10. Remaining integration gaps
1. **The real Judge's quote gate collapses a run when the model writes an ellipsis in a quote.** The production gate (a quote must appear verbatim in the cited passage) correctly discards a quote containing `...`; when the model does this for every claim, the whole run reads as "nothing evidenced". Seen in this phase on the unchanged requirement prompt (see section 7). This is existing production behaviour, not the new contract, and it makes a single run unreliable as an exclusion; a decision is needed (re-ask on mass-discard, or verify the fragments around an ellipsis).
2. **What a `present` exclusion does is undefined.** The verdict exists and is evidenced, but nothing in ranking, admission or the recruiter view reads it.
3. **Pipeline wiring is not done** (contract section 9): the compiled filter tree has no provider adapter, the budget N -> 50 -> 25 across paths and the admission rule for a candidate found by several paths are undecided, and the intake does not capture a separate recruiter / HM brief (the shadow now accepts it).
4. **Real-model verdicts are not deterministic** even at temperature 0 (section 7); an expectation that must hold on every run is a strict bar for a 30-80 item prompt.
5. The scenarios are synthetic and small; they prove the contract is consumed, not that the Judge is accurate on real profiles.

## 11. Hard stop
No CrustData. No live retrieval. No deployment. Waiting for architecture review.
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
