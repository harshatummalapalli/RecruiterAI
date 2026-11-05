# Product build plan — locked UI direction → shippable work

**Status:** awaiting go-ahead. No code until signed off. Credits spent only where
explicitly flagged 💳 and always behind a confirm.

This sequences the **locked mockup** direction
(`scratchpad/recruiterai-mockup.html`) into real work, mapped to the files each
change touches. The engine-side loop mechanics are already designed in
[SOURCING_LOOP_PLAN.md](SOURCING_LOOP_PLAN.md) (§1–7) — this plan references those
sections rather than restating them, and adds everything the loop plan doesn't
cover: the intake composer, the "understand" step, relevance grouping, the
evidence-summary cards, and the structured refine panel.

## Design invariants (carry into every phase)

1. **Hard filters stay hard.** Years, location, work mode, company/title
   exclusions are *boundary inputs*, never inferred from free text. The engine
   already enforces this (`_BLOCKING_ISSUES = {"min_years"}`,
   boundary-seeded answers). The UI must mirror it: the fence is structured
   controls only.
2. **No vendor names** in any user-facing surface (CrustData / Harvest / etc.).
3. **No internal mechanics exposed** — never "fetching 50, judging 5". Those are
   our decisions. The recruiter sees qualitative "what I did" framing; the exact
   funnel lives in an **admin-only diagnostics view**.
4. **Relevance at the group level, not per card** — groups are named
   ("Strongest relevance" / "High relevance" / "Newly surfaced"); within a card
   the signal is dots + "N of M core evidenced", never a second relevance word.
5. **Pool-first, then outside.** Every refine re-checks the held pool first
   (free, instant). Reaching wider is a separate, credit-previewed step.

---

## Phase 1 — Pool persistence + judge-8 hedge *(foundation; everything depends on it)*

**Goal:** stop discarding the 20 judged candidates we paid for, and hold the rest
of the pool so reveal / rerank / refine are free.

**What's true today:** `RankingAgent.rank` judges all `admit_n` (25) but
`to_search_response` maps only `ranking.shown` (5) into the record — the other
20 judged candidates (with `judgments`, `fit`, `final_score`) live on
`ranking.ranked` and are then dropped; candidates 26–50 are discarded before
judging.

**Backend:**
- `recruiter/agents/ranking/agent.py` — switch to the demand-driven shape from
  SOURCING_LOOP_PLAN §2: baseline-score the full pool (free), judge the top 8,
  show the best 5 by final score (judge-8 / show-5 hedge, §Hedge). Keep the
  failure-floor and concurrent judge loop as-is.
- `recruiter/agents/ranking/model.py` — `RankingResult` grows a `reserve`:
  the baseline-ranked, not-yet-judged remainder, plus the judged-not-shown rows.
- `backend/bridge/translate.py` — persist the **whole pool** with per-candidate
  state (`baseline_rank`, `judged`, `judgments`, `shown`, `decision`), not just
  the shown 5. `to_search_response` keeps emitting only the shown 5 to the
  frontend; the reserve is persisted on the record for later phases.
- `backend/bridge/session_store.py` — the search record already round-trips JSON;
  extend the saved shape to hold the pool + reserve.

**Ships independently?** Yes — invisible to the UI; verified by the record on disk
holding the full pool. **Credits:** ↓ (judge 8 not 25 on first view).
**Tests:** `recruiter/tests` — pool persisted, reserve ordered, judge-8/show-5.

---

## Phase 2 — Evidence-summary cards *(DONE 2026-11-04; depends on P1)*

> **Relevance grouping was dropped.** The shipped review screen is deliberately a
> flat, non-ranked list (tests forbid grouping and the word "Relevance"; the list
> carries "nothing here says one person is better than another"). Rather than
> overturn that honesty stance, Phase 2 shipped the grounded summary + collapsed
> ledger only. Delivered: backend `evidence_summary` (grounded paragraph replacing
> the line-by-line `rc.fit`) → `why_this_candidate`; record pane gained an
> "N of M core evidenced" line and the exhaustive per-requirement ledger now sits
> behind a "See the full requirement check" disclosure (summary by default). The
> card already carried dots + proof chips. Original scope below for reference.


**Goal:** the review page from the mockup — candidates grouped by relevance,
each card an evidence *summary* (not a line-by-line match), dots + "N of M core
evidenced", grounded quotes, expandable per-requirement ledger.

**Backend:**
- `backend/bridge/translate.py` — the Judge judgments are already stashed into
  `raw["__requirement_judgments"]` for the evidence builder (dots + ledger). Add:
  (a) a **relevance group** per shown candidate (Strongest / High / Newly
  surfaced) derived from final score bands, (b) an **evidence summary** — one
  short grounded paragraph from verified evidence, replacing the line-by-line
  tier dump, (c) the "N of M core evidenced" count from the judgments.
- Numeric score stays internal-only (already enforced,
  `frontend/src/models/discovery.ts`) — verify no leak once dots return.

**Frontend:**
- Results view: render the three named groups; card = name/title/location, dots,
  "N of M core evidenced", 2–3 grounded quotes, expandable ledger
  (met / not evidenced), Shortlist / Maybe / Reject.
- Remove the Core/Supporting/Differentiator wall — tiers become the ledger detail,
  not the headline.

**Ships independently?** Needs P1's richer persisted evidence. **Credits:** none.

---

## Phase 3 — Reject-reason capture + pool-first reveal *(DONE 2026-11-04; depends on P1)*

> **Delivered.** (3a) New-engine responses set `feedback_capture: true`; the review
> screen now shows the existing structured reason chips on Maybe/Reject (fixes "it
> didn't ask me the reason") — legacy/role searches unchanged. Backend capture
> (`apply_candidate_update`) already validated reasons. (3b) Pool-first reveal:
> `POST /search/{id}/reveal` brings the next already-read (judged-but-not-shown)
> profile forward from the Phase-1 pool — no new search, no credits — reusing a new
> shared `translate.shape_candidate`. A reject with `reserve_available > 0` triggers
> it one-in-one-out. `reserve_available = admit_n − shown` (≈3 at judge-8/show-5).
>
> **Not built (deferred to Phase 4 refine = "reach wider, cost shown first"):**
> promoting an *un-judged* reserve member (needs an on-demand Judge call = credits).
> **Polish deferred:** the "brought forward from reserve — no new search needed"
> microcopy (the card appears but isn't labelled as a reveal); feedback-reason echo
> on reload for non-role searches (events are persisted, just not echoed into
> `response.feedback`). No nginx change needed — `/search/{id}/reveal` matches the
> existing `search` proxy token. Original scope below.


**Goal:** rejecting a candidate asks *why* (structured chips), records it, reranks
the held pool with that signal, and reveals the next from reserve — no new search.

**What's true today:** the `feedback_events` schema exists on the record but
`feedback_reason` comes back `null` (reject writes nothing).

**Backend:**
- A feedback endpoint (extend the existing `/search` surface in
  `backend/api.py`) that records `decision` + structured `feedback_reason`
  (missing-skill / wrong-seniority / wrong-domain / other) + optional note into
  the persisted record.
- Pool-first rerank (SOURCING_LOOP_PLAN §5): apply the reject signal to the
  **held pool**, promote the next-best reserve member (judge it on demand if
  never judged — incremental, cheap), stream it in. Only genuine pool exhaustion
  offers a new search (Phase 4).

**Frontend:** Reject → reason chips → on submit, reveal next from reserve with the
"brought forward from reserve — no new search needed" framing (no counts).

**Ships independently?** Yes, on top of P1. **Credits:** on-demand judge of a
promoted reserve member only (far cheaper than a fresh pull); never a new search
without confirm.

---

## Phase 4 — Structured refine panel *(4a backend + 4b UI DONE 2026-11-05; reach-wider 4c remaining)*

> **4a — pool-first refine engine: DONE & tested (offline).** `recruiter/agents/
> calibration/refine.py refine_model(model, deltas)` turns typed deltas (years,
> work mode, location cascade, company include/exclude, title excludes, industries,
> requirement tense, re-tier, add-must-have-from-suggestions) into a NEW immutable
> RoleModel — no free text. `translate.refine_pool_into_record` then RE-CHECKS the
> already-read (judged) pool against the refined non-negotiables (years floor,
> company exclude, title exclude), re-ranks what survives, and rewrites the shown
> set — free, no new search. Exhaustion (nobody in the read pool matches) keeps the
> current view and returns `exhausted` so the UI can offer reach-wider. Wired:
> `POST /search/{id}/refine` (typed `RefineRequest`), `IntakeService.refine`,
> `SearchResponse.refine_outcome`, frontend `refineSearch()` + `RefineDeltas` type.
> 10 new offline tests.
>
> **4b — the refine overlay UI: DONE 2026-11-05.** `frontend/src/components/
> RefinePanel.tsx` (+ `.css`) — a modal dialog with all sections: Non-negotiables
> (years steppers, work-mode segmented, cities tag field), Companies (only-from /
> exclude-current / exclude-ever tag fields), Titles (exclude only — include is the
> 4c model gap), More filters (industries), Qualifications (per-requirement
> Core/Supporting/Differentiator segmented re-tier, seeded from the confirmed role
> understanding keyed by text), Add-a-must-have (suggestion chips from
> `technologies_mentioned` only — no free-text box). Builds a MINIMAL `RefineDeltas`
> (only what changed vs the confirmed values); Apply disabled until something
> changes; pool-first footer copy; exhausted → honest "fresh search uses credits,
> coming next" banner (no spend affordance yet — that is 4c). Wired into
> `CandidateReviewScreen` via a "Refine search" toolbar button (gated on
> `feedback_capture`) + `applyRefine` → `refineSearch()` → `onSearchResponse`; panel
> stays open to show `refine_outcome`. 5 new offline tests (RefinePanel.test.tsx);
> tsc clean; CandidateReviewScreen's 27-test contract (no select/checkbox/
> "Relevance"/grouping) still green because the panel is conditionally rendered,
> closed by default, and uses segmented buttons not `<select>`.
>
> **4c — reach-wider: REMAINING + has model gaps.** When the read pool is exhausted,
> run a NEW credit-gated search on the refined model (cost shown first). Needs:
> persist the refined model as a new confirmation; and model extensions for a true
> `include_titles` and hard "only-from companies" (today only-from → `prefer_ever`
> soft; title include not modelled). This is also where P3's un-judged-reserve
> promotion lands. Original scope below.


**Goal:** the mockup's refine overlay — structured, capability-grounded, no free
text, pool-first then outside.

**Sections (all map to verified capabilities — see memory
`crustdata-verified-capabilities`):**
- **Non-negotiables** — years stepper, work-mode segmented, location cascade
  (reuses Phase 5's geo picker). Re-edits the fence; hard.
- **Companies** — Only-from / Exclude (company current/any-time/past — verified).
- **Titles** — Include / Exclude (headline/title keyword — verified, discriminates).
- **More filters** — industry, experience counts (Currently vs Ever held →
  current/past/any tense), current-role tenure.
- **Qualifications** — re-tier (Core ↔ Supporting ↔ Differentiator) + weight.
- **Add a must-have** — suggestions only, drawn from the role's capability
  taxonomy. No free-text box.

**Backend:**
- A refine endpoint that builds a **new immutable RoleModel** from the structured
  deltas (no LLM needed for structured edits; the one small feedback-interpretation
  call from §5 is only for the reject-signal path), re-scores the **held pool
  first** (free, instant), and returns the reranked matches.
- Only when the pool is exhausted against the new constraints → offer a new
  💳 search with the credit cost shown **before** spending (SOURCING_LOOP_PLAN §5,
  §7 caps: re-searches capped per role, soft credit warning).

**Frontend:** the overlay with the pool-first banner + footer already copyed in
the mockup; wire the controls to the refine endpoint.

**Ships independently?** Needs P1 (pool) + P3 (rerank path). **Credits:** zero for
pool-first; new search only on explicit confirm with preview.

---

## Phase 5 — Intake composer + enforced fence + cascading geo *(frontend-led)*

**Goal:** the mockup's single top-down composer — role → description →
non-negotiables fence → "Read & plan the search".

**What's true today:** the engine already parses hard filters with full legacy
parity and seeds years as a boundary input. This phase is mostly frontend; the
geo cascade needs a small mapping.

**Frontend:**
- Single composer replacing the current multi-field intake.
- The fence: minimum years (18+), **cascading geo** (Country → +State / +City /
  +Radius / Several cities), work mode, exclude companies. Structured only.

**Backend:**
- `recruiter/role_model` `Location` already carries countries/states/cities/
  radius/work_mode; map the cascade onto it (preferred_cities stays soft, the
  rest hard). Confirm `_locations` in translate.py round-trips the cascade.

**Ships independently?** Yes (parity already exists in the engine). **Credits:** none.

---

## Phase 6 — The "understand" step *(the better-than-async-intake answer)*

**Goal:** replace the old async-intake idea (which you vetoed — "didn't yield good
results") with a **progressive, overlapping understanding** step: as the reader
runs, the recruiter watches the agent work — JD phrase provenance highlighting,
the fence chips locking, the capability checklist ticking in. It *feels* like the
agent doing a lot of work, instead of a spinner.

**What's true today:** `/intake/start` still blocks ~30s synchronously; `/search`
is already background+poll. `to_intake_result_reading` is the placeholder for a
poll loop that isn't wired on the frontend yet (the remaining item (a) in
`rearchitecture-progress`).

**Backend:**
- Make `/intake/start` background+poll like `/search`: return `understanding`
  immediately, run the read on a daemon thread, flip to ready. The staged shapes
  (`to_intake_result_reading` / `_pending` / `to_intake_result`) already exist.

**Frontend:**
- The "understand" screen: poll `GET /intake/{id}`, animate provenance highlights
  + fence chips + capability checklist as fields populate. No raw query shown
  (calibration validates in plain language — raw query stays admin-only).

**Ships independently?** Yes — closes the last synchronous-block gap. **Credits:** none.

---

## Cross-cutting — admin diagnostics view *(small)*

The exact funnel (pulled / kept / geo-dropped / admitted / judged / failures /
est_credits) already lives in `diagnostics` on every record. Surface it **only**
behind `require_admin` (SUPER_ADMIN_EMAIL) as an operator view — never in the
recruiter UI. This is where your "total pool / out of N" question gets answered
without leaking mechanics to the recruiter.

---

## Suggested build order (dependency-safe)

1. **Phase 1** — pool persistence + judge-8 (foundation, invisible, ↓credits).
2. **Phase 2** — evidence cards + grouping (first visible payoff).
3. **Phase 3** — reject-reason + pool-first reveal.
4. **Phase 6** — understand step (parallelizable; independent of 1–3).
5. **Phase 5** — intake composer + geo cascade (frontend-led; independent).
6. **Phase 4** — structured refine panel (needs 1 + 3).

Phases 1–3 are the core value and share the P1 foundation; 5 and 6 can run in
parallel by anyone free. Each phase ships behind the existing engine, is gated by
`recruiter/tests` (offline, no credits), and touches the files named above.

Every live run that spends credits stays behind an explicit confirm — the standing
"no credits without go" rule holds through the whole build.
