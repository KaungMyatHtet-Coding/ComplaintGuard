# Short-English Benchmark Blind Human-Review Guide

## Purpose and boundaries

This worksheet supports a delayed blind review of the 73 queued draft records.
It does not approve or freeze the benchmark. Do not use the ComplaintGuard
classifier, candidate models, predictions, confidence scores, or the sealed
reference while reviewing.

## How to complete the worksheet

1. Open `evaluation/model_hunting/short_english_benchmark_stage1b_review_worksheet.csv`
   in Excel or another spreadsheet editor.
2. Read only `complaint_text` and the neutral `review_reasons` for each row.
3. Choose the department that a normal complaint-management employee would use.
4. Enter exactly one `reviewer_decision`:
   - `approve`: the wording is usable and your chosen department is clear.
   - `revise`: the complaint intent is valid, but the wording needs correction.
   - `reject`: the record is inherently ambiguous, unrealistic, unsafe, or
     unsuitable.
   - `unsure`: you cannot confidently decide.
5. Always fill `reviewer_department` with one department ID or `unsure`.
6. For `revise`, put complete replacement wording in `revised_text`; do not
   enter only a fragment or editing instruction.
7. For `reject` or `unsure`, explain the reason in `reviewer_note`.
8. Do not open
   `evaluation/model_hunting/short_english_benchmark_stage1b_reference.json`
   during blind review. It contains the concealed source labels needed only for
   a later, separately approved reconciliation step.
9. Do not consult model predictions or run the application classifier.
10. Save the completed CSV without sorting, deleting, or adding rows. Preserve
    `review_order` and `record_id` exactly.

Typos and informal language are not automatically wrong, and hard examples are
not automatically rejected. Reject a record when two departments are equally
defensible. Revised text must preserve the original complaint intent, remain
3–20 words and 15–140 Unicode characters after normalization, and introduce no
real name, contact detail, account/card/loan/transaction identifier, password,
PIN, security code, NRC number, address, token, key, or other private data.

## Department guide

- `transfer_payment`: transfer, remittance, payment-service, or money-movement
  processing and receipt problems.
- `account_support`: deposit-account access, opening, closing, maintenance,
  statements, or ordinary account service.
- `card_atm`: debit, credit, or prepaid cards; card purchases; cash machines;
  withdrawals; activation; delivery; or card operation.
- `fraud_security`: unauthorized activity, scams, identity misuse, security or
  privacy controls, and credit-file integrity.
- `loan_credit`: mortgage, student, vehicle, personal, or other loan servicing,
  repayment, interest, escrow, payoff, or payment-plan problems.
- `general_support`: complaint-process, policy, response, or service questions
  with no more specific protected product department.

If the complaint genuinely fits two departments equally, use `reject`. If you
need more time or context to choose, use `unsure`; do not look at the sealed
reference for an answer.

## Neutral review reasons

- `hard_label_confirmation`: confirm that one department is still defensible.
- `ambiguity_review`: check whether two departments are equally plausible.
- `controlled_variation`: review intentional typo, abbreviation, or informal
  wording for readability without automatically correcting it.
- `unusual_length`: check that an unusually short or long valid record still
  communicates a complete complaint.
- `near_duplicate_review` or `cross_label_similarity_review`: compare wording
  only if those categories appear; do not infer a preferred answer.

The worksheet was shuffled deterministically with seed `20260814`. The shuffle
supports reproducibility but does not constitute review, approval, or freezing.
