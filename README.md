# ComplaintGuard

ComplaintGuard is an academic financial-complaint management prototype. It
helps customers submit and track complaints, lets department staff handle only
their assigned queue, and gives managers a manual-review and routing workspace.
The verified operating mode uses synthetic data in local Firebase Auth and
Firestore emulators. It is **not production-ready or publicly deployed**.

## What the prototype provides

| Role | Implemented scope |
|---|---|
| Customer | Submit a complaint, view routing evidence and status, exchange messages, respond to an awaiting-customer request, view resolution, leave feedback, and inspect Dataset Evidence. |
| Department staff | View only the assigned department queue, start handling, message the customer, request a customer response, resume handling, and resolve. |
| Manager | View operational metrics, review low-confidence tickets, override a department with a required reason, and inspect the classification pipeline, verified metrics, and confusion matrix. |
| Admin | Authenticate and reach an intentionally limited shell. No administration operations or endpoints are implemented. |

The end-to-end workflow is customer submission -> classification or manual
review -> department handling -> messages and status transitions -> resolution
-> feedback. Firestore rules, trusted FastAPI authorization, and UI route
guards are separate controls.

## Architecture and stack

- Next.js 16, React 19, TypeScript, Tailwind CSS, Vitest, and Playwright.
- Python 3.12 FastAPI service for trusted workflows and frozen-model inference.
- Firebase Auth and Firestore emulators for synthetic identities and operational
  records; no production Firebase project is required or verified.
- TF-IDF with Multinomial Naive Bayes for English complaint classification.
- CFPB Consumer Complaint Database for historical offline analysis and training.
  The full raw CSV/ZIP and complaint narratives must never be committed or
  loaded into Firestore.

See [architecture](docs/architecture.md), [Firestore schema](docs/firestore_schema.md),
and [access matrix](docs/access_matrix.md) for details.

## Model and dataset evidence

The production classifier is the frozen TF-IDF + Multinomial Naive Bayes v1
artifact. Its held-out test evidence is:

| Metric | Verified result |
|---|---:|
| Accuracy | 82.79% |
| Balanced accuracy / macro recall | 73.62% |
| Macro F1 | 69.23% |
| Weighted F1 | 83.78% |

The model fitted 68,034 records from a fixed 200,000-record sample and was
evaluated on 29,942 held-out records. It was not trained on all 17,034,951 raw
records or all 3,822,576 mapped records. The authoritative artifact is
[`evaluation/day18/model_evaluation_v1.json`](evaluation/day18/model_evaluation_v1.json).

Prediction confidence is uncalibrated and is not the probability that a route
is correct. English predictions below the operational `0.60` threshold remain
unassigned for manager review. Short and ambiguous complaints can therefore
require manual review. Managers may override routing without rewriting the
original prediction, and the reason and audit event remain visible.

The interface supports English and Myanmar. This does **not** mean Myanmar
automatic classification is reliable: Myanmar and mixed-language submissions
always use the safe manual-review path. MiniLM and other model candidates remain
exploratory and are not the production classifier.

## Prerequisites

- Windows PowerShell
- Git
- Node.js 22 and npm 10
- Python 3.12
- Java for the Firebase emulators
- Google Chrome at the path configured in `frontend/playwright.config.ts`
- The ignored frozen model artifact supplied separately by the evaluator or
  project owner:
  `models/generated/cfpb_department_model_v1.joblib`

Expected model SHA-256:
`bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5`.

## Local setup

From a clean clone, create the Python environment and install the locked Node
dependencies. These commands do not configure production services:

```powershell
Set-Location D:\ComplaintGuard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe -m pip install -r ml-api\requirements.txt

Set-Location frontend
npm.cmd ci
Set-Location ..\firebase
npm.cmd ci
```

Copy `frontend/.env.example` to the ignored `frontend/.env.local` and use only
local configuration. For emulator operation set
`NEXT_PUBLIC_APP_ENV=development`,
`NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true`, and
`NEXT_PUBLIC_ML_API_URL=http://127.0.0.1:8000`. Never put service-account JSON,
private keys, passwords, or ID tokens in `NEXT_PUBLIC_*` variables.

## Start the local prototype

Use four PowerShell terminals in this exact order:

1. Start Firebase Auth and Firestore emulators.
2. Run `node.exe firebase\seed-emulator.mjs` with the documented emulator
   variables; this creates synthetic roles and an ignored random-password file.
3. Start FastAPI with the emulator variables and frozen model.
4. Run `npm.cmd run dev` in `frontend` with local emulator configuration.

The exact copyable commands and cleanup process are in
[local setup](docs/local_setup.md) and the [detailed demo guide](docs/demo_guide.md).
Open `http://127.0.0.1:3000`; API health at
`http://127.0.0.1:8000/health` must report `status: ok`,
`model_loaded: true`, and `model_version: v1`. Demo identities are listed in
the detailed guide; their random shared password exists only in the ignored
`firebase/.firebase/seeded-identities.json` file.

## Verification commands

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

`firebase\run-emulator-tests.ps1` launches isolated local services, exercises
rules, Auth identities, adapters, and Playwright workflows, then stops only its
child processes. It uses synthetic records and an explicit reset for isolated
test phases; do not run it against demo state you need to preserve.

## Repository structure

```text
frontend/       Next.js bilingual role-based application
ml-api/         FastAPI inference and trusted workflow service
firebase/       Rules, synthetic seed, adapters, and emulator/E2E harness
data/           Aggregate evidence and mappings; raw/intermediate data ignored
evaluation/     Privacy-safe model-evaluation evidence
models/         Ignored local model and similarity artifacts
scripts/        Reproducible data/ML and final-verification utilities
docs/           Architecture, setup, security, test, demo, and handoff evidence
report/         Academic report source and aggregate figures
presentation/   Slide outline and reviewed synthetic screenshots; no PPTX
```

## Known limitations

- Only local emulator operation is verified; there is no public URL, production
  Firebase validation, production API, deployment, or QR code.
- Myanmar localization is implemented, but Myanmar automatic classification is
  not reliable and always requires manual review.
- The model uses proxy department labels, is class-imbalanced, misses the 0.70
  macro-F1 target, and can be confidently wrong.
- Admin operations, approved retention/deletion, rate limiting, monitoring,
  disaster recovery, live historical-neighbor search, and an independent
  security audit are not implemented.
- PII reduction does not guarantee anonymization. Use synthetic demo records
  only; never use real customer information.

## Evaluator and submission guides

- [Final 5-8 minute demo guide](docs/final_demo_guide.md)
- [Detailed emulator demo guide](docs/demo_guide.md)
- [Day 31 final E2E evidence](docs/day31_final_e2e_verification.md)
- [Day 32 packaging evidence](docs/day32_final_packaging.md)
- [Submission checklist](docs/submission_checklist.md)
- [Model evaluation](docs/model_evaluation.md)
- [Claim-to-evidence matrix](docs/claim_evidence_matrix.md)
- [Final report](report/final_report.md)
- [Presentation outline](presentation/slide_outline.md)
