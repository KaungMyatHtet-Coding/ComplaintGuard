# Current Local Development Setup

This is the current Windows PowerShell setup for the integrated ComplaintGuard
system. Historical day-specific setup notes remain in Git history and milestone
documents; they are not current runtime instructions.

## Prerequisites

- Node.js 22 and npm 10
- Python 3.12 virtual environment at `.venv`
- Java for Firebase emulators
- Chrome at the path configured in `frontend/playwright.config.ts` for E2E
- For an existing workspace, installed dependencies under `frontend/node_modules`
  and `firebase/node_modules`; a clean setup installs them from the lockfiles
- Ignored frozen model at `models/generated/cfpb_department_model_v1.joblib`

Do not install or upgrade dependencies merely for finalization. Create the
virtual environment only when setting up a new machine, then install the pinned
project requirement files deliberately:

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

The complete historical data/ML suite additionally imports Matplotlib. If it is
absent from `.venv`, report that exact limitation; do not silently switch to a
different global Python interpreter.

## Configuration

Copy `frontend/.env.example` to the ignored `frontend/.env.local` only for local
use. Firebase Web values are public application configuration, but they must not
be confused with Firebase Admin credentials. Never put service-account JSON,
private keys, ID tokens, or generated emulator passwords in `NEXT_PUBLIC_*`.

For live Firebase, FastAPI requires Application Default Credentials and an
explicit `ALLOWED_ORIGINS` allowlist. Live Firebase and production deployment
are not verified. For the supported emulator mode, use the process-scoped
variables and four-terminal sequence in `docs/demo_guide.md`.

## Services and routes

- Frontend: `http://127.0.0.1:3000`
- API health: `http://127.0.0.1:8000/health`
- Login: `/login`
- Role dashboard: `/dashboard`
- Auth Emulator: `127.0.0.1:9099`
- Firestore Emulator: `127.0.0.1:8185`

The API health response must report `status: ok`, `model_loaded: true`, and
`model_version: v1`. A degraded response means inference must not be presented.

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
```

`firebase/run-emulator-tests.ps1` starts an isolated demo project, seeds random
local credentials, runs rules/adapters/browser tests, and stops only the child
processes it launched. Its generated identity file is ignored and sensitive.

## Troubleshooting

- If PowerShell blocks `npm.ps1`, use `npm.cmd`.
- If an emulator port is occupied, identify the existing process before stopping
  anything; never kill unrelated processes automatically.
- If API health is degraded, verify the ignored model file and SHA-256 rather
  than regenerating it.
- If Myanmar translation is unavailable, keep the durable ticket/manual-review
  recovery path and demonstrate English; do not invent translated output.
- If browser state has the wrong role, sign out or use a fresh private window.
- If Day 19 evidence synchronization fails, confirm the repository-level
  `evaluation/day18/model_evaluation_v1.json` is present and unchanged.

## Supported boundary

The supported and verified mode is local emulator-based demonstration. There is
no verified Vercel URL, Hugging Face Space, production Firebase rules deployment,
QR code, retention/deletion job, or admin operations UI.
