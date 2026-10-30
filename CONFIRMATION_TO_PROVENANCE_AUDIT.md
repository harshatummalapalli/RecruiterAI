# Confirmation → Compiler Provenance Audit

**Date:** 2026-10-27 · Read-only. **No provider/model calls, no edits, no commits, no tests run.** This file is the only artifact created; nothing else was modified (the frozen experiment report and prior diagnosis are untouched).

---

## 1. Repository state

- Branch `claude/sleepy-clarke-5ueovf`, HEAD `fbd5626`, working tree clean.
- Components inspected (production + experiment): `backend/api.py`, `backend/services/{confirmation,search_translator,search_planner,search_compiler,source_provenance,structured_intent_extractor}.py`, `backend/models/structured_intent.py`, `backend/experiments/live_retrieval_ab/{harness,run_role3}.py`.

## 2. Field-by-field data-flow trace (title: "Senior Manager – FP&A and Business Finance")

### 2a. The PRODUCTION path (what a recruiter actually uses)

| Stage | Field / value | Kind | Provenance | Code |
|---|---|---|---|---|
| JD + notes | raw title string | source-verbatim | — | caller |
| Intake (Task A/B) | `role.posted_title` + `role.posted_title_source` | recruiter-stated, source-tagged | preserved as a tagged value | `intake_reasoning.py` ("Use it verbatim as posted_title") |
| Confirmation | recruiter edits whitelisted (`include_titles`/`exclude_titles`/seniority…); server builds an **immutable, content-hashed** snapshot | recruiter-confirmed | preserved in `ConfirmedHiringIntent` | `confirmation.py`; `build_confirmed_hiring_intent` carries `posted_title`, `posted_title_source` ([search_translator.py:301-302](backend/services/search_translator.py#L301-L302)) |
| `/search` | `to_search_intent(confirmed)` → legacy `SearchIntent`; `SearchPlanner.build(intent)` | recruiter-confirmed values | `posted_title_source` tag retained ([search_translator.py:371-372](backend/services/search_translator.py#L371-L372)) | [api.py:761,780-781](backend/api.py#L761) |
| Provider query | `SearchPlanner` plan (titles + natural-language query) | — | — | `search_planner.py` |

**The production path never calls `compile_intent`.** `compile_intent` is not imported in `api.py`; `/search` runs the legacy `SearchIntent` + `SearchPlanner`.

### 2b. The EXPERIMENT path (what produced the FP&A diagnosis)

| Stage | Field / value | Kind | Provenance | Code |
|---|---|---|---|---|
| JD + brief | role title | source-verbatim | — | `run_role3.py` |
| Extraction | `StructuredHiringIntent.role_family = ["FP&A and Business Finance Manager"]` | **model-reconstructed** (meaning-normalized, not verbatim) | none stored on the atom (the model carries **no `basis` field** — [structured_intent.py:166-185](backend/models/structured_intent.py#L166-L185)) | `structured_intent_extractor.py` |
| Compile (retrieval tree) | `compile_intent(exp_intent)` — **no `sources` argument** | — | **lost here** | [run_role3.py:98](backend/experiments/live_retrieval_ab/run_role3.py#L98) |
| Compile (eval intent) | `compile_intent(experimental_intent)` — **no `sources`** | — | **lost here** | [harness.py:160](backend/experiments/live_retrieval_ab/harness.py#L160) |
| `role_family()` | provenance = `"absent"` → `_blocked` → title **withheld**; `retrieval_title_family = []` | — | — | [search_compiler.py:720-742](backend/services/search_compiler.py#L720-L742) |
| Provider query | no title / no topical leaf | — | — | — |

## 3. The exact reason the FP&A title was omitted

Provenance in this compiler is **not** a stored field; it is **re-derived at compile time by matching the value against `SourceTexts` (JD + recruiter brief)** (`prov()`, [search_compiler.py:450-473](backend/services/search_compiler.py#L450-L473); docstring: *"with no text to check… ABSENT in an intent that records provenance"*).

The experiment called `compile_intent(exp_intent)` **without `SourceTexts`**. The builder therefore set `self.sources = None` ([line 383](backend/services/search_compiler.py#L383)). With `self.sources is None`, `prov(title=True)` skips every source-matching branch and returns state `"absent"` ([lines 462-473](backend/services/search_compiler.py#L462-L473)). `role_family()` withholds any title whose provenance is `_blocked`, so `retrieval_title_family = []` and no title leaf is emitted.

**Primary cause: the compiled plan was built with no source texts, so the title's provenance was `absent` by construction** — independent of wording. **Secondary cause:** even had `SourceTexts` been supplied, `role_family = "FP&A and Business Finance Manager"` is a model reconstruction that `classify_title` would not find stated verbatim in the JD ("Senior Manager – FP&A and Business Finance") → still `absent`. Both roads lead to the title being withheld.

## 4. Does confirmation already provide the required provenance?

**No — and not for the compiler at all.**

- Confirmation produces a **legacy `SearchIntent`** on the **production** path. It preserves `posted_title` + `posted_title_source` and the recruiter's whitelisted edits, but it is **never handed to `compile_intent`**.
- The compiler derives provenance from **source text**, not from a "recruiter confirmed this" flag. There is **no contract** that treats a recruiter-confirmed value as a trusted `SourceText`.
- **What confirmation authorizes:** the executable **values** of the legacy intent (through the `ConfirmationEdits` whitelist) plus the Search Boundary — i.e. the *source/value*, bound into an immutable snapshot. It does **not** authorize *meaning* for the compiler, and it does not feed the compiler's provenance gate. So confirmation currently authorizes **the value on the legacy path only**.
- The same confirmed information **does** reach the legacy natural-language retrieval path (it *is* that path), which carries topical FP&A terms in its NL query — consistent with legacy out-retrieving compiled in the experiment.

## 5. Smallest justified fix — classified (NOT implemented)

This is **not a compiler bug.** The compiler honored its documented contract: no source text ⇒ `absent` ⇒ conservatively no hard title filter.

The finding is a combination of:
- **Path mismatch (primary):** the StructuredHiringIntent compiler is **experiment-only**; production uses the legacy path. Fixing compiler title-provenance would **not change what recruiters receive today.**
- **Missing data-flow connection (in the experiment):** `compile_intent` was called without `SourceTexts`.
- **Provenance-contract limitation:** no mechanism treats a recruiter-confirmed title as a compiler source.
- **Not** an intake extraction error (extraction produced a valid, meaning-normalized `role_family`), **not** solely a provider-capability limitation.

Three options, smallest first:

1. **No change (recommended for product).** The compiler is not the product path. The production legacy path already carries the recruiter-confirmed `posted_title` (+ source tag) and an NL topical query, and retrieved better in the experiment. For product readiness, nothing here needs fixing.
   - *Before/after:* unchanged. *Offline-testable:* n/a. *Recall risk:* none.
2. **Experiment-wiring only.** Pass `SourceTexts(jd, recruiter_brief)` into `compile_intent(...)` in `compiled_single_path_intent`/`run_role3`.
   - *Affected:* experiment call site, not product. *Before:* title `absent`. *After:* title provenance is evaluated against JD/brief — **may still be `absent`** because `role_family` is a reconstruction. *If it did resolve:* the compiler emits a **hard current-title filter** ([search_compiler.py:731,741-742](backend/services/search_compiler.py#L731)) → **recall risk** (off-title FP&A people excluded). *Offline-testable:* yes. *Verdict:* does not advance product; low value.
3. **Make the compiled path production (large, strategic — not a fix).** Wire `compile_intent` into `api.py`, feed it `SourceTexts`, and decide whether a recruiter-confirmed `posted_title` (which already has `posted_title_source`) should count as a trusted compiler `SourceText`. This is a design decision with recall implications, **not** a small change, and must not be done on the assumption that exact-title filtering is safe.

**Confirmation approves the intended role; it does not make exact-title filtering safe.** Option 3's title leaf is a hard filter.

## 6. Required offline regression tests (if a change were later approved)

- `tests/test_search_compiler.py`, `tests/test_compiler_audit.py`, `tests/test_requirement_provenance.py` — title/role_family provenance and withholding behavior. (Inspected as definitions; **not run.** They exercise the compiler on in-memory intents; a provenance test that passes `SourceTexts` would assert: title stated in sources ⇒ `retrieval_title_family` non-empty; not stated ⇒ empty. No external calls in these definitions, but I did not execute them.)
- For Option 2: a test asserting `compile_intent(intent, SourceTexts(jd=...))` resolves/withholds the title as expected, and that a resolved title produces a hard-title leaf (documenting the recall risk).
- `tests/test_real_judge_validation.py` and any `*live*` tests are **opt-in and call paid models** — do **not** run them for this.

## 7. Known limitations & remaining uncertainty

- I did not execute any tests; behavioral claims are from reading code + the documented contract (and consistent with the observed FP&A omission).
- I did not exhaustively confirm the literal membership of the `_BLOCKING` set; the `absent` → withheld path is inferred from `prov()`'s return, `role_family()`'s `_blocked` filter, and the observed outcome.
- Whether the compiled path is *intended* to become production is a product decision outside this trace.

## 8. Recommendation

**Make no change, and do not treat "fix the confirmed-title gap" as the next task.** The audit shows the premise was slightly off: the compiler is not the production path, and the FP&A title omission was largely an **experiment-wiring artifact** (compiling with no `SourceTexts`) layered on a **correctly conservative** provenance gate — not a lost confirmed-title connection in the product.

The productive next seam is the **legacy production path** (confirm → `SearchIntent` → `SearchPlanner` → provider + Judge), which already preserves the recruiter-confirmed title and topical query. Investigate/productize that, rather than patching the experiment-only compiler. Any move to make the compiled path production is a separate, explicitly-scoped design decision with recall implications — not a small fix.

*Stopping here. No changes will be made without explicit authorization.*
