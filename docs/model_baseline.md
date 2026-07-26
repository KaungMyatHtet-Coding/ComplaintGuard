# Day 8 TF-IDF + Multinomial Naive Bayes Baseline

## Status and scope

Day 8 is complete. This is the first transparent, reproducible baseline, not a tuned or deployed model. It uses dataset version `v1`, mapping version `v1`, and the six stable department IDs. Day 9 improvement and finalization have not started.

The source labels are deterministic Product/Issue policy proxies rather than verified institutional ground truth. Narrative text was not used to create those labels.

## Architecture and privacy

`scripts/train_department_baseline.py` is the source of truth:

1. Validate the completed Day 7 manifest and exact two-column CSV schema.
2. Validate all 3,822,576 source rows in 39 chunks.
3. Select a bounded 200,000-row uniform reservoir with seed `20260727`.
4. Normalize selected text with Unicode NFKC, case-folding, and whitespace collapse.
5. Assign each normalized-narrative group deterministically to train, validation, or test with SHA-256 and ratios 70%/15%/15%.
6. Apply a 30,000-row per-class cap only to training.
7. Fit word-level TF-IDF only on balanced training text.
8. Fit `MultinomialNB(alpha=1.0)`, then evaluate validation and test separately.
9. Publish the ignored model first and aggregate-only completed metrics last.

Exact normalized duplicate narratives cannot cross partitions because the split key is derived from normalized narrative text. Validation and test are never balanced or used to fit TF-IDF. The metrics contain no narrative, vocabulary token, Complaint ID, row-level prediction, or private absolute path.

## Data and sampling

| Partition | Rows |
|---|---:|
| Selected sample | 200,000 |
| Natural training partition | 140,781 |
| Balanced training used for fitting | 68,034 |
| Validation | 29,277 |
| Test | 29,942 |

The selected sample preserves the natural source imbalance:

| Label | Selected | Natural train | Balanced train | Validation | Test |
|---|---:|---:|---:|---:|---:|
| `transfer_payment` | 4,364 | 3,109 | 3,109 | 692 | 563 |
| `account_support` | 10,434 | 7,279 | 7,279 | 1,533 | 1,622 |
| `card_atm` | 12,774 | 8,943 | 8,943 | 1,872 | 1,959 |
| `fraud_security` | 145,716 | 102,747 | 30,000 | 21,233 | 21,736 |
| `loan_credit` | 15,918 | 11,138 | 11,138 | 2,405 | 2,375 |
| `general_support` | 10,794 | 7,565 | 7,565 | 1,542 | 1,687 |

Only `fraud_security` exceeded the training cap. This changes training priors but leaves validation and test representative of the selected natural sample. This is one fixed baseline experiment; no parameter was selected after viewing test results.

## Configuration and resource result

- TF-IDF: word analyzer, `(1, 2)` n-grams, `min_df=3`, `max_df=0.98`, `max_features=100000`, sublinear TF, float32, lowercasing disabled because normalization case-folds first.
- Vocabulary size: 100,000. Vocabulary tokens are not published.
- Sparse shapes: training `68,034 × 100,000`; validation `29,277 × 100,000`; test `29,942 × 100,000`.
- Classifier: `MultinomialNB(alpha=1.0)`.
- Generated model: `models/generated/cfpb_tfidf_mnb_baseline_v1.joblib`, 13,311,188 bytes, ignored and untracked.
- Aggregate metrics: `data/processed/cfpb_baseline_v1_metrics.json`, 10,506 bytes.

## Test metrics

| Metric | Value |
|---|---:|
| Accuracy | 0.838989 |
| Balanced accuracy | 0.705094 |
| Macro precision | 0.727508 |
| Macro recall | 0.705094 |
| **Macro F1** | **0.688484** |
| Weighted precision | 0.864468 |
| Weighted recall | 0.838989 |
| Weighted F1 | 0.844496 |

The project target is macro-F1 ≥ 0.70. **The Day 8 baseline did not achieve the target.** The result is retained without relabeling, hidden classes, test-driven parameter changes, or a second experiment.

### Per-class results

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `transfer_payment` | 0.987705 | 0.428064 | 0.597274 | 563 |
| `account_support` | 0.684037 | 0.768804 | 0.723948 | 1,622 |
| `card_atm` | 0.592608 | 0.728433 | 0.653538 | 1,959 |
| `fraud_security` | 0.954380 | 0.882591 | 0.917083 | 21,736 |
| `loan_credit` | 0.551078 | 0.904000 | 0.684739 | 2,375 |
| `general_support` | 0.595238 | 0.518672 | 0.554324 | 1,687 |

### Confusion matrix

Rows are true labels and columns are predicted labels in this fixed order: transfer, account, card/ATM, fraud/security, loan/credit, general.

| True label | Transfer | Account | Card/ATM | Fraud | Loan | General |
|---|---:|---:|---:|---:|---:|---:|
| `transfer_payment` | 241 | 223 | 46 | 18 | 34 | 1 |
| `account_support` | 1 | 1,247 | 212 | 59 | 102 | 1 |
| `card_atm` | 0 | 113 | 1,427 | 271 | 136 | 12 |
| `fraud_security` | 1 | 210 | 630 | 19,184 | 1,153 | 558 |
| `loan_credit` | 0 | 19 | 44 | 142 | 2,147 | 23 |
| `general_support` | 1 | 11 | 49 | 427 | 324 | 875 |

All 29,942 test supports, predictions, and confusion-matrix cells reconcile. Aggregate error patterns show low transfer recall and overlap among account, card, loan, and general proxy categories. No complaint text or row-level error example is published.

## Timings and environment

- Source validation and selection: 57.366 seconds
- TF-IDF fitting: 40.577 seconds
- Held-out transformation: 25.483 seconds
- Model training: 0.475 seconds
- Prediction: 0.236 seconds
- Pipeline total: 133.507 seconds
- Python 3.12.0, pandas 2.3.3, NumPy 2.5.1, scikit-learn 1.9.0, joblib 1.5.3

## Reproduction

Run once from the repository root after the ignored Day 7 dataset is available:

```powershell
.\.venv\Scripts\python.exe scripts/train_department_baseline.py `
  --input data/interim/cfpb/cfpb_training_v1.csv `
  --input-manifest data/processed/cfpb_training_v1_manifest.json `
  --metrics data/processed/cfpb_baseline_v1_metrics.json `
  --model models/generated/cfpb_tfidf_mnb_baseline_v1.joblib `
  --chunk-size 100000 `
  --max-rows 200000 `
  --train-per-class-cap 30000 `
  --seed 20260727 `
  --max-features 100000 `
  --min-df 3 `
  --max-df 0.98 `
  --alpha 1.0
```

Both destinations use overwrite protection. The ignored model is published before the completed aggregate metrics marker.

## Limitations and next step

- Product/Issue proxy labels may differ from real department ownership.
- The source is strongly imbalanced and selected from complaints with usable narratives.
- A 200,000-row bounded sample, not the full corpus, was used for fitting and evaluation.
- Training-only undersampling changes learned priors.
- Exact normalized duplicates are grouped, but near-duplicates are not detected.
- The baseline does not include translation, deployment, confidence routing, or application integration.
- Day 9 may investigate improvements only under separate authorization; final test-driven tuning is not part of this Day 8 result.
