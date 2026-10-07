# ROLE 3 — GROUND TRUTH (written BEFORE any model execution)

Third and final planned intake-representation validation. Derived ONLY from `inputs/role3_jd.txt` (verbatim). **Role 3 is JD-only: there is no
recruiter/HM brief and none was created.** Consequently there is no recruiter source, no JD-vs-brief reconciliation, and no assertion below is
classified RECRUITER_BRIEF. Nothing here was informed by a model output or by how the evaluator will score.

Every assertion carries its provenance class:

- **JD** — stated in the JD text (the quotation is given).
- **APPROVED_KNOWLEDGE** — supplied by an existing approved knowledge source in this repository (checked read-only: the role-family taxonomy and
  `knowledge/seniority.json`). Where none exists, that is said.
- **INFERRED** — my reading or a mapping decision, not stated by the JD. An INFERRED assertion is never a hard requirement of the role; it is a
  statement about how the JD should be represented, and is marked so that the evaluator does not treat it as a source fact.

What the JD contains, structurally: a header (Location, Work Mode, Experience), a Job Summary, 10 Key Responsibilities, a Qualifications list
(9 stated qualifications and 1 marked "preferred"), a "Preferred Background" section (three preference statements, one naming companies), and an
"Important Profile Consideration" (one requirement and one exclusion). There is no conditional language anywhere ("if", "alternatively", "in the
case of"), no "or" between whole candidate populations, and no wording that makes any requirement apply to only some candidates.

## 1. Role identity
| id | assertion | class | source |
|---|---|---|---|
| I1 | The title is **Senior Manager – FP&A and Business Finance** | JD | "Senior Manager – FP&A and Business Finance" |
| I2 | The function is financial planning & analysis and business finance (financial planning, forecasting, performance analysis, business decision support) | JD | "lead financial planning, forecasting, performance analysis, and business decision support" |
| I3 | The organisation is "large, complex"; the role partners with business leaders | JD | "for a large, complex organization … partner closely with business leaders" |
| I4 | **Commercial Finance** and "closely related financial planning roles" are named as acceptable *experience backgrounds*, not as titles of this role | JD | "relevant experience in FP&A, Business Finance, Commercial Finance, or closely related financial planning roles" |
| I5 | No finance role family exists in the approved taxonomy (`role_family_taxonomy` has no finance entry), so the title is carried as the source wrote it | APPROVED_KNOWLEDGE (absence) | read-only check |

## 2. Candidate identity
A finance professional with **meaningful FP&A / business-finance ownership**, 8–12 years of relevant experience, who can model, forecast and
present to senior stakeholders, based in Hyderabad and able to work hybrid. A large multinational / complex-enterprise background is preferred,
and experience at the named consumer/industrial companies is "particularly relevant". A candidate whose experience is exclusively
statutory-audit / tax / bookkeeping / transaction-processing, without substantive FP&A or business-finance responsibilities, is not suitable.
| id | assertion | class | source |
|---|---|---|---|
| C1 | "meaningful FP&A/business-finance ownership" is **required** | JD | "This role requires meaningful FP&A/business-finance ownership" |

## 3. Sourcing strategy
**One** strategy, **zero** conditional paths. The JD describes a single candidate population. The Preferred Background and the Important Profile
Consideration are a preference and a negative on that one population, not alternatives. **`sourcing_paths` must be empty and nothing may be
path-scoped.** There is no brief, so there are no reconciliations and `reconciliations` must be empty. (Roles 1 and 2 are not templates.)

## 4. Hard requirements (stated without "preferred"; the Qualifications list)
| id | assertion | class | source |
|---|---|---|---|
| H1 | Bachelor's degree in Finance, Accounting, Economics, Business, or a related discipline (streams are an OR) | JD | "Bachelor’s degree in Finance, Accounting, Economics, Business, or a related discipline." |
| H2 | **8–12 years** of relevant experience (min 8, max 12), a single range | JD | "Experience: 8–12 years"; "8–12 years of relevant experience in FP&A, Business Finance, Commercial Finance, or closely related financial planning roles." |
| H3 | Strong experience in financial planning, budgeting, forecasting and variance analysis | JD | "Strong experience in financial planning, budgeting, forecasting, and variance analysis." |
| H4 | Strong financial modeling skills, including scenario and sensitivity analysis | JD | "Strong financial modeling skills, including scenario and sensitivity analysis." |
| H5 | Microsoft Excel | JD | "Advanced proficiency in Microsoft Excel." |
| H6 | Power BI or a similar BI / reporting platform | JD | "Working knowledge of Power BI or a similar business intelligence/reporting platform." |
| H7 | Experience presenting financial analysis and recommendations to senior stakeholders | JD | "Experience presenting financial analysis and recommendations to senior stakeholders." |
| H8 | Strong business partnering and communication skills | JD | "Strong business partnering and communication skills." |
| H9 | Experience working with ERP systems; "SAP, Oracle, or comparable platforms" are **examples** ("such as"), not each required | JD | "Experience working with ERP systems such as SAP, Oracle, or comparable platforms." |
| H10 | Meaningful FP&A / business-finance ownership (C1) | JD | see C1 |

## 5. Preferred requirements (every one is explicitly "preferred" or "particularly relevant")
| id | assertion | class | source |
|---|---|---|---|
| P1 | Professional qualification such as CA, CMA, ACCA, or MBA Finance (examples; an OR) is **preferred** | JD | "Professional qualification such as CA, CMA, ACCA, or MBA Finance is preferred." |
| P2 | Experience in large multinational or complex enterprise environments is **preferred** | JD | "Experience in large multinational or complex enterprise environments is preferred." |
| P3 | Experience at **Unilever, Procter & Gamble, PepsiCo, Nestlé, Coca-Cola, Mondelez International**, or similar large consumer/industrial organisations is **"particularly relevant"** (a company/background PREFERENCE; the named companies illustrate a preferred background) | JD | "Candidates with experience in organizations such as Unilever, … would be particularly relevant." |
| P4 | Experience supporting commercial, operations, or business-unit leadership is **preferred** | JD | "Experience supporting commercial, operations, or business-unit leadership is preferred." |
| P5 | The company preference carries **no temporal condition**: nothing says current employer or previous employer, so its relationship is the least restrictive (`any`) | INFERRED | absence of any temporal wording in the sentence |
A company named in P3 is not a hard filter: the JD never says "must", "required", "currently at" or "previously at". It does not follow that every
candidate from those companies qualifies.

## 6. Exclusions / negatives
**Exactly one**, a semantic profile / work-history exclusion:
| id | assertion | class | source |
|---|---|---|---|
| X1 | Candidates whose experience is **exclusively** in statutory audit, tax, bookkeeping, or transaction processing, **without substantive FP&A or business-finance responsibilities**, are not suitable | JD | "Candidates whose experience is exclusively in statutory audit, tax, bookkeeping, or transaction processing, without substantive FP&A or business-finance responsibilities, are not suitable." |
| X2 | The qualifier is part of the meaning: it does NOT exclude someone who has ever done audit, tax, bookkeeping or transaction processing alongside substantive FP&A/business-finance work | JD (the qualifier) | "exclusively … without substantive …" |
| X3 | It is not a company, title or industry exclusion; `exclusions` (companies/titles) must be empty | INFERRED | the JD names no company, title or industry to exclude |
No other negative exists: no company, title, industry, geography, or "not remote" exclusion.

## 7. Geography
| id | assertion | class | source |
|---|---|---|---|
| G1 | The place is the **city Hyderabad** ("Hyderabad, India"); a single geography | JD | "Location: Hyderabad, India" |
| G2 | The state (Telangana) is not in the JD. `Hyderabad, Telangana, India` is an acceptable normalisation of the stated city (the prompt asks for City, State, Country). It rests on the model's own world knowledge: **no approved knowledge source supplies it** (read-only check: the compiler's canonical-city alias table does not contain Hyderabad; the string appears only as a schema comment example) | INFERRED | the city head `Hyderabad` is in the JD; the state is not |
| G3 | "India" is the country OF the city, not a country-wide area: `countries` must be empty; no radius; no second place; no path-scoped location | JD / INFERRED | "Hyderabad, India" names one city |

## 8. Work mode
| id | assertion | class | source |
|---|---|---|---|
| W1 | Work mode is **Hybrid** (typed `work_mode = hybrid`) | JD | "Work Mode: Hybrid" |
| W2 | Hybrid is not remote and not on-site; Hyderabad does not imply on-site. `remote` is **not** stated by the JD and stays null; `work_mode` must not be `remote` or `onsite` | JD / INFERRED | no remote-acceptance statement exists |
Work mode is distinct from the location above: the JD gives both as separate header facts.

## 9. Experience
H2 above: a single range, **min 8, max 12**, `required`, global. Converting it to "8+" only, "12+" only or any other threshold is wrong; so is a
path-specific experience (there is one path).

## 10. Seniority
| id | assertion | class | source |
|---|---|---|---|
| S1 | The level is **Senior Manager** (the title). Accepted: value `Senior Manager`; or `Senior` with `Manager` kept in the role family (the prompt's rule 2 strips seniority from titles). Strength `required` or `preferred` | JD | title |
| S2 | No other level is stated or supportable: **no** Director, VP, Head, Staff, Principal, Lead or Associate; no `alternatives`; no `leadership` entries. The responsibility "Lead the annual budgeting…" is a task, not a level | JD / INFERRED | title; responsibilities |
| S3 | "Senior Manager" is not in `knowledge/seniority.json` (`senior`, `junior`, `mid` only): an unknown compound level, a TAXONOMY follow-up, to be kept as written | APPROVED_KNOWLEDGE (absence) | read-only check |

## 11. Skills and proficiency (what the JD states about DEPTH)
| item | JD wording | accepted `proficiency` | class |
|---|---|---|---|
| Microsoft Excel | "Advanced proficiency in Microsoft Excel" | `advanced` (null = the stated depth lost: PARTIAL; `hands_on`: understates; `working_knowledge`: wrong) | JD |
| Power BI or a similar BI/reporting platform | "Working knowledge of Power BI or a similar business intelligence/reporting platform" | `working_knowledge` (null = lost: PARTIAL; any other value: wrong) | JD |
| financial planning, budgeting, forecasting, variance analysis | "Strong experience in…" | **null only** ("Strong" is not a depth on the scale) | JD |
| financial modeling (scenario, sensitivity) | "Strong financial modeling skills" | **null only** | JD |
| ERP systems | "Experience working with…" | **null only** | JD |
| business partnering, communication | "Strong … skills" | **null only** | JD |
| presenting to senior stakeholders | "Experience presenting…" | **null only** | JD |
Any proficiency on any other item is invented, and promoting finance skills to `hands_on` or `advanced` is the specific failure under test.
`Power BI or a similar platform` has an OR and a depth together. `skill_any_of` carries no proficiency, so the lossless typed form is ONE skill atom
whose name carries the alternative (for example "Power BI or a similar BI/reporting platform") with `working_knowledge`. A plain `Power BI` atom with
`working_knowledge` is acceptable but drops "or similar" (PARTIAL).

## 12. Education
H1. `required`. The professional qualification P1 is a different, **preferred** item; it must not be merged into the Bachelor's record (that record
has one strength) and must not make the degree `preferred`.

## 13. Company / background preferences
P2, P3, P4 above. Company preference is represented, if at all, as `companies` entries with `strength = preferred` and `relationship = any`;
environment/background preferences as `preferred` or `context` signals (or `domain` at preferred/context). **No company may be required, no company
may be `current` or `past`, `company_scale` stays null, and no company may appear in `exclusions`.**

## 14. Alternatives (genuine OR groups in the JD)
degree streams (Finance / Accounting / Economics / Business / related); experience backgrounds (FP&A / Business Finance / Commercial Finance / closely
related); "Power BI or a similar platform"; ERP "SAP, Oracle, or comparable"; professional qualification "CA, CMA, ACCA, or MBA Finance"; the company
list "or similar". SAP and Oracle as two separately **required** skills would convert "such as" examples into an AND (the same grouping error seen
with AKS/EKS in Role 2).

## 15. Conditional paths
**None.** No conditional requirement, geography, exclusion, alternative or lane.

## 16. Relationship (temporal scope)
The JD never states current or present application ("currently", "presently", "in their current role" do not occur). Every skill, group and
company statement is therefore `any` (the least restrictive source-supported relationship). `current` is unsupported everywhere; `past` is also
unsupported (nothing says "previously"). | INFERRED rule, grounded in the absence of any temporal wording.

## 17. Responsibilities are not selection criteria
The ten Key Responsibilities describe the job. A responsibility is a requirement only where the JD also states it as a qualification:
| responsibility | also a stated qualification? | so it may be `required`? |
|---|---|---|
| Lead budgeting / forecasting / long-range planning | yes (H3: "financial planning, budgeting, forecasting") | planning, budgeting, forecasting: yes |
| Develop financial models, scenario analysis | yes (H4) | financial modeling: yes |
| Analyse actuals vs budget, variance | yes (H3: "variance analysis") | variance analysis: yes |
| Partner with business and functional leaders | yes (H8: "business partnering") | business partnering: yes |
| Present insights to senior leadership | yes (H7) | presenting to senior stakeholders: yes |
| **Prepare monthly and quarterly management reporting packs** | **no** | **no: context** |
| **Improve processes through automation, standardisation** | **no** | **no: context** |
| **Work cross-functionally with Accounting, Commercial, Operations** | **no** | **no: context** |
| **Support ad hoc financial analysis and strategic projects** | **no** | **no: context** |
| Evaluate financial implications of initiatives | partly (H7/H8) | not as a separate required atom |
Responsibility-only atoms (management reporting packs, automation/standardisation, cross-functional work, ad hoc / strategic projects) must be
`context` or omitted. | INFERRED classification of each row, from the sentence meaning.

## 18. Provenance expectations
Every atom is attributed to `jd`. **No atom may cite `recruiter_brief`**: there is no brief, so such a claim is a fabricated source. `inferred`
atoms may exist but never `required`. `approved_knowledge` is not needed anywhere: the one normalisation (Hyderabad → Telangana) is the model's own
knowledge (INFERRED, G2), and a claim of `approved_knowledge` for it would be unverifiable.

## 19. Could the CURRENT schema represent the correct meaning? (decided from the schema, before the run)
| meaning | representable? | if the model gets it wrong |
|---|---|---|
| one path, no reconciliation | yes (empty lists) | EXTRACTION |
| 8–12 range | yes (`experience.minimum_years` and `maximum_years`) | EXTRACTION |
| Excel `advanced`; Power BI `working_knowledge` | yes (`advanced` now exists) | EXTRACTION |
| hybrid | yes (`location.work_mode`) | EXTRACTION |
| company preference | yes (`companies`, preferred, any) | EXTRACTION |
| semantic profile exclusion with its qualifier | yes (`semantic_exclusions`; the qualifier lives in the concept text) | EXTRACTION |
| Power BI **or similar**, with a depth | yes as ONE atom whose name carries the alternative; **not** as `skill_any_of` (no proficiency there). The typed OR-ness is lost | not a failure by itself; **observation: proficiency cannot ride on an OR group** |
| preferred professional qualification (CA/CMA/ACCA/MBA) | yes as a preferred `skill_any_of` or signal; **`education` has one strength**, so it cannot also hold it beside a required degree | not a failure; **observation: qualifications/certifications have no typed home** |
| large-multinational / complex-enterprise preference | yes (`domain` preferred/context, or a preferred signal) | EXTRACTION |
| "Senior Manager" level | yes (`seniority.value` is free text); unknown to `seniority.json` | TAXONOMY follow-up |
No representation gap is predicted. The two observations above are recorded now so they cannot be discovered afterwards and called gaps or non-gaps.

## 20. What counts as a failure (fixed in advance)
Over-application (each FAIL): any sourcing path or path-scoped structure; any reconciliation; any `exclusions` entry; more than one semantic exclusion;
a semantic exclusion that loses its "exclusively … without substantive" qualifier (PARTIAL: broadened); any `countries`, second place, radius; `remote =
allowed`; `work_mode` other than `hybrid`; proficiency on anything but Excel and Power BI; a required, `current` or `past` company, `company_scale`;
a seniority other than Senior Manager (including Director / VP / Head / Staff / Principal / Lead), any `leadership`, any `alternatives`; a role-family
title not stated by the JD (Analyst, Controller, Director, Accountant, …); `current` relationship anywhere; a responsibility-only atom required; a
preference (professional qualification, environment, companies, commercial-leadership support) hardened to required; a `recruiter_brief` source claim.
Fidelity failures: 8–12 changed; the degree weakened or the professional qualification merged into it; Excel not `advanced`; Power BI not
`working_knowledge`; SAP and Oracle as separate required skills; the exclusion absent; hybrid absent.

Smaller and correct beats richer and invented. A schema that succeeds only by populating many optional structures is not an acceptable
general representation; Role 3 exists to test restraint.
