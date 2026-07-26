# Day 9 Model Improvement and Frozen Model v1

## Status

Day 9 is complete. The frozen model remains TF-IDF plus Multinomial Naive Bayes. Candidate selection and confidence-threshold selection used validation data only; the selected candidate was evaluated on test exactly once. Day 8 remains the locked baseline and Day 10 has not started.

- Model version: `v1`
- Dataset version: `v1`
- Mapping version: `v1`
- Seed: `20260727`
- Selected candidate: `lower_alpha`
- Selected confidence threshold: `0.0`
- Generated model: `models/generated/cfpb_department_model_v1.joblib`
- Aggregate metrics: `data/processed/cfpb_model_v1_metrics.json`

## Fixed selection protocol

Day 9 recreated the exact Day 8 200,000-row seeded reservoir and normalized-narrative group split. Exact normalized duplicates therefore remain in one partition. The natural training, validation, and test partitions are unchanged from Day 8. Only training is capped by class.

Four candidates were declared before production:

| Candidate | N-grams | Alpha | Training cap | Validation macro-F1 |
|---|---|---:|---:|---:|
| `baseline_reference` | 1–2 | 1.0 | 30,000 | 0.706543 |
| **`lower_alpha`** | **1–2** | **0.5** | **30,000** | **0.710159** |
| `unigram_lower_alpha` | 1 | 0.5 | 30,000 | 0.704578 |
| `stronger_balance` | 1–2 | 0.5 | 20,000 | 0.704222 |

Each candidate evaluated the fixed thresholds `0.0`, `0.35`, `0.45`, `0.55`, and `0.65` on validation. Candidate and threshold selection maximized validation macro-F1 with declared candidate order as the deterministic tie-break. Test data was not transformed or predicted until selection finished.

The selected threshold was `0.0`: routing additional validation examples to `general_support` did not improve validation macro-F1. The artifact still exports the threshold and `general_support` fallback contract for later inference. Choosing operational manual-review behavior beyond this validated result remains later work.

## Data partitions and features

| Partition | Rows |
|---|---:|
| Selected sample | 200,000 |
| Natural training | 140,781 |
| Final capped training | 68,034 |
| Validation | 29,277 |
| Test | 29,942 |

The final vectorizer uses word-level `(1, 2)` n-grams, `min_df=3`, `max_df=0.98`, at most 100,000 float32 features, and sublinear TF. It was fitted only on final training text.

- Vocabulary size: 100,000; tokens are not published.
- Training matrix: `68,034 × 100,000`, 14,038,180 nonzeros.
- Validation matrix: `29,277 × 100,000`, 5,662,247 nonzeros.
- Test matrix: `29,942 × 100,000`, 5,689,550 nonzeros.
- Classifier: `MultinomialNB(alpha=0.5)`.

## Final test result and Day 8 comparison

| Metric | Day 8 baseline | Day 9 frozen v1 | Change |
|---|---:|---:|---:|
| Accuracy | 0.838989 | 0.827934 | -0.011055 |
| Balanced accuracy | 0.705094 | 0.736204 | +0.031110 |
| Macro-F1 | 0.688484 | 0.692345 | +0.003861 |

The project target is macro-F1 ≥ 0.70. **The frozen v1 model did not achieve the target.** The modest macro-F1 and balanced-accuracy improvements are reported alongside the reduced overall accuracy. No further experiment was run to force the target.

| Aggregate test metric | Value |
|---|---:|
| Accuracy | 0.827934 |
| Balanced accuracy | 0.736204 |
| Macro precision | 0.707515 |
| Macro recall | 0.736204 |
| Macro-F1 | 0.692345 |
| Weighted precision | 0.866300 |
| Weighted recall | 0.827934 |
| Weighted F1 | 0.837764 |

### Per-class metrics

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `transfer_payment` | 0.984000 | 0.436945 | 0.605166 | 563 |
| `account_support` | 0.658333 | 0.827990 | 0.733479 | 1,622 |
| `card_atm` | 0.547253 | 0.762634 | 0.637236 | 1,959 |
| `fraud_security` | 0.966249 | 0.850847 | 0.904883 | 21,736 |
| `loan_credit` | 0.588560 | 0.896842 | 0.710711 | 2,375 |
| `general_support` | 0.500693 | 0.641968 | 0.562597 | 1,687 |

### Fixed-order confusion matrix

Rows are true labels and columns use this order: transfer, account, card/ATM, fraud/security, loan/credit, general.

| True label | Transfer | Account | Card/ATM | Fraud | Loan | General |
|---|---:|---:|---:|---:|---:|---:|
| `transfer_payment` | 246 | 252 | 35 | 12 | 17 | 1 |
| `account_support` | 1 | 1,343 | 179 | 39 | 56 | 4 |
| `card_atm` | 0 | 140 | 1,494 | 198 | 102 | 25 |
| `fraud_security` | 2 | 255 | 890 | 18,494 | 1,080 | 1,015 |
| `loan_credit` | 0 | 30 | 67 | 113 | 2,130 | 35 |
| `general_support` | 1 | 20 | 65 | 284 | 234 | 1,083 |

All 29,942 supports, predictions, and confusion cells reconcile. Aggregate error patterns show improved minority recall but continued transfer/account confusion, broad card overlap, and fraud-to-general routing errors. No complaint narrative or row-level prediction is published.

## Frozen artifact and reproducibility

The ignored model is 13,311,363 bytes with SHA-256 `bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5`. It contains the fitted vectorizer, classifier, ordered labels, normalization contract, model/dataset/mapping versions, selected candidate configuration, threshold `0.0`, and fallback label.

Run from the repository root only when both versioned destinations are absent:

```powershell
.\.venv\Scripts\python.exe scripts/finalize_department_model.py `
  --input data/interim/cfpb/cfpb_training_v1.csv `
  --input-manifest data/processed/cfpb_training_v1_manifest.json `
  --baseline-metrics data/processed/cfpb_baseline_v1_metrics.json `
  --metrics data/processed/cfpb_model_v1_metrics.json `
  --model models/generated/cfpb_department_model_v1.joblib `
  --chunk-size 100000 `
  --max-rows 200000 `
  --seed 20260727
```

Candidate selection took 126.144 seconds, final test transformation 9.063 seconds, final test prediction 0.073 seconds, and the complete internal workflow 187.107 seconds.

## Privacy and limitations

- Tracked outputs contain aggregate configuration, counts, metrics, matrices, timings, and integrity metadata only.
- No narrative, vocabulary token, Complaint ID, row prediction, credential, or private absolute path is tracked.
- Proxy labels may not represent actual institutional department ownership.
- Training-only undersampling changes learned priors.
- Exact normalized duplicates are grouped, but near-duplicates are not detected.
- The bounded sample does not train on the full corpus.
- No Myanmar processing, translation, API integration, deployment, or Day 10 work is included.
