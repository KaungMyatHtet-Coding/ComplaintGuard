# ComplaintGuard Local Emulator Demo Guide

## Safety boundary

This guide supports only the verified local emulator-based demonstration. Use
synthetic identities and synthetic complaints. Never expose the ignored seeded
password file, Firebase ID tokens, `.env.local`, terminal environment values,
service-account material, real complaint narratives, or raw CFPB Complaint IDs.

Do not present public deployment, live historical neighbors, admin operations,
production security, or automatic Myanmar routing as implemented.

## Prerequisites

- Repository at a writable local path; commands below use `D:\ComplaintGuard`
  for the verified machine.
- Existing Node, Python `.venv`, Java, frontend/firebase dependencies, and Chrome.
- Ignored frozen model with documented SHA-256.
- Ports 3000, 8000, 8185, and 9099 available.

Preflight:

```powershell
Set-Location D:\ComplaintGuard
git status --short
Get-FileHash models\generated\cfpb_department_model_v1.joblib -Algorithm SHA256
Test-Path frontend\node_modules
Test-Path firebase\node_modules
Test-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Expected model hash:
`BAFC086FE5B11BDCC5CBC4F04F3F3F222DE8CBAD27FE66D62A6685CC30F953D5`.

## Four-terminal startup order

### Terminal 1 — Firebase Auth and Firestore emulators

```powershell
Set-Location D:\ComplaintGuard
$env:FIREBASE_CLI_DISABLE_UPDATE_CHECK = "true"
$env:FIREBASE_EMULATORS_PATH = "D:\ComplaintGuard\firebase\.firebase\emulators"
$env:XDG_CONFIG_HOME = "D:\ComplaintGuard\firebase\.firebase\config"

node.exe firebase\node_modules\firebase-tools\lib\bin\firebase.js `
  emulators:start `
  --project demo-complaintguard `
  --only auth,firestore
```

Wait for Auth on `127.0.0.1:9099` and Firestore on `127.0.0.1:8185`.

### Terminal 2 — deterministic-role seed

```powershell
Set-Location D:\ComplaintGuard
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8185"
$env:FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099"
$env:GCLOUD_PROJECT = "demo-complaintguard"
node.exe firebase\seed-emulator.mjs
```

The seed creates four customers, six department staff profiles, and one manager
with stable synthetic email addresses. The first seed generates one random
demo-only shared password and writes it to the ignored
`firebase/.firebase/seeded-identities.json`. Later seeds reuse that password and
the existing Auth UIDs, upsert matching profiles, and preserve emulator tickets.
If emulator Auth contains one of these emails but the ignored credential file is
missing or inconsistent, seeding stops instead of deleting or replacing the
account. Open the credential file only locally. Never project, record,
screenshot, print, paste, or commit it.

The automated emulator test harness uses the explicit `--reset-firestore` flag
between isolated test phases. Do not use that flag for an ordinary demo reseed;
the default command above preserves existing emulator tickets.

## Local demo accounts

All passwords come from the ignored `firebase/.firebase/seeded-identities.json`;
the table deliberately contains no password value.

| Email | Role | Department | Password source | Intended scenario |
|---|---|---|---|---|
| `customer@complaintguard.test` | Customer | — | Ignored shared-password file | Primary end-to-end complaint workflow |
| `customer.two@complaintguard.test` | Customer | — | Ignored shared-password file | Customer ownership isolation |
| `customer.three@complaintguard.test` | Customer | — | Ignored shared-password file | Customer ownership isolation |
| `customer.four@complaintguard.test` | Customer | — | Ignored shared-password file | Customer ownership isolation |
| `staff.transfer@complaintguard.test` | Staff | `transfer_payment` | Ignored shared-password file | Transfer/payment queue |
| `staff.account@complaintguard.test` | Staff | `account_support` | Ignored shared-password file | Account-support queue |
| `staff.card@complaintguard.test` | Staff | `card_atm` | Ignored shared-password file | Card/ATM queue and manager override |
| `staff.fraud@complaintguard.test` | Staff | `fraud_security` | Ignored shared-password file | High-confidence fraud workflow |
| `staff.loan@complaintguard.test` | Staff | `loan_credit` | Ignored shared-password file | Loan/credit queue |
| `staff.general@complaintguard.test` | Staff | `general_support` | Ignored shared-password file | General-support queue |
| `manager@complaintguard.test` | Manager | — | Ignored shared-password file | Review, override, and analytics |

### Terminal 3 — FastAPI

```powershell
Set-Location D:\ComplaintGuard\ml-api
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8185"
$env:FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099"
$env:GOOGLE_CLOUD_PROJECT = "demo-complaintguard"
$env:FIREBASE_CONFIG = '{"projectId":"demo-complaintguard"}'
$env:ALLOWED_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"

..\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --host 127.0.0.1 --port 8000
```

Health check from a separate prompt:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected: `status=ok`, `model_loaded=true`, and `model_version=v1`. Do not
continue with an inference demo if health is degraded.

### Terminal 4 — Next.js

```powershell
Set-Location D:\ComplaintGuard\frontend
$env:NEXT_PUBLIC_FIREBASE_API_KEY = "emulator-only"
$env:NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN = "demo-complaintguard.firebaseapp.com"
$env:NEXT_PUBLIC_FIREBASE_PROJECT_ID = "demo-complaintguard"
$env:NEXT_PUBLIC_FIREBASE_APP_ID = "1:000:web:emulator"
$env:NEXT_PUBLIC_APP_ENV = "local-emulator"
$env:NEXT_PUBLIC_USE_FIREBASE_EMULATORS = "true"
$env:NEXT_PUBLIC_ML_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev -- -H 127.0.0.1 -p 3000
```

Visit `http://127.0.0.1:3000/login`. All roles use `/dashboard` after profile
resolution. Admin is intentionally not seeded and has no operational workflow.

## Approved synthetic examples

- Strong English routing: “My credit report contains accounts caused by
  identity theft and fraud.” Expected: a real prediction, normally routed to
  `fraud_security` when confidence meets the operational threshold.
- Ambiguous English review: “I cannot understand this fee.” Expected:
  `routingSource: manual_review`, no assigned department, and manager review.
- Myanmar review: “ငွေလွှဲထားတာ မရောက်သေးလို့ စစ်ဆေးပေးပါ။” Expected: local
  translation/classification evidence if the checkpoint loads, but always
  `routingSource: manual_review` and no automatic department assignment.

Exact confidence values are model outputs; do not script or promise a fabricated
percentage. Confirm the visible state before explaining it.

## Myanmar warm-up

The pinned translator is local-only and lazy-loaded. Before the audience arrives,
submit the approved Myanmar example once using the emulator customer. Confirm
that the request completes and remains manual review. If the translator cache is
unavailable, the durable ticket must remain recoverable/manual review. Use the
committed Day 10 evidence rather than claiming a live translation result.

## Recommended 5–8 minute sequence

| Time | Action | Expected visible evidence |
|---|---|---|
| 0:00–0:40 | State problem, proxy departments, and local/emulator boundary. | Privacy warning and login page. |
| 0:40–1:25 | Customer submits strong English fraud example. | Ticket ID, real predicted department/confidence, Dataset Evidence. |
| 1:25–2:20 | Fraud staff signs in, opens the scoped ticket, begins work, replies. | Other departments cannot see it; status/event/message update. |
| 2:20–3:05 | Customer reads and replies. | Participant thread and customer-visible status. |
| 3:05–4:00 | Staff resumes and resolves with a synthetic summary. | Resolved state and timestamp. |
| 4:00–4:30 | Customer submits feedback. | Persisted feedback success. |
| 4:30–5:15 | Customer submits ambiguous example. | Unassigned manual-review state. |
| 5:15–6:05 | Manager reviews and overrides to `card_atm`. | Review row disappears; routing source becomes manager override. |
| 6:05–7:20 | Manager shows operational and model/dataset analytics. | Real artifact metrics, pipeline, class distribution, confidence bins, matrix. |
| 7:20–8:00 | State limitations and optional warmed Myanmar evidence. | Manual-review-only wording; similarity shown as local/not deployed. |

## Failure and recovery

- Port unavailable: identify the owning process before stopping anything. Never
  use broad process-kill commands.
- Bad seed/browser role: reseed, then sign out or use a private browser window.
- Degraded API: verify the local model path/hash; do not regenerate the model.
- CORS/API failure: confirm Terminal 3 origins and Terminal 4 API URL, then
  restart only the affected service.
- Myanmar failure: demonstrate English and committed evaluation evidence; never
  invent a translation or route.
- Model analytics unavailable: verify Day 18 source/generated hashes and rerun
  `npm.cmd run sync:evaluation`; never edit metrics manually.
- Demo interruption: use only privacy-reviewed synthetic screenshots if they
  were captured after a passing emulator flow.

## Must not be demonstrated as live

- Historical-neighbor results or similarity percentages
- Coverage over all mapped/raw complaints
- Admin operations
- Production Firebase or public deployment
- QR code
- Automatic Myanmar routing
- Real consumer narratives or raw CFPB IDs
- Enterprise security, guaranteed anonymization, or calibrated confidence

## Pre-demo checklist

- [ ] Clean Git status and correct branch recorded.
- [ ] Model and Day 18 hashes match documentation.
- [ ] All four services start in order and health is `ok`.
- [ ] Seed credential file remains off-screen.
- [ ] Customer, relevant staff, and manager logins work.
- [ ] English high/low examples and Myanmar manual review were rehearsed.
- [ ] Only synthetic complaint and resolution text is used.
- [ ] Backup screenshots, if any, passed manual privacy inspection.

## Post-demo checklist

- [ ] Sign out browser sessions.
- [ ] Stop only the four demo processes deliberately.
- [ ] Confirm generated credentials, logs, emulator state, `.env.local`, model,
  cache, and indexes remain ignored.
- [ ] Run `git status --short`; investigate any unexpected file.
- [ ] Never publish the seed identity file or terminal history containing secrets.
