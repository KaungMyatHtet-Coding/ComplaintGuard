# Day 28 Local Demo Rehearsal Acceptance

## Scope and boundary

Branch: `docs/day28-local-demo-rehearsal-acceptance`
Verified base: `688fcc4b9b97a1e056a88c72fcce6a7cc51d2c26`

This record covers two complete, timed rehearsals of the existing 5–8 minute
ComplaintGuard demonstration. Both sessions used synthetic identities and
records only, development mode, and a fresh disposable import of
`firebase/emulator-data/canonical-visual-demo-v1`.

The rehearsals prove repeatable local-emulator demonstration only. They do not
prove production readiness, production Firebase behavior, public deployment,
or enterprise security. No final slide-deck file was created or verified;
`presentation/slide_outline.md` remains an outline.

## Startup and isolation

Each accepted run followed the documented order: Firebase Auth/Firestore
emulators with canonical import, deterministic synthetic-role seed, local
FastAPI API, and Next.js development server with explicit emulator-routing
environment values. The API reported `status=ok`, `model_loaded=true`, and
`model_version=v1`; the frontend returned HTTP 200 from loopback.

Before and during each run, browser request observation recorded only
`127.0.0.1`. Auth, Firestore, API, and frontend were loopback endpoints. No
production Firebase host or non-loopback application endpoint was observed.

The canonical snapshot was never exported, overwritten, or changed. Rehearsal
mutations existed only in each disposable emulator session and were discarded
during shutdown.

## Run 1 — accepted

- Duration: 300 seconds.
- Result: Pass.
- Request observation: `127.0.0.1` only.
- Roles: Customer, department-scoped staff, and Manager.
- Covered: high-confidence English routing and Dataset Evidence; staff
  department isolation; staff begin/reply/await-customer flow; customer reply;
  staff resolution; customer feedback; low-confidence manual review; manager
  review and disposable override; manager metrics and pipeline; confusion
  matrix with true departments by row and predicted departments by column; and
  Myanmar UI evidence without inspecting the optional translation cache.
- Backup material: all five accepted Day 27 synthetic screenshot assets were
  available and referenced.
- Privacy: synthetic fixture records only; no credentials, tokens, terminal
  output, filesystem paths, developer tools, debug UI, real narratives, or raw
  CFPB identifiers were exposed.
- Cleanup: all services stopped, required ports released, mutations discarded,
  and the canonical snapshot remained unchanged.

## Run 2 startup attempt — rejected

The first Run 2 startup attempt never reached service readiness. It used the
ambiguous PowerShell alias `sp`, which resolved to `Set-ItemProperty` instead
of `Start-Process`. It was rejected and was not counted as a rehearsal. No
accepted evidence or emulator state from that attempt was retained.

## Run 2 — accepted

- Duration: 300 seconds.
- Result: Pass.
- Request observation: `127.0.0.1` only.
- Roles and flows matched Run 1: Customer, department-scoped staff, Manager,
  Dataset Evidence, high- and low-confidence routing, customer/staff
  messaging, resolution, feedback, manager manual review/override, metrics,
  pipeline, confusion-matrix explanation, and Myanmar UI evidence without
  cache inspection.
- Mutations: synthetic complaint submissions, staff transitions/replies,
  customer reply and feedback, and one manager override, all inside the
  disposable imported emulator session.
- Privacy: same synthetic/local-only result as Run 1; no private or production
  data was visible.
- Cleanup: all services stopped, ports 3000, 8000, 8185, 9099, 4400, and 9150
  released, temporary logs and runner artifacts removed, and mutations
  discarded.

## Integrity and remaining gates

Before and after both accepted runs, the canonical snapshot contained exactly
6 files totaling 27,410 bytes and all six accepted SHA-256 hashes matched.
No emulator export, new fixture, source, configuration, dependency, rule,
model, dataset, or snapshot change was made.

The optional Myanmar cache check remains incomplete. Final slide-deck
completion, deployment, production Firebase, public URL, QR/mobile testing,
demo video, retention/deletion, admin operations, historical-neighbor search,
and production operational controls remain incomplete.
