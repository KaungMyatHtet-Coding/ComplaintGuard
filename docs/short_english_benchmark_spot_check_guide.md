# Stage 1B Reviewed-Candidate Spot Check

This local interface supports the pending 12-record human spot check recorded in
the Stage 1B application report. It saves answers only to the ignored local file
`evaluation/model_hunting/short_english_benchmark_stage1b_completed_spot_check.json`.
It does not modify, approve, version, or freeze the reviewed candidate.

## Start the interface

From the repository root in PowerShell, run:

```powershell
.\.venv\Scripts\python.exe scripts/run_stage1b_spot_check_app.py
```

Open <http://127.0.0.1:8769/> in Firefox. An optional port override is limited to
the local listener, for example:

```powershell
.\.venv\Scripts\python.exe scripts/run_stage1b_spot_check_app.py --port 8770
```

The server always binds to `127.0.0.1`. Candidate, source, report, evidence, and
working-copy paths are fixed repository paths. The CLI intentionally provides no
source, working, candidate, output, or environment-variable path override.

## Review contract

The interface shows one record at a time without a default decision or department.
It presents authored, blind-review, adjudication, rationale, and variation context
neutrally. For `SEB-0176`, verify the relationship among its original
`account_support` proposal, blind-review and candidate `fraud_security` label, and
the recorded `use_reviewer` adjudication without assuming any is automatically
correct.

Choose exactly one decision:

- `confirm_candidate`: keep the candidate department and leave corrected rationale empty.
- `correct_rationale_only`: keep the candidate department and provide corrected rationale.
- `reconsider_label`: select a different real department, explain why, and correct preserved rationale when needed.
- `unsuitable_example`: select `unresolved` and explain why the record may not belong.
- `needs_followup`: select `unresolved` and explain the remaining issue.

Every completed record requires a note. Human-entered fields reject secrets,
credentials, contact details, real identifiers, financial numbers, and
user-specific absolute paths. Saves are atomic and revalidate the fixed local
target immediately before writing.

Completing this working copy is evidence for a later controlled preservation step.
It does not apply answers to the candidate, complete benchmark approval, accept
the documented leakage limitation, or authorize model evaluation.
