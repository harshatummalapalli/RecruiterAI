# compiler_contract — offline compiler-contract experiment (EXPERIMENT ONLY)

Question: can the CURRENT deterministic compiler (`backend/services/search_compiler.py`, unchanged) translate the extended hiring intent without silently
dropping, strengthening or weakening meaning? Measurement only: no model, no CrustData, no Harvest, no retrieval, no production/provider/compiler/schema change.

- `CONTRACT_EXPECTATIONS.md` — written and committed BEFORE any compile output was examined: method, expected fate per concept, ten predictions, checks, gap-type rules.
- `RESULTS_COMPILER_CONTRACT.md` — the report (generated tables from `results/contract_analysis.json` + `report_template.md`).
- `results/baseline/` + `baseline_manifest.json` — compiled plans, audit records, downstream checklists, read sets for the 15 frozen intents, with hashes of the compiler-side files and stored runs.
- Code: `loader.py` (frozen intents, read-only), `signature.py` (output signatures, diff, read-set tracer), `atoms.py` (atom enumeration + ablation), `fate.py` (destination -> fate),
  `paths.py` (per-path compile vs whole plan), `probes.py` (strength / relationship / location / level probes), `checks.py` (Role 1/2/3 critical checks), `contract.py` (expected fates, gap types),
  `run_contract.py` (`baseline`, `analyse`), `build_report.py`.
- Tests: `tests/test_experiment_compiler_contract.py` (pins the unchanged compiler-side files and each baseline fact).

Reproduce: `python -m backend.experiments.compiler_contract.run_contract baseline && python -m backend.experiments.compiler_contract.run_contract analyse && python -m backend.experiments.compiler_contract.build_report`

## Hardening phase (compiler contract v1)
`RESULTS_COMPILER_HARDENING.md` (report, generated tables), `backend/services/COMPILER_CONTRACT.md` (the formal contract), `hardened_verify.py` (independent ablation verification of the LIVE compiler),
`results/hardened/` + `hardened_summary.json` (after measurements), `legacy_compiler_v1.py` (byte-identical copy of the compiler before hardening, pinned by hash, so the BEFORE measurements stay reproducible),
`tests/test_compiler_contract.py` (matrix A-O). The BEFORE modules (`fate.py`, `paths.py`, `probes.py`, `signature.py`, `run_contract.py`) deliberately measure the legacy copy.
Reproduce: `python -m backend.experiments.compiler_contract.hardened_verify && python -m backend.experiments.compiler_contract.build_hardening_report`

## Runtime-integration phase (offline)
`RESULTS_RUNTIME_INTEGRATION.md` (generated tables), `backend/services/RUNTIME_INTEGRATION_CONTRACT.md` (the contract), `runtime_verify.py` (removes every atom, recompiles with the source text, rebuilds the downstream contexts, checks where each atom lands),
`results/runtime/` + `runtime_summary.json`, `compiler_contract1_snapshot.py` (the contract-1 compiler, pinned, so the earlier hardening results stay reproducible).
Production additions: `backend/services/source_provenance.py` (source classification), `downstream_context.py` (per-path contexts, Judge adapter, legacy-consumer gaps), `path_merge.py` (merge data contract).
Tests: `tests/test_runtime_integration.py`. Reproduce: `python -m backend.experiments.compiler_contract.runtime_verify && python -m backend.experiments.compiler_contract.build_runtime_report`

Downstream consumer integration (this phase): `RESULTS_DOWNSTREAM_INTEGRATION.md` (generated), `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (the contract), `backend/services/consumer_input.py` (the one seam: `resolve(intent)` -> `JudgeChecklist`, `AdmissionFacts`, title facts, recorded disagreements; legacy fallback when `SearchIntent.compiled_context` is None), `downstream_verify.py` (synthetic candidates A/B/C/D through the real Judge with a scripted model; measurements to `results/downstream/summary.json`).
Tests: `tests/test_downstream_consumers.py`. Reproduce: `python -m backend.experiments.compiler_contract.downstream_verify && python -m backend.experiments.compiler_contract.build_downstream_report`
(`RESULTS_RUNTIME_INTEGRATION.md` is a frozen deliverable of the runtime phase and is pinned by hash; its generator is kept for provenance only.)

Real-Judge validation (this phase): `RESULTS_REAL_JUDGE_VALIDATION.md` (generated), `real_judge_scenarios.py` (hand-written SYNTHETIC profiles and expectations), `real_judge_run.py` (runs the production Judge model on them N times, no tuning between runs; `analyze`; `diagnose`), `build_real_judge_report.py`, `results/real_judge/` (every request and verdict, the analyses, the admission decisions).
Tests: `tests/test_real_judge_validation.py` (offline). Reproduce: `python -m backend.experiments.compiler_contract.real_judge_run run --runs 6 && ... analyze && ... build_real_judge_report`

Evidence Check validation (this phase): `RESULTS_EVIDENCE_CHECK_VALIDATION.md` (generated), `backend/services/evidence_check.py` (the check schema, binding, predicates, quote gate), `evidence_check_scenarios.py` (hand-written SYNTHETIC scenarios A/B/C), `evidence_check_run.py` (6 real runs each; `analyze`; `diagnose_at_least` = an exploratory diagnostic, not adopted), `build_evidence_check_report.py`, `results/evidence_check/` (raw runs, analysis, the analyst's classification).
Tests: `tests/test_evidence_check.py` (offline). Reproduce: `python -m backend.experiments.compiler_contract.evidence_check_run run --runs 6 && ... analyze && ... build_evidence_check_report`

Status: Evidence Check contract validated on synthetic candidates with the real Judge model; not 6/6 on every scenario (see the results); no CrustData, no retrieval, no deployment; waiting for architecture review.
