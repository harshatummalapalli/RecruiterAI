# RecruiterAI — Engineering Hand-off

**Audience:** an engineer or AI assistant picking up this codebase to continue development.
**Last updated:** 2026-11-06. **Live SHA:** `3d4abea` on `main`.
**Everything described here is committed and deployed** unless a section says otherwise.

---

## 1. What the product is, and where it's going

RecruiterAI turns a job description into a ranked, evidence-backed shortlist of candidates, so a
recruiter never has to hand-search LinkedIn. The vision (confirmed with the owner, Harsha, a solo
operator) is a **continuous, budgeted sourcing machine**:

- The recruiter defines a role + hard constraints.
- The engine searches the market (CrustData), reads the strongest profiles in depth (Harvest
  enrichment), judges them against the role, and surfaces the best few for validation.
- The recruiter validates/gives feedback; the engine re-evaluates its held pool and, within budget,
  pulls more over a **time-boxed campaign (3/5/7 days)** — not a literal always-on daemon.
- Selected candidates then flow into an **Outreach** stage (LinkedIn invite / InMail / email).

**North star:** recruiters get the same-or-better results than manual LinkedIn sourcing, from our product.

---

## 2. Architecture overview

Two engines coexist; the **new engine is live** (`RECRUITER_NEW_ENGINE=1`).

- **New engine — `recruiter/`** (a clean 7-agent pipeline). This is what runs in production.
  - `recruiter/agents/intake/` — reads the JD into a role understanding (title, requirements by tier,
    boundary). Model: Haiku. Includes capability proposal + per-recruiter capability memory
    (`output/capability_memory/<domain>.json`).
  - `recruiter/agents/briefing/` — turns the understanding into provider queries.
  - `recruiter/agents/calibration/` — applies recruiter answers/retier/feedback (`apply.py`).
  - `recruiter/agents/search/` — pulls the pool from CrustData, runs geo/city/company/title safety
    nets. `SearchResult` (model.py) carries `pulled`, `kept`, `total_available` (the market universe).
  - `recruiter/agents/ranking/` — the **back-half brain** (see §3).
  - `recruiter/live.py` — assembles the live `Pipeline` from env/config. **Start here to understand wiring.**
  - `recruiter/config.py` — the single place models are chosen.
  - `recruiter/llm/core.py` — `complete_json(system, user, model)`; routes `claude-*` → Anthropic,
    else → OpenAI. The one LLM seam.
  - `recruiter/candidates/record.py` — `CandidateRecord`, the per-candidate accumulator passed between agents.

- **Legacy engine — `backend/services/search_pipeline.py`** — still present, dormant. Kept until the
  new engine has soaked. Do not extend it.

- **The bridge — `backend/bridge/`** — translates engine objects ↔ the frontend's `SearchResponse`
  contract. **`translate.py` is critical**: `to_search_response()` (first view), `shape_candidate()`
  (per-candidate shaping), `reveal_into_record()` / `refine_pool_into_record()` (the free-reveal and
  refine paths), `pool_snapshot()` (the held pool persisted per search). `intake_service.py` runs intake
  + `run_search`.

- **API — `backend/api.py`** (FastAPI). Routes: `/intake/*`, `/search`, `/search/{id}`,
  `/search/{id}/role` (pause/resume/close/reopen), `/searches`, `/export`, `/auth/*`, `/credits`.
  Auth in `backend/auth.py`. Role lifecycle in `backend/services/role_runtime.py`. Search records
  persist as JSON in `output/searches/` (candidates/diagnostics live under `record["response"]`).

- **Frontend — `frontend/` (React + TS + Vite).** Entry: `src/main.tsx` → `AuthGate` →
  `RecruiterWorkspaceScreen.tsx` (the orchestrator — state, polling, step routing). Key screens:
  `HomeScreen`, `LivingBrief` (the Discover/brief), `CandidateReviewScreen` (Decide), `UnderstandScreen`
  (the read animation), `SettingsScreen`. Shell: `GlobalShell` (the single rail). Candidate UI:
  `CandidateWorkspace` (cards) + `CandidateRecord` (the right-pane profile). Models in `src/models/`
  (`discovery.ts` maps the API evidence → the UI candidate; `roleLifecycle.ts` Active/Completed;
  `livingBrief.ts` the brief view-model). Design tokens: `src/styles/tokens.css`.

---

## 3. The ranking pipeline (the core IP) — `recruiter/agents/ranking/agent.py`

For an admitted pool, `RankingAgent.rank()` does:

1. **Experience floor** — drop candidates whose dated roles are clearly below min-years
   (CrustData's years filter leaks).
2. **Baseline rank** — `score.py: baseline_score` (deterministic, evidence-aware; not a coin-flip).
3. **Tier-1 admission screen (cheap, CrustData-only)** — `screener_adapter.py: ScreenerAdapter`
   (Haiku, `SCREEN_MODEL`). Screens the **whole pool up to `screen_cap=80`** ("read all 50 cheaply"),
   returns keep/score per candidate on thin data (title, headline, past titles, skills, years, geo),
   chunked (≤20/call) and **fails open**. Admits the best `admit_n` keepers. Opt-in via
   `RECRUITER_SCREENER`. If off → baseline top-N (old behaviour).
4. **Enrich + judge the admitted (concurrent)**:
   - **Enrich** — `providers/harvest_adapter.py` (Harvest LinkedIn profile → `record.raw["_harvest_evidence"]`).
   - **Career-fit (Tier-2, holistic)** — `career_fit.py: CareerFitAssessor` (Sonnet, `CAREER_MODEL`).
     Reads the **enriched** profile and rates overall career fit **without needing a quote per
     requirement** → `{score 0..1, rationale}` on `record.raw["_career_fit"]`. On by default
     (`RECRUITER_NO_CAREER_FIT` disables). Failure swallowed.
   - **Judge (quote-grounded)** — `backend/services/requirement_judge.py` via `judge_adapter.py`.
     Holistic reading that credits job TITLES, judges a requirement on its **primary subject**
     (compound qualifiers are depth, not gates), two-pass (verify quote exists + review it means what
     was claimed). Produces the per-requirement ledger ("N of M core evidenced").
5. **Final score + re-rank** — `score.py: final_score`. When a career-fit score is present:
   `base + CAREER_WEIGHT(10)*career_fit + COVERAGE_WEIGHT(6)*coverage_fraction`. **Career-fit is the
   primary driver; quote-coverage (normalized) is a meaningful secondary.** Graceful fallback to
   `base + coverage` when no career score (tests / assessor off / failure).
6. **Show top `show=5`; hold the rest as `reserve`** (baseline-ranked, un-judged) for free reveal.

**Default knobs** (`recruiter/live.py`): `admit_n = RECRUITER_ADMIT_N or 8` (prod = **10**),
`show=5`, `screen_cap=80`, `judge_workers = RECRUITER_JUDGE_WORKERS or 8` (prod = **2**, small box).

**Key seam fixed this cycle:** `shape_candidate()` must pass `harvest_evidence` to
`build_candidate_evidence()` — otherwise the *displayed* record is CrustData-only and looks thin even
though the Judge read the full profile. It now pops `_harvest_evidence` off raw (non-serializable) and
passes it.

---

## 4. What was built this cycle (all committed + deployed)

| Area | What | Where |
|---|---|---|
| Judge | Holistic, title-crediting, primary-subject judging; two-pass | `backend/services/requirement_judge.py` |
| Enrichment display | Pass Harvest to the evidence builder so the card shows the rich LinkedIn profile | `backend/bridge/translate.py` (`shape_candidate`) |
| Tier-1 screener | Cheap Haiku batched admission gate on CrustData-only data, fails open | `recruiter/agents/ranking/screener_adapter.py` |
| Career-fit (Tier-2) | Holistic career score, primary ranking driver | `recruiter/agents/ranking/career_fit.py`, `score.py` |
| Screen-all | Screen the whole pool (≤80), not a shortlist | `agent.py` (`screen_cap`) |
| Total-market count | `SearchResult.total_available` from CrustData `total_count` → "Found N matching profiles" | `recruiter/agents/search/{model,agent}.py`, `translate.py`, `CandidateReviewScreen.tsx` |
| Record richness | Projects + Certifications sections; connections + profile-age chips (weak anti-spam cues, never ranked); folded "Candidate Snapshot" into "Why this candidate" | `candidate_evidence*.py`, `types.ts`, `discovery.ts`, `CandidateRecord.tsx` |
| Archive lifecycle | Server-side Close/Reopen + 14-day idle auto-archive; `archived` flag on `/searches` | `role_runtime.py`, `api.py`, frontend `roleLifecycle.ts` |
| Dev auth bypass | `RECRUITER_DEV_NO_AUTH` opens local gates (never on server) | `backend/auth.py` |
| UI revamp | See §6 | frontend |

---

## 5. Experiments & validations (paid, live)

All against CrustData/Harvest/LLMs; CrustData credits noted (Harvest/LLM billed separately, small).

1. **Holistic Judge** (~3 cr) — IAM role; strong fits went from 0–1/7 to **3–5/7**, every "met"
   grounded in a real quote/title. Confirmed the Judge rework.
2. **Phase A screener A/B** (~3 cr, 2 runs) — AI Platform Engineer role. The cheap screener scores
   0.30–0.95, high-recall (keeps plausible candidates, drops clear misses — a Data Analyst scored
   0.04), fails open. admit_n=10 + screener surfaced stronger matches (Ahsan J. 4/7, Sazzad 4/7).
   Found + fixed a truncation bug (30-wide batch at 660 tokens → chunk + bigger budget).
3. **Career-fit A/B** (~1.5 cr, single pull, re-ranked two ways) — same 10 candidates:
   - Old (coverage-only): Parth(4 met) #1, Deepak(1) #2, …, Randima #4, Adrian #5.
   - New (career-fit primary): **Randima(0.82) #1**, **Camila(0.72) #2 — newly surfaced**,
     Deepak #3, …, Parth #5; **Adrian(0.30) dropped out**. Strongest careers rose, weak-career/
     decent-coverage dropped, coverage still moved things. Validated the blend.
4. **Harvest resume probe** (~$0.006) — the `/linkedin/profile` endpoint returns `featured`,
   `websites`, `projects`, `certifications`, `connectionsCount`, `registeredAt`, `followerCount`,
   `recommendations`, `honorsAndAwards`, `courses`, `publications`. **No dedicated resume field**;
   a resume only appears if pinned to Featured (rare) → resume-from-Featured was **skipped**.

**"Deepak 0/8" mystery, resolved:** his earlier 0/8 was stale results from *before* the holistic
Judge deploy, plus a genuinely data-platform (not agentic) described career. On a fresh run he's 2/7,
honestly. Judgments persist on the search record — they are not recomputed until the role is re-run.

---

## 6. UI/UX journey & product decisions

- **Palette/type:** chose **Midnight & Coral** (navy `#16203a` primary, coral `#ff6a4d` signal,
  near-white bg) + **Plus Jakarta Sans**. Tokens in `src/styles/tokens.css` (light + dark).
- **Stage names:** **Define · Discover · Decide** (the `StepPlayer` top nav). Chosen over the old
  "Understanding/Candidates".
- **One rail (big decision):** collapsed the two sidebars (a global Home/Settings rail + a second
  all-roles rail that appeared on New Search) into a **single `GlobalShell` rail** (brand, Home,
  Settings, New search, a short **Recent** list of ≤4 active roles, account). New Search no longer
  swaps sidebars.
- **Home:** active work only, grouped **Needs-review → Searching → Paused → Drafts**, with skeletons;
  a **Completed** tab (Close or 14-day idle); View / Reopen actions.
- **Discover (LivingBrief) decluttered:** per-requirement **tier mover** (Core/Supporting/
  Differentiator) restored; exclusions rendered as **chips** not a long list; **"Search boundary" +
  "This is what I'll search for" folded into one** section.
- **Candidate record:** "Candidate Snapshot" **folded into "Why this candidate"** (as "In their
  words"); evidence ledger; Experience; **Projects**; **Certifications**; Skills; Education;
  header chips for LinkedIn / Open-to-work / **connections** / **profile age**. **Recommendations
  deliberately omitted** (space). **Cards left as-is** (owner chose not to change the chips).
- **Results framing:** "Found N matching profiles — showing the strongest few, read in depth"
  (N = CrustData filter universe). Contiguous evidence dots (●●●○○).
- **Scoring philosophy (owner's call):** rank by **overall career fit** (weighted higher) because
  not everyone writes LinkedIn like a résumé; keep the quote ledger for honesty and as a secondary
  ranking factor. Both must move the ranking.
- **Campaign model:** time-boxed **3/5/7-day** windows with budget pacing, **not** a literal
  always-on daemon. Per-role **budget cap AND target** (whichever hits first), recruiter's choice.

---

## 7. Deployment (OCI) — see `docs/deployment/production.md` for the verified runbook

- **Host:** OCI micro VM (Oracle Linux 9.8, 1 GB RAM), IP `140.245.235.18`, site
  `https://hire.dayzero.partners`. SSH: `opc` user, key `~/Downloads/ssh-key-2026-09-14.key`.
- **App:** `/opt/recruiterai` (NOT a git repo — built locally, copied up). systemd
  `recruiterai-backend.service` runs uvicorn; nginx serves `frontend/dist` + proxies `/…` to :8000.
  Secrets/flags in `/etc/recruiterai.env`. `DEPLOYED_SHA` marker.
- **Deploy sequence:** `npm run build` (local) → `tar czf … backend recruiter prompts frontend/dist
  requirements.txt` (exclude `recruiter/tests`, `recruiter/evals`, `backend/experiments`, pycache) →
  `scp` → on server: backup, replace `frontend/dist`, extract, `chown`, `pip install -r
  requirements.txt`, write `DEPLOYED_SHA`, `systemctl restart recruiterai-backend` → smoke test
  (health 200, search 401, site 200, bundle hash matches).
- **Env flags on the server** (`/etc/recruiterai.env`): `RECRUITER_NEW_ENGINE=1`,
  `RECRUITER_SCREENER=1`, `RECRUITER_ADMIT_N=10`, `RECRUITER_JUDGE_WORKERS=2`, `ANTHROPIC_API_KEY`
  (+ OpenAI/CrustData/Harvest keys), `ALLOWED_EMAIL_DOMAIN=gmail.com`, `SUPER_ADMIN_EMAIL`.
  Career-fit is ON by code default. `RECRUITER_DEV_NO_AUTH` is **never** set on the server.
- **Auth:** Google OAuth, gated to `ALLOWED_EMAIL_DOMAIN`; admin surfaces (credits) gated to
  `SUPER_ADMIN_EMAIL`. Verify live is gated: `/auth/me` with no cookie → 401.

**Deploy gotchas (learned):**
- Server `/etc/recruiterai.env` ≠ local `.env` — a key present locally can be missing on the server
  (bit us with `ANTHROPIC_API_KEY`). Always verify on the server.
- A **new API route must be added to the nginx path regex** or it returns the SPA HTML.
- The Claude Code "Production Deploy" permission classifier sometimes blocks `scp`/`ssh` — the owner
  must approve.
- **Local dev:** stale `uvicorn`/`vite` processes can hold `:8000`/`:5173` across session restarts —
  kill via `Get-CimInstance Win32_Process` matching `uvicorn backend.api` / `vite`. Vite binds IPv6
  (`localhost`/`::1`), so `curl 127.0.0.1:5173` fails while the browser works.

---

## 8. Config & feature flags (quick reference)

| Flag / setting | Effect | Default |
|---|---|---|
| `RECRUITER_NEW_ENGINE=1` | Use the `recruiter/` engine (else legacy) | on (server) |
| `RECRUITER_SCREENER=1` | Tier-1 cheap admission screener | on (server) |
| `RECRUITER_ADMIT_N` | How many admitted (enriched+judged) per view | 8 code / 10 server |
| `RECRUITER_NO_CAREER_FIT` | Disable Tier-2 career-fit (for A/B) | unset = career-fit ON |
| `RECRUITER_JUDGE_WORKERS` | Judge concurrency | 8 code / 2 server |
| `RECRUITER_DEV_NO_AUTH=1` | Skip Google login locally (NEVER on server) | off |
| Models (`recruiter/config.py`) | READER/SCREEN = Haiku; CAPABILITY/JUDGE/CAREER = Sonnet | — |

Cost note: the screener (Haiku ×~50) + career-fit (Sonnet ×admit_n) + Harvest (×admit_n) raise
per-search cost vs the old top-8. All tunable via the flags above.

---

## 9. Testing & running

- **Backend:** `PYTHONPATH=. .venv/Scripts/python.exe -m pytest …`. The `recruiter/tests/` suites are
  fast and offline (fake providers). Known: a pre-existing failing test
  `tests/test_requirement_semantics.py::test_mixed_requirements…` is unrelated to engine changes.
- **Frontend:** `npx tsc --noEmit` (keep clean) and `npx vitest run`. **Baseline = 15 pre-existing
  failures** (livingBrief/LivingBrief/MultiSearch/RecruiterWorkspaceScreen/RoleOrder) — don't let the
  count rise above that; those predate this work.
- **Run locally:** backend — `RECRUITER_DEV_NO_AUTH=1 RECRUITER_NEW_ENGINE=1 RECRUITER_SCREENER=1
  RECRUITER_ADMIT_N=10 PYTHONPATH=. uvicorn backend.api:app --port 8000`; frontend — `cd frontend &&
  npm run dev` (http://localhost:5173). `RECRUITER_DEV_NO_AUTH` means no login locally.
- **Validation scripts:** offline tests never spend; any script calling `build_live_pipeline().run_all`
  spends real CrustData credits — get owner approval first. Examples lived in the scratchpad.

---

## 10. What's built but NOT committed

**Nothing.** As of `3d4abea` the entire working tree described here is committed on `main` and
deployed. (Untracked throwaway files that are intentionally NOT committed: validation-org capability
memories like `output/capability_memory/judge-val-*.json`.)

---

## 11. What's left to build (roadmap)

- **Phase B — the time-boxed campaign loop (next):** per-role duration (3/5/7 days), **budget cap +
  target** (whichever first), paced cycles that: pull → screen → admit → enrich → judge → surface →
  capture feedback → **re-evaluate the held reserve against what the recruiter validated** → next pull
  within budget. Needs: a lightweight scheduler (the 1 GB box can't run heavy workers — one scheduler
  that wakes, runs one role's budgeted cycle, sleeps), durable campaign state on the search record
  (cursor, spend, target, stop conditions), and an overnight/next-day digest. Most plumbing exists
  (reserve/reveal, feedback capture, calibration, pause/resume, daily background cycle in
  `role_runtime.py`).
- **Phase C — Outreach:** from Shortlisted → contact resolution (emails via CrustData/Harvest +
  GitHub) → channel (LinkedIn invite / InMail / email) → personalized multi-touch sequences (grounded
  in the candidate's evidence) → state machine + send guardrails (daily limits, draft-vs-auto-send
  approval). Design the candidate state model so "Shortlisted → Outreach" is clean.
- **Anti-spam mechanism:** connections count + profile-created date are *shown* but not yet *used* —
  turn them into an actual authenticity filter/flag.
- **Title normalization/dedup (backend):** the frontend normalizes a single title; distinct re-pasted
  JDs can still create duplicate roles — needs a server-side dedup guard.
- **Legacy cleanup:** delete `backend/services/search_pipeline.py` and related once the new engine has
  soaked.
- **Candidate-card evidence:** the owner declined changing the card chips for now; a one-line career-fit
  rationale on the card (already computed, not yet surfaced to the frontend) remains an option.
- **Model migration watch:** engine is on Claude (Haiku/Sonnet). If any OpenAI model remains in a path,
  note `gpt-4o-mini` end-of-life (see owner's memory) and migrate with a validation.

---

## 12. Known issues / watch items

- **Stale results:** judgments persist on the search record; re-run a role to recompute after an
  engine change. Old searches keep their old verdicts.
- **Broad-role universe count:** `total_available` is the hard-filter match count — large for broad
  roles (hundreds of thousands). Honest, but may need friendlier wording per role scope.
- **Career-fit/screener cost:** per-search cost is higher now (see §8); watch spend and tune
  `RECRUITER_ADMIT_N`.
- **1 GB box:** documented swap-storm/lock-up failure mode; `earlyoom` installed, swappiness lowered.
  Keep `RECRUITER_JUDGE_WORKERS=2`. Recovery = OCI console force-reboot (see runbook).
- **Judge variance:** the LLM Judge can give slightly different verdicts run-to-run; the review pass
  and failure-floor mitigate, but expect ±1 on "N of M".

---

## 13. Owner context

Harsha — solo owner-operator, recruiter + product. Preferences that recur:
- Keep code changes **small and powerful**, not big blocks.
- **Offline/no-credit first**; explicit per-run approval before spending CrustData credits.
- Validate changes live before trusting them; honest reporting of what actually happened.
- Test on the local site, then commit and deploy (often batched).
