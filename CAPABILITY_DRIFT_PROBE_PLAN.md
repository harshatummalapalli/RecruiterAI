# Capability Drift-Probe Harness — design (queued for AFTER cutover #4)

Status: **design only, not started.** Do not build before cutover #4 deletes the
legacy brain — cutover removes the duplicate capability map
(`backend/services/crustdata_capabilities.py`) for free, and this harness should
target the one surviving map, `recruiter/providers/capability_model.py`.

## 1. The problem this solves

`recruiter/providers/capability_model.py` is the code-owned source of truth for
what CrustData can enforce / return / be trusted on. It is accurate but:

- **Statically maintained.** `VERSION = "v1-2026-10-01"`; provenance dates live
  in code comments, so staleness is prose, not data you can query or alert on.
- **Silently drifts.** CrustData changes under us (documented: `Bangalore` filter
  → 0 rows while `Bengaluru` → millions; `description` ~1.4% populated; skills-list
  filter unavailable *on our plan*; `(.)` is whole-word; NL company injection
  inert). Nothing re-checks these facts or tells us when one went stale.

This is NOT a RAG problem. We do not retrieve over CrustData docs (docs lie / omit
plan-specific gating). The harness re-establishes **ground truth by live probe**
and diffs it against the map. That is the real version of "the LLM understands
CrustData's capabilities" — a trustworthy, dated, machine-checked map, fed into
the LLM as structured context, not fuzzy retrieval.

Non-goals: not a doc ingestion pipeline; not a vector store; not a replacement for
the map (it *guards* the map). Passive run-time observation (Rec #2 in the
discussion) is a separate, later phase — sketched in §7, not built here.

## 2. Core primitive

`recruiter/providers/crustdata_adapter.py::CrustDataAdapter.count(query)` →
exact-mode match count, ~0.03 credits. Cheap enough to run the whole suite for
~1 credit. A **probe** is an assertion that a `count()` (or a tiny `search()`
sample) over a crafted `ProviderQuery` still holds the shape the map claims.

Two things a probe can catch:
- **Filter drift** — a field the map calls `verified` now returns 0 on a query
  that used to match millions (filter removed / renamed / regated on our plan).
- **Response drift** — a field the map calls `returned` now comes back blank
  (needs a 1-row `search()` sample, not `count()`).

## 3. Data-model changes to `capability_model.py`

Move provenance out of comments and into the dataclass so staleness is queryable:

```python
@dataclass(frozen=True)
class FieldCapability:
    field: str
    filter_status: str
    response_status: str
    data_confidence: str
    downstream_verifiable: bool
    note: str = ""
    verified_on: date | None = None      # NEW: when a live probe last confirmed this row
    probe: str | None = None             # NEW: name of the probe that confirms it (see §4)
```

`verified_on` makes "older than N days" a function, not a reading of comments.
`probe` links a map row to the probe that guards it; a `verified` row with no
probe is itself a finding ("unguarded claim").

## 4. The probe registry

Co-locate expected values with the map, in a new
`recruiter/providers/capability_probes.py`, so the assertion and the claim never
drift apart (same discipline that keeps Intake and Briefing reading one map):

```python
@dataclass(frozen=True)
class Probe:
    name: str
    field: str                       # the capability_model field it guards
    kind: str                        # "filter_nonzero" | "filter_discriminates" | "response_returned"
    build: Callable[[], ProviderQuery]   # the crafted query (a known-good base: e.g. India + 2y)
    expect: Callable[[ProbeResult], bool]
    # e.g. filter_nonzero: count > FLOOR; filter_discriminates: narrowed count is
    # materially below the base count; response_returned: field non-blank in a 1-row sample.
```

Seed it from the facts already proven in the map's own comments, so day one has
real coverage:

| probe | field | assertion |
|---|---|---|
| `city_bengaluru_matches` | `basic_profile.location.city` | count(Bengaluru) ≫ floor (and `Bangalore` still ≈ 0 — the alias trap) |
| `current_company_discriminates` | `...current.company_name` | count narrows ~Nx vs base |
| `min_years_discriminates` | `years_of_experience_raw` | count(min=10) < count(min=0) |
| `headline_keyword_narrows` | `basic_profile.headline` | `(.)` group narrows the pool (recall, not precision) |
| `description_returned_blank` | `...current.description` | still GATED — sample row has it blank (guards response_status) |
| `skills_list_unavailable` | `skills.professional_network_skills` | filter still rejected / inert → stays UNAVAILABLE |
| `employment_type_vocab` | `...employment_type` | each `SUPPORTED_EMPLOYMENT_TYPES` value still non-zero |
| `education_school_filterable` | `education.schools.school` | IIT-style count still in expected band (latent cap) |

## 5. The runner

New `recruiter/providers/capability_audit.py` (small; reuse, don't reinvent —
`backend/experiments/crustdata_retrieval/` already has live-probe plumbing to
borrow from):

```
run_audit(adapter, probes, map) -> AuditReport
  - parallelMap the probes (independent counts) — fast, same credits
  - each probe -> ProbeResult{name, field, observed, passed, note}
  - diff vs map:
       FAIL           = probe assertion broke           -> map claim contradicted
       STALE          = verified_on older than MAX_AGE   -> re-probe / re-confirm
       UNGUARDED      = verified row with no probe        -> coverage gap
  - sum credits_used across calls; report total (~1 cr expected)
```

`AuditReport` is JSON to `output/capability_audit/<date>.json` + a one-screen
stdout summary (green / FAIL / STALE / UNGUARDED counts, then the failing rows).
Exit non-zero if any FAIL, so CI/cron can gate on it.

## 6. Cadence, cost, surfacing

- **Cost:** ~22–30 probes × ~0.03 cr ≈ **~1 credit per full run.** Weekly ≈ 4 cr/mo.
  Negligible — this is the cheapest insurance against silently shipping a broken
  hard filter.
- **Cadence:** weekly scheduled run (use the `schedule` skill / CronCreate) +
  a manual `python -m recruiter.providers.capability_audit` before any map edit.
- **Surfacing:** FAIL → it's shipping a wrong claim; alert loud (the run's
  non-zero exit + the report). STALE → a nudge to re-confirm, not an alarm.
- **Credit safety:** every run spends real money → the scheduled job needs its own
  tiny budget guard, and the first live run is gated/approved like every other
  paid CrustData run in this repo.

## 7. Phase 2 (separate, later) — passive observation

The harness above is *active* probing. The higher-leverage follow-on (Rec #2 from
the discussion) is **passive**: every real recruiter search already emits
capability truth for free —
- `count == 0` immediately after a filter was applied,
- a `returned` field coming back blank in live results,
- out-of-geo candidates despite a country filter (the documented hybrid-leak bug).

Log these as `CapabilityObservation{field, signal, search_id, ts}` and, when
observations contradict the map over a threshold (a `verified` field that
consistently returns 0), raise the same FAIL the active probe would. This turns
paying traffic into a continuous probe. **Design separately — do not fold into
phase 1.**

## 8. Rollout steps (after cutover)

1. Confirm cutover deleted `backend/services/crustdata_capabilities.py` and nothing
   in the live path imports it. (Already verified today: `backend/providers/crustdata.py`
   does not import it — only the legacy brain did.)
2. Add `verified_on` + `probe` to `FieldCapability`; backfill dates from the
   existing comment provenance (2026-10-01 / 10-30 / 10-31).
3. Add `capability_probes.py` with the §4 seed set.
4. Add `capability_audit.py` runner (§5), offline-testable with a fake adapter.
5. Tests: fake adapter returning scripted counts → assert FAIL / STALE / UNGUARDED
   classification. No live calls in the test suite (same discipline as the rest of
   `recruiter/` — live runs are gated and explicit).
6. One gated live run to confirm the seed probes pass against real CrustData, and
   to set the real `verified_on = today`.
7. Schedule the weekly run.

## 9. What this is NOT

- Not a reason to delay cutover — it's queued *behind* it.
- Not doc retrieval / RAG (see §1).
- Not a change to routing or to how searches run today; it only *guards* the map
  the compiler already reads.
