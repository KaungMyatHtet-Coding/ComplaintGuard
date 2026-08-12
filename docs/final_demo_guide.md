# ComplaintGuard Final 5-8 Minute Demo Guide

This is a concise evaluator flow for the verified local Firebase-emulator
prototype. Use only synthetic identities and complaint text. The full commands,
credentials boundary, and troubleshooting steps remain in
[`demo_guide.md`](demo_guide.md).

## Before the timer

1. Confirm a clean Git status and the frozen model SHA-256 documented in the
   README.
2. Start, in order, the Auth/Firestore emulators, synthetic seed, FastAPI, and
   Next.js frontend using the four-terminal procedure in `demo_guide.md`.
3. Confirm `http://127.0.0.1:8000/health` reports model v1 loaded and open
   `http://127.0.0.1:3000`.
4. Keep the ignored generated-password file and all terminal credentials off
   screen. Use separate browser profiles or sign out between roles.

## Timed flow

### 0:00-0:45 - Scope and roles

State that ComplaintGuard is a verified local-emulator prototype, not a
production service. Briefly show customer, staff, manager, and the intentionally
limited admin shell. Mention that all operational records are synthetic.

### 0:45-2:00 - Clear English customer complaint

Sign in as `customer@complaintguard.test` and submit a clear synthetic English
complaint such as: "A card purchase I did not make appeared today. Please block
the card and investigate the transaction." Show the ticket, predicted route,
confidence wording, status, and Dataset Evidence. Do not call confidence a
probability of correctness.

### 2:00-3:30 - Department handling and conversation

Sign in as the staff identity for the routed department. Show that its queue is
department-scoped, start handling, send a synthetic reply, and mark the ticket
awaiting customer. Return as the customer, reply, and show that handling resumes.
Return as staff, resolve with a synthetic summary, then show the customer
resolution and submit feedback.

### 3:30-5:00 - Ambiguous complaint and manager review

As a customer, submit a short synthetic complaint such as "Payment issue."
Show that it enters manual review and is not presented as certain. As manager,
open the low-confidence queue, choose the appropriate department, enter a
required synthetic reason, and confirm the original prediction, override reason,
routing decision, and audit evidence remain visible.

### 5:00-6:30 - Evidence views

Show manager operational metrics, the classification pipeline, the 6x6
confusion matrix, and the locked metrics: 82.79% accuracy, 73.62% balanced
accuracy, 69.23% macro F1, and 83.78% weighted F1. Show customer Dataset
Evidence and explain that CFPB evidence is aggregate or privacy-safe; raw
narratives and Complaint IDs are not exposed.

### 6:30-7:30 - Localization and honest limitations

Switch the interface to Myanmar and show localized navigation at desktop and a
390 x 844 viewport if time permits. State explicitly that Myanmar UI support
does not mean reliable Myanmar classification: Myanmar/mixed complaints remain
manual-review cases. MiniLM is exploratory only. Also state that production
Firebase, public deployment, admin operations, retention/deletion, and
production security certification are not verified.

## Cleanup

1. Sign out browser sessions and close demo tabs.
2. Stop only the four processes started for the demo.
3. If a canonical snapshot must be restored, stop the emulators and restart the
   documented isolated seed; do not copy emulator state into Git.
4. Run `git status --short` and investigate any unexpected file. Generated
   credentials, logs, `.env.local`, emulator state, build output, caches, and
   model files must remain ignored and untracked.

If a live step is unavailable, say so and use only the privacy-reviewed Day 27
synthetic screenshots as backup. Never describe a screenshot as live or
production evidence.
