# ComplaintGuard Pre-Model-Hunting Checkpoint

## 1. Checkpoint information

- Recorded: 2026-08-12 17:58:09 +06:30 (Asia/Rangoon).
- Current branch: `main`.
- HEAD: `8c78604f38593d6996d3ea6e4ad0ebb224cf8c2a`.
- Latest commit: `8c78604 Merge pull request #30 from
  KaungMyatHtet-Coding/docs/day32-final-packaging` (`docs: prepare Day 32 final
  project package`).
- Initial working tree: clean; `main` was 0 commits ahead and 0 behind
  `origin/main`.
- Checkpoint working tree before this report: clean. This report and the minimal
  task-board update are the only intended changes.
- Existing relevant tags: none (`git tag --list` returned no entries).

This document records the known-good local-emulator prototype immediately
before separately authorized model-candidate work. It does not change runtime
behavior, the classifier, data, dependencies, Firebase, UI, or security rules.

## 2. Project purpose and current scope

ComplaintGuard is an academic complaint-management prototype that accepts
English or Myanmar interface input, classifies English complaint text into one
of six proxy departments, retains uncertain or Myanmar/mixed submissions for
manager review, and supports customer/staff complaint handling with synthetic
Firebase-emulator data. The verified boundary is local Next.js + FastAPI +
Firebase Auth/Firestore emulators. It is not production-ready, publicly
deployed, or a production security certification.

## 3. Completed functionality

The following is implemented and verified by the current frontend, backend,
rules, adapter, and Playwright suites:

- **Customer:** emulator authentication; complaint submission; ticket history,
  detail, routing evidence and status; participant messaging; awaiting-customer
  reply; resolution visibility; feedback; and Dataset Evidence.
- **Department staff:** exact-department complaint queue and detail; start
  handling; reply; mark awaiting customer; resume; resolve; and view permitted
  events. Cross-department and null-department access is denied.
- **Manager:** operational metrics, low-confidence/manual-review queue,
  department override with a required reason, original-prediction preservation,
  model/dataset pipeline, confidence evidence, per-department metrics, and the
  held-out confusion matrix.
- **Admin/owner:** an authenticated admin role and limited dashboard shell are
  represented in policy/UI, but no admin seed identity, administration UI, or
  administration endpoint exists. The project owner performed the documented
  Myanmar semantic review; owner review is evidence, not an application role.
- **Classification:** the trusted ticket pipeline invokes the hash-verified
  frozen classifier. Accepted high-confidence English output is routed; low-
  confidence output remains unassigned for manual review.
- **Workflow:** submitted/triaged/in-progress/awaiting-customer/resolved paths,
  messages, immutable audit evidence, and resolved feedback are covered. The
  broader designed reopen/close/priority administration scope is not delivered.
- **Localization:** English and Myanmar interface catalogs and a 390 x 844
  viewport are covered by Playwright. This is interface support, not proof of
  reliable Myanmar classification.
- **Firebase:** local Auth and Firestore emulators, synthetic identity seeding,
  rules, trusted adapters, and end-to-end browser workflows are verified. No
  production Firebase project or public deployment is verified.

## 4. Current ML/classifier baseline

### Implemented and verified

- **Production model:** ComplaintGuard department model v1, TF-IDF plus
  `MultinomialNB(alpha=0.5)` (the Day 9 `lower_alpha` candidate).
- **Artifact:** ignored local file
  `models/generated/cfpb_department_model_v1.joblib`, 13,311,363 bytes in the
  recorded evidence, SHA-256
  `BAFC086FE5B11BDCC5CBC4F04F3F3F222DE8CBAD27FE66D62A6685CC30F953D5`.
  The hash matched at this checkpoint.
- **Historical source:** CFPB Consumer Complaint Database snapshot described in
  `docs/dataset_profile.md`; raw CSV/ZIP remains under ignored
  `data/raw/cfpb/` and must not be committed.
- **Training dataset:** ignored
  `data/interim/cfpb/cfpb_training_v1.csv`; aggregate manifest at
  `data/processed/cfpb_training_v1_manifest.json`. It contains 3,822,576 mapped
  narrative/label records. Modeling selected 200,000; 68,034 training records
  were fitted after training-only caps.
- **Evaluation:** validation has 29,277 records; the unchanged held-out test has
  29,942. Authoritative aggregate evidence is
  `evaluation/day18/model_evaluation_v1.json` (SHA-256
  `F6B3A872396BA8A8DB874BDB0CA00F839A4515C1C77E935CE13CD02D488DAE06`).
  Locked Day 9 metrics are in `data/processed/cfpb_model_v1_metrics.json`
  (SHA-256
  `99FC40B8E791FE65FF7ED22E8E5A731ED650351AD577D27322E95F2BDD1550D8`).
- **Labels:** `transfer_payment`, `account_support`, `card_atm`,
  `fraud_security`, `loan_credit`, and `general_support`.
- **Label source:** deterministic CFPB Product/Issue mapping v1, not narrative
  text and not institutional ground truth.
- **Classifier preprocessing:** Unicode NFKC, case-folding, and whitespace
  collapse. The earlier privacy-aware cleaning pipeline also removes URLs and
  conservatively redacts obvious email, phone-like, and long-number patterns.
- **Prediction paths:** `POST /predict` is a stateless English-only diagnostic.
  Authenticated `POST /tickets` creates a durable PII-reduced ticket and runs
  trusted language/routing inference.
- **Confidence:** maximum MultinomialNB class probability; it is uncalibrated
  and is not accuracy or probability of correctness.
- **Thresholds:** the artifact's validation-selected threshold is `0.0`. The
  later operational routing/manual-review threshold is `0.60`. English output
  below `0.60` remains unassigned with `routingSource: manual_review`.
- **Held-out metrics:** accuracy 0.827934 (82.79%), balanced accuracy/macro
  recall 0.736204 (73.62%), macro precision 0.707515, macro F1 0.692345
  (69.23%), weighted precision 0.866300, weighted recall 0.827934, and weighted
  F1 0.837764 (83.78%). The 0.70 macro-F1 target was not achieved.
- **Known short-text behavior:** short or ambiguous complaints can be low
  confidence and require review. `Mobile transfer failed` is protected as a
  low-confidence manual-review regression. A longer clear transfer complaint
  can still be misrouted to Account Support at high confidence; that frozen-v1
  defect is a strict expected failure.
- **Myanmar pipeline:** Myanmar/mixed input is normalized, translated locally
  with pinned `Helsinki-NLP/opus-mt-mul-en` revision
  `848eae0c1676cfce9bb791c200e8228e5a6396ff`, then passed to the frozen English
  classifier only as review evidence. It is always manual-review-only.
- **Myanmar evidence:** the frozen 30-case synthetic validation produced 14/30
  owner-rated usable translations and 11/30 correct classifications; both
  acceptance thresholds failed. Base NLLB development evidence produced 23/30
  pass-or-partial translations and 9/30 correct routes; it also failed and did
  not replace the production path.

### Implemented but not fully verified

- The local Marian translator is implemented and its real manual-review safety
  path passed the current API suite. Translation quality is explicitly not
  accepted and the external cache is not a tracked/reproducible package.
- Historical similarity code/evidence exists for an ignored local index over
  29,942 held-out vectors, but live neighbor search is not deployed in the app.
- Redaction reduces obvious sensitive patterns but does not guarantee
  anonymization.

### Planned or exploratory, not implemented as production behavior

- MiniLM and other model candidates are exploratory only.
- Reliable Myanmar automatic routing, calibrated confidence, broader short-text
  coverage, production Firebase, public hosting, monitoring, retention/deletion,
  rate limiting, disaster recovery, and admin operations are not implemented or
  not verified.

## 5. Current test and verification results

| Exact command | Result | Counts and important notes |
|---|---|---|
| `cd frontend; npm.cmd test` | PASS | 19 files, 74 tests. Evaluation evidence synchronized to hash prefix `f6b3a872396b`. |
| `cd frontend; npm.cmd run typecheck` | PASS | `tsc --noEmit --incremental false`. |
| `cd frontend; npm.cmd run lint` | PASS | ESLint reported no findings. |
| `cd frontend; npm.cmd run build` | PASS on unchanged retry | Initial sandboxed run failed with Windows `EPERM` opening ignored `.next/trace`. The normal-filesystem retry passed Next.js 16.2.10 compilation, TypeScript, six static pages, and routes `/`, `/_not-found`, `/dashboard`, `/login`. |
| `cd ml-api; ..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider` | PASS | 107 passed, 7 standalone emulator-adapter skips, 1 expected xfail, 40 warnings. Warnings were dependency/deprecation notices; the real local Myanmar case executed and required manual review. |
| `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_evaluate_department_model.py scripts/tests/test_historical_similarity.py scripts/tests/test_bilingual_inference.py scripts/tests/test_finalize_department_model.py -p no:cacheprovider` | PASS | 44 passed, 9 joblib/NumPy deprecation warnings. Covers evaluation reconciliation, similarity, bilingual safety contracts, and frozen artifact finalization contracts without retraining. |
| `cd firebase; npm.cmd test` | PASS on unchanged retry | First launcher exited code 1 before Auth readiness; all relevant ports were free and no emulator process remained. Retry passed 4 Firestore rules, 1 Auth identity, 7 real emulator adapters, and 3 Playwright tests. Expected `PERMISSION_DENIED` logs prove negative rules cases; adapters emitted 7 dependency warnings. |

The complete historical data pipeline and full held-out evaluator were not
rerun: they require ignored multi-gigabyte datasets and would attempt protected
artifact publication. Current aggregate hashes and focused integrity tests
passed instead. The Myanmar validation publisher was not rerun because the
owner-reviewed output already exists and the command intentionally refuses to
overwrite it. No dependency was installed or changed.

## 6. Firebase and demo state

- Root `firebase.json` configures Auth at `127.0.0.1:9099`, Firestore at
  `127.0.0.1:8185`, rules at `firebase/firestore.rules`, and disables Emulator
  UI. The harness uses project `demo-complaintguard`.
- `firebase/run-emulator-tests.ps1` starts isolated emulators, seeds identities,
  runs rules/Auth/adapters/browser tests, and stops only its child processes.
  Ports 3000, 4400, 4500, 8000, 8185, 9099, and 9150 were released afterward.
- The seed defines four synthetic customers, six staff identities (one for each
  department), and one manager. Passwords are generated into ignored
  `firebase/.firebase/seeded-identities.json` and are intentionally absent here.
  No admin identity is seeded.
- Normal reseeding preserves existing emulator tickets. The test harness uses
  explicit `--reset-firestore` between isolated phases. Emulator data is local
  and process/session state is not production persistence; no emulator export
  is tracked.
- Verified access: customers are limited to owned tickets/messages; staff need
  exact department equality and cannot read null/other-department tickets;
  managers can read operational tickets; direct client ticket/message/event
  writes are denied; trusted backend endpoints repeat authorization.
- Current demo flow is verified with synthetic data for high-confidence English
  routing, low-confidence manager review/override, staff/customer messaging,
  awaiting-customer/resume, resolution, feedback, bilingual dashboards, and
  mobile containment.
- Guides: `docs/local_setup.md`, `docs/demo_guide.md`,
  `docs/final_demo_guide.md`, `docs/day31_final_e2e_verification.md`, and
  `docs/day32_final_packaging.md`.

## 7. Repository and Git state

- Branch at entry: `main`.
- HEAD at entry: `8c78604f38593d6996d3ea6e4ad0ebb224cf8c2a`.
- Upstream: `origin/main`; 0 commits ahead and 0 behind at inspection.
- Initial working tree: clean; no tracked modifications or non-ignored
  untracked files.
- Intended checkpoint changes: this new document and the minimal Model Hunting
  tracking entry in `docs/task_board.md` only.
- Existing tags: none.
- Ignored local dependencies, model/cache files, build output, Firebase state,
  and logs remain outside Git. No generated file, raw dataset, emulator export,
  archive, credential, or temporary artifact belongs in the checkpoint commit.

## 8. Known limitations and unresolved issues

- Very short/ambiguous English text can lack discriminating features and enter
  manual review; longer text can still be confidently wrong.
- The model confuses Transfer & Payment with Account Support: the held-out
  matrix records 252 of 563 true transfer cases predicted as Account Support.
- Confidence is uncalibrated. High confidence does not guarantee correctness;
  the `0.60` threshold is operational policy, not a calibrated cutoff.
- CFPB Product/Issue-derived labels are policy proxies, not actual company
  department ground truth. The bounded sample and strong class imbalance create
  domain/representation limitations.
- English held-out evidence does not establish Myanmar performance. The current
  Marian and base-NLLB evidence failed acceptance; Myanmar/mixed remains manual
  review.
- Only local Firebase emulators and headless Chrome are verified. Production
  Firebase, deployment, physical devices, multi-browser behavior, and an
  independent security audit are not verified.
- This is an academic prototype, not a production system. Retention/deletion,
  monitoring, rate limiting, recovery, admin operations, and public deployment
  remain incomplete.

## 9. Safe rollback instructions

After an approved checkpoint commit and annotated tag exist:

1. Inspect current work with `git status` and `git diff`. Never use
   `git reset --hard` or discard uncommitted files.
2. If work is uncommitted, preserve it first on its own branch and commit it, or
   use `git stash push -u -m "preserve work before checkpoint recovery"` and
   verify the stash with `git stash list`.
3. Create a separate recovery branch without moving or rewriting an existing
   branch: `git switch -c recovery/pre-model-hunting
   pre-model-hunting-checkpoint-v1`.
4. Verify restoration with `git rev-parse HEAD`, `git status`, the model and
   evidence SHA-256 checks, frontend/API suites, focused classifier/bilingual
   tests, and the isolated Firebase harness recorded above.
5. Restore preserved work deliberately with a merge/cherry-pick or
   `git stash apply`; use `apply`, not `pop`, until the result has been reviewed.

The proposed tag does not exist yet and must not be used until its target commit
and annotation are separately approved and verified.

## 10. Model Hunting phase entry criteria

Candidate evaluation must preserve:

- the exact six-label set and label order;
- the frozen 29,942-record held-out test set, with no tuning or selection on it;
- the existing accuracy, balanced accuracy, macro/weighted precision, recall,
  F1, per-department metrics, confusion matrix, confidence, latency, and resource
  reporting definitions;
- leakage controls, deterministic split/provenance, and the current text
  normalization contract where a candidate is intended as a drop-in model;
- the current known-good model artifact, hash, runtime path, and production/demo
  behavior until a candidate satisfies approved acceptance criteria;
- manual review, manager override/audit evidence, department isolation,
  bilingual interface, and all customer/staff/manager workflows;
- synthetic-only demo records, ignored raw/intermediate data and model caches,
  zero-cost/offline constraints, and no production service change.

Candidate development data must remain separate from frozen validation and
held-out test evidence. A candidate result is research evidence, not authority
to replace the known-good model.

## 11. Next phase summary

The next planned Model Hunting phase will evaluate candidates for short English
complaints, Myanmar complaints, six-department classification accuracy,
confidence reliability/calibration, CPU latency and memory, offline/free
usability, and integration complexity. Model Hunting is not started or complete
at this checkpoint, and no candidate is approved for production/demo use.
