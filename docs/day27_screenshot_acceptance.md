# Day 27 Screenshot Acceptance

## Session boundary

An initial production-mode startup was rejected because outbound Auth behavior
could not be certified. No evidence from that attempt was retained. All
provisional images were rejected and deleted. The accepted evidence pack was
recaptured in a separate verified local-emulator development session.

The accepted session imported only
`firebase/emulator-data/canonical-visual-demo-v1` into disposable loopback
Firebase emulators. The documented development frontend connected Auth and
Firestore to loopback emulators; the local API, frontend, Auth, and Firestore
were observed on `127.0.0.1`. Browser request observation for the accepted
session contained only `127.0.0.1`; no Firebase production host or non-loopback
application endpoint was observed. This observation applies only to the fresh
accepted session and does not retroactively certify the rejected attempt.

No ticket, message, status, assignment, manager override, sign-out, or emulator
export was performed. The canonical snapshot was used only as an immutable
import source.

## Accepted assets

Every PNG below was inspected at its original resolution. Each application
screenshot contains synthetic data shown from the local Firebase emulator and
is local demonstration evidence, not production evidence. No real data,
secrets, terminal output, filesystem path, developer tools, or debug UI is
visible.

| File | Dimensions | Subject and source | Capture viewport | Original-resolution privacy result |
|---|---:|---|---|---|
| `presentation/assets/day27/01-customer-ticket-dataset-evidence.png` | 503 x 1472 | Customer ticket with Dataset Evidence; canonical synthetic customer fixture. Synthetic data shown from the local Firebase emulator. | 1440 x 1000 | Pass — synthetic fixture only; no real data, secrets, terminal output, or debug UI. |
| `presentation/assets/day27/02-staff-ticket-detail-message.png` | 424 x 308 | Department-scoped staff ticket detail; existing canonical synthetic fixture message. Synthetic data shown from the local Firebase emulator. | 1440 x 1000 | Pass — existing synthetic message only; no real data, secrets, terminal output, or debug UI. |
| `presentation/assets/day27/03-manager-low-confidence-review.png` | 672 x 856 | Manager low-confidence review; canonical synthetic manual-review fixture, without confirmation. Synthetic data shown from the local Firebase emulator. | 1440 x 1000 | Pass — synthetic fixture only; no real data, secrets, terminal output, or debug UI. |
| `presentation/assets/day27/04-manager-metrics-pipeline.png` | 730 x 3359 | Manager metric cards and pipeline; committed `evaluation/day18/model_evaluation_v1.json` aggregate evaluation evidence in a synthetic local-emulator application context. | 1440 x 1000 | Pass — approved aggregate evidence only; no real narrative, secrets, terminal output, or debug UI. |
| `presentation/assets/day27/05-manager-confusion-matrix.png` | 730 x 555 | Confusion matrix; committed `evaluation/day18/model_evaluation_v1.json` aggregate evaluation evidence in a synthetic local-emulator application context. True departments are rows and predicted departments are columns. | 1440 x 1000 | Pass — approved aggregate evidence only; no real narrative, secrets, terminal output, or debug UI. |

## Documentation integration

- `presentation/slide_outline.md` replaces the five corresponding screenshot
  placeholders with accepted assets and local-emulator captions.
- `report/final_report.md` links the accepted evidence and distinguishes it from
  production behavior.
- `docs/release_checklist.md` marks only the completed screenshot evidence gates
  complete. Deployment, QR, video, rehearsal, and other unfinished gates remain
  incomplete.

## Integrity and acceptance checks

- Canonical snapshot inventory and the six accepted hashes matched before and
  after capture.
- All five asset references resolve from the report and presentation outline.
- All five screenshot placeholders are replaced.
- The five accepted captures were created in the fresh emulator-only session;
  rejected temporary captures were deleted.
