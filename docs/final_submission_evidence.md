# ComplaintGuard Final Submission Evidence

This matrix is the current claim-to-evidence boundary for the local,
synthetic ComplaintGuard demonstration. It does not replace historical
checkpoint records. Browser visual verification of the later UI/UX slices and
new account workflows remains incomplete.

| Claim | Evidence source | Verification type | Current status | Limitation |
| --- | --- | --- | --- | --- |
| Customer can submit complaints and view history, messages, resolution, and feedback | `ml-api/app/customer_workflow.py`, `frontend/src/components/customer-ticket-history.tsx`, `docs/final_test_report.md` | Historical local Emulator/browser verified; automated tests | Implemented | Later UI/UX visual changes were not browser-verified |
| English routing uses the frozen classifier and the `0.60` operational policy | `ml-api/app/routing.py`, `ml-api/app/model.py`, `models/generated/cfpb_department_model_v1.joblib` | Static/hash verified; historical local Emulator verified | Implemented | Not a production deployment claim |
| Low-confidence, Myanmar, and mixed-language cases require manual review | `ml-api/app/routing.py`, `docs/architecture.md`, `docs/demo_guide.md` | Automated/pure tests; historical local Emulator evidence | Implemented | Myanmar translation quality remains limited |
| Staff access is isolated to the assigned department and staff workflow | `ml-api/app/staff_workflow.py`, `firebase/firestore.rules`, `ml-api/tests/test_staff_workflow.py` | Historical local Emulator/browser verified; automated tests | Implemented | Production rules deployment is unverified |
| Staff can use Overview, Messages, Activity, and Model Data tabs | `frontend/src/components/staff-ticket-detail.tsx`, commit `9245bdd3` | Automated frontend tests | Implemented | Browser/device visual verification is pending |
| Manager can review low-confidence tickets and override routing | `ml-api/app/manager_workflow.py`, `frontend/src/components/manager-low-confidence-review.tsx`, `ml-api/tests/test_manager_workflow.py` | Historical local Emulator/browser verified; automated tests | Implemented | New visual presentation is not browser-verified |
| Customer ownership isolation is enforced | `firebase/firestore.rules`, `ml-api/app/customer_workflow.py`, `docs/access_matrix.md` | Historical local Emulator/rules/browser verified | Implemented locally | Not production security certification |
| Admin may provision only disabled, passwordless, inactive pending Staff/Manager accounts | `ml-api/app/admin_auth.py`, `ml-api/app/admin_workflow.py`, `ml-api/app/main.py`, `ml-api/tests/test_admin_workflow.py` | Pure/fake test verified | Implemented but runtime-unverified | Owner activation is required; no live account mutation has been performed |
| Admin has a read-only Staff/Manager directory | `ml-api/app/admin_directory.py`, `frontend/src/components/admin-user-directory.tsx`, `ml-api/tests/test_admin_directory.py` | Pure/fake/component tests | Implemented but runtime-unverified | Pending/Active describes profile state only |
| Local Admin bootstrap and pending-user activation helpers are committed but unexecuted | `ml-api/scripts/bootstrap_local_admin.py`, `ml-api/scripts/activate_pending_user.py`, corresponding tests | Static/pure/fake tests | Implemented but unexecuted and runtime-unverified | No application Admin or activated Staff/Manager account has been created by these workflows |
| Customer registration and missing-profile recovery are Customer-only | `frontend/src/app/register/page.tsx`, `frontend/src/components/app-provider.tsx`, `ml-api/app/customer_workflow.py`, `ml-api/tests/test_auth_workflow.py` | Pure/component tests | Implemented but Emulator E2E unverified | Firebase CLI startup blocker prevents runtime proof |
| UI/UX Slice A is implemented | Commit `85b1a0e`, Customer/Landing component tests | Automated frontend tests | Implemented and automated-test verified | No browser visual verification |
| UI/UX Slice B is implemented | Commit `9245bdd`, Staff tab tests | Automated frontend tests | Implemented and automated-test verified | No browser/device visual verification |
| UI/UX Slice C is implemented | Commit `8a875bf`, Login/Register tests and theme CSS | Automated frontend tests, TypeScript, ESLint | Implemented and automated-test verified | Autofill, focus appearance, and responsive visuals are not browser-verified |
| UI/UX Slice D is implemented | Commit `9214828`, Manager analytics tests | Automated frontend tests, TypeScript, ESLint | Implemented and automated-test verified | No browser visual verification |
| Manager equations and analytics are available | `frontend/src/components/model-equations.tsx`, `frontend/src/components/model-analytics-dashboard.tsx` | Static/source and frontend tests | Implemented | Manager-only; no browser runtime proof |
| Official held-out evaluation is `82.7934%` accuracy | `evaluation/day18/model_evaluation_v1.json`, `frontend/src/generated/model_evaluation_v1.json` | Static/hash verified | Frozen evidence | Macro-F1 is `0.692345`, below the `0.70` target |
| V1 is a short-English controlled challenge | `evaluation/controlled/six_department_synthetic_v1.json`, `docs/controlled_synthetic_testing.md` | Offline evaluator and artifact contract | Committed evidence | Six synthetic cases; not official accuracy or live-user performance |
| V2 is a long-English supported-use demonstration | V2A manifest, V2B result artifact, `docs/controlled_synthetic_testing.md` | Manifest/result hash and contract verified; offline evaluator executed once | Committed evidence | Six synthetic cases; not overall accuracy or live-user performance |
| Local Firebase Emulator is the supported application mode | `docs/local_setup.md`, `docs/demo_guide.md`, `docs/architecture.md` | Historical local Emulator evidence | Supported local mode | Current CLI startup is blocked; Cloud is not connected |
| Cloud Firebase is not adopted by the application | `PROJECT_PLAN.md`, `docs/cloud_firebase_staging_adoption.md` | Static/documentation verified | Deferred; `cloud_staging_not_adopted` enforced | Requires separate budget, billing, hosting, and identity approval |
| ComplaintGuard is production-ready | No supporting source | Not verified | Not claimed | Deployment, monitoring, backups, retention, rate limits, recovery, and security certification are incomplete |

## Frozen metrics boundary

Official held-out metrics remain separate from controlled demonstrations:

- Test rows: `29,942`
- Accuracy: `82.7934%`
- Macro precision: `0.707515`
- Macro recall: `0.736204`
- Macro-F1: `0.692345` (below the `0.70` target)
- Weighted-F1: `0.837764`
- Balanced accuracy: `0.736204`

V1 reports classifier matches `2/6`, automatic-route coverage `1/6`, correct
automatic routes `0/1`, and manual review `5/6`. V2 reports classifier matches
`2/6`, automatic-route coverage `2/6`, correctness among automatically routed
cases `2/2`, and manual review `4/6`. V2 `2/2 (100%)` is routed-case
correctness only; it is not overall accuracy. V1 and V2 are never combined.
Confidence is uncalibrated, and no causal conclusion about complaint length is
supported.

## Submission checklist

- [x] Repository state and current branch/commit recorded.
- [x] Official, V1, and V2 evidence are separated.
- [x] Role boundaries and Customer-only registration are documented.
- [x] Runtime, browser, Emulator, Cloud, and production limitations are disclosed.
- [x] Model and evidence hashes are recorded in the authoritative documentation.
- [x] No secrets, credentials, raw corpus, or private identifiers are included.
- [ ] Any newly captured screenshots are privacy-reviewed and provenance-verified.
- [ ] A live browser/Emulator rehearsal of the new registration/Admin/UI slices is completed.
- [x] No production-readiness claim is made.
