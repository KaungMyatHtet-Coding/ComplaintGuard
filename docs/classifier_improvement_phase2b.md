# Phase 2B Classifier Research

## Status

Phase 2B completed as development-only research. The predeclared 11-group
matrix expanded to 13 candidate runs because `CNB-SET` contained three
additional ComplementNB settings. No candidate passed every acceptance gate.
No finalist was named, and neither the original validation partition nor the
held-out test partition was transformed, predicted, or used for selection.

This is a successful rigorous research outcome: the bounded sparse TF-IDF
matrix did not provide an end-to-end production candidate under the declared
short-text and synthetic-safety gates. It does not establish a universal
performance ceiling for every sparse model, but it justifies a separately
authorized Phase 3 Dense Embeddings track using candidates such as FastText or
MiniLM.

The machine-readable outputs are:

- `evaluation/research/phase2b_classifier_experiments.json`
- `data/processed/phase2b_data_quality_audit.json`

Both outputs are aggregate-only and refuse overwrite.

## Locked protocol

The runner used dataset `v1` with SHA-256
`71a5ffda7914664a2b6803d92a6327bbe8e2438036e4420d3b30b95928241848`, the
seed-`20260727` reservoir, and the exact Phase 2A normalized-text grouping
contract. The original training partition contained `140,781` rows. The
Phase 2B development partitions were:

| Partition | Rows |
|---|---:|
| Fit | 99,200 |
| Calibration | 21,909 |
| Development validation | 19,672 |

The original validation partition (`29,277`) and held-out test partition
(`29,942`) remained protected. Vectorizers, classifiers, class weights,
training caps, and data transformations used fit rows only. Calibration was
performed after fitting and was not used for threshold selection.

## Matrix results

The Phase 2A MNB development baseline was macro-F1 `0.675418`, weighted-F1
`0.832567`, Transfer recall `0.387812`, Transfer→Account `171`, and
Account→Transfer `1`.

`T/A/C/F/L/G` in the table are per-class F1 values in the stable label order:
Transfer, Account, Card/ATM, Fraud, Loan/Credit, and General.

| Group | Candidate | Macro-F1 | Weighted-F1 | T/A/C/F/L/G F1 | Transfer recall | T→A | A→T | Fraud FPR/FNR | Loan F1 | Short 0–100 | Cal. ECE | Gates |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| MNB-0 | `mnb_0` | 0.675418 | 0.832567 | 0.556660/0.734711/0.642586/0.904700/0.707477/0.506375 | 0.387812 | 171 | 1 | 0.0947/0.1435 | 0.707477 | 0.516732 | 0.037377 | Fail |
| CNB-0 | `cnb_0` | 0.673531 | 0.826212 | 0.601449/0.724478/0.657303/0.900240/0.662232/0.495483 | 0.459834 | 154 | 8 | 0.0911/0.1523 | 0.662232 | 0.511810 | 0.052339 | Fail |
| LR-W | `lr_w` | 0.729799 | 0.836799 | 0.699229/0.787622/0.702952/0.886919/0.792433/0.509641 | 0.753463 | 68 | 44 | 0.0413/0.1903 | 0.792433 | 0.533268 | 0.039813 | Fail |
| LR-WC | `lr_wc` | 0.732861 | 0.838041 | 0.703046/0.785989/0.722118/0.886883/0.796674/0.502455 | 0.767313 | 67 | 46 | 0.0396/0.1909 | 0.796674 | 0.507595 | 0.043333 | Fail |
| HIER-WC | `hier_wc` | 0.768825 | 0.878592 | 0.706494/0.804016/0.759685/0.928331/0.823696/0.590731 | 0.753463 | 67 | 43 | 0.0862/0.1046 | 0.823696 | 0.580759 | 0.027296 | Fail |
| MNB-SW | `mnb_sw` | 0.647572 | 0.781167 | 0.568093/0.707503/0.590514/0.841000/0.747511/0.430809 | 0.404432 | 195 | 3 | 0.0364/0.2641 | 0.747511 | 0.467104 | 0.047086 | Fail |
| MNB-C15 | `mnb_c15` | 0.675177 | 0.828855 | 0.556660/0.735632/0.637788/0.899461/0.704704/0.516816 | 0.387812 | 174 | 1 | 0.0793/0.1574 | 0.704704 | 0.503387 | 0.034273 | Fail |
| CNB-SET | `cnb_set_alpha_01` | 0.666053 | 0.816959 | 0.606498/0.721674/0.660371/0.890322/0.659847/0.457605 | 0.465374 | 151 | 6 | 0.0864/0.1706 | 0.659847 | 0.510433 | 0.046544 | Fail |
| CNB-SET | `cnb_set_alpha_10` | 0.673464 | 0.829092 | 0.596364/0.724832/0.662143/0.903952/0.668258/0.485236 | 0.454294 | 156 | 8 | 0.0996/0.1432 | 0.668258 | 0.500515 | 0.054420 | Fail |
| CNB-SET | `cnb_set_norm_true` | 0.705848 | 0.853332 | 0.644295/0.726763/0.676779/0.922331/0.765969/0.498952 | 0.531856 | 143 | 13 | 0.1553/0.0922 | 0.765969 | 0.525752 | 0.032548 | Fail |
| DQ-EXACT | `dq_exact` | 0.684779 | 0.846600 | 0.553785/0.737017/0.669616/0.919524/0.728205/0.500526 | 0.385042 | 171 | 1 | 0.1282/0.1064 | 0.728205 | 0.530798 | 0.036293 | Fail |
| DQ-CONFLICT | `dq_conflict` | 0.674850 | 0.832843 | 0.553785/0.734105/0.641270/0.905185/0.709270/0.505484 | 0.385042 | 171 | 1 | 0.0956/0.1424 | 0.709270 | 0.511099 | 0.038879 | Fail |
| DQ-NEAR | `dq_near` | 0.684510 | 0.846984 | 0.553785/0.735967/0.670540/0.920152/0.729550/0.497067 | 0.385042 | 171 | 1 | 0.1331/0.1036 | 0.729550 | 0.520960 | 0.037393 | Fail |

The JSON artifact contains the complete per-class precision/recall/F1 values,
confusion matrices, word/character overlap metrics, all length buckets,
calibration Brier scores, wrong-high-confidence counts at `0.60`, `0.70`,
`0.80`, and `0.90`, and every synthetic regression result.

## Gate findings

- `LR-W`, `LR-WC`, and `HIER-WC` improved Transfer recall and reduced
  Transfer→Account errors, but exceeded the Account→Transfer or Fraud/Loan
  guardrails and/or failed synthetic safety cases.
- `CNB-0` reproduced the Phase 2A Transfer recall improvement but failed the
  weighted-F1, Loan/Credit F1, ECE, and short-text gates.
- `cnb_set_norm_true` exceeded macro-F1 `0.70` and improved both Transfer
  metrics, but its Fraud false-positive rate, Loan recall, and short-text
  improvement gates failed.
- Exact and near-duplicate sensitivity did not improve Transfer recall and did
  not meet the Transfer error gate.
- No candidate passed all gates. No threshold was optimized and no production
  artifact or routing behavior was changed.

The short-text and synthetic-safety failures are therefore retained as the
primary evidence for moving beyond this bounded sparse-feature search. Phase 3
must evaluate Dense Embeddings separately, with a new locked protocol and no
reuse of the held-out test for candidate development.

## Data-quality audit

The mapping audit processed all `3,822,576` mapped rows in 39 chunks using
Product and Issue only. Counts were:

| Mapping method | Rows |
|---|---:|
| Exact Product + Issue | 275,838 |
| Product fallback | 3,340,191 |
| General Support fallback | 206,547 |

Product-family and Issue-family aggregates, label counts, method-by-label
counts, missing-value counts, and source hashes are in
`data/processed/phase2b_data_quality_audit.json`. No Product/Issue relabeling
was performed.

Within original training development data, the audit found `3,732` exact
duplicate groups, `31,247` extra duplicate rows, and `112` conflicting-label
groups containing `3,658` rows. After the Phase 2A Fraud cap, the fit view had
`1,153` exact duplicate groups and `39` conflicting groups.

The fixed near-duplicate method was `char_wb` TF-IDF with 4–5 character grams,
cosine threshold `0.98`, disjoint reciprocal nearest-neighbor pairs, and
dropping the later SHA-256-sorted representative only for same-label pairs.
Conflicting near pairs were retained. On the capped fit view it found `886`
candidate pairs, collapsed `870` same-label pairs, retained `16` conflicting
pairs, and reduced the fit view from `46,442` exact-collapsed rows to `45,572`
rows. The separate 2,000-by-2,000 development-only risk sample found 189
validation items at similarity at least `0.90` and 127 at least `0.95`; this is
not exhaustive proof of semantic duplication.

## Reproduction

Run from the repository root only when a fresh Phase 2B artifact path is
approved; the runner refuses to overwrite existing outputs:

```powershell
.\.venv\Scripts\python.exe scripts/research_phase2b_classifier.py `
  --input data\interim\cfpb\cfpb_training_v1.csv `
  --manifest data\processed\cfpb_training_v1_manifest.json `
  --cleaned-source data\interim\cfpb\complaints_cleaned_corrected.csv `
  --cleaning-report data\cfpb_cleaning_corrected_report.json `
  --mapping data\mapping\cfpb_department_mapping_v1.json `
  --output evaluation\research\phase2b_classifier_experiments.json `
  --audit-output data\processed\phase2b_data_quality_audit.json
```

Focused tests passed: `12 passed`. Phase 2B did not run SMOTE, embeddings,
keyword overrides, per-class threshold tuning, held-out evaluation, or
production integration.
