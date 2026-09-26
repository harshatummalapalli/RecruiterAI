# Release 4 hardening (post-release review)

## 1. Provenance is decided by code

Before: the "Candidate identity", "How I read this role" and Seniority tags followed the model's own `source` flag, so a
model claiming `explicit` / `stated_in_jd` showed "Stated in JD" for text the input never said. Requirements were already
code-verified.

Now (`requirement_provenance.apply_field_provenance`, called after Task A):
- A reading field (identity, role interpretation, seniority, archetype) is `explicit` ("Stated in JD") only if every
  meaningful word of its value appears in ONE sentence of the raw input. The real sentence replaces the model's quote as
  evidence. Otherwise it is `inferred`. The stricter 100% word match (requirements use 75%) is deliberate: in testing,
  "Backend Engineer with ML focus" matched 3 of 4 words of a backend sentence and would have passed at 75%.
- A value the recruiter set by answering a question keeps `recruiter` ("Confirmed by you").
- The frontend no longer maps an unknown or missing source to "no tag": it shows Inferred.
- Search boundary is always "Confirmed by you"; system limitations are always "System limitation". Unchanged.

## 2. Seniority

No years-to-seniority rule. Seniority stays a separate field from experience. "mid-level" next to "8-10 years, Confirmed by
you" is allowed, and the seniority value is now always tagged Inferred (unless the input says it or the recruiter set it).

## 3. The 24 of 25 profile read in the production smoke

Both production smoke searches (API and UI) read 24 of 25. It was the same profile both times (candidate 251359507).
- Category: `malformed_response`, but the stored body shows the truth: HTTP 200 from Harvest with
  `{"element": null, "status": 404, "error": "Profile not found", "cost": 0.004}`. The LinkedIn URL from CrustData does
  not resolve at Harvest.
- Retry: attempted once (`attempts: 2`, two GETs to the same URL in the log), then exhausted. Both returned the same 404.
- Verdict: a stale or unresolvable profile, deterministic for that profile, not transient and not an application defect.
  The pipeline degraded as designed (that candidate keeps CrustData evidence, the funnel says "24 were read in full").
- Not changed, per instruction. Two observations for later, neither urgent: the label `malformed_response` hides a
  clean "profile not found" (Harvest's `status`/`error` fields could name it), and the retry on a 404 cannot succeed and
  costs a second request.

## 4. Cleanup

Removed from production storage only what the Release 4 smokes created: 2 intake sessions, 2 confirmations, 2 searches.
(The count of three sessions in the earlier report was wrong; only two exist on the server.) Raw smoke artifacts and the
experiment documents in the repository are untouched.
