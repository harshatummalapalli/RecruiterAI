# Adaptive sourcing loop — design (awaiting go-ahead; NOT started)

Consolidates the decisions from the Q1/Q2/Q3 review. Implement only on explicit
go. Independent of cutover #4 except where noted in §9.

## The shift: 50 → 5 (demand-driven), not 50 → 25 → 5

**Today:** pull ~50 → baseline-rank → admit 25 → Harvest-enrich + Judge all 25 →
show 5 → **drop the other 20 we paid for.**

**New:** pull ~50 → **store all 50** → baseline-rank (free) → Harvest-enrich +
Judge **only the 5 we're about to show** → show 5. The rest of the pool is judged
**on demand**, a batch at a time, as the recruiter advances. We never pay Harvest/
Judge for a candidate we don't surface.

Net effect: first view costs **5 enrich+judge instead of 25** — cheaper and
faster — and nothing is wasted.

### The one tradeoff to accept (honest flag)

The "best 5" are now chosen by the **baseline score** (CrustData record only: title,
headline, provider score) — *not* by the Judge, because we judge only after
picking the 5. Previously the Judge re-ranked 25, so it could promote a
record that looks mediocre but is actually excellent once enriched.

Why it's acceptable here: baseline only sets the **order of evaluation**, not who
is eligible. Everyone in the stored pool can still be judged as the recruiter
advances/refines, so a hidden gem surfaces in a later batch rather than being lost.
The feedback loop is the safety net.

**Hedge — CONFIRMED (judge-8, show-5):** judge the top 8 of the pool, show the
best 5 by final score. ~3 extra judgments buy a Judge-ranked first impression
instead of a baseline-ranked one. Subsequent batches: same shape (judge a small
buffer, show the batch).

## 1. Pool persistence

Persist the full in-scope pool (~50 `CandidateRecord`s) in the search store, keyed
to the role, for the role's lifetime — plus per-candidate state: `baseline_rank`,
`judged` (bool), `judgments`, `shown`, `decision`, enriched evidence. Today
[translate.py](backend/bridge/translate.py) keeps only the shown 5; this is the
foundation for everything below.

## 2. Ranking becomes incremental (the core code change)

`RankingAgent` today judges `admit_n` in one shot. New capability: **judge the next
K of a stored, baseline-ranked pool, skipping anyone already judged**, holding pool
state across calls. Baseline-score the 50 once (free); each batch enriches+judges
only its K members (K=5), streams them in ranked order (Q2: top-first, no
click-through). First batch 5; subsequent batches 5 (configurable).

## 3. Green dots + requirement ledger restored; no numbers

The dots and the "met / not evidenced" ledger are built from
`evidence.requirement_judgments`. The Judge already produces these
(`record.judgments`) but translate.py discards them. **Fix = surface
`record.judgments` into the evidence** instead of emitting only the prose `fit`.
Numeric score is already internal-only ([discovery.ts:132](frontend/src/models/discovery.ts#L132),
"never rendered as a score/percentage") — verify no leak once dots return. The
dots become the sole alignment signal shown.

## 4. One-time validation gate

After the **first 5**, the recruiter must decide on each (shortlist / reject).
Reject requires a **structured reason** (missing-skill / wrong-seniority /
wrong-domain / other) + optional free text. This single validation unlocks the
flow; **subsequent batches do NOT re-gate** — they stream in as judged, top-first,
"like a recruiter would normally work."

## 5. Constant feedback loop (any point, no restart)

At any point the recruiter can refine specs. Then:
1. 🧠 One small LLM call interprets the feedback into a RoleModel refinement.
2. Build a **new immutable RoleModel** (provenance = recruiter feedback).
3. **Re-score the remaining UNSHOWN pool** with the refined model — do NOT restart
   from candidate 1; continue from where they are (mid-session refine after, say,
   20 reviewed picks up at 21 with the new priorities).
4. If the remaining pool still has qualifying matches → enrich+judge the new top
   ones and continue. Only if the pool is **genuinely exhausted / no match** →
   offer a **new paid CrustData search** with the refined requirements (credit-gated).

Re-scoring already-judged candidates is free; promoting a never-judged pool member
costs its Harvest+Judge (incremental, far cheaper than a fresh 50-pull). The feedback
interpretation is a new LLM touch-point (one small call per refine).

## 6. Small-pool intelligence

Use the preview `count()` (pre-pull) + actual `SearchResult.pulled`. If the market
is genuinely narrow, tell the recruiter honestly up front ("about 18 people match
this — narrow pool"), still enrich + rank + show everyone available, never pad.

## 7. Stop / budget policy (proposed — confirm the numbers)

Core rule — **demand-driven, no speculative burn:** we never enrich/judge ahead of
the recruiter. The next batch is processed only once they've engaged with the
current one. That alone stops runaway spend on an idle role.

Hard ceilings per role (proposed defaults):
- **Pool exhaustion:** stop serving when the stored ~50 are all judged; continuing
  needs an explicit new search.
- **New re-searches capped at 3** per role (each credit-gated + shown), so a role
  can't silently trigger pull after pull.
- **Soft credit warning** at ~10 credits for the role, explicit confirm beyond.

Time-based:
- **Inactivity dormancy: 7 days.** No recruiter action for 7 days → role goes
  dormant. Resuming warns that CrustData data/pool may be stale and offers a fresh
  search rather than silently serving aged results.
- No in-session auto-advance timer — advancement is always recruiter-triggered.

## 8. Intake changes (Q3)

- **Years = required precondition**, not a mid-flow block. The role can't be
  submitted for reading without it. If the notes already state years, **pre-fill**
  the field to confirm (don't make the recruiter retype). Saves the wasted LLM read
  that today happens before the block.
- **Tiering = Option A (editable brief).** The reader LLM's proposed tiers show on
  the brief as the starting assumption; the recruiter can move any requirement's
  tier (Core ↔ Differentiator ↔ Supporting) inline before GO. No new round-trip,
  no blocking page — flexibility without the friction you removed earlier.

## 9. Suggested staging

- **Stage A (small, safe, now):** §3 dots+ledger+no-numbers, §8 years precondition,
  §8 Option-A tier editing. Low risk, immediate UX wins.
- **Stage B (the loop):** §1 pool persistence, §2 incremental ranking, §4 validation
  gate, §5 feedback loop, §6 small pools, §7 stop policy. The meaty piece; its own
  stage with its own tests.
- **CONFIRMED:** Stage A before cutover #4, Stage B after.

## New LLM / cost touch-points introduced

- 🧠 Feedback interpretation — one small call per refine (§5). New.
- 💳 Harvest+Judge now scoped to **shown** candidates only (5 first, then on
  demand) — a **reduction** vs today's 25, unless the recruiter pages deep.
- 💳 New re-searches only on genuine pool exhaustion, capped (§7).
