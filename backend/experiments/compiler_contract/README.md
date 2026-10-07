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

Status: runtime integration verified offline; the Judge and admission are not wired (LEGACY DOWNSTREAM CONSUMER); waiting for architecture review.
