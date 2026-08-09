# Mobile-transfer routing reconciliation

## Scope and frozen evidence

This maintenance audit is diagnostic only. It does not change, retrain, tune, or
replace the frozen model, mapping, routing threshold, Day 18 artifact, or held-out
test set. The inspected model SHA-256 matched the committed runtime contract:

`BAFC086FE5B11BDCC5CBC4F04F3F3F222DE8CBAD27FE66D62A6685CC30F953D5`.

## Reconciled emulator ticket

A read-only search of the already-running local Firestore Emulator found one
matching synthetic ticket:

- Ticket ID: `ticket_eebca6ce95f1c80d2550d18cf7ecda06`
- Text: “I transferred money through the mobile banking application. The amount
  was deducted from my account, but the recipient did not receive it. Customer
  support has not resolved the issue.”
- Stored prediction: `account_support`
- Stored confidence: `0.8342084895220766`
- Stored/current department: `account_support`
- Routing source: `model`
- Model version: `v1`
- Detected language: `en`
- Routing-event timestamp: `2026-08-09T12:25:03.198Z`
- Review/translation fields: no `reviewRequired` field and no translated text;
  `manualReviewReason` is null.

Read-only inference of the exact stored text with the current hash-verified
artifact reproduced the same department and confidence. This confirms that the
reported approximately 83.4% result belonged to the longer complaint, not the
three-word phrase `Mobile transfer failed`. It provides no evidence of a stale UI
or a mismatched runtime model for this ticket.

The customer dashboard does retain the previous `ticketDetail` until the queued
fetch for a newly selected ticket begins and completes. That creates a possible
brief stale-detail transition in the UI. It should be addressed as later UI/UX
work, but it does not explain this observation because the inspected ticket,
stored confidence, routing event, and current inference reconcile exactly.

The exact three-word phrase produces `account_support` at approximately
`0.355232` and `transfer_payment` at approximately `0.311258`. The authenticated
`/tickets` routing policy therefore leaves it unassigned with
`routingSource=manual_review` under the operational `0.60` threshold.

The longer complaint exposes a confirmed frozen-v1 classification defect: clear
transfer intent can be routed to Account Support with high uncalibrated
confidence. Confidence is not a probability of correctness. The Day 18 held-out
matrix independently records 252 of 563 true Transfer & Payment examples as
Account Support, versus 246 correct Transfer & Payment predictions.

## Safe diagnostic procedure

Use only an already-running local emulator. Do not start an empty emulator to
look for a stopped session, and do not run the Firebase test harness against
valued demo data.

1. Confirm `127.0.0.1:8185` and `127.0.0.1:9099` are reachable.
2. Verify the frozen artifact with `Get-FileHash` against the runtime hash above.
3. Query `tickets` read-only and match normalized complaint text for `mobile
   transfer`, `transfer failed`, or `mobile banking`.
4. Read the ticket and `tickets/{ticketId}/events/model_v1_routing`; never write
   a diagnostic result back to Firestore.
5. Compare the exact stored, PII-reduced complaint with the frozen classifier.
6. Reconcile `predictedDepartmentId`, `predictionConfidence`, `departmentId`,
   `routingSource`, `predictionModelVersion`, detected language and event time.

If no ticket exists, reproduce later with a new synthetic customer action only
after explicit approval. Never fabricate the missing ticket or result.
