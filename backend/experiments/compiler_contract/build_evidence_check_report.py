"""Builds RESULTS_EVIDENCE_CHECK_VALIDATION.md from results/evidence_check/analysis.json (+ the analyst's classification.json, if present). No number is typed by hand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import evidence_check_scenarios as scn
from backend.experiments.compiler_contract.build_report import md

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "evidence_check"
OUT = HERE / "RESULTS_EVIDENCE_CHECK_VALIDATION.md"


def _load(name: str) -> Any:
    p = RES / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _table(rows: List[Dict[str, Any]]) -> str:
    return md([[r["eid"], r["candidate"], r["check"], (r["item"] or "")[:60], r["expected"], r["status"], f"{r['passed_runs']}/{r['runs']}", ", ".join(sorted(set(map(str, r["observed"]))))[:120], r["why"]] for r in rows],
              ["expectation", "cand.", "check", "item", "expected", "status", "runs correct", "observed", "why"])


def build() -> str:
    a = _load("analysis.json")
    cls = _load("classification.json") or {}
    t, u, sc = a["totals"], a["universal_violations"], a["scenarios"]
    ex = a["expectations"]
    by = {r["eid"]: r for r in ex}
    gating = [r for r in ex if r["gating"]]

    def ok(ids):
        return all(by[i]["status"] == "PASS" for i in ids)

    scen_pass = {g: s["runs_all_correct"] == s["runs"] and s["runs"] > 0 for g, s in sc.items()}
    criteria = [
        ["each verdict maps to the correct check_id", "PASS" if u["unbound"] == 0 and not any("no verdict bound" in str(o) for r in gating for o in r["observed"]) else "FAIL",
         f"{u['unbound']} verdicts without a known check_id over {t['jobs']} runs; every expectation was read through its check_id"],
        ["evidence cannot be cross-assigned between skills", "PASS" if u["binding_violations"] == 0 and ok(["B2-java", "B3-python", "C3-excel", "C4-pbi"]) else "FAIL",
         f"{u['binding_violations']} accepted verdicts whose quote does not name the check's subject; the four cross-assignment expectations: {', '.join(by[i]['status'] for i in ['B2-java', 'B3-python', 'C3-excel', 'C4-pbi'])}; the validator discarded {t['binding_discards']} proposed verdicts"],
        ["proficiency is evaluated separately", "PASS" if scen_pass["B"] and scen_pass["C"] else "FAIL", f"scenario B {sc['B']['runs_all_correct']}/{sc['B']['runs']}, scenario C {sc['C']['runs_all_correct']}/{sc['C']['runs']} runs fully correct"],
        ["exclusion semantics are reliable", "PASS" if ok(["A-E-present", "A-A-not-present", "A-G-not-broadened"]) else "FAIL", ", ".join(f"{i}: {by[i]['passed_runs']}/{by[i]['runs']}" for i in ["A-E-present", "A-A-not-present", "A-G-not-broadened"])],
        ["insufficient exclusion evidence remains distinct", "PASS" if by["A-H-insufficient"]["status"] == "PASS" else "FAIL", f"A-H-insufficient {by['A-H-insufficient']['passed_runs']}/{by['A-H-insufficient']['runs']}: observed {sorted(set(map(str, by['A-H-insufficient']['observed'])))}"],
        ["exact quote verification remains active", "PASS" if u["bad_quotes"] == 0 else "FAIL", f"{u['bad_quotes']} accepted quotes fail the gate; of {t['first_pass_claims_with_quote']} first-pass claims, {t['first_pass_claims_with_ellipsis']} contained an ellipsis and none was accepted"],
        ["successful checks are not retried", "PASS" if u["retry_violations"] == 0 else "FAIL", f"{u['retry_violations']} violations; {t['retry_calls']} retry calls re-asked {t['retried_checks']} checks ({t['retries_recovered']} recovered)"],
        ["no provider syntax reaches the Judge", "PASS" if u["leaks"] == 0 else "FAIL", f"{u['leaks']} hits over {t['calls']} calls (provider syntax, compiler detail, check_id, recruiter wording, evidence terms)"],
    ]
    overall = all(c[1] == "PASS" for c in criteria) and all(scen_pass.values())
    target = [[g, {"A": "Role 1 negative", "B": "Role 2 proficiency", "C": "Role 3 proficiency"}[g], f"{s['runs_all_correct']}/{s['runs']}", "PASS" if scen_pass[g] else "NOT 6/6"] for g, s in sorted(sc.items())]
    failing = [r for r in gating if r["status"] != "PASS"]
    cls_rows = [[r["eid"], f"{r['passed_runs']}/{r['runs']}", ", ".join(sorted(set(map(str, r["observed"]))))[:100], cls.get(r["eid"], {}).get("class", "(unclassified)"), cls.get(r["eid"], {}).get("note", "")] for r in failing]
    mech = [["model calls / tokens / cost", f"{t['calls']} / {t['input_tokens']:,} in, {t['output_tokens']:,} out / about ${t['estimated_cost_usd']}"],
            ["first-pass claims carrying a quote", t["first_pass_claims_with_quote"]], ["... of which contained an ellipsis (all rejected by the gate)", t["first_pass_claims_with_ellipsis"]],
            ["checks retried (only those that failed the quote gate)", f"{t['retried_checks']} in {t['retry_calls']} retry calls; {t['retries_recovered']} recovered"],
            ["proposed verdicts discarded by deterministic binding", t["binding_discards"]], ["verdicts downgraded by the (unchanged) review pass", t["review_downgrades"]],
            ["API failures", t["failed_jobs"]]]
    prof_rows = [[p.key, p.label] for g in "ABC" for p in scn.SCENARIOS[g][0]]
    return f"""# RESULTS — Evidence Check validation (real Judge model; synthetic candidates only)

Phase: harden the downstream Evidence Check contract. **Not called:** CrustData, Harvest, any provider, any retrieval; **no real candidate data; not deployed; `StructuredHiringIntent` unchanged (hash-pinned); ranking and admission unchanged (hash-pinned).** The only external call is the Judge's own model (OpenAI, through the sandbox proxy), gpt-4o-mini at temperature {", ".join(t["temperatures"])}, with the requirement and review prompts unchanged (hash-pinned). Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3b-3f). Raw outputs: `results/evidence_check/raw/`. Reproduce: `python -m backend.experiments.compiler_contract.evidence_check_run run --runs 6` then `analyze`, then `build_evidence_check_report`.

## Verdict
**{"PASS: every acceptance criterion holds and every scenario is 6/6 correct." if overall else "NOT 6/6 on every scenario: see the target table and the classification of each failure below."}**

## 1. What changed (the Evidence Check)
* An **Evidence Check** (`backend/services/evidence_check.py`) is the semantic unit the Judge evaluates: `check_id`, `path_id`, `concept`, `criterion`, `positive|negative`, `strength`, `proficiency`, `relationship`, `provenance`, plus the deterministic binding fields (`subject_terms`, `requires_work_evidence`) and, for negatives, an explicit `predicate`. It is a downstream execution artifact built from the compiled checklist; it is not part of `StructuredHiringIntent`.
* **Binding.** A verdict binds to exactly one `check_id` (an id answered twice is unanswered). A `met` / `partly` / `PRESENT` stands only if its quote passes the gate **and** supports THIS check: a named skill's quote must name that skill; a depth claim (skill + depth is ONE claim) needs demonstrated work or a certification, never a skills-list entry, a title or a headline; a PRESENT exclusion's quote must contain an indicator of its own predicate.
* **Exclusions** are explicit predicates (`must_not_indicate`, `not_sufficient`, `unless_candidate_also_shows`, `exclusive`, the recruiter's `qualifier`), answered `PRESENT` / `NOT_PRESENT` / `INSUFFICIENT_EVIDENCE`. The recruiter prose is never sent to the model. A PRESENT that cannot be evidenced, and a NOT_PRESENT on a profile that describes no work, are INSUFFICIENT_EVIDENCE, never NOT_PRESENT.
* **Quote gate** unchanged in strength, now explicit: one contiguous exact span of ONE passage, no ellipsis (`...` or the single character), no paraphrase. **One narrow retry**: only the checks whose quote failed the gate are re-asked, once, with an exact-quote instruction; a successful check is never re-asked and a binding discard is final.

## 2. Scenarios (synthetic, hand-written before any run, unchanged between runs)
{md(prof_rows, ["candidate", "designed to show"])}

## 3. Target: 6/6 semantic correctness on each scenario
A run is correct only if EVERY gating expectation of the scenario holds in that run.

{md(target, ["scenario", "what", "runs fully correct", "target"])}

## 4. Results per expectation (6 runs each)
{_table([r for r in ex if r["scenario"] == "A"])}

{_table([r for r in ex if r["scenario"] == "B"])}

{_table([r for r in ex if r["scenario"] == "C"])}

(`A-G-firm-info` is informational and not part of the acceptance.)

## 5. Acceptance
{md(criteria, ["criterion", "status", "evidence"])}

## 6. The mechanisms, measured
{md(mech, ["", ""])}

### What the deterministic binding discarded
{md([[b["label"], b["kind"], ", ".join(b["subject_terms"]) or "-", b["reason"].replace("binding:", ""), b["count"], b["example_quote"]] for b in a["binding_breakdown"]], ["check", "kind", "subject tokens", "why discarded", "times", "example quote the model cited"])}

{cls.get("_binding_note", "")}

### Exploratory diagnostic (NOT part of the validation, NOT adopted)
{cls.get("_diagnostic_note", "")}

{md([[c, ", ".join(f"{k}: {v.count('met')}/{len(v)} met" for k, v in sorted(d.items()))] for c, d in sorted(a["diagnostic_at_least"].items())], ["candidate", "with the depth clause worded 'at least' (6 runs)"]) if a["diagnostic_at_least"] else ""}

## 7. Failures, classified
{md(cls_rows, ["expectation", "runs correct", "observed", "class", "note"]) if cls_rows else "None: every gating expectation passed on every run."}

Classes: PROMPT/CONTRACT (what the model was asked), MODEL CAPABILITY (the model cannot do it reliably as asked), VALIDATION (the deterministic checks), REPRESENTATION (the check is mis-built). The classification is the analyst's reading of the evidence above; the verdicts are measured.

## 8. Remaining risks
{cls.get("_risks", "(see the contract, section 8)")}

## 9. Hard stop
No CrustData. No retrieval. No deployment. Paths, path allocation and result merging are unchanged. Waiting for architecture review.
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
