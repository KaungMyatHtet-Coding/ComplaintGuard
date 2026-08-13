# ComplaintGuard Short-English Benchmark Specification

## 1. Purpose

This benchmark will measure six-department routing performance on short English
complaint text independently of any candidate-model design. It will provide a
fixed, privacy-safe comparison for the frozen v1 baseline and later approved
candidates; it is not training data.

## 2. Scope

The benchmark covers synthetic, single-intent, short English complaints that a
customer could submit to ComplaintGuard. It covers all six departments,
controlled language variation, ambiguity, confidence, and Manual Review
behavior. It does not evaluate Myanmar or mixed-language text, long narratives,
translation, customer identity, workflow handling, Firebase authorization, or
candidate training.

## 3. Protected six-label contract

The fixed repository order is:

1. `transfer_payment`
2. `account_support`
3. `card_atm`
4. `fraud_security`
5. `loan_credit`
6. `general_support`

Every baseline and candidate must use these exact IDs and the repository's
unchanged mapping. No benchmark-only label, including Manual Review, may be
added.

## 4. Definition of a short complaint

A short complaint is proposed as 3–20 whitespace-delimited words and 15–140
Unicode characters after the repository's NFKC, case-fold, and whitespace-
collapse classifier normalization. Both limits must pass. Text below either
minimum is not automatically invalid, but must be rejected or separately
approved with a documented reason; it must never be padded artificially.

Short does not mean empty or inadequate. Each complaint must state a concrete
problem and contain enough information for one department label. Greetings,
isolated product names, random tokens, and statements such as “help me” are
meaningless or insufficient and are excluded.

## 5. Proposed benchmark size

All values in this section are **proposed until owner approval**:

- 180 total examples, exactly 30 per department.
- Equal class balance; no class weighting changes the stored dataset.
- Per department: 10 easy, 12 medium, and 8 hard examples.
- Overall length distribution: 25% at 3–6 words, 50% at 7–13 words, and 25% at
  14–20 words, allowing at most a two-example rounding adjustment per label.

## 6. Inclusion rules

An example must be synthetic, non-sensitive English; express one actionable
complaint; satisfy the approved length rule; map to exactly one protected
department; sound plausible without private context; and pass privacy,
duplicate, leakage, author, and reviewer checks.

## 7. Exclusion rules

Exclude empty or meaningless text; multiple unrelated complaints; complaints
whose label requires unavailable private context; real personal or financial
data; text copied or paraphrased from protected final-test data; and text taken
from candidate-model outputs. Also exclude promotional text, commands to the
model, and unsupported-script or mixed-language content.

## 8. Ground-truth and single-label rules

Ground truth follows the documented Product/Issue-to-department intent policy,
not model output or keywords. The author records one intended department and a
brief rationale before prediction access. If two departments remain equally
valid after context-neutral review, rewrite the example to establish one
primary intent or reject it; do not resolve ties by consulting a classifier.

## 9. Ambiguity policy

Natural ambiguity is acceptable when a reasonable reader still identifies one
best department, especially for hard examples. Competing labels with no clear
winner are unacceptable. Rewrite when a small natural clarification produces a
single label without exposing a keyword recipe. Reject when clarification would
make the text unrealistic, exceed scope, or introduce private context.
`ambiguity_notes` records the plausible alternative, why the selected label is
still primary, and the review decision; use an empty string when none exists.

## 10. Natural-language variation

The set must include direct statements, informal phrasing, common
abbreviations, missing articles, varied sentence structures, and limited
realistic grammar mistakes. Variation must be planned across labels and
difficulty levels and must not target features or weaknesses of character
TF-IDF, transformers, translation, or any other candidate.

## 11. Typo and informal-language policy

Proposed proportions are 10% with one controlled typo, 10% with a common
abbreviation, and 15% with informal wording; categories may overlap, but no more
than 25% of the set may contain any of them. No example may contain more than
two deliberate deviations. Author and reviewer must confirm readability,
intent preservation, and neutral distribution across departments.

## 12. Difficulty levels

- **Easy:** explicit object and failure, with no credible competing department.
- **Medium:** intent is clear from ordinary context but uses paraphrase,
  omission, informal wording, or one plausible weak alternative.
- **Hard:** very concise or naturally indirect and requires combining available
  clues, while still having one reviewable correct label.

Difficulty describes human routing evidence, not baseline or candidate scores.

## 13. Dataset schema

The future UTF-8 dataset is proposed as JSON Lines with these fields:

| Field | Definition |
|---|---|
| `example_id` | Stable, label-neutral identifier. |
| `text` | Synthetic English complaint. |
| `expected_department` | One protected department ID. |
| `word_count` | Count after approved normalization and whitespace splitting. |
| `character_count` | Unicode code-point count after approved normalization. |
| `difficulty` | `easy`, `medium`, or `hard`. |
| `ambiguity_notes` | Review note or empty string. |
| `source_type` | Fixed value such as `synthetic_authored`. |
| `author` | Non-personal role or approved contributor identifier. |
| `reviewer` | Reviewer role/identifier, or disclosed delayed self-review. |
| `split` | `development` or `final`; see Section 19. |
| `duplicate_group` | Stable group ID for related wording, or empty string. |
| `approved` | Boolean sign-off state. |
| `benchmark_version` | Frozen semantic version. |
| `ground_truth_rationale` | Concise policy-based label justification. |
| `variation_tags` | Sorted controlled tags such as `typo` or `informal`. |
| `review_status` | `pending`, `approved`, `rewrite`, or `rejected`. |

Do not store names, contact details, account identifiers, credentials, or other
unnecessary personal information.

## 14. Stable ID format

Use `SEB-0001` through `SEB-NNNN`, assigned from the approved authoring ledger
before shuffling. IDs contain no department or split hint, are never reused,
and remain attached to the same text after freezing. A material pre-freeze
rewrite receives a new ID; post-freeze changes require an amendment version.

## 15. Authoring procedure

Approve the schema and quotas first. Author from department intent definitions
and variation/difficulty quotas without running any model. Record text, intended
label, rationale, and provenance in an access-controlled draft. Normalize and
validate mechanically, then perform privacy, ambiguity, duplicate, and leakage
reviews. Candidate predictions must remain unavailable until the benchmark is
approved and frozen.

## 16. Independent review and sign-off

The author proposes text and ground truth; a reviewer independently checks
intent, label, difficulty, privacy, and naturalness before seeing the author's
rationale where practical. Disagreement requires documented discussion and
rewrite or rejection; unresolved items cannot be approved. Approval requires
all fields valid, one defensible label, and every safety check passing.

For the current solo project, use a delayed blind self-review in a new session
with randomized order and hidden prior rationale, then request documented
mentor or official-team review where available. If another reviewer is
unavailable, disclose that limitation in the manifest; never describe delayed
self-review as independent review. Sign-off records reviewer role, date,
decision, version, and dataset hash.

## 17. Duplicate and near-duplicate detection

Check exact UTF-8 text equality and equality after NFKC, case-folding,
punctuation-to-space normalization, and whitespace collapse. Review near
duplicates using standard-library token sets, character n-grams, and sorted
similarity reports; no new dependency is required. Related retained variants
share `duplicate_group`. Exact/normalized duplicates are rejected, and no
duplicate group may cross development and final splits.

## 18. Leakage prevention

Do not copy from training, validation, or existing final-test examples; translate
evaluation examples into training data; reuse benchmark text during model
development; inspect candidate predictions while authoring ground truth; or
select examples to favor character TF-IDF, transformers, translation, or any
other candidate. Compare normalized hashes against locally available protected
partitions without exporting narratives. Record unavailable overlap checks as
limitations and block freezing until the owner accepts them.

## 19. Split and usage policy

The proposed 180 examples form a final held-out benchmark, not a development
set. If development examples are needed, create a separately authored and
versioned dataset before freezing; never carve them from a viewed final set.
Candidates may use development data repeatedly, but each approved finalist gets
one registered final-benchmark evaluation. Final results cannot tune features,
hyperparameters, calibration, thresholds, or example selection.

## 20. Hashing and freezing procedure

After approval, serialize one JSON object per line with UTF-8 without BOM,
sorted keys, compact separators, LF line endings, and a final LF. Sort rows by
numeric `example_id`. Compute SHA-256 over the exact file bytes. A separate
metadata manifest records file name, SHA-256, row and label counts, schema,
normalization, serialization, freeze date/timezone, version, Git commit, checks,
limitations, and sign-off. Freeze both files read-only/protected and prohibit
overwrite. This task creates neither dataset nor hash.

## 21. Metrics

Report accuracy, balanced accuracy where applicable, macro precision, macro
recall, macro F1, weighted F1 where useful, per-department precision/recall/F1,
the fixed-order confusion matrix, Manual Review coverage, accuracy among
automatically accepted predictions, error count, and categorized errors.
Accuracy alone can hide class-specific harm, abstention, and imbalance even in
a nominally balanced set.

## 22. Confidence and Manual Review evaluation

Use the unchanged operational threshold of `0.60` unless a separately approved
calibration study defines a development-only policy. Report automatic
acceptance count/coverage, Manual Review count/coverage, accuracy among accepted
predictions, incorrect accepted predictions (especially high-confidence
errors), and correct predictions unnecessarily sent to review. Confidence is
not described as calibrated probability.

## 23. Versioning

Use semantic benchmark versions such as `1.0.0`. Drafts are explicitly
unfrozen. Never silently change a frozen version; any byte or ground-truth
change produces a new version, manifest, hash, and result namespace.

## 24. Amendment policy

Log post-freeze errors in an append-only amendment record with affected ID,
discovery date, reason, impact, decision, and superseding version. Preserve the
original files and historical results. Re-evaluate candidates only under a
declared new version and retain version-to-version comparability notes.

## 25. Candidate-neutrality check

Before freezing, confirm:

- [ ] Authors did not view candidate predictions or scores.
- [ ] Quotas were fixed before candidate evaluation.
- [ ] Examples were derived from label policy, not architecture features.
- [ ] Variations and difficulty are distributed across all labels.
- [ ] No model-specific success or failure drove inclusion.
- [ ] Ground truth was decided without classifier assistance.
- [ ] Candidate names and outputs are absent from authoring records.
- [ ] Reviewer signed the neutrality declaration or the solo-review limitation.

## 26. Acceptance gate before candidate training

Candidate training must not begin until the schema, label mapping, example
counts, authoring/review procedure, and leakage checks are approved; the dataset
is created and reviewed; duplicate checks pass; dataset and manifest are
hashed; the benchmark version is frozen; Git state is clean; and explicit owner
approval is recorded. Short-English examples, benchmark freezing, and candidate
training remain not started under this specification task.

The specification and future benchmark must never contain real names, bank or
loan account numbers, card or transaction identifiers, passwords, PINs,
security codes, NRC numbers, phone numbers, email or home addresses,
authentication tokens, API keys, or private Firebase data. Only synthetic,
clearly non-sensitive text is permitted.
