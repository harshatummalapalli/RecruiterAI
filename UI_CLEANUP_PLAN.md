# UI cleanup — from the Cowork audit (queued for the cutover cleanup stage)

Source: Claude Cowork end-to-end run `e2cf3aa8-2fcc-4606-9627-c4be96dde2f1` (one real
search, ~1.5 credits). **Stage A verified PASS on all 6 checks** — these are polish
and a few functional gaps, not regressions. Do alongside the OCI cleanup in next
steps, except the two "pull forward" items flagged below.

## Already fixed (Stage A, in this branch)
- **Copy bug:** the capability note said "remove it from the core requirements
  **below**" while the requirements render above it → changed to "above"
  ([translate.py](backend/bridge/translate.py)).

## Functional gaps — candidates to PULL FORWARD (money / correctness)
1. **Re-search has no credit warning on the Edit-Brief path** (audit #6). The
   warning is gated on `searchId !== null` ([RecruiterWorkspaceScreen.tsx:554](frontend/src/screens/RecruiterWorkspaceScreen.tsx#L554));
   the Edit-Brief → Search route apparently reaches it with no confirm. Also the
   existing warning never says the current results will be **replaced**. Fix:
   ensure every re-search route hits the confirm, and add "…and replaces these
   results" to the text. **Recommend pulling this forward** — it's about spend.
2. **"Why is Build Brief disabled?" is unexplained** (audit #1 / top-5 #5). The
   years precondition works, but a recruiter with everything else filled gets a
   dead button with no hint. Fix: show "Add a minimum years of experience to
   continue" near the disabled button. Cheap, high-friction-removal.

## Brief polish
3. **Silent tier snap-back on the role-defining requirement** (audit #1, top-5 #2).
   Moving "Agentic AI" out of Core reverts with no message. Fix: the backend
   should mark the capability-label requirement as non-retierable; the frontend
   then **disables that row's dropdown** with a tooltip ("Role-defining skill —
   remove it with the capability control to widen"). Needs a small backend signal
   (flag the capability rows in the brief payload).
4. **Everything lands in Core + near-duplicates** (audit #2, top-5 #3). "Agentic
   AI" and "Building agentic AI systems" overlap, and 6–7 items all sit in Core,
   which makes the tiers hard to use. Fix: dedupe near-duplicate requirements in
   the reader/assemble step and bias toward fewer Core items. (Reader-side; verify
   against the golden set.)
5. **No saving cue on a tier change** (audit #4). Each move fires a ~650 ms
   `POST /answer` with no spinner/saved state. Fix: a lightweight saving indicator
   (reuse `isAnswering`, which the selector already respects — just surface it).
6. **"Adjust before searching" reads as plain text, not a control** (audit #5,
   cosmetic). Make it obviously expandable.

## Results / candidate-review polish
7. **Counters read backwards** (audit #7, top-5 #4). "N ready · M surfaced" counts
   down as the search runs. Fix: a single "Reading profiles: N of 25".
8. **Show the real funnel** (audit #8, top-5 #4). The progress line ends at 5 with
   no context. Fix: surface 50 → 40 kept → 25 reviewed → 5 shown (the diagnostics
   already carry these numbers).
9. **Stale titles/status after results** (audit #9, cosmetic). The page still says
   "What are you hiring for today?" above finished results; the sidebar read
   "Drafting". Fix: title/status reflect the completed search.
10. **Long keyword headlines** (audit #10, cosmetic). e.g. "Senior AI Engineer -
    MCP, LangGraph, AWS, AZURE, RAG…". Fix: truncate or prefer the actual title.
11. **Ledger wording** (audit #4/#11). Says "4 of 5 evidenced" (fine) but a
    "Related… Not counted" quote reads like positive evidence. Fix: clearer
    "not counted" styling/label.

## Intake polish
12. **No inline validation for Onsite** (audit #12). State/City/Radius are required
    with no inline error, and Country/State/City only commit when picked from the
    dropdown (Cowork had to supply State = Karnataka, which the task omitted). Fix:
    inline message naming the missing field; confirm the typed-vs-picked commit
    behavior is intended.
13. **Country dropdown overlaps the Max-years label** when open (audit #13,
    cosmetic). Fix: z-index / spacing.

## Consistency (one product, not three)
14. Label drift: "Build brief" vs "Search brief"; "Edit Brief" vs "Edit boundary"
    vs "Edit description". Pick one vocabulary and apply it across screens.

## Responsive / tap targets (390px)
15. Sub-44px tap targets remain (top-5 #5): filter tabs 27px, Export CSV 36px, tier
    dropdowns 22px. Fix: raise to ≥44px at phone width (the decision buttons were
    already fixed in an earlier batch — extend the same treatment).

## Confirmed healthy (no action)
- Keyboard: cards reachable, Enter opens / Escape closes, 2px focus ring, no trap.
- Responsive: no horizontal overflow at 390/768; rail → top bar.
- Dots have non-color cues (filled/hollow + aria-label + tooltip).
- No numeric scores anywhere; data quality good (all 5 in-geo, ledgers non-empty).
- Console: only pre-login 401s and a Google-popup COOP warning; **no JS errors in
  the flow**. Network all 2xx; polling ~1.5s, no duplicates.

## Suggested effort split
- **Pull forward into Stage A (small, pre-cutover):** #1 credit warning, #2
  disabled-button hint, #5 saving cue, #3 lock the capability row.
- **Cleanup stage (with OCI cleanup):** #4 dedupe/tiering, #7/#8 funnel counters,
  #9 stale title/status, #10 headlines, #11 ledger wording, #12/#13 intake,
  #14 vocabulary, #15 tap targets.
