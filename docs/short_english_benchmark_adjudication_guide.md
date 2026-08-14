# Stage 1B Human Adjudication Guide

## Purpose and boundary

This local interface supports human adjudication of the ten Stage 1B authored-
label versus blind-review disagreements. It writes only to the ignored local
working copy. It does not modify the committed disagreement queue or draft
benchmark, approve a record, freeze a benchmark, or run a model.

Both label proposals are visible because controlled unsealing is complete.
Neither is automatic ground truth. Make no decision from keywords alone, and do
not consult classifiers, predictions, confidence scores, or external services.

## Start the interface

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_stage1b_adjudication_app.py
```

Open Firefox locally at:

<http://127.0.0.1:8767/>

To use another local port, stop the server with `Ctrl+C` and pass, for example,
`--port 8877`. The application always binds to `127.0.0.1`; it does not expose
the interface to the network or load external assets.

Progress is stored only in:

`../evaluation/model_hunting/short_english_benchmark_stage1b_completed_adjudication.json`

The exact path is ignored by Git. The app creates it from the committed source
only when absent, resumes it when present, validates immutable content on every
load, and saves by atomic replacement in the same directory.

## Decisions

- `keep_original`: retain the authored department; revised text stays empty.
- `use_reviewer`: use the delayed blind-review department; revised text stays
  empty.
- `revise_and_relabel`: select one of the six departments and supply revised
  text of 3–20 words and 15–140 normalized characters.
- `remove_from_benchmark`: use `unresolved`, leave revised text empty, and
  explain why the draft example is unsuitable.
- `needs_second_review`: use `unresolved`, leave revised text empty, and explain
  the remaining ambiguity.

Every completed decision requires an adjudication note. Human-entered text must
not contain secrets, credentials, contact information, real financial
identifiers, or user-specific absolute paths. The interface does not permit
record deletion, insertion, reordering, or edits to complaint text, either
label proposal, difficulty, review reasons, or variation flags.

## Neutral department guide

- `transfer_payment`: transfer or payment delivery, pending or failed payment.
- `account_support`: login, access, verification, profile, account settings.
- `card_atm`: card operation, ATM, withdrawal, retained or activated card.
- `fraud_security`: unauthorized activity, scam, compromised access, suspicious
  transaction.
- `loan_credit`: loans, repayment, installments, borrowing, credit reporting.
- `general_support`: a clear support problem not fitting the other five.

## Boundary reminders

- Account-access inconvenience alone generally indicates `account_support`.
- Evidence of unauthorized access, takeover, suspicious activity, or security
  compromise generally indicates `fraud_security`.
- Mentioning a card or transfer does not automatically determine the label; use
  the complaint's primary harm.
- Do not use `general_support` merely because an example is difficult.
- If both labels remain equally defensible, choose `needs_second_review`.
- Do not force a final label when genuine ambiguity remains.

Completing the local working copy is not benchmark approval or freezing. A later
separately authorized reconciliation step would be required to apply any human
decision to the draft benchmark.
