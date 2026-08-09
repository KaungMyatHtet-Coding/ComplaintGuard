# ComplaintGuard

ComplaintGuard is an academic bilingual financial-complaint workflow. It accepts
English or Myanmar input, applies privacy-aware preprocessing, uses a frozen
TF-IDF plus Multinomial Naive Bayes classifier to predict one of six proxy
departments, and stores synthetic operational tickets in Firebase Cloud
Firestore. Customers, department staff, and managers follow a complaint from
submission through review, messaging, resolution, and feedback.

## Current status

Days 1–19 are implemented and merged. Day 20 finalization is in progress. The
verified operating mode is a **local emulator-based demonstration** using the
Firebase Auth and Firestore emulators, the local FastAPI service, and the Next.js
frontend. No public frontend/API deployment, production Firebase verification,
QR code, production retention workflow, or admin operations are claimed.

The `admin` role can authenticate and reach an administration shell, but it has
no operational UI or administration endpoints. Historical day documents retain
their original milestone context; this README and [`docs/local_setup.md`](docs/local_setup.md)
are the current operating instructions.

## Implemented system

- Customer authentication, complaint submission, history, detail, messages,
  resolution visibility, feedback, and privacy-safe Dataset Evidence.
- Real frozen-model English routing. Predictions below the operational `0.60`
  threshold stay unassigned with `routingSource: manual_review`.
- Myanmar and mixed-language ticket submissions run the local translation and
  classifier pipeline but always require manual review because translation
  quality was not accepted. Direct `POST /predict` remains English-only.
- Department-scoped staff queues, replies, lifecycle transitions, resolution,
  and immutable events.
- Manager operational analytics, low-confidence review/department override, and
  held-out Model & Dataset Analytics.
- Deny-by-default Firestore rules and trusted FastAPI authorization, verified in
  local emulator tests. Production deployment is not verified.

## Evidence boundary

The frozen model was evaluated on a genuine 29,942-record held-out test set.
Accuracy is `0.827934` and macro-F1 is `0.692345`; the `0.70` target was not
achieved. The model fitted 68,034 training records from a fixed 200,000-record
sample—not all 3,822,576 mapped records or all 17,034,951 raw records.

[`evaluation/day18/model_evaluation_v1.json`](evaluation/day18/model_evaluation_v1.json)
is the authoritative evaluation artifact. Prediction confidence is an
uncalibrated per-complaint model output, not accuracy. Historical similarity is
a local-only cosine search foundation over exactly 29,942 held-out vectors; its
ignored index is not deployed or used by the application.

## Repository layout

```text
frontend/       Next.js bilingual role-based application
ml-api/         FastAPI inference and trusted workflow service
firebase/       Firestore rules, emulator seed, rules/adapters/E2E harness
data/           Aggregate evidence, mappings, and ignored raw/intermediate data
evaluation/     Privacy-safe Day 10 and Day 18 evaluation artifacts
models/         Ignored local model and similarity artifacts
scripts/        Reproducible data/ML pipelines and final verification
docs/           Architecture, setup, evidence, demo, and release documentation
report/         Academic report source and aggregate figures
presentation/   Presentation outline and speaker notes
```

## Setup and demonstration

Use the four-terminal Windows PowerShell procedure in
[`docs/demo_guide.md`](docs/demo_guide.md). It starts isolated Firebase
emulators, writes randomly generated emulator credentials to an ignored local
file, starts FastAPI with the verified ignored model, and starts the frontend.
Never copy the generated password, Firebase token, `.env.local`, service-account
material, or real complaint data into Git, screenshots, reports, or recordings.

The current local model prerequisite is:

```text
models/generated/cfpb_department_model_v1.joblib
SHA-256 bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5
```

The application must show `/health` as `ok` with `model_loaded: true` before a
demo. See [`docs/release_checklist.md`](docs/release_checklist.md) for all gates.

## Verification

```powershell
Set-Location D:\ComplaintGuard\frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build

Set-Location D:\ComplaintGuard\ml-api
..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider

Set-Location D:\ComplaintGuard\firebase
npm.cmd test

Set-Location D:\ComplaintGuard
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_final.ps1
```

The wrapper does not install packages, regenerate artifacts, deploy, seed live
Firebase, commit, push, or expose credentials. Day 20 results are recorded in
[`docs/final_test_report.md`](docs/final_test_report.md).

## Privacy and security limitations

- Only synthetic demo identities and complaints are approved for demonstrations.
- Deterministic redaction reduces obvious PIN/password/account patterns but does
  not guarantee anonymization. Operational complaint text remains sensitive.
- Historical CFPB narratives and raw Complaint IDs remain outside tracked UI and
  evaluation artifacts.
- UI visibility, FastAPI authorization, and Firestore rules are separate layers.
- Local emulator tests support customer/staff/manager authorization claims; they
  are not a production security certification.
- No approved retention/deletion workflow, rate limiting, monitoring, disaster
  recovery, penetration test, or independent security audit exists.
- Total project cost must remain USD 0; do not enable billing or paid services.

## Documentation map

- [`docs/architecture.md`](docs/architecture.md) — current system boundaries
- [`docs/model_evaluation.md`](docs/model_evaluation.md) — held-out methodology
- [`docs/claim_evidence_matrix.md`](docs/claim_evidence_matrix.md) — allowed claims
- [`docs/demo_guide.md`](docs/demo_guide.md) — local demonstration procedure
- [`report/final_report.md`](report/final_report.md) — academic report source
- [`presentation/slide_outline.md`](presentation/slide_outline.md) — slide plan
