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

- None.

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

## Day 2 completion rule

Move verification to Done only after `npm run lint` and `npm run build` pass and the repository audit confirms that secrets and generated/local files will not be committed. Account availability is confirmed, but credentials and service integration remain deferred to their scheduled project days.

## Day 3 completion rule

Move Day 3 work to Done only after archive validation, extracted-size verification, a complete chunked profile, documentation review, ignore checks, and a scan confirming that tracked outputs contain no narratives or complaint-level records. Cleaning, sampling, translation, feature engineering, mapping implementation, and model work remain deferred.

## Day 5 completion rule

Day 5 started early with owner approval on 23 July 2026. Move Day 5 work to Done only after the reusable cleaner and synthetic tests pass, the complete raw CSV is processed successfully in bounded chunks, all input rows reconcile to retained plus mutually exclusive rejection counts, the aggregate report is reviewed, the full cleaned CSV and processing artifacts are confirmed ignored, raw-file integrity is unchanged, and tracked outputs are scanned to confirm that they contain no complaint IDs, narratives, row-level records, or personal identifiers. A bounded smoke test alone does not complete Day 5. Mapping, EDA, translation, feature engineering, sampling, model training, frontend work, and Firebase implementation remain deferred.
