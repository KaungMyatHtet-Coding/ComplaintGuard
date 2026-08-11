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

Use the full PowerShell `Start-Process` cmdlet when launching background
services. Do not use the ambiguous `sp` alias, which can resolve to
`Set-ItemProperty` rather than `Start-Process`.

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

### Canonical visual-demo snapshot target

The only authorized canonical visual-demo snapshot target is local and
repository-scoped:

```text
D:\ComplaintGuard\firebase\emulator-data\canonical-visual-demo-v1
```

Repository-relative form:

```text
firebase/emulator-data/canonical-visual-demo-v1
```

This Git-ignored directory may contain only Auth and Firestore Emulator export
state for the clearly non-production `demo-complaintguard` project. Create it
only from an empty isolated emulator state, without importing any earlier
snapshot. It must never contain production data or credentials.

The target must not exist before canonical creation. If it already exists, stop
and request human review: never delete, empty, merge, update, replace, or
overwrite it automatically. After successful creation and validation,
`canonical-visual-demo-v1` is immutable. Any future replacement requires a
newly authorized versioned path, such as `canonical-visual-demo-v2`; this guide
does not authorize any later version.

This documentation checkpoint does not authorize emulator startup, fixture
creation, snapshot export or import, source-code changes, deployment, or Day 26
work.

### Synthetic Auth export safety exception

The canonical snapshot may contain Firebase Auth Emulator-generated
`passwordHash` and `salt` fields only for the 11 deterministic synthetic Day 25
demo identities. These fields are expected Auth export/import material, not
plain-text passwords, but remain sensitive authentication material. Never
print, decode, copy into reports, commit, upload, or use their values outside
the isolated local demo-emulator workflow.

This exception is valid only when all of the following are true:

- the Firebase project ID is exactly `demo-complaintguard`;
- every identity is a deterministic synthetic fixture, with no real user,
  production account, or personal data;
- the snapshot remains under the documented Git-ignored local target;
- no API key, service-account key, access token, refresh token, private key,
  session cookie, production credential, or real password is present;
- the snapshot is used only with isolated loopback Firebase emulators; and
- the snapshot is never deployed or imported into a real Firebase project.

The exception applies only to `auth_export/accounts.json` and only to
`passwordHash` and `salt` fields generated for the synthetic fixture
identities. It does not authorize displaying or inspecting their values,
changing the existing snapshot, deleting or overwriting it, accepting it
without successful isolated round-trip verification, production Firebase
access, or broader credential storage.

#### Day 25 acceptance — 2026-08-11

`canonical-visual-demo-v1` passed isolated read-only round-trip validation on
2026-08-11 and is accepted as the immutable canonical visual-demo baseline.
The accepted Git-ignored directory is
`firebase/emulator-data/canonical-visual-demo-v1`: it contains six files totaling
27,410 bytes with snapshot fingerprint
`38a332a81c12c418ae5874dfb5dd2182163419454c0a823c6004409a871e00cb`.

The accepted state uses exactly 11 deterministic synthetic Auth identities and
21 deterministic Firestore fixture paths: 11 tickets, 4 messages, 4 events, 1
top-level feedback document, 1 fixture marker, and 0 actions. Its fixture
fingerprint is
`5107998dcf2dec9621a9922cdb01ee63a7f79f8b17955eac26ab9358359bb8ef`.

Acceptance was established by importing into fresh isolated loopback Auth and
Firestore emulators for project `demo-complaintguard`, verifying exact Auth
identity membership and the standalone Firestore fixture contract, confirming
matching pre/post snapshot fingerprints with unchanged six-file structure and
byte size, then shutting down cleanly with ports released. No production
Firebase access occurred, and the final Git state was clean.

The synthetic Auth exception above remains in force: `passwordHash` and `salt`
are sensitive Auth Emulator export material. Their values must never be
displayed, decoded, copied, committed, uploaded, or reused outside the isolated
local demo workflow.

Do not edit, normalize, repair, regenerate, overwrite, merge into, or export
onto the accepted v1 directory. Any future snapshot must use a newly authorized
versioned directory; v1 remains the reproducible Day 25 baseline. Acceptance
does not authorize production import or deployment. The existing immutable and
non-overwrite contract remains in force.

### Preserve emulator data across a restart

Normal `emulators:start` without `--import` starts an empty Auth/Firestore
session. The normal seed recreates synthetic identities and matching profiles,
but it does not restore tickets, messages, events, actions, or feedback.

Export only to a new ignored directory and fail if it already exists:

```powershell
Set-Location D:\ComplaintGuard
$demoExport = "D:\ComplaintGuard\firebase\.firebase\restart-persistence-audit"
if (Test-Path $demoExport) {
    throw "Export destination already exists; choose a new path."
}

node.exe firebase\node_modules\firebase-tools\lib\bin\firebase.js `
  emulators:export $demoExport `
  --project demo-complaintguard
```

After a clean emulator shutdown, import that exact directory:

```powershell
Set-Location D:\ComplaintGuard
$env:FIREBASE_CLI_DISABLE_UPDATE_CHECK = "true"
$env:FIREBASE_EMULATORS_PATH = "D:\ComplaintGuard\firebase\.firebase\emulators"
$env:XDG_CONFIG_HOME = "D:\ComplaintGuard\firebase\.firebase\config"

node.exe firebase\node_modules\firebase-tools\lib\bin\firebase.js `
  emulators:start `
  --project demo-complaintguard `
  --only auth,firestore `
  --import "D:\ComplaintGuard\firebase\.firebase\restart-persistence-audit"
```

Verify the same synthetic accounts, ticket IDs, messages, events, and feedback
after import. Keep the export local and ignored. Never:

- use `--reset-firestore` with valued demo data;
- run `firebase\run-emulator-tests.ps1` or `cd firebase; npm test` against the
  valued emulator ports, because test setup clears Firestore;
- add `--force` to overwrite an existing export;
- treat reseeding as a ticket/history restore; or
- export real complaint or credential data.

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
