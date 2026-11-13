# RecruiterAI — Engineering Hand-off

**Audience:** an engineer or AI assistant picking up this codebase to continue development.
**Last updated:** 2026-11-13. **Live SHA:** `dd88eda` on `main`.
**Everything described here is committed on `main` and deployed to production** unless a section says otherwise.

---

## 1. What the product is

RecruiterAI turns a role definition into a ranked, evidence-backed shortlist, then runs outreach — so a
recruiter never hand-searches LinkedIn. The flow is a five-stage journey, **Define · Discover · Decide ·
Dialogue · Deliver**:

- **Define** — the recruiter gives a JD and/or a hiring-manager brief + hard constraints; the engine reads it into a role.
- **Discover** — the engine searches the market (CrustData), reads the strongest profiles in depth (Harvest), judges them against the role.
- **Decide** — it surfaces the best few for validation; the recruiter shortlists/maybe/rejects.
- The first-five "Go" validation **auto-starts an autonomous campaign** that keeps surfacing matches within a budget (no re-validation needed).
- **Dialogue** — selected candidates flow into outreach (LinkedIn connect / InMail / email), and replies are read + answered inline.
- **Deliver** — (future) hire tracking.

Owner: **Harsha**, solo owner-operator (recruiter + product).

---

## 2. Architecture

The 7-agent engine in `recruiter/` is **live** (`RECRUITER_NEW_ENGINE=1`). The legacy
`backend/services/search_pipeline.py` is dormant (kept only as a rollback; do not extend it).

- **`recruiter/`** — the engine.
  - `agents/intake/` — reads JD + hiring-manager brief into a role understanding (requirements by tier, boundary). Dual-source reconciliation: HM-only reqs → Core, JD-only → Supporting. Includes capability proposal + per-recruiter capability memory (`output/capability_memory/<domain>.json`).
  - `agents/briefing/` — turns the understanding into provider queries.
  - `agents/calibration/` — applies recruiter answers / retier / feedback.
  - `agents/search/` — pulls the pool from CrustData, runs geo/city/company/title safety nets. `SearchResult` carries `pulled`, `kept`, `total_available` (the market universe).
  - `agents/ranking/` — the back-half brain (see §3).
  - `live.py` — assembles the live `Pipeline` from env/config. **Start here to understand wiring.**
  - `config.py` — the one place models are chosen (see §7).
  - `llm/core.py` — `complete_json(system, user, model)`; routes `claude-*` → Anthropic, else → OpenAI. Prompt caching (`cache_control` on the system block) + an optional cost ledger live here.
  - `candidates/record.py` — `CandidateRecord`, the per-candidate accumulator.

- **`backend/bridge/`** — translates engine objects ↔ the frontend `SearchResponse` contract.
  - `translate.py` — `to_search_response()` (first view), `shape_candidate()`, `reveal_into_record()` / `refine_pool_into_record()`, `pool_snapshot()` (the held pool persisted per search, under `internal_diagnostics.pool` with `judged` + `reserve`).
  - `intake_service.py` — intake + `run_search`; the **STEER** refine path (`refine`, `_enrich_reserve_matches`) and the **RUN** campaign loop (`start_campaign`, `campaign_due`, `campaign_round`). See §4.

- **`backend/api.py`** (FastAPI). Routes: `/intake/*`, `/search`, `/search/{id}`, `/search/{id}/role`, `/searches`, `/export`, `/auth/*`, `/credits`, the outreach routes (`/search/{id}/outreach/*`, `/integrations/outreach/*`), and the campaign routes (`/campaigns/tick`, `/search/{id}/campaign/start`). Auth in `backend/auth.py`; **owner_email tenant scoping** throughout (`require_owned_search`, `_session_owner`; `account_id` is never taken from the client). Search records persist as JSON in `output/searches/`.

- **`backend/providers/`** — `crustdata.py` (search), `harvest_adapter.py` (enrichment), `unipile.py` (outreach). `backend/services/outreach.py` + `sequence.py` = send guardrails + follow-up sequences.

- **`frontend/` (React + TS + Vite).** Entry `src/main.tsx` → `AuthGate` → `RecruiterWorkspaceScreen.tsx` (orchestrator). The five stages map to the step nav; outreach UI in `CandidateOutreach` + the inbox/Dialogue view. Design tokens in `src/styles/tokens.css`.

---

## 3. The ranking pipeline (core IP) — `recruiter/agents/ranking/agent.py`

For an admitted pool, `RankingAgent.rank()`:

1. **Experience floor** — drop candidates clearly below min-years (CrustData's years filter leaks). Years stays a **hard filter**.
2. **Baseline rank** — `score.py: baseline_score` (deterministic, evidence-aware).
3. **Tier-1 admission screen** — `screener_adapter.py` (Haiku). Screens the whole pool cheaply on thin CrustData data, keep/score per candidate, chunked (≤20/call), **fails open**. Admits the best `admit_n` keepers.
4. **Enrich + judge the admitted (concurrent):** Harvest enrich → career-fit (Sonnet, holistic) → Judge (Sonnet, quote-grounded, two-pass: verify quote + review). Produces the per-requirement ledger.
5. **Final score + re-rank** — `score.py: final_score`: career-fit is the primary driver, normalized quote-coverage a meaningful secondary.
6. **Show top `show=5`; hold the rest as `reserve`** (un-enriched) for reveal / campaign.

**Prod knobs:** `admit_n=10`, `show=5`, `judge_workers=2` (1 GB box). A working screener is **required** for reserve enrichment — `_admit` admits nothing on `admit_all_relevant` without one.

---

## 4. The campaign engine — STEER + RUN (live)

After the first view, the reserve sits un-enriched. Two mechanisms work it:

- **The Go (auto-start):** when the recruiter's first-five validation is positive (≥3 shortlist, or ≥2 shortlist + 1 maybe), `_maybe_start_feedback_pool_analysis` in `api.py` deep-reads the relevant reserve (`analyze_reserve`) **and opens a campaign** (`start_campaign`, idempotent). That first pass is the campaign's first round; its deep-reads charge the budget.
- **RUN (the paced loop):** `campaign_round` enriches the next budgeted batch of reserve matches toward the validated intent and surfaces them. Caps: `CAMPAIGN_PER_ROUND=15`, budget=100 deep-reads, 72h window, 2h cadence. Driven by a **server cron** (`0 */2 * * *`) that POSTs `/campaigns/tick?token=…` (token-gated by `CAMPAIGN_TICK_SECRET`). Stops on window/budget/exhaustion.
- **STEER (course-correction):** if the recruiter refines mid-campaign, `refine` → `_enrich_reserve_matches` cheap-screens the reserve against the new intent and enriches **only** the matches, leaving the rest. Returns `reserve_enriched` / `reserve_remaining`.
- **Value nudge (not auto-pause):** the `campaign` object rides on `SearchResponse` (with `reserve_available`), so the UI badges "N new matches waiting." The system never pauses on inaction — the budget cap is the only ceiling.

---

## 5. Outreach — Unipile (live)

- **Vendor fully white-labelled.** Recruiters never see "Unipile"; hosted auth is on our domain (`connect.dayzero.partners`, env `UNIPILE_HOSTED_AUTH_DOMAIN`). **Per-recruiter isolation**: connected accounts are keyed on `owner_email`; `account_id` is never accepted from the client.
- **Channels:** LinkedIn connect / InMail / email, each AI-drafted (`OUTREACH_MODEL`, Sonnet) with a tone option; the recruiter **approves every send** — nothing auto-sends.
- **Replies (Dialogue):** a per-recruiter reply webhook (`UNIPILE_WEBHOOK_SECRET`) captures reply content; the inbox (`/integrations/outreach/inbox`) shows every candidate contacted, replies on top, and supports inline reply.
- **Follow-up sequences:** one built-in flow, **approve-each-step** (`backend/services/sequence.py`).
- **Send safety:** daily caps per category via `check_limit` / `record_send` (`/integrations/outreach/limits`).

---

## 6. Cost per step (measured live 2026-11-13; owner-confirmed)

All figures are per the live harness. **The one number not ours to measure is CrustData's $/credit — the owner's plan rate.** Everything is quoted in Claude/Harvest dollars + CrustData credits.

| Step | Engine | Cost |
|---|---|---|
| Intake read + capability | Haiku + Sonnet | ~$0.003–0.005 / role |
| CrustData search (one pull of 50) | CrustData | **1.5 credits / role** — one pull, reused across the whole campaign |
| Tier-1 screener (whole pool, cheap) | Haiku | ~$0.002 / batch — near-zero vs the Sonnet passes |
| Harvest enrichment | HarvestAPI | **$0.0064 / profile** ($0.29 for 46) |
| Judge + review + career-fit | Sonnet (~5 calls/cand) | **~$0.0137 / candidate** (after caching) |
| First view (10 admitted, 5 shown) | — | ~$0.06 Harvest + intake + ~$0.14 Claude |
| Reserve deep-read on the Go | Sonnet + Harvest | the rest of the relevant pool, same per-candidate rate |
| **One fully-validated role** | — | **$0.64 Claude** (was $0.89; −28% after prompt-caching, live) **+ $0.29 Harvest + 1.5 CrustData credits** |
| **A whole RUN campaign** (Go + paced rounds to budget) | — | **≈ $0.55 Claude + $0.26 Harvest + 1.5 CrustData credits ≈ ~$0.80 + CrustData, for the entire role** |
| Outreach draft | Sonnet (1 call) | ~$0.005 / send |
| Unipile | — | ~$53 / month flat, up to 10 connected accounts (fixed, amortizes across seats) |

**Headline:** one role, brief → fully-worked shortlist, costs **under $1**. The reserve deep-read is ~75% of Claude spend; the budget cap bounds it. Prompt-caching is live. Interactive economics + pricing model: `claude.ai/artifact/6etgGufedjncubWZftQN1f`.

---

## 7. Config & feature flags (live on the server)

Models (`recruiter/config.py`): **READER/SCREEN = `claude-haiku-5-5`; CAPABILITY/JUDGE/CAREER/OUTREACH = `claude-sonnet-5-5`**.

| Flag | Effect | Server value |
|---|---|---|
| `RECRUITER_NEW_ENGINE` | use the `recruiter/` engine | `1` |
| `RECRUITER_SCREENER` | Tier-1 cheap admission screener | `1` |
| `RECRUITER_ADMIT_N` | admitted (enriched+judged) per view | `10` |
| `RECRUITER_JUDGE_WORKERS` | Judge concurrency (small box) | `2` |
| `CAMPAIGN_TICK_SECRET` | token gating `/campaigns/tick` | set (secret) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `CRUSTDATA_API_KEY` / `HARVEST_API_KEY` | vendor keys | set (secret) |
| `UNIPILE_API_KEY` / `UNIPILE_HOSTED_AUTH_DOMAIN` / `UNIPILE_WEBHOOK_SECRET` | outreach | set (secret) |
| `ALLOWED_EMAIL_DOMAIN` / `SUPER_ADMIN_EMAIL` | auth gating | set |

Career-fit is ON by code default (`RECRUITER_NO_CAREER_FIT` disables). `RECRUITER_DEV_NO_AUTH=1` skips Google login **locally only — never set on the server**. Secret *values* live only in `/etc/recruiterai.env`, never in the repo.

---

## 8. Deployment (OCI) — full runbook in `docs/deployment/production.md`

- **Host:** OCI micro VM (Oracle Linux 9.8, 1 GB RAM), IP `140.245.235.18`, site `https://hire.dayzero.partners`. SSH: `opc` user, key `~/Downloads/ssh-key-2026-09-14.key`.
- **App:** `/opt/recruiterai` (NOT a git repo — built locally, copied up). systemd `recruiterai-backend.service` runs uvicorn; nginx serves `frontend/dist` + proxies the API. `DEPLOYED_SHA` marker.
- **Deploy (backend-only):** `tar` `backend recruiter prompts requirements.txt` (exclude tests/experiments/pycache; **do not include or delete `frontend/dist`**) → `scp` → on server: backup, extract, `chown`, write `DEPLOYED_SHA`, `systemctl restart recruiterai-backend` → smoke (health 200, search 401, `/campaigns/tick` 401 without token, site 200).
- **Frontend change:** also `cd frontend && npm run build` locally, include `frontend/dist`, and on the server `rm -rf frontend/dist` before extract.
- **Deploy commands must start with `ssh`/`scp`** (inline the key, no leading `cd`/`VAR=`) to go through without a permission prompt.
- **New API route?** add it to the nginx path regex or it returns the SPA HTML. (`/campaigns/tick` is called internally on 127.0.0.1, so it needs no nginx entry.)
- **Gotcha:** server `/etc/recruiterai.env` ≠ local `.env` — a key present locally can be missing on the server; always verify.

---

## 9. Testing & running

- **Backend:** `PYTHONPATH=. python -m pytest tests/ recruiter/tests/` — full suite green (**1122 passed, 4 skipped** at `dd88eda`). `recruiter/tests/` are fast + offline (fake providers). Campaign/outreach/STEER suites: `test_run_campaign.py`, `test_steer_refine.py`, `test_outreach_*`, `test_sequence.py`.
- **Frontend:** `cd frontend && npx tsc --noEmit` and `npx vitest run`.
- **Run locally:** backend — `RECRUITER_DEV_NO_AUTH=1 RECRUITER_NEW_ENGINE=1 RECRUITER_SCREENER=1 RECRUITER_ADMIT_N=10 PYTHONPATH=. uvicorn backend.api:app --port 8000`; frontend — `cd frontend && npm run dev`.
- **Spending:** offline tests never spend. Any script calling `build_live_pipeline().run*` spends real CrustData credits + Harvest + Claude — **get owner approval first**. Measurement harnesses used this cycle lived in the session scratchpad (not committed).

---

## 10. What's left to build

- **CrustData $/credit** — owner to supply their plan rate so the exact all-in role cost + pricing-tier margins can be finalized (model artifact is ready, waiting on this one number).
- **Pricing decision** — four packaging structures are modelled (unified credits / seat + fair-use / outcome per-placement / hybrid seat + credit-grant). Owner to choose.
- **Security + GDPR/DPDP written audit** — owner requested a written review (no rogue agent/injection; data-protection posture). Not yet written.
- **Cost lever not yet taken** — tier the Judge *review* pass to Haiku (the last meaningful Claude saving).
- **Deliver stage** — hire tracking, to close the loop (and enable outcome-based pricing).
- **Legacy cleanup** — delete `backend/services/search_pipeline.py` and related once the new engine has soaked.
- **Minor hardening** — a non-JSON model response was seen to trip the fail-open path harmlessly in a campaign measurement; tighten `_loads` robustness.

---

## 11. Known issues / watch items

- **Stale results:** judgments persist on the search record; re-run a role to recompute after an engine change.
- **Model lifecycle:** any OpenAI path still uses `gpt-4o-mini`, which retires 2027-01-14 → migrate to `gpt-6-luna` before then (needs a validation). The engine itself is on Claude.
- **1 GB box:** documented swap-storm/lock-up failure mode; `earlyoom` installed, swappiness lowered, keep `RECRUITER_JUDGE_WORKERS=2`. Recovery = OCI console force-reboot (see runbook).
- **Judge variance:** the LLM Judge can vary ±1 on "N of M" run-to-run; the review pass + failure-floor mitigate.

---

## 12. Owner working preferences

- Keep code changes **small and powerful**, not big blocks.
- **Offline / no-credit first**; explicit per-run approval before spending CrustData credits.
- Validate changes live before trusting them; **honest reporting** of what actually happened.
- **Deploy without prompting** (the owner has standing approval); deploy commands start with `ssh`/`scp`.
- **Never expose a vendor** (Unipile etc.) to recruiters — everything white-label on our domain.
- Maintain **per-recruiter isolation** everywhere (`owner_email` scoping; `account_id` never from the client).
