# Release 4 pre-deploy gate: real-model smoke test

Run: 2026-09-26, once, before commit. `python -m backend.experiments.intake_smoke` (raw results: `output/experiments/release4_smoke/results.json`, git-ignored).
Real OpenAI (gpt-4o-mini, temperature 0) through the real `IntakeReasoner`, `IntakeSessionManager`, backstops, Search
Boundary and confirmation gate. No scripted client. Boundary for all cases: Northwind Payments, Toronto, Ontario, Canada, hybrid, 25 mi.

**Result: 27 of 27 checks passed.**

| Case | What was checked | Result |
|---|---|---|
| 1. Clear AI Engineer role | zero questions; status ready; confirmation gate open; posted title kept verbatim | pass. No questions. Core requirements: "Strong Python", "Experience with event-driven systems", "5+ years of professional software engineering experience". |
| 2. "3+ years" and "8-10 years" | exactly one question; it is the experience question; blocked until answered; answered; does not reappear; ready; no drift; recorded as confirmed; survives reload | pass. One question ("What is the correct range of experience required for this role?"). Answered "8-10 years": experience 3-None to 8-10, status ready. Role interpretation identical except `explicit_constraints`; requirement lists identical. Recorded as "Experience: 8-10 years" (confirmed by the recruiter). A brand-new manager reading only the stored session returned the identical brief with the answer intact and no question. |
| 3. Product Analyst, entry-level and 10+ years | contradiction raised; blocked; still blocked after an unrelated boundary edit; resolved; does not return | pass. Blocked ("1 question still needs your answer"). The question was authored by the model ("How should we interpret the experience requirement for this entry-level role?", options "Entry-level with extensive experience" / "Standard entry-level experience"); the deterministic backstop deferred to it rather than adding a duplicate. Resolving cleared the block and it did not return. |
| 4. JD says fully remote, boundary says Hybrid | no work-mode question; boundary precedence visible as a TELL; limitation shown; not blocking | pass. TELL: "The job description has remote. The search follows the work mode you selected (hybrid)." Limitation: "Work mode (hybrid) is recorded for context. The search cannot filter candidates by work mode." Status ready; no work-mode reason in the gate. |

Notes:
- Case 3 was caught by the model itself, not the regex backstop. The backstop is the floor underneath it; the test shows the
  block holds either way.
- The one check that originally read `or True` (experience range equals the answer) was corrected to a strict comparison
  after the run; the recorded values (8, 10) satisfy it. No second real run was made.
