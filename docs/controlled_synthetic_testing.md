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
