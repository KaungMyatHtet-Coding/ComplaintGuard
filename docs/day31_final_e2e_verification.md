# Day 31 Final End-to-End Verification

## Environment and repository state

- Verification date: 2026-08-12
- Starting branch: `fix/day30-ui-polish`
- Starting HEAD: `445a2c78d4014fff55e56cca16a84d8cf0196b35`
- Initial worktree: clean
- Day 30 merge: PR #28, merge commit
  `b558eee7613bb48a7ef82d5a7c4684f345448e76`
- Updated local `main` and `origin/main`:
  `b558eee7613bb48a7ef82d5a7c4684f345448e76`
- Verification branch: `test/day31-final-e2e-verification`
- Supported target: synthetic local Firebase-emulator prototype

Day 31 does not authorize deployment, model retraining, model replacement, UI
redesign, or production Firebase access. The production classifier remains the
frozen TF-IDF plus Multinomial Naive Bayes model v1.

## Verification matrix

This matrix was established before any Day 31 source-code change. Results and
evidence are filled only after the corresponding check executes.

| ID | Role | Preconditions | Steps or automated reference | Expected result | Actual result | Result | Evidence source | Limitation |
|---|---|---|---|---|---|---|---|---|
| PUB-01 | Public | Frontend available | Open `/` and `/login`; inspect configuration/authentication states | Landing and login render; missing configuration and bad authentication are understandable | Component/auth state coverage passed. | Pass | 74-test frontend suite | Local browser only |
| PUB-02 | Public | Signed out | Open `/dashboard` and attempt protected access/action | Redirect to login; no protected data/action available | Signed-out routing and protected policy checks passed. | Pass | Auth policy/component tests | UI redirect is not the data authorization layer |
| CUS-01 | Customer | Synthetic customer authenticated; model/API healthy | Submit approved clear fraud complaint | Real high-confidence English prediction routes to Fraud & Security | Real frozen-model submission routed to Fraud & Security. | Pass | Playwright `day17-emulator.spec.ts` | Confidence is uncalibrated |
| CUS-02 | Customer | CUS-01 ticket exists | Open ticket and Dataset Evidence | Prediction, confidence, current route, status, and local-only evidence wording are visible | Dataset Evidence showed the real prediction/route and honest local-only wording. | Pass | Playwright and Dataset Evidence tests | No live historical neighbors |
| CUS-03 | Customer/staff | CUS-01 routed | Staff starts, replies, awaits customer; customer replies; staff resumes and resolves | Messages and lifecycle states remain consistent and visible | Full message and lifecycle sequence completed. | Pass | Playwright complete-flow test | Synthetic emulator data only |
| CUS-04 | Customer | CUS-03 resolved | View resolution and submit rating/comments | Resolution is visible and feedback persists without duplicate form | Resolution displayed and 4/5 feedback persisted. | Pass | Playwright and feedback tests | Local emulator persistence during test only |
| LOW-01 | Customer | Synthetic customer authenticated | Submit `I cannot understand this fee.` | Ticket remains unassigned in manual review and is not presented as certain | Ticket displayed Manual review and remained hidden from department staff. | Pass | Playwright and routing tests | Short example is synthetic |
| LOW-02 | Manager | LOW-01 exists | Open review dialog; attempt empty reason; choose department and enter reason | Empty reason cannot confirm; manager override succeeds without rewriting prediction | Confirm was disabled until a reason was entered; override succeeded. | Pass | Playwright and manager tests | Override is operational routing, not relabeling |
| LOW-03 | Manager/staff | LOW-02 complete | Inspect review result, staff queue, and audit record | Queue updates, target department gains access, and audit evidence records override | Review row cleared, target Card staff gained access, and transactional audit tests passed. | Pass | Emulator adapters/browser/API tests | UI exposes only implemented evidence |
| STF-01 | Staff | Fraud ticket plus Card staff identity | Compare Fraud and Card staff queues/access | Exact-department staff sees own department only | Card staff could not see Fraud ticket; Fraud staff could. | Pass | Rules, adapters, and Playwright | Emulator evidence, not production certification |
| STF-02 | Staff | Routed ticket | Begin, reply, await, resume, resolve | Only approved transitions succeed and events/messages are immutable | All approved transitions passed; mutation and rollback tests passed. | Pass | Backend, adapter, and Playwright tests | Broader manager lifecycle operations remain absent |
| MAN-01 | Manager | Manager authenticated with synthetic emulator data | View dashboard, low-confidence queue, pipeline, metrics, and matrix | Operational analytics and verified aggregate model evidence render | Manager dashboard, review queue, pipeline, metrics, and matrix render tests passed. | Pass | Browser/component/artifact tests | Aggregates are held-out academic evidence |
| MAN-02 | Manager | Day 18 evidence synchronized | Reconcile displayed headline values | Accuracy 82.79%, balanced accuracy 73.62%, macro F1 69.23%, weighted F1 83.78% | Source/generated hash and strict metric reconciliation passed unchanged. | Pass | Focused Python and frontend artifact tests | Rounded display values; source retains precision |
| SEC-01 | Customer A/B | Two synthetic customer identities and one ticket | Query/read other customer's ticket/messages | Other customer's resources are denied/not visible | Rules denied cross-owner reads; three additional customers saw only their own tickets. | Pass | Rules, adapters, and Playwright | Local emulator only |
| SEC-02 | Staff A/B | Staff identities in different departments | Query/read/update cross-department complaint | Cross-department resources are denied/not visible | Exact department equality and null-department denial passed. | Pass | Rules, adapters, and Playwright | Local emulator only |
| SEC-03 | Unauthenticated/invalid profile | No token or invalid/inactive role data | Call protected endpoints and direct Firestore operations | Requests fail; invalid claims do not elevate access | Auth, profile, API authorization, and denied direct-write tests passed. | Pass | 107 backend, Auth, and rules tests | No production identity-provider test |
| SEC-04 | Non-manager | Customer/staff token | Attempt manager analytics/override | Manager-only endpoints reject the request | Manager authorization and override endpoint tests passed. | Pass | Backend manager tests | Frontend hiding is not authorization |
| UI-01 | All roles | Desktop browser | Run complete browser workflow at configured desktop viewport | English UI and workflows render without blocking overflow | Complete English workflow passed in headless Chrome. | Pass | Playwright desktop flow | Headless Chrome, not manual multi-browser review |
| UI-02 | All roles | 390 x 844 browser viewport | Switch English/Myanmar on customer, staff, manager dashboards | Both catalogs render with no document-level horizontal overflow | All three roles switched catalogs with viewport containment. | Pass | Playwright mobile/bilingual test | Localization test does not validate Myanmar classification |
| UI-03 | Customer/staff | Long synthetic text fixture | Render long IDs, complaints, messages, and resolution text | Text remains contained in cards/scroll regions | Long-reference/message component regressions and mobile containment passed. | Pass | Component tests and Playwright | Static/component coverage plus headless browser containment |
| UI-04 | Keyboard manager | Browser and review ticket | Tab through controls; open/close manager dialog; test required reason | Focus is visible; dialog is labeled; reason gate and focus return work | Focus-visible CSS, dialog labeling, and required-reason gate passed; Escape/focus restoration are component implementation evidence. | Pass | Component markup and Playwright | No screen-reader session |
| MY-01 | Customer | Myanmar UI and optional local translation path | Verify interface localization and manual-review safety contract | Myanmar/mixed input never auto-routes; UI does not claim reliability | Myanmar UI passed; real local Myanmar routing test required manual review. | Pass | Backend routing and UI tests | Translation quality remains below acceptance |
| DAT-01 | Test harness | Clean disposable emulator state | Run isolated emulator suite and inspect shutdown | Only synthetic data is used; child services stop; disposable state is not exported | Harness used generated synthetic identities, released all six ports, and did not export state. | Pass | Emulator output and port audit | Generated ignored credentials remain local |
| DAT-02 | Repository | Checks complete | Scan tracked files/status for secrets and forbidden artifacts | No secret, raw corpus, emulator state, cache, screenshot, build output, or model artifact becomes tracked | Scans passed; only this Day 31 document is untracked. | Pass | Git, secret, and artifact scans | Pattern scan cannot prove absence of every possible secret |
| MOD-01 | Evidence audit | Frozen model and Day 18 artifacts present | Hash model; run artifact/evaluation integrity checks | Frozen v1 hash and aggregate evidence reconcile unchanged | Model hash matched; source/generated evaluation hashes matched; 9 focused tests passed. | Pass | Hashes, focused tests, and wrapper | No retraining or held-out tuning |

## Synthetic scenarios

- High-confidence English: `My credit report contains accounts caused by
  identity theft and fraud.`
- Ambiguous English: `I cannot understand this fee.`
- Messages and resolution: clearly labeled synthetic E2E text generated by the
  Playwright test.
- Myanmar validation is limited to interface localization and the established
  safe manual-review contract; reliable automatic classification is not claimed.

## Commands and exact results

| Command | Exact result |
|---|---|
| `cd frontend; npm.cmd test` | Pass: 19 files, 74 tests. |
| `cd frontend; npm.cmd run typecheck` | Pass: `tsc --noEmit --incremental false`. |
| `cd frontend; npm.cmd run lint` | Pass: no ESLint findings. |
| `cd frontend; npm.cmd run build` | Pass: Next.js 16.2.10 compiled, type-checked, and generated `/`, `/_not-found`, `/dashboard`, and `/login`. |
| `cd ml-api; ..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider` | Pass: 107 passed, 7 emulator-only skipped, 1 documented expected failure, 40 warnings. |
| `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_evaluate_department_model.py scripts/tests/test_historical_similarity.py -p no:cacheprovider` | Pass: 9 passed, 3 joblib/NumPy deprecation warnings. |
| `.\.venv\Scripts\python.exe -m ruff check scripts ml-api/app ml-api/tests` | Pass: all checks passed. |
| `.\.venv\Scripts\python.exe -m ruff format --check scripts ml-api/app ml-api/tests` | Pass: 42 files already formatted. |
| `cd firebase; npm.cmd test` | Pass: 4 rules, 1 Auth identity, 7 emulator adapters, and 3 Playwright tests. Adapter run emitted 7 dependency warnings; negative rules cases emitted expected permission-denied logs. |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_final.ps1` | Pass: all executed mandatory checks passed. Firebase was run separately. Complete root scripts suite was skipped because `.venv` still cannot import Matplotlib; nothing was installed and no global interpreter was substituted. |
| Model/source/generated SHA-256 checks | Pass: model `BAFC086F...F953D5`; source and generated evaluation `F6B3A872...8DAE06`. Similarity index also matched the wrapper contract. |
| `git diff --check` | Pass. |
| Tracked secret-signature and forbidden-artifact scans | Pass: no findings. |
| Emulator port audit | Pass: 3000, 8000, 8185, 9099, 4400, and 9150 released. |
| Canonical snapshot structural audit | Pass: still 6 files and 27,410 bytes; newest write remains 2026-08-11 19:14:01 +06:30, before Day 31. |

## Workflow results

The high-confidence scenario used the unchanged frozen model and routed the
approved synthetic fraud complaint to Fraud & Security. Fraud staff alone could
handle it, exchanged messages with the customer, moved through awaiting
customer and resume, resolved it, and the customer submitted 4/5 feedback.

The ambiguous scenario remained unassigned in manual review. Card staff could
not see it before manager action. The manager dialog prevented confirmation
without a reason, then routed it to Card & ATM; the review row cleared and Card
staff gained access. Prediction evidence was not rewritten.

## Security, language, responsive, and cleanup results

Customer ownership, exact staff department scope, manager-only authorization,
invalid/unauthenticated rejection, and denied direct Firestore writes all
passed in the local emulator. Expected `PERMISSION_DENIED` output is evidence
from negative rules tests, not a suite failure.

English desktop and English/Myanmar 390 x 844 role dashboards passed in
headless Chrome with no document-level horizontal overflow. Myanmar/mixed
automatic routing remains blocked; the real local Myanmar backend test required
manual review. This is localization and safe-fallback evidence, not reliable
Myanmar classification evidence.

The isolated harness stopped its child services and released all ports. It did
not import, export, or modify the immutable canonical snapshot. Generated
credentials, emulator logs/state, `.env.local`, caches, build output, model
artifacts, and translation/model caches remain ignored and untracked.

## Defects and minimal fixes

No reproducible Day 31 defect blocked a required flow. No application source,
test, model, rule, configuration, dependency, or fixture change was required.

## Remaining limitations

- Browser verification used headless Chrome, not physical devices, a manual
  multi-browser matrix, a screen reader, or a production network.
- The complete root scripts suite remains unavailable in `.venv` because
  Matplotlib is absent. Focused model/evidence tests and every product/runtime
  gate passed; no global Python substitute was used.
- One routing regression is deliberately marked expected-failure because the
  frozen model reproduces a known high-confidence transfer/account defect.
- Backend standalone tests skip seven emulator adapters; the same seven tests
  passed inside the isolated emulator harness.
- Accuracy and weighted metrics are influenced by class imbalance; macro F1
  remains below the 0.70 target and confidence remains uncalibrated.
- Myanmar automatic classification is not reliable. MiniLM remains exploratory
  and is not the production classifier.
- Production Firebase, public deployment, QR/mobile public URL, retention,
  rate limiting, monitoring, recovery, admin operations, and enterprise
  security certification remain incomplete.

## Release-readiness conclusion

All Day 31 product/runtime, security, evidence-integrity, desktop/mobile, and
bilingual-interface checks executed successfully. ComplaintGuard is a verified
local-emulator prototype ready for final packaging and demonstration. It is not
production-ready and is not publicly deployed.
