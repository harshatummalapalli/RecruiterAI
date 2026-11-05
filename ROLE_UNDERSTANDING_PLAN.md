# Role-understanding plan — disambiguation, capability precision, level/track

The product's job across all of this is one principle: **make the implicit
explicit, ground every decision in the role's own evidence, keep the recruiter
in control — never silently force (bug #2) and never silently drop (level gating,
dropped free-text negatives).** Detect the ambiguity → propose the resolution
*with evidence and consequences* → let the recruiter confirm, adjust, or remove.

This is the concrete content of the agreed capability-aware direction
(`CAPABILITY_AWARE_AGENT_ARCHITECTURE.md`).

---

## Thread A — Capability memory: stop forcing, start proposing

**The bug (#2 from CoWork's test).** `output/capability_memory/<org>.json` learned
`backend engineer → ML Platform` from one ML-heavy JD. On every later backend
role, `CapabilityProposer.propose()` returned that cached group as a **hard Core
requirement** with no re-check and no confirmation — collapsing a payments search
to 8 of 47 kept, with no way to remove it.

**Root cause (two faults, one layer):**
1. The memory key strips seniority, so craft base titles (`backend engineer`)
   collide across unrelated domains.
2. A cache hit is **forced**, not proposed or re-validated against the current JD.

**Do NOT delete the layer** — it is the look-alike defense that makes an "AI
Architect" search find real AI people (see `intent-retrieval-root-cause`). Demote
it from *decider* to *vocabulary cache*.

### A1 — DONE (offline, no credits)
- **Data unblock:** corrected the overfit `backend engineer` row to `is_broad:true`.
- **Recurrence guard** (`capability_proposal.py`): a learned *narrow* capability is
  no longer force-applied when the normalized identity is a generic craft/base
  title (software/backend/frontend/full-stack engineer, developer, analyst,
  associate, consultant, specialist, manager, …) **unless the current role's own
  requirement texts corroborate it**. A genuine ML backend role (requirements name
  ML/serving/SageMaker) still keeps the group; a payments backend role does not.
  Offline unit-tested.

### A2 — DONE 2026-11-05 (offline, no credits)
The capability keep/remove, and Thread B's specialization/stack, were being sent as
read-only `tell` insights — so A2 had "no remove control" and Thread B wasn't
answerable in the UI. Added a non-blocking `offer` decision (`translate._issue`):
these now render as interactive choice cards in the brief (via a new
`offeredDecisions` selector + `LivingBrief` rendering) that the recruiter can act on,
and they never block Search. The remove/keep + specialization + stack answers apply
live through the existing `apply_answers` path. Deeper redesign below still optional:

### A2+ — optional later (not needed now)
- Replace the hardcoded generic-title set with **taxonomy-driven breadth detection**
  (Thread B).
- Treat a memory hit as a **prior re-validated against this role**, not an override;
  key the *vocabulary* (label → synonyms) separately from the *per-role decision*.
- Surface the capability as a **confirmable, removable proposal** in the brief
  (fixes "the brief says remove it above but there's no control, and demote snaps
  back"). Backend + Living-Brief UI.
- **Validation:** one paid intake run on a small gold set before ship.

---

## Thread B — Archetype disambiguation ("Software Engineer → backend? frontend? full-stack?")

**Gap today:** the system does not recognize a *super-type* title that needs
narrowing. `knowledge/semantic-titles.yaml` has title *equivalence* groups (the
leaves); there is no *specialization* map (parent → children), no breadth
detector, and no front-loaded "which kind?" step.

**What exists to build on:** the equivalence knowledge + `ai-engineering-roles.yaml`
/ `data-roles.yaml`; the capability proposer (JD → defining capability); and the
intake **ask mechanism** already present — `IntakeIssue` carries `question`,
`options`, and `consequence_if_answer_a/b`.

**Design (domain-agnostic — tech first, then finance, then others):**
1. **Specialization taxonomy.** `Software Engineer → {backend, frontend, full-stack,
   mobile, data, ML, DevOps/SRE, platform, embedded}`; `Analyst → {FP&A, equity
   research, risk, ops, BI}`; etc. New knowledge file(s); the mechanism is built
   once, the taxonomy grows over time.
2. **Breadth detection.** Flag when the posted title is a super-type vs already
   specific (Backend Engineer).
3. **Propose-or-ask, evidence-grounded.** Strong JD signals (Spring/Kafka/Postgres →
   backend) → *propose* the archetype with its evidence, recruiter confirms/corrects.
   Weak or conflicting signals → *ask* with concrete options + consequences.
4. **Scope control for adjacency.** Make the archetype explicit and show what's
   in/out: "DevOps/SRE is adjacent to a backend role — including it widens the pool
   and changes what counts as evidence. Include as adjacent?" Answers the recruiter's
   own confusion ("can I submit a DevOps/Cloud person for a Software role?").
5. The confirmed archetype drives Thread A's capability group — now grounded in
   *this* role and confirmed, not a cached title lookup.

**AI roles** are the same tree, deeper (research / ML-platform / applied-agentic /
MLOps) — which is why #2 surfaced there first.

### B1 — DONE (offline, no credits, 2026-11-05)
Detection + ask, reusing the existing refinement surface — no new UI/model/prompt.
- `recruiter/agents/intake/specialization.py` — a small knowledge table (software /
  AI / analyst super-types → specializations with signal terms) + pure
  `disambiguate(identity, requirement_texts)`. Asks **only when** the title is a
  broad super-type AND the role's own evidence doesn't single out one kind (no nag
  when the JD is clear; silent for already-specific titles).
- `question_planner.plan_refinements` prepends that `Question` (kind `choice`, which
  the brief already renders like the `domain` question). 6 new offline tests; 177
  recruiter tests green.

### B-depth2 — stack axis (small, rides B2)
Once a specialization is pinned (e.g. Backend) but the JD names no language, ask a
nested question — "Java / .NET / C# / Python / Node / Go, or **any backend stack is
fine**?" A chosen language → `must_have_keywords` (hard, whole-word; verified
mechanism). "Any" → nothing filtered. Never inferred from silence. Same
`disambiguate` pattern one level down: each specialization carries an optional stack
axis with options + an explicit "any".

### B2 — DONE (offline, no credits, 2026-11-05)
`calibration/apply.py` now applies a `specialization` answer by adding the chosen
label as a **soft core requirement** (shapes judge/ranking toward e.g. Backend) —
deliberately NOT a hard keyword gate, which would over-narrow on generic craft terms
(the #2 lesson). The precise hard filter is the stack axis (B-depth2), where a
specific language like "Java" is safe. 1 new calibration test; 178 recruiter green.

### B-validation — DONE 2026-11-05 (1.5 credits, one real end-to-end)
Ran the real reader + one live CrustData search. **Apply path proved end-to-end:**
specialization=Backend → "Backend" core requirement; stack=Java → capability group
`('Java', java/spring/jvm)`; search pulled 50 → 48 candidates, est_credits 1.5,
shown 5 / admitted 8 / reserve 40. **Detection caught two real bugs** offline tests
missed, both from naive substring matching ("ui" ⊂ "built" false-pinned Frontend on
a vague JD; a clear backend JD then asked nothing). **Fixed:** word-start-anchored
matching (`_matches`) — `api` still matches `APIs`, `ui` no longer matches `built`.
The real reader's actual requirement texts are now offline regression fixtures
(187 recruiter tests green), so the fix is locked without a second paid run.

**Ships:** backend intake step + (existing) Living-Brief refinement surface.

---

## Thread C — Level & track precision (Senior≠Staff, Architect≠Manager, Manager≠Director)

**What exists (a deliberate, defensible design):**
- `role_model/seniority.py`: **years are the only gate.** A title *label* ("Senior"
  vs "Staff") is company-relative noise and never excludes.
- `role_model/levels.py`: classifies the **role** as IC / Architect / Manager /
  Director+ (two axes: IC-technical vs management track) — used to **flag** fit and
  to pick default title exclusions, **never to gate**. `level_note()` already emits
  "reads above/below the role's level".

**Honest reconciliation of the edge cases:**
- **Senior vs Staff** — both IC, separated only by a company-relative label + years.
  *Not reliably separable.* Keep gating on **years**, show the title, don't ship a
  filter that lies. (A hard label filter is what gated out real seniors in the
  `ai-architect-funnel-experiment`.)
- **Architect / Manager / Director** — these are **track** distinctions, already
  classified and far more reliable. Today they only *flag* (and for a Director role
  the exec exclusions are suppressed, which is why a Manager can still surface).

**C1 — DONE 2026-11-05 (offline, no credits).** An opt-in `track` offer (brief choice
card, non-blocking): for a role whose band suppresses default exclusions (architect /
manager / director+), "Tighten to this role's level — exclude <off-track titles>?".
`levels.off_track_titles` gives a conservative per-band set (architect → people-
managers; manager → higher execs; director+ → non-director managers), applied to the
verified `exclude_titles` filter via `apply_answers`. Default stays flag-and-surface;
years remain the only gate; Senior-vs-Staff is deliberately NOT offered (not
reliably separable). 2 new calibration tests.

---

## Cross-cutting — dropped free-text negatives (from CoWork's negative-ask test)

**DONE 2026-11-05 (offline, no credits).** Free-text negatives are correctly never
inferred as hard filters; now, when the notes contain clear exclusion phrasing but
nothing was excluded, `translate._dropped_negative_nudge` adds a plain `limitations`
line pointing to the Exclude controls. High-precision (fires only on explicit
"exclude/not from/no one from…" language AND only when no exclusions were set), so a
false nudge is avoided. Presentation-level (not in the quality-critical intake
model). 1 new bridge test.

---

## Sequence

1. **A1 — DONE** (data + recurrence guard, offline).
2. **Thread B core** (taxonomy + breadth + propose-or-ask) — the permanent #2 fix
   and the Software-Engineer answer; also yields the archetype that C hangs off.
   *One paid validation before ship.*
3. **A2** (confirmable/removable capability proposal UI) — rides B.
4. **C1** (track strictness control) + the negatives acknowledgement.

CoWork's smaller UI findings (#3 keyboard, #8 header staleness, #9 disabled-control
messaging, #6 "Direct title match" label) are independent polish, fixable offline
alongside any of the above.
