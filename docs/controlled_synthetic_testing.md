# Controlled six-department synthetic demonstration

The local runner in `ml-api/scripts/controlled_synthetic_test.py` evaluates
exactly one predefined synthetic English complaint for each authoritative
department using the existing hash-checked, prediction-only frozen model.

V1 is a **Controlled short-English challenge demonstration**. Its six-case
profile contains **five short English complaints and one medium-length English
complaint**. It is not the intended long-English supported-use benchmark, the
official held-out model evaluation, live-user performance, or overall
ComplaintGuard model accuracy. It should be interpreted as evidence of known
short-text generalization and confidence-threshold limitations.

The expected department is defined before inference and is immutable during the
run. The result is a small controlled demonstration, not official model
accuracy, the frozen held-out evaluation, or live-user performance. The six
cases are not sourced from CFPB narratives and contain no real personal,
financial, account, contact, or institution-specific data.

The runner writes only to the dedicated `evaluation/controlled/` directory and
refuses to overwrite an existing artifact or any file under `evaluation/day18`.
It does not import Firebase, call a service, access a network, write Firestore,
or create accounts and tickets.

The controlled result keeps classifier matching separate from automatic-route
correctness. The corrected controlled classifier match rate is **2/6 =
33.3333%**. The automatic-routing success rate is **0/1 = 0%**. A confidence
below the operational `0.60` threshold is manual review with no automatic final
department. Five cases were held for manual review: two were classifier
matches held for safety review and three were incorrect predictions prevented
from automatic routing. One Card/ATM complaint was confidently misrouted to
Account Support. Manager override simulation is disabled. Confidence is
uncalibrated. The sample is too small to generalize overall performance.
Myanmar and mixed-language behavior is outside this six-case English
percentage and remains governed by the manual-review policy.

This is **not official model accuracy**. The official frozen held-out accuracy
remains **82.7934%**. The threshold prevented three incorrect predictions from
being automatically routed, while also holding two correct but low-confidence
predictions for review. These operational safety counts must not be presented
as precision, recall, F1, calibrated confidence, or live-user performance.

Each case records `classifierPredictionMatches` using only predicted-versus-
expected department equality. `correctAutomaticRoute` additionally requires
model routing, confidence at least `0.60`, and an expected final route.

The corrected V1 results remain: classifier matches **2/6 (33.3333%)**;
automatic routes **1**; correct automatic routes **0**; manual review **5**;
correct predictions held for review **2**; incorrect predictions held for
review **3**; and one confidently wrong Card/ATM route to Account Support.
V1 complaint wording, expected labels, predictions, confidence values, and
the generated artifact remain unchanged. A future separately predefined and
pre-hashed V2 may evaluate the intended clear, detailed, long-English
supported-use profile; V2 does not yet exist and has not passed.

Run from `ml-api` only when the already-cached frozen model and dependencies are
available locally:

```powershell
..\.venv\Scripts\python.exe scripts/controlled_synthetic_test.py
```

The historical validation-selected model threshold `0.0` and the operational
routing threshold `0.60` are recorded separately. No controlled result may be
copied into the Day 18 official evaluation artifacts or presented as a model
replacement.

## V2A case-definition checkpoint

V2A is a case-definition-only checkpoint for the intended supported-use
benchmark. The separate manifest
`evaluation/controlled/six_department_long_english_v2a_manifest.json` contains
six predefined long-English synthetic cases, one per authoritative department,
with no prediction, confidence, routing, or correctness fields. The wording
and expected labels are committed before any V2 inference so later V2B
execution cannot tune them after observing results.

At the V2A checkpoint, inference had not run and no V2 success rate existed.
V2A is not official held-out evaluation or live-user performance. The V2B
execution documented below required the finalized manifest SHA-256 before
loading the model or producing results.

## V2B long-English supported-use result

V2B executed once offline against the committed V2A manifest after verifying
manifest SHA-256
`6043166A0C5660B201D6AECCCB997FB2CAA2FAC50164415E06190119F38E62C7` and the
frozen model contract. The result artifact is
`evaluation/controlled/six_department_long_english_supported_use_v2b.json`.
It contains aggregate-safe results only and does not copy complaint text.

| Case | Expected | Predicted | Confidence | Language | Route | Review | Final route | Classifier match | Correct automatic route |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| `v2a-transfer-payment-001` | `transfer_payment` | `account_support` | 0.542489 | `en` | manual review | low confidence | none | No | No |
| `v2a-account-support-001` | `account_support` | `card_atm` | 0.486111 | `en` | manual review | low confidence | none | No | No |
| `v2a-card-atm-001` | `card_atm` | `card_atm` | 0.667539 | `en` | model | — | `card_atm` | Yes | Yes |
| `v2a-fraud-security-001` | `fraud_security` | `card_atm` | 0.562638 | `en` | manual review | low confidence | none | No | No |
| `v2a-loan-credit-001` | `loan_credit` | `loan_credit` | 0.978426 | `en` | model | — | `loan_credit` | Yes | Yes |
| `v2a-general-support-001` | `general_support` | `card_atm` | 0.388580 | `en` | manual review | low confidence | none | No | No |

V2B summary:

- Classifier match rate: **2/6 (33.3333%)**.
- Automatic-route coverage: **2/6 (33.3333%)**.
- Correctness among automatically routed cases: **2/2 (100%)**.
- Manual-review rate: **4/6 (66.6667%)**.
- Confidently incorrect automatic routes: **0**.

The 100% value applies only to the two automatically routed cases. It is not
overall model accuracy or six-case success. The four manual-review cases were
classifier mismatches, but they are excluded from the automatic-routing
denominator because no automatic route occurred. They are therefore not
counted as automatic-routing failures. Their final routes remain unset because
no Manager assignment or override was simulated. Confidence values are
uncalibrated, the sample is a small controlled synthetic demonstration rather
than verified live-user performance, and the official frozen held-out accuracy
remains **82.7934%**.

V1 and V2B are separate demonstrations: V1 is a short-English challenge with
one automatic route and zero correct automatic routes, while V2B is the
long-English supported-use profile with two automatic routes, both correct.
This is a descriptive comparison of two six-case synthetic samples, not a
causal claim and not a combined twelve-case accuracy.

Only two of six V2B cases received automatic routing. The earlier informal
“at least 5/6” observation is not included as verified evidence. V1 and V2
remain separate demonstrations and are not combined.
