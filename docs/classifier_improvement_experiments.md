# Phase 2A classifier-improvement research

## Scope and integrity boundary

Phase 2A is validation-only research. It does not replace the frozen production
model, change routing, tune the `0.60` operational policy, or alter Day 18
evidence. The machine-readable source is
`evaluation/research/phase2a_classifier_experiments.json`.

The seed-`20260727` reservoir reconstructed exactly from the hash-verified
3,822,576-row mapped CSV: 140,781 original training rows, 29,277 original
validation rows, and 29,942 held-out test rows. Only the 140,781 original
training rows entered Phase 2A. Seed `20260810` assigned normalized-text groups
to 99,200 fit, 21,909 calibration, and 19,672 validation rows. Training-only
class capping reduced the fitted rows to 56,675. The original validation and
test narratives were neither transformed nor predicted.

The held-out test is protected but is not pristine: Day 9 evaluated it once,
Day 18 reconciled that evaluation, and the known Transfer & Payment defect now
informs the research question and acceptance gates. It must not be used to
choose among Phase 2A candidates.

## Inputs and labels

- Source snapshot: 17,034,951 raw CFPB records; 3,822,576 usable mapped
  narrative records in the ignored `cfpb_training_v1.csv`.
- Mapping: deterministic Product/Issue policy `v1`; narrative text never
  determines its own training label.
- Labels: `transfer_payment`, `account_support`, `card_atm`,
  `fraud_security`, `loan_credit`, and `general_support`.
- Transfer sources: `Money transfer, virtual currency, or money service`,
  legacy `Money transfers`, and `Virtual currency`, except explicit fraud,
  scam, or unauthorized-transaction overrides.
- Account sources: `Checking or savings account` and legacy
  `Bank account or service`, except explicit security overrides.
- Preprocessing: Unicode NFKC, case-folding, and whitespace collapse.
- Baseline features: word TF-IDF, 1–2 grams, `min_df=3`, `max_df=0.98`,
  `max_features=100000`, sublinear term frequency, float32.

Mapped-corpus imbalance is severe: Transfer & Payment has 85,180 examples
(2.23%), Account Support 198,831 (5.20%), and Fraud & Security 2,785,444
(72.87%). Original natural-training counts were 3,109 Transfer, 7,279 Account,
8,943 Card/ATM, 102,747 Fraud, 11,138 Loan/Credit, and 7,565 General.

## Duplicate and length audit

Exact normalized text groups cannot cross development partitions. The audit
found 112 exact normalized groups with conflicting labels; they remain grouped
but demonstrate noisy proxy labeling. A deterministic 2,000-by-2,000 character
4–5 gram sample found 189 validation items with a nearest fit similarity at or
above 0.90 and 127 at or above 0.95 (maximum 0.9991). This is a risk signal, not
an exhaustive near-duplicate count or proof of leakage.

Median normalized character lengths in the fit partition were: Transfer 660,
Account 881, Card/ATM 879, Fraud 629, Loan/Credit 1,022, and General 559.
Baseline validation macro-F1 was weakest for 0–100 characters (0.5167) and
101–300 characters (0.5546), versus 0.7113 for 301–1,000 characters. The
candidate results therefore do not establish reliable short-message behavior.

## Validation comparison

| Candidate | Macro-F1 | Weighted-F1 | Transfer recall | Account recall | Transfer→Account | Wrong ≥0.60 | Confirmed transfer |
|---|---:|---:|---:|---:|---:|---:|---|
| Word TF-IDF + MNB 0.5 | 0.675418 | 0.832567 | 0.387812 | 0.833959 | 171 | 2,045 | Account, 0.871971 |
| Word TF-IDF + ComplementNB 0.5 | 0.673531 | 0.826212 | 0.459834 | 0.862101 | 154 | 571 | Account, 0.452217; manual review at 0.60 |
| Word TF-IDF + balanced LR | 0.729799 | 0.836799 | 0.753463 | 0.871482 | 68 | 1,781 | Account, 0.513851; card regression fails |
| Word+char TF-IDF + balanced LR | 0.732861 | 0.838041 | 0.767313 | 0.863039 | 67 | 1,985 | Account, 0.531152; card regression fails |
| Word+char TF-IDF + LinearSVC | 0.747781 | 0.864596 | 0.720222 | 0.848968 | 77 | N/A | Account; decision score 0.634468; card regression fails |

LinearSVC values are decision scores, not probabilities. Its calibrated
validation analysis is separate from its native regression output.

## Baseline and strongest transfer-boundary candidate

| Department | Baseline P | Baseline R | Baseline F1 | ComplementNB P | ComplementNB R | ComplementNB F1 | Support |
|---|---:|---:|---:|---:|---:|---:|---:|
| Transfer & Payment | 0.985915 | 0.387812 | 0.556660 | 0.869110 | 0.459834 | 0.601449 | 361 |
| Account Support | 0.656573 | 0.833959 | 0.734711 | 0.624745 | 0.862101 | 0.724478 | 1,066 |
| Card & ATM | 0.563021 | 0.748339 | 0.642586 | 0.626926 | 0.690775 | 0.657303 | 1,355 |
| Fraud & Security | 0.958627 | 0.856517 | 0.904700 | 0.959747 | 0.847682 | 0.900240 | 14,148 |
| Loan & Credit | 0.579411 | 0.908218 | 0.707477 | 0.515536 | 0.925615 | 0.662232 | 1,667 |
| General Support | 0.495986 | 0.517209 | 0.506375 | 0.506809 | 0.484651 | 0.495483 | 1,075 |

Baseline confusion matrix (true rows, predicted columns in the stable label
order):

```text
[[140,171, 30,    3, 16,  1],
 [  1,889,110,   26, 40,  0],
 [  0, 80,1014, 164, 81, 16],
 [  1,186,575,12118,742,526],
 [  0, 19, 42,   70,1514,22],
 [  0,  9, 30,  260,220,556]]
```

ComplementNB confusion matrix:

```text
[[166,154, 18,    1, 21,  1],
 [  8,919, 74,   15, 49,  1],
 [  1,107,936,  149,147, 15],
 [ 15,245,426,11993,995,474],
 [  0, 27, 23,   58,1543,16],
 [  1, 19, 16,  280,238,521]]
```

## Boundary and feature findings

Common high-weight terms include `account`, `money`, `funds`, `bank`, and
generic function words. Account-distinguishing terms include `checking`,
`deposit`, `overdraft`, `fees`, `closed`, and `debit`; Transfer-distinguishing
terms include `cash app`, `cash`, `app`, and transfer-oriented phrases.

For the confirmed synthetic complaint, baseline contributions toward Account
include `banking`, `mobile`, `mobile banking`, `deducted`, and `account but`.
Transfer evidence includes `recipient`, `the recipient`, `money through`, and
`did not`.

Confirmed evidence supports several interacting causes: broad Product fallback
labels, substantial imbalance, 112 conflicting exact-text label groups, strong
shared account vocabulary, and insufficient representative transfer signal.
The claim that any one cause alone explains the defect remains a hypothesis.
No keyword override is proposed.

## Confidence and calibration

Raw MNB validation ECE was 0.054996 and multiclass Brier score 0.269041. Sigmoid
calibration on the separate calibration partition reduced these to 0.037377 and
0.221084. ComplementNB raw ECE/Brier were 0.087529/0.299698; calibration changed
them to 0.052339/0.215594. Calibration improved aggregate reliability measures
but increased ComplementNB wrong predictions at or above 0.60 from 571 to
1,056. Calibration does not fix the class boundary.

For the raw baseline, wrong predictions at or above 0.60/0.70/0.80/0.90 were
2,045/1,529/1,098/690. ComplementNB reduced them to 571/381/286/170, largely
because its raw probabilities are less extreme. These counts do not establish
a production threshold.

## Recommendation and limitations

No candidate qualifies under all declared gates. `word_complement_nb` is the
strongest transfer-boundary candidate:
Its Transfer recall improves by 0.0720 and Transfer→Account errors fall by 17;
macro-F1 regresses by 0.00189, Account recall improves, account/card regression
labels remain correct, and the confirmed transfer complaint is safely below
0.60. However, Loan & Credit F1 falls by 0.0452, exceeding the conservative
0.03 maximum per-class F1 regression gate. It therefore is not a finalist.

Candidate Loan and General F1 regressions, short-text performance remains weak,
near-duplicate risk is unresolved, labels are policy proxies, and the held-out
set has historical exposure. Phase 2B should refine the bounded development-only
search or mapping/data-quality strategy before locking any finalist. No held-out
evaluation is recommended yet. The production model, routing, threshold,
Myanmar manual-review policy, and strict xfail remain unchanged.

## Reproduction

```powershell
Set-Location D:\ComplaintGuard
.\.venv\Scripts\python.exe scripts\research_classifier_improvement.py `
  --input data\interim\cfpb\cfpb_training_v1.csv `
  --manifest data\processed\cfpb_training_v1_manifest.json `
  --output evaluation\research\phase2a_classifier_experiments.json
```

The output refuses overwrite. Remove or archive a prior research output only in
an explicitly approved rerun; never point this command at production artifact
locations.
