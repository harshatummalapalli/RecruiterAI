# RecruiterAI — clean architecture (`recruiter/`)

This package is the re-architected product. It is built **beside** the legacy
`backend/` and takes over from it one agent at a time; `backend/` keeps running
until cutover, after which it is deleted.

## The one rule that fixes "new role, new issue"

Every role is described by **one canonical, immutable object: `RoleModel`**
(see `recruiter/role_model/`). It is built once, by the Intake agent, and then
only **read** — never re-derived, re-interpreted, or mutated — by every agent
downstream. Candidates accumulate on a single `CandidateRecord`. Agents talk to
each other *only* through these two objects. No agent owns a private model of
the role. That is the "no leakage" contract.

Why: the legacy system had ~7 role representations and ~6 understanding engines
joined by lossy conversions, so each new role hit a different seam. One source
of truth removes the seam class entirely.

## The agents (one spine, one direction)

```
raw hiring notes + boundary
   │
   ▼
1. Intake      → builds the RoleModel (understands context, not keywords)
   │ RoleModel
   ▼
2. Briefing    → RoleModel → provider plan; owns "what CrustData can/can't do"
   │ ProviderPlan (+ disclosed limitations)
   ▼
3. Calibration → shows strategy + consequences to the human, AUTHORISES the run
   │ (human go)
   ▼
4. Search      → pulls records, routes to enrichment + the Judge
   │ CandidateRecord[]
   ▼
5. Ranking     → ranks on verified evidence, explains fit (not keywords)
   │ top findings
   ▼
6. Outreach    (later)
7. Interview   (later)
```

## Seniority & level (design decision)

**Years of experience is the one seniority gate.** It is objective, portable
across companies, and the only seniority signal CrustData can hard-filter on. A
title *label* ("Senior" vs "Lead") is company-relative noise and never excludes a
candidate. If the hiring notes state no minimum, **Intake asks** the recruiter.

The role's *level* (`ic | architect | manager | director+`) is derived once and
kept only for two non-gating jobs:
- **Default title exclusions.** Founder / CxO / Manager / VP / AVP / Head of (and
  the exec family) are excluded by default — *suppressed* when the role itself is
  architect / manager / director+ (you'd be excluding who you're hiring).
- **A ranking flag.** Ranking surfaces "reads above/below the role's level" as a
  note for the recruiter — never an exclusion.

See `role_model/seniority.py` (years) and `role_model/levels.py` (level, flag,
exclusions).

## Conventions (non-negotiable)

- **Small files.** Target **< 250 lines** per module, **hard ceiling ~400**.
  One responsibility per file. The legacy 1,196-line evidence builder is the
  anti-pattern we are correcting — split by concern, not by convenience.
- **Pure where possible.** Logic that can be a pure function of its inputs
  (scoring, derivation, assertions) takes no I/O and is unit-tested directly.
- **Immutable spine.** `RoleModel` is frozen. A stage that needs a change makes
  a new model with provenance, it never mutates in place.
- **Honesty, kept.** Anything that cannot be enforced (e.g. work-mode on
  CrustData person-search) is a recorded *limitation* on the model, shown to the
  recruiter — never silently dropped.
- **Every change is gated by the golden-set** (`recruiter/evals/`). New-role
  regressions are caught there, not in production.

## Keepers migrated from `backend/` (good code, reused)

- `requirement_judge` — quote-verified, reviewed LLM matcher. The scorer.
- `providers/crustdata` — live-probed, honest provider adapter.
- `services/crustdata_capabilities` — the enforce/judge/disclose capability
  model. Becomes the core of the **Briefing** agent (it was wired only to the
  inert shadow compiler before).
- Harvest enrichment; the diagnostics/persistence discipline.

## Retired at cutover (do not port)

- The legacy `/parse-jd` pipeline + the frontend `src/intelligence/` brain.
- Dead `SearchIntent` fields (`ranking`, `ai_focus`, `preferred_technologies`).
- `RetrievalConcepts` (storage-only). The shadow-mode `search_compiler` is not
  deleted — its routing logic is promoted into Briefing.

## Build order (dependency-safe)

0. **Golden-set net** (`evals/`) — baseline + assertions. *First.*
1. **`RoleModel` spine** — this package's keystone. *Done alongside 0.*
2. Intake agent → emits a valid `RoleModel` for the golden roles.
3. Briefing agent → promote the capability router; fix multi-city + NL query.
4. Ranking agent → one engine, evidence-aware admission + failure floor.
5. Delete the legacy duplicates.
6. Calibration agent → explicit pre-search authorise gate.
7. Outreach + Interview.
