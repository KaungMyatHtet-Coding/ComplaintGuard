# Day 7 Deterministic Department Label Mapping

## Status and versions

Day 7 is complete after the production v1 dataset build and verification.

- Mapping version: `v1`
- Dataset version: `v1`
- Corrected cleaning run: `e1996a2c34d0457fa08b83864b4f1a9d`
- Input rows: 3,822,576
- Output rows: 3,822,576
- Dropped rows: 0
- Production chunks: 39 at 100,000 rows per chunk

The reviewable policy is `data/mapping/cfpb_department_mapping_v1.json`. The execution logic is `scripts/cfpb_label_mapping.py`. The aggregate-only completion manifest is `data/processed/cfpb_training_v1_manifest.json`.

## Leakage boundary

The label is derived only from CFPB `Product` and `Issue`. `Consumer complaint narrative` is copied to the ignored training dataset as the future model input but is never accepted by the mapping function and never inspected to choose a label. `Complaint ID` is not read by the Day 7 pipeline.

This separation is mandatory: using narrative words to create the target would leak the future model input into label construction and invalidate later evaluation.

## Normalization and precedence

Product and Issue values use deterministic Unicode NFKC normalization, trimming, internal-whitespace collapse, and case-folding. There is no substring, fuzzy, inferred, or narrative-based matching.

Precedence is:

1. Exact normalized `Product` + `Issue` rule.
2. Exact normalized Product fallback.
3. `general_support`.

The manifest records which method labeled every row in aggregate:

| Method | Rows | Percentage |
|---|---:|---:|
| Exact Product + Issue | 275,838 | 7.216024% |
| Product fallback | 3,340,191 | 87.380630% |
| General Support fallback | 206,547 | 5.403346% |
| Total | 3,822,576 | 100.000000% |

## Department definitions

| Department ID | Mapping meaning |
|---|---|
| `transfer_payment` | Transfers, remittances, payment services, and virtual-currency movement |
| `account_support` | Deposit-account access, maintenance, opening, closing, and service support |
| `card_atm` | Credit, prepaid, debit-card, card-payment, and ATM support |
| `fraud_security` | Credit-reporting integrity, identity protection, scams, fraud, and unauthorized activity |
| `loan_credit` | Mortgage, student, vehicle, payday, personal, and consumer-loan servicing or repayment |
| `general_support` | Ambiguous, unresolved, missing, or newly observed Product/Issue combinations |

Exact fraud/security rules deliberately override otherwise clear transfer, account, card, or loan Product families when the Issue explicitly describes fraud, unauthorized activity, identity protection, privacy, or security controls. The complete exact rule list and a reason for each decision are in the policy JSON.

## Ambiguous and fallback decisions

The following observed Products intentionally use `general_support` unless an earlier exact pair rule applies:

- `Debt collection`: 200,915 fallback rows after explicit debt-not-owed and false-representation overrides.
- `Debt or credit management`: 5,340 fallback rows.
- `Other financial service`: 292 fallback rows.

No unexpected Product remained after applying v1. Missing Product and Issue counts were both zero. A future unseen or missing category will safely receive `general_support` and will be reported in the next manifest rather than crashing or silently disappearing.

These choices avoid concealing uncertain business ownership behind an overly broad label. They are reviewable proxy-label decisions, not claims about CFPB intent or ground-truth organizational routing.

## Production label distribution

| Department ID | Rows | Percentage |
|---|---:|---:|
| `transfer_payment` | 85,180 | 2.228340% |
| `account_support` | 198,831 | 5.201492% |
| `card_atm` | 241,219 | 6.310378% |
| `fraud_security` | 2,785,444 | 72.868244% |
| `loan_credit` | 305,355 | 7.988200% |
| `general_support` | 206,547 | 5.403346% |
| Total | 3,822,576 | 100.000000% |

The extreme `fraud_security` concentration largely reflects the retained CFPB credit-reporting taxonomy and Day 5 narrative-selection boundary. It is a major class-imbalance limitation for Day 8, not a model result. No model has been trained or evaluated.

## Dataset v1 schema and integrity

The ignored output is `data/interim/cfpb/cfpb_training_v1.csv` with exactly:

1. `Consumer complaint narrative` — PII-reduced Day 5 text retained only as future model input.
2. `department_label` — one of the six stable IDs.

Product and Issue are not retained because the reviewed mapping policy and aggregate manifest provide the audit trail without adding future label-source columns to model input. Complaint ID is excluded.

The completed output contains 3,822,576 rows, is 3,958,969,065 bytes, and has SHA-256 `71a5ffda7914664a2b6803d92a6327bbe8e2438036e4420d3b30b95928241848`. The full CSV remains ignored and untracked. The tracked manifest contains aggregate information only.

## Reproduction

Run from the repository root after the verified corrected Day 5 pair is available:

```powershell
python scripts/cfpb_label_mapping.py `
  --input data/interim/cfpb/complaints_cleaned_corrected.csv `
  --cleaning-report data/cfpb_cleaning_corrected_report.json `
  --mapping data/mapping/cfpb_department_mapping_v1.json `
  --output data/interim/cfpb/cfpb_training_v1.csv `
  --manifest data/processed/cfpb_training_v1_manifest.json `
  --chunk-size 100000
```

The builder refuses to overwrite either destination. It stages the dataset and manifest, validates row, schema, label, method, size, and hash reconciliations, publishes the full dataset first, and publishes completed aggregate metadata last. The manifest is the authoritative completion marker.

## Limitations

- Product/Issue proxy labels may not match a real institution's department ownership.
- Exact security overrides are policy decisions, not learned conclusions.
- Taxonomies can change; unseen values fall back rather than being guessed.
- Day 5 rejected rows without usable narratives, so v1 is a selected subset.
- The class distribution is strongly imbalanced.
- Myanmar translation, feature engineering, splitting, model training, and evaluation remain future work.
- Day 8 has not started and no accuracy, precision, recall, macro-F1, or confusion matrix exists.
