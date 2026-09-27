# Release 5 (local, not deployed): roles, progressive review, one-time calibration, continuous search

## Model
A role is a search record. Every retrieval "cycle" is one run of the existing pipeline (retrieve up to 50, read, admit up to
25). Candidates from every cycle are kept in one inventory (index-aligned candidates / explanations / evidence, as before).
`presentation[candidate_id]` says `presented` or `reserve`; reserve is reviewed and kept, never rejected. A record with no
`role` (stored before this release) shows every candidate exactly as before.

Cycle kinds: `initial`, `change` (fresh retrieval after a meaningful change), `more` (next page from the stored cursor),
`resume` (same, on resuming), `daily` (fresh first-page retrieval in the background).

## Feedback -> retrieval guidance (exactly)
Stored as given: `{candidate_id, search_id, decision, feedback_reason, feedback_note, at}`. Only the latest reason per
candidate that still matches the candidate's current decision counts. Reasons map by a fixed table to four dimensions:
experience, technology, seniority, work_type (see `backend/services/role_feedback.py`). Domain/industry, career background,
Other and every free-text note are stored and NOT translated. Guidance = counts per dimension. It is used in two places only:
1. Admission tie-break in later cycles: among retrieved candidates with EXACTLY equal baseline score, those showing more on the
   named dimensions are admitted first. Scores, formula and the 50 -> 25 cut are untouched.
2. Order of the next batch shown from already-read candidates, within an evidence level.
Empty guidance changes nothing. The confirmed brief is never modified; the query sent for later pages is the same query.

## Lifecycle
Day 0 = confirmation. Window 3 days; a meaningful change (`intent_change.py`: compares the stored confirmed intents) extends
by 1 day; hard stop 5 days from Day 0; manual pause/resume any time (resume refused after the hard stop; "Show me more"
still works). A timer (`RoleScheduler`, started at server startup only, every 15 min) applies the clock and runs one fresh
daily retrieval per 24h while SEARCHING. Env `RECRUITERAI_ROLE_SCHEDULER=false` disables it.

## Calibration
The FIRST FIVE shown are the calibration set. There is no fixed count. It is `pending` while they are reviewed, `ready` once
there is signal (at least two of them have a decision AND at least one Maybe/Reject carries a reason the search can act on;
plain shortlists alone manufacture nothing), and `closed` for good when the recruiter moves on ("Show me more") after seeing
the summary. Asking for more before there was signal does not use it up. If a change of mind removes the signal before it is
closed, it goes back to pending. Later decisions never reopen it. The summary is deterministic text built from structured
reasons and stored evidence (no model call); the recruiter can remove a dimension. No questionnaire.

## Retrieval history (daily search)
Three separate concepts per role: `retrieved_ids` (every profile the provider has returned for the role, admitted or not),
the inventory (candidates read and kept), and `presentation` (what is on screen). A fresh daily retrieval still asks the
provider for the first page, but skips every profile already in `retrieved_ids` before ranking, so nothing already retrieved
is enriched, read or judged again. Skipped profiles keep whatever data and decision they had; they are not re-ranked or
decided. "Show me more" is unchanged (stored cursor, dedupe against the inventory).

## Role ownership
Role ownership deferred until multi-user pilot. Sessions are deliberately shared and carry no user identity
(`create_session_cookie_value` stores only `authenticated: true`), so the sidebar lists every role on the server. Safe for one
controlled recruiter; before a second recruiter is added, identity has to be added to auth (then an owner on each role).
