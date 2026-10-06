# RESULTS — Role 1 intake experiment: baseline vs experimental representation

Config for both arms: `gpt-6.1-sol`, reasoning effort `medium`, same JD, same brief, 5 runs each. Raw per-run evidence is in
`results/` (model prompts stripped; they are the committed inputs plus `prompt_v2.txt`). Reproduce the table offline with
`python -m backend.experiments.intake_strategy.compare_arms`. Design rationale is in `DESIGN.md`.

## Provenance of this result (what to distrust)
- **Prompt and schema changed together.** The baseline used the production prompt; the experimental arm uses `prompt_v2.txt`
  (production rules 1-10 verbatim, plus nine new generic rules; the "treat the brief exactly like JD requirements" tail is
  replaced by the source-priority model). The two cannot be separated: 13 of the 16 baseline failures were classed
  REPRESENTATION from the schema alone, so they needed fields regardless of the prompt, but the reconciliation gains also
  owe something to the new priority rule.
- **The prompt's illustrations were written with this class of role in mind.** They contain none of Role 1's values (a test
  enforces that, and that no gold assertion text reaches a prompt), but they show the same *shape* (a domain-led track with
  wide geography vs a capability-led track in a city; a "monitoring" item contradicted by the brief). This result shows Role 1
  is expressible; it does not show the prompt generalises to a differently shaped role.
- **One role.** Role 2 is deferred by the owner.
- **Transport.** The first experimental attempt failed 5/5 (`InternalServerError: upstream request failed`, three tries each,
  every try ending at ~92 s, the same cutoff the baseline's first run 5 hit). A non-streaming call that runs past ~90 s is cut off
  upstream; the larger experimental reply (22.6k in / 20.6k out for 5 runs vs 15.3k / 8.4k) exceeds it. The retry streams the
  response (same model, effort, prompt, parse path; `StreamingRecordingClient`). Failed attempts returned no usage data, so
  whether they consumed credits is unknown. The baseline's run 5 was likewise retried once (separately, same code).
- **Post-hoc change.** After seeing the results I added `quote_overlap` (informational only, never changes a status or verdict)
  once I noticed `verified` proves a quote exists, not that it supports the atom. No threshold or verdict was loosened.
- The stricter `no_invented_company_exclusion` did not exist at baseline; it was computed from the stored baseline intents.

## C/D. Five-run gold table (previously failing assertions first)
Baseline = unchanged production schema, prompt, extractor. Experimental = `ExperimentalHiringIntent` + `prompt_v2.txt`.

| assertion | baseline | experimental | experimental failure class |
|---|---|---|---|
| `two_paths_preserved` | FAIL x5 | **PASS x5** | |
| `path_a_domain_led` | FAIL x5 | **PASS x5** | |
| `path_b_capability_led` | FAIL x5 | **PASS x5** | |
| `path_geography_differs` | FAIL x5 | **PASS x5** | |
| `pq_not_mandatory_path_a` | FAIL x5 | **PASS x5** | |
| `pq_working_knowledge_path_b` | FAIL x5 | **PASS x5** | |
| `sql_hands_on` / `python_hands_on` | PARTIAL x5 | **PASS x5** | |
| `path_b_min_6_years` | PARTIAL x5 | **PASS x5** | |
| `path_b_lead_requirement` | PARTIAL x3, FAIL x2 | **PASS x5** | |
| `cyber_review_not_secops` | FAIL x5 | **PASS x5** | |
| `hard_negative_secops_preserved` | FAIL x5 | **PASS x5** | |
| `lead_people_or_technical` | FAIL x5 | PASS x2, **PARTIAL x3** | RECONCILIATION x3 |
| `provenance_preserved` | FAIL x5 | **PASS x5** | |
| `no_invented_radius` | PASS x5 | PASS x5 | |
| `no_invented_company_filter` | PASS x5 | PASS x5 | |
| `no_invented_company_exclusion` (new) | FAIL x5 (`Security firm(s)` as a company) | PASS x5 | |
| `path_b_domain_not_required` (new) | not expressible | PASS x4, **FAIL x1** | RECONCILIATION x1 |
| `intent_country_level_geography` (new) | not expressible | PASS x5 | |
| `reconciliation_visible` (new) | not expressible | PASS x5 | |
| `jd_not_silently_discarded` (new) | not expressible | PASS x5 | |

Compiler checks (unchanged compiler, out of scope, so not re-run in the experimental arm): `compiler_country_not_city` FAIL x5,
`compiler_multi_location_keeps_country` FAIL x5, `compiler_no_company_filter` PASS x5. These stay COMPILER / NORMALIZATION.
The experimental intent says `India` as a country-level entry in 5/5 runs.

## The two non-PASS assertions, read, not summarised
- **`lead_people_or_technical` PARTIAL x3 (runs 2, 4, 5).** `seniority.leadership = [people, technical]` in 5/5 and a reconciliation
  records it, but a JD *responsibility* stayed `required` as an evidence signal ("Lead, mentor, support, coach, and develop review
  analysts" and equivalents). That contradicts "technical leadership suffices". Debatable whether a role responsibility is a
  candidate requirement; the schema has `context` for it and the production rule 3 pushes the model to `required`. Classed
  RECONCILIATION (extraction behaviour), not representation.
- **`path_b_domain_not_required` FAIL x1 (run 2).** The model rewrote the JD's "solid understanding of **cybersecurity** review
  processes" as "understanding of **cyber incident review** processes" and kept it `required` globally, so it applies to Path B.
  This is the cyber vs cybersecurity conflation the experiment exists to catch, arriving through paraphrase.

## Observations the gold does not gate
- **Security-firm statement.** The brief says "a strong SQL/Python analyst working at a security firm should be excluded". The
  model carried it as a second *semantic* concept in 5/5 runs, never as a company filter. Owner decision needed: keep it as a
  recruiter-stated hard negative, or treat it as an illustration of the work-type negative?
- **Path A seniority.** "Lead / Senior" is held as one value: `Senior/preferred` x3, `Lead/preferred` x2. The schema's `value` is
  single. Flagged, not added.
- **Path A experience.** 6+ years required on Path A in 5/5 (the model read the brief's header as global). The brief is ambiguous
  and the model did not mark it `unresolved`.
- **Remote.** "Remote across India" has no typed place; it survives only in quote/label text (5/5). Flagged, not added.
- **Granularity.** Domain atoms per run: 5, 5, 4, 9, 4 (run 4 split one domain into eight). Semantic exclusions 3 per run,
  reconciliations 6 per run: those were stable. One of the three semantic exclusions is a "cyber or incident wording alone is not
  enough" rule, which stretches the field (it is an insufficient-evidence rule, not an exclusion).
- **Cost/latency.** ~2.4x output tokens per run; 56-72 s per run vs 29-61 s baseline.

## Item-by-item: representable / consistently extracted / deterministically validated
"Validated" means checked at runtime from the two source texts alone (no ground truth). `gold-only` means only the offline
evaluator, which holds Role 1's truth, can judge it.

| # | item | structurally representable | consistently extracted (5 runs) | deterministically validated |
|---|---|---|---|---|
| 1 | two paths | yes (`sourcing_paths`) | 5/5 | count and correctness: gold-only; ids unique, strategy enum, path quote verbatim: yes |
| 2 | path identity | yes (`strategy`) | 5/5 | enum only; correctness gold-only |
| 3 | path geography | yes (path `location`) | 5/5 | quote verbatim; entry-to-quote lexical only; correctness gold-only |
| 4 | path requirements | yes (path overrides) | 4/5 (domain leak x1) | waiver-applied check for skills; domain leakage gold-only |
| 5 | path requirement strength | yes (override replaces) | 5/5 | enum only |
| 6 | proficiency | yes (`proficiency`) | 5/5 | enum only |
| 7 | semantic negative | yes (`semantic_exclusions`) | 5/5 | quote verbatim; concept wording model-only |
| 8 | cyber vs SOC | yes (domain + negative pair) | 5/5 | "no SecOps promoted" is gold-only (a Role-1 regex) |
| 9 | leadership meaning | yes (`seniority.leadership`) | field 5/5; conflict-free 2/5 | enum; people-only-requirement conflict is gold-only |
| 10 | reconciliation | yes (`reconciliations`) | 5/5 (all three expected found, 6 per run) | quotes verbatim in the right source; waiver applied; contradicted item not surviving (generic) |
| 11 | provenance | yes (`basis`) | 5/5 (100% of atoms carry one) | existence and source of the quote: yes. Entailment: no |
| 12 | no invented radius | yes (existing field) | 5/5 | gold-only |
| 13 | no invented company filter | yes | 5/5 | invented/inferred required atoms are flagged generically (`inferred_hard_constraint`); none occurred |
| 14 | country not city (intent) | by form only (`"India"`; no level field) | 5/5 | gold-only |

Provenance in the experimental runs: every atom `verified` (a verbatim quote in the cited source), 0 unsupported, 0 misattributed,
0 inferred. 27 of 192 quoted atoms share under half their words with their quote; I read all 27 and each is a genuine paraphrase
(path labels from headings, `Hyderabad, Telangana, India` from "Hyderabad OR Pune"). A lexical check cannot tell paraphrase from
mismatch, so entailment is unvalidated, not validated.

## G. Change summary
Added (experiment only): `experimental_schema.py`, `experimental_extractor.py`, `prompt_v2.txt`, `validators.py`,
`gold_experimental.py`, `run_experimental.py`, `compare_arms.py`, `DESIGN.md`, this file, `results/`, and
`tests/test_experiment_intake_strategy_v2.py`. Production files, the production prompt, `search_compiler`, providers and the
baseline evaluator are untouched (a test asserts no production module imports the experiment).

## H. Tests
Full suite: **822 passed, 4 skipped** (789 passed, 4 skipped at handoff). The 33 new tests are offline: they pin that a
correct intent passes every assertion, that each specific flaw fails the specific assertion with the right class, that a
fabricated or misattributed quote is caught, that production is unchanged and the new fields are additive, that the prompt keeps
rules 1-10 verbatim and adds no Role 1 terms, and the harness (streaming, retry only on transient errors, a cut stream is an error).

## F/I/K. Architectural decision
**INTAKE REPRESENTATION SUFFICIENT FOR THIS CLASS OF ROLE** (one role with alternative sourcing paths and a brief that narrows the JD).

Evidence: every path/geography/requirement/strength/proficiency/negative/provenance/reconciliation assertion that FAILed or was
PARTIAL at baseline is PASS 5/5, and the two that are not were produced by a model leaving a JD item at the wrong strength while the
schema could say the right thing (2 of 5 runs got leadership right in the same schema).

What this does and does not license:
- It is a verdict on the *representation*. The acceptance gate for live retrieval also requires the brief to override the JD
  correctly and acceptable five-run stability; with leadership PARTIAL x3 and one Path B domain leak, **that gate is not met**, and
  I am not recommending retrieval or compiler work.
- Reconciliation reliability is the open problem and it is not a schema problem. The deterministic checks that exist are
  generic but narrow; the two failures were found by the Role-1-specific evaluator, so nothing at runtime would have caught them.
- Three things the owner should decide (above): the security-firm statement, "Lead / Senior" on one path, and whether remote
  earns a field.

Smallest next experiment (not run): keep the schema; add one generic runtime consistency check (a required atom whose wording
overlaps a recorded `waived/narrowed/contradicted` topic on the same scope is flagged), plus one prompt rule that role
*responsibilities* are `context` unless the source frames them as a qualification, re-run 5x, and only then try a differently
shaped second role to test generalisation.
