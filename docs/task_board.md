# Project Task Board

This lightweight board is optimized for one active developer. `PROJECT_PLAN.md` remains the schedule and source of truth.

## Backlog

- Confirm which official team members, if any, will review or present later.
- Choose the repository remote/hosting organization when collaboration begins.
- Approve a configurable complaint-text retention and deletion period before production deployment.

## In Progress

### Day 10

- [x] Implement NFC/whitespace normalization and explicit English, Myanmar, mixed, invalid, and unsupported-script detection.
- [x] Pin and verify local PyTorch-only Myanmar-to-English translation at immutable revision `848eae0c1676cfce9bb791c200e8228e5a6396ff`.
- [x] Preserve the frozen Day 9 classifier contract and keep translation failure distinct from low-confidence fallback.
- [x] Add structured missing, timeout, failed, empty, and non-fatal slow-translation behavior.
- [x] Run 30 privacy-safe synthetic cases, five for each fixed department.
- [x] Complete owner translation-quality review for every synthetic case: 5 score-2, 9 score-1, and 16 score-0; usable translation acceptance failed at 14/30.
- [x] Diagnose translation and classifier failures without tuning on the frozen validation cases.
- [x] Research stronger Myanmar-to-English checkpoints and approve a candidate-specific 2.6 GB cache ceiling for a pinned NLLB-200 600M base plus LoRA adapter.
- [x] Freeze a separate 30-case privacy-safe checkpoint development set without executing it.
- [x] Prepare and statically validate a free-Colab development-only evaluation notebook after local acquisition was blocked by the 12 GB RAM gate.
- [x] Execute the 30-case development set in free Colab using pinned base NLLB; the intended LoRA adapter was unavailable and not used.
- [x] Record 30/30 successful translation executions, zero empty/error outputs, and 9/30 (30%) routing correctness.
- [x] Complete owner semantic review: 13 pass, 10 partial and 7 fail; pass plus partial was 23/30, below the prior 24/30 usable threshold.
- [ ] Accept a final Myanmar translation route; neither Marian nor base NLLB has met the approved quality and routing thresholds.
- Day 10 status: In Progress; the Colab result is development evidence, Myanmar production readiness is not approved, and no final route is accepted.

## Review

### Day 31

- [x] Fast-forward local `main` to verified Day 30 merge commit `b558eee` and
  create `test/day31-final-e2e-verification` from that clean base.
- [x] Establish the public/auth, customer, low-confidence, staff, manager,
  security, bilingual/responsive, privacy, cleanup, and model-integrity matrix
  before source-code changes.
- [x] Pass 74 frontend tests, TypeScript, ESLint, the Next.js production build,
  107 standalone backend tests, 9 focused evaluation/similarity tests, Ruff
  check, and Ruff format check.
- [x] Pass 4 Firestore rules tests, 1 Auth identity test, 7 emulator adapter
  tests, and 3 Playwright tests covering the complete synthetic high- and
  low-confidence workflows, role isolation, and 390 x 844 bilingual UI.
- [x] Reconcile the frozen model and source/generated Day 18 hashes, release all
  harness ports, preserve the canonical snapshot, and pass secret, forbidden
  tracked-artifact, UTF-8, and Git integrity checks.
- [x] Record the unchanged Matplotlib blocker for the complete root scripts
  suite without installing packages or substituting global Python.
- Day 31 status: Review. No product defect or source-code fix was required; the
  documentation-only evidence remains uncommitted pending owner approval.

### Day 30

- [x] Verify `main` at `6368e78` as the clean base and confirm Day 29 produced
  no repository commit, diff, or tracked PowerPoint output.
- [x] Audit the implemented public, customer, department-staff, and manager UI
  routes and states without changing classifier, evidence, backend contracts,
  Firebase rules, or deployment.
- [x] Localize customer history/detail/message/feedback states in English and
  Myanmar and clarify the awaiting-customer timeline.
- [x] Improve long-text containment, narrow-screen padding, table/dialog
  containment, keyboard focus visibility, feedback rating semantics, and
  manager override clarity.
- [x] Display the existing authoritative balanced-accuracy value without
  changing model evidence.
- [x] Add unit and isolated emulator browser regressions for bilingual mobile
  containment, accessibility semantics, complete customer/staff lifecycle,
  feedback, manual review/override, and department isolation.
- Day 30 status: Review. Implementation and verification are complete, but no
  commit has been created pending owner approval.

## Done

### Day 1

- Read `PROJECT_PLAN.md` and freeze the title, problem, users, departments, must-haves, and exclusions.
- Create the Git repository structure, root README, scope, task board, safe ignore rules, and placeholder environment template.
- Record one active developer as owner with self-review checkpoints.

### Day 2

- Confirm `D:\ComplaintGuard` and branch `chore/day-2-architecture` before changes.
- Audit the installed local software without installing dependencies first.
- Scaffold the npm-based Next.js frontend with TypeScript, App Router, Tailwind CSS, ESLint, and `src`.
- Keep the generated page as a simple environment-ready placeholder with no ComplaintGuard features.
- Create and verify the root Python 3.12 `.venv`.
- Record lightweight future Python development dependencies without installing them.
- Document the zero-cost architecture, offline training flow, live prediction flow, data boundaries, and free-tier limitations.
- Document local setup and Windows PowerShell troubleshooting.
- Verify the frontend with ESLint, a production build, and an HTTP 200 development-server response.
- Confirm `.venv`, `node_modules`, `.next`, local environment files, and raw CFPB data are ignored.
- Review all Day 2 files and scan trackable content for likely secrets; none were found.
- Record the unresolved moderate transitive PostCSS advisory without applying npm's breaking forced downgrade.
- Confirm the Firebase project is on Spark with no billing account attached.
- Confirm free Vercel and Hugging Face account logins work.

### Day 3

- Reconfirm branch `data/dataset-profile` and a clean starting worktree.
- Validate the 1,420,663,360-byte CFPB archive with ZIP CRC testing and SHA-256.
- Confirm `data/raw/` is ignored and extract the single CSV member without changing the archive.
- Profile all 17,034,951 rows in 171 chunks without emitting narratives or complaint-level records.
- Record snapshot metadata, schema, logical types, missing values, safe aggregate distributions, intended columns, and privacy limitations.
- Document the source data dictionary and reproducible local data procedure.
- Record the initial mapping approach without creating the mapping or starting cleaning/model work.
- Perform the owner self-review and retain all Day 3 changes uncommitted for review.

### Day 4

- Define and owner-approve the Firestore operational schema, collection relationships, source-of-truth boundaries, and complaint lifecycle.
- Define and owner-approve the customer, staff, manager, and admin access matrix.
- Create and owner-approve deny-by-default initial Firestore development rules with explicit authenticated, ownership, department, and role checks.
- Create and owner-approve implementation-neutral Customer, Staff, and Manager wireframes with responsive and loading, empty, and error states.
- Define and owner-approve English/Myanmar translation-key namespaces with English fallback.
- Verify cross-document consistency, privacy boundaries, stable department IDs, ignore rules, tracked-data boundaries, and diff formatting.
- Retain the unresolved production retention period as a required pre-deployment decision; it does not block the Day 4 design milestone.
- Record that Firebase CLI and emulator tooling remain unavailable, so the rules are not compiled, emulator-tested, or production-approved.

### Day 5

- [x] Confirm the approved privacy-minimized schema and immutable raw-data boundary.
- [x] Implement reusable Unicode normalization, whitespace cleanup, URL removal, and conservative PII-reduction functions.
- [x] Implement deterministic chunked CSV cleaning with strict required fields and disk-backed cross-chunk deduplication.
- [x] Produce the final full cleaned corpus at the ignored, untracked path `data/interim/cfpb/complaints_cleaned_corrected.csv`.
- [x] Produce the aggregate-only version-2 report at `data/cfpb_cleaning_corrected_report.json` with reconciled before/after counts and no complaint-level values.
- [x] Add synthetic automated tests for validation, redaction, rejection precedence, duplicate handling, and publication behavior; the complete suite passed 117 tests in 25.42 seconds.
- [x] Complete the authorized syntax, synthetic-test, full-run, production-validation, ignore, integrity, privacy, and tracked-content checks. Ruff was not run during the corrected full-run or final review.
- [x] Complete the owner-authorized full run and strict reviews. Run `e1996a2c34d0457fa08b83864b4f1a9d` processed 17,034,951 rows in 171 chunks, retained 3,822,576, rejected 13,212,375, and passed production completed-pair validation.

### Day 6

- [x] Build a deterministic chunked EDA pipeline over the corrected Day 5 CSV.
- [x] Produce ten reconciled aggregate files without complaint-level output.
- [x] Produce six readable aggregate-only charts and one evidence-based finding per chart.
- [x] Document imbalance, possible bias, limitations, reproducibility, strict calendar validation, and safe completion publication.
- [x] Add synthetic tests and complete the authorized full EDA verification.
- [x] Complete correction verification and the second strict read-only re-review with no Critical or Major findings.
- [x] Process 3,822,576 of 3,822,576 rows from corrected cleaning run `e1996a2c34d0457fa08b83864b4f1a9d`; targeted Day 6 tests passed 27 tests and the complete relevant suite passed 144 tests.
- Day 6 status: Done.

### Day 7

- [x] Finalize reviewable mapping policy `v1` using CFPB Product/Issue only.
- [x] Implement exact-pair, Product-fallback, and explicit `general_support` precedence.
- [x] Prove all six labels, narrative independence, normalization, invariants, chunking, metadata, and publication behavior with 22 synthetic tests.
- [x] Build dataset `v1` from 3,822,576 corrected rows in 39 bounded chunks with zero dropped rows.
- [x] Validate the exact narrative/label schema, label and method reconciliation, aggregate-only manifest, size, and SHA-256.
- [x] Keep the 3,958,969,065-byte output ignored and untracked and document mapping limitations and class imbalance.
- Day 7 status: Done.

### Day 8

- [x] Validate dataset/mapping `v1` and all 3,822,576 source rows in bounded chunks.
- [x] Implement deterministic sampling, conservative normalization, duplicate-group splitting, and training-only balancing.
- [x] Fit word-level TF-IDF only on training data and train `MultinomialNB(alpha=1.0)`.
- [x] Evaluate 29,942 untouched test rows with fixed-order aggregate metrics and a reconciled confusion matrix.
- [x] Publish an ignored model plus aggregate-only completed metrics without narrative, vocabulary, Complaint ID, or row-level predictions.
- [x] Verify 19 synthetic tests, Ruff check/format, smoke behavior, overwrite protection, and privacy boundaries.
- [x] Document the honest macro-F1 result of 0.688484; the 0.70 target was not achieved.
- Day 8 status: Done.

### Day 9

- [x] Preserve Day 8 as the locked baseline and recreate its deterministic sample and duplicate-group partitions.
- [x] Compare four predeclared TF-IDF/MultinomialNB and training-cap candidates using validation macro-F1 only.
- [x] Select confidence threshold from five fixed values using validation only; selected threshold was 0.0.
- [x] Evaluate the selected `lower_alpha` candidate on 29,942 test rows exactly once.
- [x] Export ignored frozen model `v1` with vectorizer, classifier, ordered labels, threshold, fallback, versions and metadata.
- [x] Publish aggregate-only metrics and privacy-safe confusion/error analysis with exact reconciliation.
- [x] Verify 12 focused synthetic tests and Ruff checks.
- [x] Record macro-F1 0.692345 and the +0.003861 Day 8 improvement; the 0.70 target remains unmet.
- Day 9 status: Done.

### Day 11

- [x] Create the local FastAPI ML service around frozen model `v1`.
- [x] Add typed `GET /health` and `POST /predict` endpoints.
- [x] Enforce the six stable department IDs and return genuine classifier confidence.
- [x] Validate missing, empty, whitespace-only, wrong-type, extra-field, over-limit and unsupported input.
- [x] Return structured errors without echoing complaint text or exposing local paths.
- [x] Keep Myanmar and mixed input explicitly blocked as a development baseline that is not production-ready.
- [x] Verify 15 focused API tests, 208 API/affected regression tests, Ruff check and Ruff format check.
- [x] Confirm frozen-model integrity and a real synthetic prediction response.
- Day 11 status: Done.

### Day 12

- [x] Build responsive home, login and protected dashboard shells.
- [x] Add English/Myanmar UI catalogs, per-key English fallback and a persistent language switch.
- [x] Add configuration-gated Firebase email/password authentication without committing configuration or credentials.
- [x] Validate active Firestore profiles and the four approved roles: customer, staff, manager and admin.
- [x] Add role-aware dashboard navigation and signed-out route protection.
- [x] Add loading, missing-configuration, authentication and permission error states.
- [x] Verify prepared customer, staff and manager accounts reach the correct dashboard shells.
- [x] Verify signed-out dashboard redirection, English/Myanmar switching and clean-restart hydration.
- [x] Verify nine synthetic frontend tests, ESLint, TypeScript and the production build.
- Day 12 status: Done on 29 July 2026.

### Day 13

- [x] Resolve pending classification with nullable `departmentId` and `routingSource: pending` without adding a seventh department.
- [x] Add the bilingual customer complaint form to the authenticated Day 12 dashboard.
- [x] Validate, trim and normalize complaint text up to 5,000 characters and preserve input after failures.
- [x] Send only complaint text and input locale with the Firebase ID token to trusted FastAPI.
- [x] Verify the token and active customer role, derive the owner UID, and reject protected request fields.
- [x] Apply deterministic demo PII redaction before persistence.
- [x] Create Firestore tickets with generated IDs, server timestamps and protected pending defaults.
- [x] Keep client ticket writes denied and prove null-department tickets do not match staff access.
- [x] Show accessible loading, validation, authentication, permission, backend, unexpected-error and success states.
- [x] Verify 27 backend tests, 16 frontend tests, Ruff, ESLint, strict TypeScript, production build, Firebase Admin import and `git diff --check`.
- Day 13 status: Done on 1 August 2026.
- ML classification, prediction population and department routing remain deferred; Day 13 does not fabricate them.

### Day 14

- [x] Add a department-scoped staff ticket queue with status, priority and date filters.
- [x] Add ticket detail, participant-safe messages and immutable audit history.
- [x] Require a verified active staff profile with a valid department on every endpoint.
- [x] Hide cross-department, missing and pending null-department tickets with the same not-found response.
- [x] Add only the four approved staff lifecycle transitions through trusted endpoints.
- [x] Bind/redact staff replies and persist their immutable message and audit event atomically.
- [x] Make resolution update plus resolution event transactional and rollback-safe.
- [x] Add idempotent `request_reassignment` and `request_escalation` events without changing protected state.
- [x] Add a fixed Admin-only synthetic `card_atm`/`triaged` fixture procedure separate from customer submission.
- [x] Add English/Myanmar queue, filters, detail, statuses, errors, loading and empty states.
- [x] Verify 66 backend tests, 27 frontend tests, Ruff, ESLint, strict TypeScript, production build and `git diff --check`.
- Day 14 status: Done in automated/synthetic scope on 2 August 2026.
- Firebase Emulator rules evidence and live Firebase workflow verification remain outstanding; neither is claimed as passed.

### Day 15

- [x] Add customer-owned complaint history and ticket detail.
- [x] Add participant-safe customer/staff messaging and customer-visible status.
- [x] Add resolved-ticket feedback with duplicate prevention.
- [x] Enforce customer ownership in trusted backend queries and transactions.
- Day 15 status: Done; later emulator verification confirmed the integrated customer/staff conversation flow.

### Day 16

- [x] Add manager operational totals, active/resolved counts, low-confidence count, department workload, and average resolution time.
- [x] Add manager-only low-confidence review and transactional department override without rewriting the original prediction.
- [x] Enforce active-manager API authorization.
- Day 16 status: Done for implemented operational analytics and department override. Broader priority/reopen/close manager operations were not implemented.

### Day 17

- [x] Integrate the frozen TF-IDF/Multinomial Naive Bayes classifier with trusted ticket submission and routing.
- [x] Route accepted high-confidence English predictions transactionally and retain low-confidence cases for manager review.
- [x] Run genuine Myanmar and mixed-language inference while keeping both manual-review only pending quality acceptance.
- [x] Add explicit Auth and Firestore Emulator configuration, deterministic local identity/profile seeding and reliable cleanup.
- [x] Add customer submission idempotency and emulator-backed routing, authorization, transaction and rollback coverage.
- [x] Verify high-confidence and manual-review browser workflows using authenticated emulator identities without fallback identities.
- [x] Verify backend, ML, rules, Auth, Firestore adapters, frontend, production build and Playwright E2E locally.
- Day 17 status: Local/emulator verified on 8 August 2026; live Firebase and production deployment are not verified.
- The `0.60` routing confidence threshold is configurable operational policy, not a statistically calibrated threshold.
- Frozen-model macro-F1 remains below `0.70`; Myanmar translation quality remains below target, so Myanmar/mixed-language tickets remain manual-review only.

### Day 18

- [x] Reconstruct the seed-`20260727` 200,000-record sample and exact normalized-narrative partitions from the complete mapped corpus.
- [x] Evaluate the unchanged frozen model on the genuine 29,942-record held-out test partition without retraining.
- [x] Reconcile accuracy, macro/weighted metrics, per-department metrics and the confusion matrix exactly against locked Day 9 evidence.
- [x] Publish stable aggregate JSON/CSV artifacts with dataset counts, class distributions, confidence analysis and privacy-safe example metadata.
- [x] Build a local ignored cosine-similarity index over exactly 29,942 held-out TF-IDF vectors without narrative strings.
- [x] Add focused evaluation/schema/similarity tests and document methodology, metric meanings, leakage controls and limitations.
- Day 18 status: implementation and local evidence complete; 229 data/ML script tests, 102 backend tests, 44 frontend tests, scoped Ruff/format, TypeScript, ESLint, artifact validation and diff checks passed. Seven emulator-dependent backend tests were skipped; broad historical Ruff findings are documented without modifying unrelated files.

### Day 19

- [x] Add a manager-dashboard model and dataset analytics section sourced from the committed Day 18 evaluation evidence.
- [x] Validate schema, metrics, six-department ordering, partitions, supports, confidence bins, privacy flags and similarity metadata in TypeScript.
- [x] Visualize model metrics, pipeline counts, department performance, held-out distribution, confidence bins and the full confusion matrix without a chart dependency.
- [x] Add bilingual, privacy-safe Dataset Evidence panels to customer, staff and manager review details.
- [x] Keep similarity honest as a local-only, undeployed 29,942-record TF-IDF foundation with no neighbor results or narratives.
- [x] Preserve the existing manager-only dashboard role boundary and distinguish it from bundled non-sensitive aggregate evidence.
- [x] Add focused parser, reconciliation, rendering, authorization, localization, privacy and accessibility tests.
- Day 19 status: Done and merged through `629fc5d`; 64 frontend tests, TypeScript, ESLint, production build, focused ML evaluation tests, backend preservation tests, artifact/hash reconciliation, and Git integrity passed before merge.

### Day 20

- [x] Reconcile current setup, architecture, security, milestone, and operating-mode documentation.
- [x] Publish demo, claim-evidence, release, final-report, presentation-outline, and final-test sources.
- [x] Add a safe repository-relative final verification wrapper.
- [x] Run frontend, ML/evaluation, backend, Firebase rules/adapters/E2E, Ruff, artifact, UTF-8, secret, privacy, size, and Git checks.
- [x] Record actual results and mark completion only after mandatory acceptance checks pass.
- Day 20 status: Complete in the supported local/emulator scope. All available mandatory gates pass, including repository-wide Ruff check/format and the final wrapper. The complete scripts suite remains unavailable because `.venv` lacks Matplotlib. Public deployment, QR code, production Firebase, retention/deletion, and admin operations remain incomplete.

### Maintenance and Validation Phase

- [x] Reconcile the approximately 83.4% Account Support observation to the
  longer synthetic mobile-banking transfer ticket and reproduce it with the
  current hash-verified frozen v1 artifact.
- [x] Protect `Mobile transfer failed` as an authenticated low-confidence,
  unassigned manual-review regression.
- [x] Record the clear mobile-transfer high-confidence misroute as a strict
  expected-failure regression rather than asserting the wrong label is correct.
- [x] Add initial Account Support and Card & ATM short user-style cases.
- [ ] Add short user-style cases for all six departments.
- [ ] Expand Transfer & Payment versus Account Support boundary coverage.
- [ ] Add accuracy-by-text-length analysis.
- [ ] Evaluate calibration using validation data only; confidence remains an
  uncalibrated model output.
- [x] Verify with a controlled test double that manager override remains
  available for a wrong-high-confidence prediction without rewriting original
  prediction evidence.
- [x] Document non-destructive emulator export/import with new-path protection.
- [ ] Execute and verify a full emulator export, shutdown, import, and history
  recovery in a separately approved maintenance window.
- [x] Keep Myanmar/mixed complaints manual-review-only.
- [x] Preserve the frozen Day 18 model artifact, metrics, and held-out test set.
- [ ] Keep production Firebase deployment/rules verification incomplete.

## Day 2 completion rule

Move verification to Done only after `npm run lint` and `npm run build` pass and the repository audit confirms that secrets and generated/local files will not be committed. Account availability is confirmed, but credentials and service integration remain deferred to their scheduled project days.

## Day 3 completion rule

Move Day 3 work to Done only after archive validation, extracted-size verification, a complete chunked profile, documentation review, ignore checks, and a scan confirming that tracked outputs contain no narratives or complaint-level records. Cleaning, sampling, translation, feature engineering, mapping implementation, and model work remain deferred.

## Day 5 completion rule

Day 5 started early with owner approval on 23 July 2026. Move Day 5 work to Done only after the reusable cleaner and synthetic tests pass, the complete raw CSV is processed successfully in bounded chunks, all input rows reconcile to retained plus mutually exclusive rejection counts, the aggregate report is reviewed, the full cleaned CSV and processing artifacts are confirmed ignored, raw-file integrity is unchanged, and tracked outputs are scanned to confirm that they contain no complaint IDs, narratives, row-level records, or personal identifiers. A bounded smoke test alone does not complete Day 5. Mapping, EDA, translation, feature engineering, sampling, model training, frontend work, and Firebase implementation remain deferred.
