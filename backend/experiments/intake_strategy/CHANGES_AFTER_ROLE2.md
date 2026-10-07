# CHANGES AFTER ROLE 2 — the smallest changes Role 2 justified (before Role 3)

Status: experiment only. Nothing here is promoted, and nothing outside `backend/experiments/intake_strategy/` and the experiment tests changed.
No model was run (Role 2 was not re-run, Role 3 has not started), and no retrieval or CrustData call was made. The experimental schema is **not**
promoted into the production `StructuredHiringIntent`.

**Frozen, and proven unchanged by tests** (`tests/test_experiment_cross_role_changes.py`, last section): the Role 1 and Role 2 inputs, ground truth,
stored results, docs, evaluators, `validators.validate()`, `prompt_v2.txt`, `prompt_v3.txt`, and the Role 1 / Role 2 runners are pinned by hash.
Re-evaluating the stored Role 1 and Role 2 runs with the current code reproduces their committed tables exactly. Every stored intent from every
earlier arm still validates against the extended schema.

## 1. Exact schema diff (`experimental_schema.py`; the production model is untouched)
```diff
-PROFICIENCIES = ("hands_on", "working_knowledge")
+PROFICIENCIES = ("hands_on", "working_knowledge", "advanced")
+PROFICIENCY_RANK = {"working_knowledge": 1, "hands_on": 2, "advanced": 3}     # ordinal; used for ordering, not stored
 REMOTE_VALUES = ("allowed", "not_allowed")                                      # unchanged
+WORK_MODES = ("remote", "hybrid", "onsite")

 class XLocationReq(LocationReq, _Based):
     countries: List[str] = []
     remote: Optional[str] = None                                                # unchanged
+    work_mode: Optional[str] = None                                             # None = unspecified; validated against WORK_MODES
```
and `schema_concepts()` gains `ordinal_proficiency` and `work_mode`. No other field, type or default changed. `domain` is untouched (a test pins its
members, its prompt rule text and its optionality).

Also, one **non-schema** edit to a Role 2 file: `gold_role2.py` now holds Role 2's two enums as they stood during Role 2 (`("hands_on",
"working_knowledge")`, `("allowed","not_allowed")`) instead of importing the live ones. Otherwise extending the schema would silently re-score Role 2.
Its outputs are byte-identical (a test re-derives Role 2's committed table).

## 2. Exact validator changes
`validators.validate()` is unchanged. The new checks are in a **new module**, `validators_cross_role.py`, whose `validate_cross_role()` is
`validate()` plus five ERROR checks, so Role 1 and Role 2 re-evaluation cannot move. Roles 3 onward use it. Plus one prompt file.

| code | fires when | role knowledge in code |
|---|---|---|
| `title_analogy` | a `role_family` title's only mentions are comparisons ("more like", "similar to", "resembles", "akin/comparable to", "reminiscent of", "someone/people like", "like a/an/the") | none |
| `responsibility_only_required` | a REQUIRED evidence signal / skill / skill group / domain whose only source is a statement of what the role does, never a stated qualification, never the recruiter brief | none |
| `unsupported_current_relationship` | `relationship=current` (skill, skill group, company) and no supporting source text states current/present use ("currently", "presently", "at present", "now", "current role"; "stay/keep current" is excluded) | none |
| `unsupported_proficiency` | a depth the cited wording **for that skill** does not state, or a weaker depth read as a stronger one; `proficiency_understated` (setting a depth below the stated one) is informational, never an error | none |
| `work_mode_unsupported` | a `work_mode` no non-negated source line states (or states only for other paths); "hybrid" additionally needs working-arrangement context so a strategy word does not count | none |

How responsibility vs qualification is decided (`classify_lines`): by meaning first, heading second. Explicit selection language ("N+ years", degree,
"experience with", "proficiency", "ability to", "hands-on", "must have", ...) makes a line a qualification wherever it sits. With no such language, a line under a
responsibilities-style heading, or (with no heading at all) an imperative / "you will" / "responsible for" line, is a responsibility. A task listed among requirements
without selection language reads as a responsibility; a qualification under a responsibilities heading stays a qualification.

`prompt_v4.txt` is a **new file** (`prompt_v3.txt` is byte-identical and still the default, so the frozen runners are unaffected; Role 3 selects `v4`). It keeps
production rules 1-10 verbatim and changes only generic wording: ordinal proficiency stated only where the cited wording states it (rule 14); work mode as its
own typed fact (18); an unknown level kept as written (20); new rules 21 (title analogy), 22 (responsibilities are not selection criteria), 23 (temporal
relationship, refining rule 4). A test forbids any Role 1 or Role 2 term in the added text.

## 3. Why each change is justified by Role 2 evidence
Replay of the new validators over the stored Role 2 runs (read-only; `results/cross_role_validator_replay.json`):

| change | Role 2 evidence | replay (5 runs) |
|---|---|---|
| ordinal proficiency (`advanced`) | JD: "Advanced proficiency in Python and Java"; the enum stopped at `hands_on`; the model used `hands_on` for them in 5/5 runs, losing the stated depth | the lost depth is reported as informational `proficiency_understated`; the gap was REPRESENTATION by schema introspection |
| `unsupported_proficiency` | `hands_on` on 15-20 skills per run, 8-12 with no depth wording at all (also what makes "hands_on" the only 'doing' value over-used) | 7-13 flags per run, 52 total, all skills whose cited wording states no depth |
| `work_mode` | brief: "Hybrid basis"; no typed place, `remote` could only say allowed / not_allowed; the model correctly left `remote` null and kept "hybrid" in text (5/5) | n/a: no stored intent has the field; `work_mode_unsupported` is the guard against inventing it |
| `title_analogy` | "more like a Forward Deployed Engineer" became a `role_family` entry in 5/5 runs and reached the compiler's title filter (D1) | 1 flag per run, 5 total, only that title; no other title flagged |
| `responsibility_only_required` | 13-16 required signals per run came only from the Responsibilities section | 16-19 flags per run, 87 total (skills and domain atoms included); spot-read: true positives |
| `unsupported_current_relationship` + rule 23 | 10, 10, 5, 1, 6 required skills marked `current` with no present-use wording, driving 11, 11, 6, 2, 7 hard skill ANDs in the compiler (D2) | 10, 10, 5, 1, 6: exactly the `current` skills, every one |
| prompt v4 rule 20 (unknown level) | "Staff" left the typed level null because the prompt's level list had no "Staff" | see section 5 |

The same validators over Role 1's v3 runs (informational; Role 1's verdicts do not use them): `responsibility_only_required` 6-7 per run (the JD responsibility
bullets), `unsupported_current_relationship` 3 (run 1: SQL, Python, Power Query), `unsupported_proficiency` 1-3 per run (e.g. `working_knowledge` on "Data privacy"
with no stated depth). Plausible under the same rules; this is a sample, not a false-positive rate.

## 4. Design notes
- **Proficiency.** The existing enum was not ordinal in structure, so the smallest extension is one value above `hands_on`, plus a rank table. "Expert"
  is accepted as wording for `advanced` by the validator; no further levels were invented. Source wording and provenance live where they already do (`basis.quote`);
  the validator ties the level to a cue in that quote about that skill. Compiler behaviour is unchanged (the compiler never reads proficiency; a test compares plans).
- **Work mode vs `remote`.** `remote` is a sourcing allowance (are candidates who work remotely acceptable); `work_mode` is the role's arrangement. Role 1's
  `remote: allowed` keeps its meaning and coexists with `work_mode: None`. `hybrid` is rejected as a `remote` value. **Unspecified is `None`**, not a fourth
  enum value: absence is the one unambiguous way to say it, and an explicit "unspecified" would be one more thing a model could invent.
- **Work mode is not geography.** Geography is WHERE (a city or a country); work mode is HOW (on-site, hybrid, remote). They vary independently (hybrid in
  Hyderabad; remote anywhere in India; on-site in Pune), they have different downstream behaviour (a place can be a provider filter, a work mode cannot), and a
  location with no place can still state a mode. It sits on the location record only so that a path's location override carries both together; it is a separate
  typed member, and nothing compiles it.
- **Domain is unchanged,** optional, not expanded, not classified Role-1-specific. Role 2 correctly needing no domain is optionality working.

## 5. Issues by kind (schema vs extraction vs validation vs taxonomy)
| issue | kind | what was done |
|---|---|---|
| "Advanced proficiency" inexpressible | **SCHEMA** | added `advanced` |
| "Hybrid" inexpressible | **SCHEMA** | added `work_mode` |
| `hands_on` promoted onto skills with no stated depth | **EXTRACTION** (the schema could say null) | prompt rule 14; validator `unsupported_proficiency` |
| "Forward Deployed Engineer" as a title | **EXTRACTION** | prompt rule 21; validator `title_analogy` |
| responsibilities hardened to `required` | **EXTRACTION** | prompt rule 22; validator `responsibility_only_required` |
| `relationship=current` with no present-use wording | **EXTRACTION** (prompt rule 4's "present-tense technical stack" clause) | prompt rule 23; validator `unsupported_current_relationship` |
| "Staff" left untyped | **TAXONOMY / KNOWLEDGE follow-up**; the representation can preserve it (`Seniority.value` is free text, the compiler carries it verbatim, the audit row reads `value=Staff`); the cause was a closed-looking level list in the prompt shape | v4 shape and rule 20 say the list is examples and an unknown level is kept as written. `knowledge/seniority.json` (no `staff`) is production and untouched. The invariant "an unknown level never silently becomes a different known level" is guarded by `unsupported_level` (it flags a substituted level) and tested |
| AKS and EKS as separate required skills | **EXTRACTION / grouping**, no change | see below |

**AKS / EKS.** The Role 2 ground truth (R8) records the source as `DevOps tools and practices "including CI/CD pipelines, Terraform, AKS, EKS, GitHub Actions,
containerized deployments"; the named tools are examples ("including")`. So the source means neither "AKS AND EKS" nor "AKS OR EKS"; it names examples of DevOps
experience, and the sentence sits beside "Azure and/or AWS". Making AKS and EKS each a separate required skill (5/5 runs) is therefore a grouping error
(examples promoted to individual requirements). **No generalised OR-group change, validator or prompt rule was added**: this is one role's evidence.

## 6. What remains unresolved
1. **Whether the new prompt and validators fix extraction is untested.** No model has run on v4. These are generic rules written from Role 2's evidence; Role 3 is the first test.
2. **The validators are lexical.** A depth cue can sit in a sentence about another skill (partly handled: the cue must mention the skill); the imperative-verb list is
   finite; a requirement phrased as a task under no heading reads as a responsibility; `current` cues are English words; section headings are a second signal only.
3. **Latent default.** The production `SkillReq.relationship` defaults to `current`. An atom that omits the field silently becomes `current`; the new validator flags it
   when the source does not support it, but the default itself is production and was not touched.
4. **`responsibility_only_required` can miss** a responsibility the model quotes from a requirement line (then it is a qualification by the source's own framing).
5. **Taxonomy:** `knowledge/seniority.json` has no `staff`; role-family expansion (e.g. `Software Engineer` to Backend/Python titles) is untouched and downstream.
6. **Downstream follow-ups D1-D5 from `RESULTS_ROLE2.md` stand,** unchanged: the compiler still never reads proficiency or work mode, and still turns every required
   `current` skill into a hard AND. Fewer `current` skills should reach it only if extraction actually improves (unproven).
7. **Not covered:** the AKS/EKS grouping; the typed "IC engineer" concept (an evidence signal still carries it); Role 2's other post-hoc observations.
8. **Two roles still do not prove generality,** and the promotion gate (Role 3 and the criteria in the brief) is open.
