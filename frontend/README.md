# ComplaintGuard frontend

The frontend is a Next.js 16 TypeScript application with English/Myanmar
localization and authenticated role shells.

## Implemented role experiences

- Customer: complaint submission, history/detail, participant messages,
  resolution/feedback, and Dataset Evidence.
- Staff: exact-department queue, filters, details, messages, approved lifecycle
  actions, resolution, audit requests/events, and Dataset Evidence.
- Manager: operational analytics, low-confidence department override, and
  aggregate Model & Dataset Analytics.
- Admin: authenticated shell only; no operational or administration UI.

Frontend visibility is not an authorization boundary. FastAPI independently
verifies Firebase ID tokens and roles, and Firestore rules govern permitted
client reads while denying protected client writes.

## Evaluation evidence

`evaluation/day18/model_evaluation_v1.json` is the source of truth. Turbopack
cannot import outside this directory in the production client graph, so
`scripts/sync-model-evaluation.mjs` creates an exact frontend-local build input.
It runs before dev/test/typecheck/lint/build and fails if the source is missing,
invalid at its top-level boundary, or cannot be synchronized. The TypeScript
parser then performs strict schema and reconciliation validation with no fallback
metrics.

The bundled file is non-sensitive aggregate academic evidence. Manager-only UI
visibility does not make the bundled JSON a backend-protected resource.

## Configuration

Copy `.env.example` to ignored `.env.local` for local use. Never store Admin
credentials, ID tokens, seeded passwords, or service-account JSON in public
variables. Emulator connections require both explicit local flags and a
non-production Next.js runtime.

See `../docs/demo_guide.md` for the supported emulator configuration.

## Commands

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
npm.cmd run dev -- -H 127.0.0.1 -p 3000
```

The supported evidence is local/emulator-based. No public frontend URL or QR
code is currently verified.
