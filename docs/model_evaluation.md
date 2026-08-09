# Day 18 Real Model Evaluation and Dataset Evidence

## Status and evidence boundary

Day 18 reproduces the frozen ComplaintGuard model-v1 evaluation without fitting,
tuning, or replacing the model. The evaluator validates the model SHA-256,
reconstructs the original deterministic sample and partitions, transforms only
the held-out test narratives, and requires every recalculated metric to equal
the locked Day 9 evidence before publishing.

- Model: TF-IDF plus `MultinomialNB(alpha=0.5)`
- Model, dataset, and mapping versions: `v1`
- Random seed: `20260727`
- Selected sample: 200,000 records
- Held-out test set: 29,942 records
- Model retrained on Day 18: no
- Locked Day 9 metrics reconciled: yes
- Project macro-F1 target: 0.70
- Actual test macro-F1: 0.692345; target not achieved

The authoritative machine-readable artifact is
`evaluation/day18/model_evaluation_v1.json`, schema version 1.

## Dataset pipeline

| Pipeline stage | Records | Meaning |
|---|---:|---|
| Raw CFPB snapshot | 17,034,951 | All rows in the immutable 20 July 2026 snapshot |
| Raw rows with non-null narrative | 3,823,413 | Availability count before usability checks |
| Usable cleaned narratives | 3,822,576 | Rows retained after required-field, narrative, and provenance validation |
| Successfully mapped records | 3,822,576 | Rows assigned one of six proxy department labels; zero mapping drops |
| Selected modeling sample | 200,000 | Fixed seeded uniform reservoir over mapped records |
| Natural training partition | 140,781 | Pre-cap training partition |
| Training records actually fitted | 68,034 | Training-only 30,000-per-class cap applied |
| Validation partition | 29,277 | Used during Day 9 candidate and model-threshold selection |
| Held-out test partition | 29,942 | Used only for final evaluation and Day 18 evidence reproduction |

The raw snapshot contained 13,211,538 null narratives. The cleaner rejected
13,210,233 rows for a missing or unusable narrative after applying rejection
precedence; it also rejected 2,135 invalid Complaint IDs and seven missing
Issues. No identical Complaint-ID duplicate was found. These categories are
mutually exclusive, so the non-null count must not be confused with the final
usable count.

Department labels are deterministic Product/Issue policy proxies. Narrative
text is never read to create a label. All 3,822,576 usable records were mapped:

| Department | Mapped records | Share |
|---|---:|---:|
| Transfer & Payment | 85,180 | 2.228340% |
| Account Support | 198,831 | 5.201492% |
| Card & ATM | 241,219 | 6.310378% |
| Fraud & Security | 2,785,444 | 72.868244% |
| Loan & Credit | 305,355 | 7.988200% |
| General Support | 206,547 | 5.403346% |

These percentages are calculated from the recorded counts. The extreme Fraud
& Security concentration is a major limitation, not evidence that this class
is intrinsically more important.

## Cleaning, preprocessing, sampling, and leakage prevention

Day 5 normalizes narratives with Unicode NFKC and collapsed whitespace, removes
URLs, and conservatively redacts obvious email, long-number, and phone-like
patterns. The output remains PII-reduced rather than anonymous.

The Day 8/9 modeling pipeline then applies NFKC, case-folding, and whitespace
collapse. It selects a single-pass uniform reservoir using seed `20260727`.
Each exact normalized narrative is assigned to train, validation, or test by a
SHA-256 function of the seed and narrative. Consequently, exact normalized
duplicates cannot cross partitions. Near-duplicates are not detected.

Only training data is capped and only the resulting 68,034 training rows fit
the TF-IDF vectorizer and classifier. Validation and test retain their natural
sample distributions. Day 18 loads the already-fitted vectorizer and classifier
and calls only `transform` and `predict_proba`; it never calls `fit`. Test data
was not used for feature fitting, model selection, or confidence-threshold
selection.

Day 18 analysis is a post-finalization audit of the already reported test set.
Its findings must not be used to tune model v1 or choose a replacement model.

## Actual held-out results

| Metric | Result |
|---|---:|
| Accuracy | 0.827934 |
| Macro precision | 0.707515 |
| Macro recall | 0.736204 |
| Macro F1 | 0.692345 |
| Weighted precision | 0.866300 |
| Weighted recall | 0.827934 |
| Weighted F1 | 0.837764 |

### Per-department results

| Department | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Transfer & Payment | 0.984000 | 0.436945 | 0.605166 | 563 |
| Account Support | 0.658333 | 0.827990 | 0.733479 | 1,622 |
| Card & ATM | 0.547253 | 0.762634 | 0.637236 | 1,959 |
| Fraud & Security | 0.966249 | 0.850847 | 0.904883 | 21,736 |
| Loan & Credit | 0.588560 | 0.896842 | 0.710711 | 2,375 |
| General Support | 0.500693 | 0.641968 | 0.562597 | 1,687 |

### Confusion matrix

Rows are true departments and columns are predicted departments in the fixed
order Transfer, Account, Card/ATM, Fraud, Loan, General.

| True department | Transfer | Account | Card/ATM | Fraud | Loan | General |
|---|---:|---:|---:|---:|---:|---:|
| Transfer | 246 | 252 | 35 | 12 | 17 | 1 |
| Account | 1 | 1,343 | 179 | 39 | 56 | 4 |
| Card/ATM | 0 | 140 | 1,494 | 198 | 102 | 25 |
| Fraud | 2 | 255 | 890 | 18,494 | 1,080 | 1,015 |
| Loan | 0 | 30 | 67 | 113 | 2,130 | 35 |
| General | 1 | 20 | 65 | 284 | 234 | 1,083 |

The largest absolute errors occur in the majority Fraud & Security class,
particularly Fraud to Loan and Fraud to General. Transfer precision is very
high but recall is low: 252 of 563 true Transfer records were predicted as
Account. This illustrates why accuracy alone is insufficient.

## Confidence analysis

Prediction confidence is the maximum MultinomialNB class probability for one
record. It is not calibrated probability that the prediction is correct. The
Day 17 `0.60` threshold is an operational routing policy, not the frozen
model's validation-selected threshold and not a Day 18 optimization.

- Minimum confidence: 0.231700
- Median confidence: 0.991329
- Mean confidence: 0.891257
- Maximum confidence: 1.000000
- Below 0.60: 3,235 records (10.8042%); 1,249 correct and 1,986 incorrect
- At or above 0.60: 26,707 records (89.1958%); 23,541 correct and 3,166 incorrect

High confidence therefore does not guarantee correctness. Complete fixed-bin
counts and empirical accuracy per bin are in `confidence_analysis.json`.

## Correct and misclassified examples

The evaluation artifact contains 12 deterministically selected correct records
and 12 deterministically selected misclassified records. Each includes an
opaque example ID, true department, predicted department, confidence, and
normalized character count. It deliberately contains no real consumer text or
Complaint ID because cleaned CFPB narratives are not anonymous. These records
are real held-out outcomes, while any narrative shown later in a presentation
must be clearly labeled synthetic and must not be counted as evaluation data.

## Metric meanings

- **Accuracy:** fraction of all held-out records classified correctly. It is
  dominated by common classes when the data is imbalanced.
- **Precision:** among records predicted as a department, the fraction whose
  proxy label is that department.
- **Recall:** among records with a department proxy label, the fraction found by
  the model.
- **F1:** harmonic mean of precision and recall.
- **Macro average:** unweighted mean across the six departments. Every
  department contributes equally.
- **Weighted average:** class metric mean weighted by held-out support. Large
  departments contribute more.
- **Support:** number of held-out records with a given true label.
- **Confusion matrix:** counts for every true-label/predicted-label pair.
- **Prediction confidence:** maximum class probability for one prediction; not
  overall model quality and not calibrated reliability.
- **Historical similarity:** cosine proximity between one complaint's TF-IDF
  vector and indexed historical vectors; not a probability and not confidence.

## Historical similarity foundation

Day 18 builds the ignored local artifact
`models/generated/cfpb_similarity_test_v1.joblib`. It uses the frozen model-v1
TF-IDF vectorizer and contains the sparse vectors, proxy department labels, and
opaque IDs for exactly 29,942 held-out historical narratives. It contains no
narrative strings or Complaint IDs.

An incoming complaint is normalized using the classifier contract, transformed
by the same frozen vectorizer, and compared by sparse cosine similarity. The
query result returns rank, cosine score, proxy department, and opaque historical
ID only. Coverage is 29,942 records, not the 3.8-million mapped corpus and not
the 17-million-row raw snapshot. The index is local and Git-ignored; a Day 19 UI
may consume the tracked metadata immediately, but live similarity requires the
runtime index to be explicitly packaged and loaded.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_department_model.py `
  --input data/interim/cfpb/cfpb_training_v1.csv `
  --input-manifest data/processed/cfpb_training_v1_manifest.json `
  --model models/generated/cfpb_department_model_v1.joblib `
  --locked-metrics data/processed/cfpb_model_v1_metrics.json `
  --snapshot-profile data/cfpb_snapshot_profile.json `
  --cleaning-report data/cfpb_cleaning_corrected_report.json `
  --output-dir evaluation/day18 `
  --similarity-index models/generated/cfpb_similarity_test_v1.joblib `
  --max-rows 200000 `
  --seed 20260727 `
  --chunk-size 100000
```

The successful local run took approximately 86 seconds including the full
source scan, held-out transformation, metric reconciliation, index compression,
and publication. The evaluator refuses to overwrite either output destination.

## Verification evidence

- Full data/ML script suite with the global environment that contains the
  declared Day 6 plotting dependency: 229 passed.
- Root-virtual-environment ML/evaluation/cleaning/mapping subset: 202 passed.
- Backend: 102 passed and seven emulator-dependent tests skipped.
- Frontend: 44 passed.
- Ruff check and format check for all Day 18 Python files plus `ml-api/app`:
  passed; 17 files were already formatted.
- TypeScript strict check: passed.
- ESLint: passed.
- Day 18 artifact schema, reconciliation, and narrative-absence validation:
  passed.
- `git diff --check`: passed.

A broader Ruff command over every historical script and backend test reports
pre-existing import-order, formatting, one broad-exception, and one duplicate
parameterized-case finding in untouched Day 5/17 files. Day 18 does not rewrite
those unrelated historical files. The root virtual environment also lacks the
already-declared `matplotlib` dependency needed to collect Day 6 EDA tests; the
complete 229-test script suite therefore ran with the existing global Python
environment (`matplotlib 3.10.0`) without installing anything.

## Limitations

- Labels are deterministic policy proxies and may differ from real company
  department ownership.
- The model uses a bounded 200,000-record sample, not all mapped records.
- Class imbalance makes accuracy and weighted metrics look stronger than
  minority-class performance.
- Training-only undersampling changes learned class priors.
- Exact duplicate leakage is prevented; near-duplicate leakage remains possible.
- Naive Bayes confidence is uncalibrated.
- Public artifacts omit consumer narrative text, limiting qualitative review.
- Similarity currently covers 29,942 vectors and is not deployed.
- English held-out evaluation does not establish Myanmar routing quality.
