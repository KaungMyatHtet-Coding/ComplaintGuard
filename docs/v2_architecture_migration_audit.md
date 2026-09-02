# ComplaintGuard Version 2  Architecture and Migration Audit

## Audit metadata

- Audit type: Read-only repository assessment
- Source branch: upgrade/v2-aya-complaint-workflow
- Baseline commit: 3034281
- Implementation status: Not started

## Audit scope and verified baseline

Audit scope: repository at D:\ComplaintGuard, branch upgrade/v2-aya-complaint-workflow.

### Verified repository facts

- Branch is correct.
- Worktree was clean before this documentation write.
- No dependencies, Firebase data, or Emulator data were modified.
- No tests were executed because the Firebase harness creates and deletes Emulator fixtures, and frontend pre-test hooks synchronize files.
- The audit distinguishes repository facts from recommendations and unresolved unknowns.

## A. Current V1 architecture

### Roles and authorization

### Verified repository facts

Verified roles are customer, staff, manager, and admin. Evidence: ml-api/app/schemas.py, ml-api/app/admin_auth.py, ml-api/app/manager_workflow.py, firebase/firestore.rules, and frontend/src/lib/auth-policy.ts.

| Capability | Customer | Staff | Manager | Admin |
|---|---:|---:|---:|---:|
| Submit complaint | Yes | No | No | No |
| Read own tickets | API projection | No | No | No |
| Read department tickets | No | Yes | No | No |
| Reply/update department tickets | No | Yes | No | No |
| Read all tickets | No | No | Yes | Planned/implemented backend path |
| Manual-review list | No | No | Yes | No |
| Override department | No | No | Yes | No |
| Provision Staff/Manager | No | No | No | Yes |
| Disable/reactivate accounts | No | No | No | Yes |
| Direct Firestore client writes | No | No | No | No |

Firestore rules deny direct client reads and writes for tickets, messages, and events. Trusted backend code uses Firebase Admin SDK and therefore bypasses rules; it performs separate application authorization. Admin is implemented in local backend/UI slices, but broader Admin operations described historically remain incomplete.

### Firestore collections and documents

### Verified repository facts

Verified collection usage:

- users/{uid}
- departments/{departmentId}; authenticated reads are allowed, but current backend usage is limited.
- tickets/{ticketId}
- tickets/{ticketId}/messages/{messageId}
- tickets/{ticketId}/events/{eventId}
- tickets/{ticketId}/actions/{actionId}
- feedback/{feedbackId}
- notifications/{notificationId}
- customerMessageActions/{actionId}
- adminProvisioningActions/{actionId}
- Admin lifecycle action/guard/audit collections defined in ml-api/app/admin_lifecycle.py
- dashboardSummaries/{summaryId}

Historical docs/firestore_schema.md describes dashboard_stats, but current code uses dashboardSummaries.

Current ticket fields include customerId, complaintText, inputLocale, departmentId, assignedStaffId, status, priority, predictedDepartmentId, predictionConfidence, routingSource, manualReviewReason, escalated, resolutionSummary, createdAt, updatedAt, and resolvedAt. assignedStaffId exists but is not populated by automatic assignment.

### Complaint lifecycle

### Verified repository facts

Current status enum:

| submitted | triaged | in_progress | awaiting_customer | resolved | closed |
|---|---|---|---|---|---|

Current staff transitions:

| From | Allowed destinations |
|---|---|
| triaged | in_progress |
| in_progress | awaiting_customer, resolved |
| awaiting_customer | in_progress |

Implemented behavior:

- A complaint is initially created as submitted.
- Customer messages may be added while the ticket is not closed.
- Staff may reply.
- Staff may request reassignment or escalation; these are audit requests, not completed workflows.
- Staff may resolve with a required resolution summary.
- Customer feedback is supported for resolved tickets.
- Reopen is not implemented.
- Closed-ticket transition is not exposed through the Staff transition API.
- There is no formal Received, Queued, Assigned, Additional Information Required, Under Investigation, or Action in Progress vocabulary.

### Classification and routing

### Verified repository facts

The model is TF-IDF plus Multinomial Naive Bayes with a frozen V1 artifact and six labels: transfer_payment, account_support, card_atm, fraud_security, loan_credit, and general_support. The default confidence threshold is 0.60. The score is maximum class probability and is explicitly not calibrated reliability.

Evidence: ml-api/app/model.py, ml-api/app/routing.py, ml-api/app/config.py, and evaluation/day18/model_evaluation_v1.json.

Current behavior:

1. Create a durable pending ticket.
2. Detect English, Myanmar, mixed, or unsupported input by script.
3. Translate Myanmar or mixed input with a locally cached pinned model.
4. Classify translated or English text.
5. Low-confidence predictions become manual_review.
6. Myanmar and mixed-language predictions always become manual_review because translation quality was not approved.
7. Translation/classification failures become manual_review.
8. Manual-review tickets have no department queue and are sent to Manager notifications.

Relevant paths: ml-api/app/routing.py; ml-api/app/ticketing.py:211-231; ml-api/app/ticketing.py:340-500.

### Notification behavior

### Verified repository facts

Notifications are persisted in Firestore under notifications. Current events include complaint received, department assigned, staff reply, information requested, status changed, complaint resolved, department complaint available, ticket assigned, customer reply, high-priority ticket, Manager manual review required, unassigned ticket, escalation requested, workload observation, and Admin account/system notifications.

Notification persistence is transactionally staged with ticket changes and uses deterministic deduplication. Customer events are customer-specific; assigned-ticket events are individual Staff-specific; department availability is broadcast to active department Staff; manual-review observations are Manager-specific; notifications have finite retention rather than permanent history.

Evidence: ml-api/app/notifications.py, firestore.indexes.json, and docs/workflow_notification_contract.md.

There is no persistent department workspace inbox document or queue-level notification identity.

### Local/cloud boundary

### Verified repository facts

The verified runtime is local Next.js, local FastAPI, Firebase Auth Emulator, Firestore Emulator, and the local frozen model. Project ID is demo-complaintguard; Auth Emulator is 127.0.0.1:9099; Firestore Emulator is 127.0.0.1:8185. Candidate Cloud project complaintguard is not connected or runtime-verified.

Evidence: ml-api/app/firebase_environment.py, frontend/src/lib/runtime-environment.ts, frontend/src/lib/firebase-environment.ts, firebase.json, docs/cloud_firebase_staging_adoption.md, and README.md.

In-memory backends exist for pure tests/development: InMemoryCustomerBackend, InMemoryStaffBackend, InMemoryManagerBackend, and InMemoryNotificationBackend. They are not permanent storage.

## B. Verified V1-to-V2 gaps

### Verified repository facts and migration assessment

| Gap | Relevant paths | Current behavior | Required V2 behavior | Migration risk | Tests affected |
|---|---|---|---|---|---|
| Six-label taxonomy | ml-api/app/schemas.py, model.py, routing.py, frontend/src/lib/department-labels.ts, mapping JSON, fixtures | Six stable IDs | Eight provisional Myanmar-banking categories | Very high: model artifact, profile validation, UI, fixtures, rules, indexes, analytics depend on IDs | Model, routing, schema, label, and Emulator authorization tests |
| Manager role remains | schemas.py, manager_workflow.py, main.py, notifications.py, Manager UI/tests | Manager has analytics, manual review, override | Remove Manager role/workflow | High: historical records and routes require safe migration | Manager workflow/API/UI/notification/rules tests |
| Manual review remains | routing.py, ticketing.py, manager_workflow.py | Low confidence, Myanmar, mixed, and failures route to Manager review | Automatic fallback to Customer Complaint Unit | High: avoid stranded tickets | Routing, submission, notification, evidence tests |
| No automatic Staff assignment | assignedStaffId and staff_workflow.py | Department notifications only | Atomic assignment by membership, status, availability, capacity, priority, age, workload, round-robin | Very high: concurrency and duplicate ownership | New transaction/race tests |
| No queue-safe busy state | staff_workflow.py, ticketing.py | No capacity or availability model | Leave ticket in department queue when all Staff are busy | High | Queue and capacity tests |
| Department workspace absent | departments and ticket fields | Department is a string/query boundary | Persistent workspace, queue metadata, policy | Medium/high | Rules, Admin, queue, notification tests |
| Staff historical identity weak | users/{uid}, lifecycle code | Profiles can be disabled; records reference UID | Immutable historical Staff identity; never hard-delete | High | Lifecycle, audit, export, analytics tests |
| Lifecycle incomplete | schemas.py, staff_workflow.py, customer_workflow.py | No reopen; limited transition graph | V2 lifecycle through Reopened | High | Lifecycle and UI tests |
| Admin incomplete | admin_workflow.py, admin_directory.py, Admin UI | Provisioning, directory, lifecycle slices exist | Department CRUD, inspection, analytics, exports, evidence | High | Admin, audit, pagination, export tests |
| Analytics not V2-ready | manager_workflow.py, dashboardSummaries | Broad scans and in-memory aggregation | Admin filters, date ranges, drill-down | High cost/privacy risk | Aggregation, index, export tests |
| Audit inconsistent | ticket events/actions and Admin lifecycle collections | Ticket-local Staff records; separate account records | Unified immutable audit events | High | Audit immutability/attribution tests |
| Manager notification targets remain | notifications.py and frontend notification components | Manager types/navigation exist | Customer Complaint Unit and Staff/department events | Medium | Notification contract/UI tests |
| English-only model assumptions | model.py, routing.py, evaluation artifacts | English CFPB proxy labels | Myanmar-aware or safe fallback | Very high | Myanmar/mixed/unsupported tests |
| Unicode policies differ | language.py, model.py, frontend validation | NFC API; NFKC/casefold model; regex script detection | Unified normalization contract | Medium/high | Unicode tests |
| Export privacy boundary absent | ticketing.py, Admin code | Submission redaction exists; V2 export policy absent | Allowlisted, safe CSV | High | Export privacy/injection tests |
| Local persistence assumptions | InMemory backends and sample data | Pure tests can avoid Firestore | Operational history must use Firestore | High if used at runtime | Persistence/wiring tests |
| Emulator assumptions | firebase_environment.py, seed scripts | Seed/reset/test paths target Emulator | Emulator remains testing-only | High if Cloud is targeted | Environment guard tests |
| Query scalability | manager_workflow.py, staff_workflow.py | Broad scans and in-memory filters | Bounded indexed/aggregate queries | High on Spark | Index/query-cost tests |
| Shared notification is not ownership | notifications.py | All active department Staff receive availability notices | Individual ownership plus queue fallback | Medium/high | Ownership/race tests |

### Taxonomy evaluation

### Recommendations

The provisional taxonomy is more suitable than the CFPB-derived taxonomy, but it is not a verified AYA Bank internal taxonomy.

Recommended provisional IDs:

| Display category | Provisional ID |
|---|---|
| Account & Branch Services | account_branch_services |
| Cards, ATM & POS | cards_atm_pos |
| Mobile & Internet Banking | mobile_internet_banking |
| Transfers, Payments & Remittance | transfers_payments_remittance |
| Loans & Credit | loans_credit |
| Fraud, Scam & Unauthorized Transactions | fraud_scam_unauthorized |
| KYC, Verification & Account Restrictions | kyc_verification_restrictions |
| General Complaints / Customer Complaint Unit | general_complaints |

Assessment: Account & Branch Services separates branch/service access from KYC; Cards, ATM & POS is a strong combined service category; Mobile & Internet Banking is a necessary V2 addition; Transfers, Payments & Remittance expands V1; Loans & Credit is reusable but needs Myanmar examples; Fraud, Scam & Unauthorized Transactions is a safety queue and should receive high priority; KYC should be separate from ordinary account support; General Complaints is the mandatory safe fallback and intake queue.

AYA’s public grievance page supports multiple channels, privacy, prioritization, timely handling, escalation information, recording, forwarding to relevant departments, and updates if unresolved after one week. It does not establish private department names, internal systems, staffing rules, or ownership. Reference: https://www.ayabank.com/grievance-handling

## C. Proposed V2 architecture

### Recommendations

The following is proposed architecture, not current repository behavior.

### Role and permission matrix

| Capability | Customer | Staff | Admin |
|---|---:|---:|---:|
| Submit complaint | Yes | No | No |
| View own tickets/messages | Yes | No | No |
| Reply to own ticket when requested | Yes | No | No |
| View department queue | No | Assigned departments only | Yes |
| Claim/release eligible ticket | No | Assigned departments only | Yes |
| Update assigned ticket | No | Assigned Staff or department policy | Yes, audited |
| Request additional information | No | Yes | Yes |
| Change lifecycle status | Limited customer actions | Yes within rules | Yes, audited |
| Manage departments | No | No | Yes |
| Create Staff account/profile | No | No | Yes |
| Disable Staff login | No | No | Yes |
| Delete Staff history | No | No | Never permitted |
| View analytics | Own history only | Own operational view | Yes |
| Export CSV | No | No or limited approved view | Yes, audited |
| View audit history | Own ticket history | Relevant ticket history | Yes |

Admin must be an operational administrator, not a Manager replacement with manual triage responsibility. The Customer Complaint Unit should be a department/workspace, not a role.

### Proposed Firestore collections and key fields

Recommended users/{uid}: uid; role customer/staff/admin; displayName; email; locale; active; loginEnabled; employmentStatus active/leave/departed/suspended; departmentIds; availability available/busy/offline/unavailable; capacity; activeWorkload; lastLoginAt; lastAvailabilityAt; createdAt; updatedAt; historicalIdentityKey.

uid remains immutable. Disable login without deleting the profile.

Recommended staffIdentities/{staffIdentityId}: staffIdentityId; uid; displayNameAtTime; emailAtTime; departmentIdsAtTime; employmentStatus; joinedAt; leftAt; disabledAt; profileVersion. This preserves reporting after profile changes.

Recommended departments/{departmentId}: departmentId; displayName; localizedNames; active; isCustomerComplaintUnit; routingEnabled; priorityPolicy; assignmentPolicy; createdAt; updatedAt; createdBy; updatedBy. IDs remain stable; rename display metadata only.

Recommended departments/{departmentId}/queueState/current: queuedCount; assignedCount; oldestQueuedAt; lastAssignmentAt; assignmentSequence; updatedAt. This is an optimization/reconciliation aid, not authoritative history.

Recommended ticket fields: ticketId; customerId; complaintTextRedacted; inputLocale; detectedLanguage; normalizedTextHash; predictedCategory; predictedDepartmentId; predictionConfidence; predictionModelVersion; routingOutcome automatic/fallback/failed; routingReason; departmentId; queueState queued/assigned/completed; assignedStaffId; assignmentVersion; assignmentAttempt; priority; status; createdAt; queuedAt; assignedAt; firstResponseAt; resolvedAt; closedAt; reopenedAt; lastCustomerActivityAt; lastStaffActivityAt; additionalInformationRequestedAt; updatedAt.

The ticket remains authoritative. Queue documents do not replace it.

Messages should include authorUid, authorRole, bodyRedacted, language, createdAt, and visibility.

Immutable ticket events should include eventType, actorUid, actorRole, fromStatus, toStatus, fromDepartmentId, toDepartmentId, fromAssignedStaffId, toAssignedStaffId, reasonCode, reasonTextRedacted, correlationId, and createdAt.

Ticket actions should include actionId, actionType, actorUid, requestFingerprint, resultFingerprint, status, createdAt, and completedAt.

Recommended auditEvents/{auditEventId}: actorUid; actorRole; actionType; targetType; targetId; before; after; reasonCode; correlationId; createdAt; privacyClass. Do not copy full complaint text into general audit events.

Notifications should add recipientType customer/staff/department/admin, recipientId, ticketId, eventId, dedupeKey, createdAt, expiresAt, and readAt. Department notifications identify a queue; Staff notifications identify an individual actor.

### Department workspace model

Each department has a persistent identity, department queue, membership references, queue metrics, assignment policy, audit visibility boundaries, and localized customer-facing names.

Customer Complaint Unit is an ordinary department with a fallback designation. It receives unsupported-language complaints, low-confidence predictions, translation/model failures, unmapped categories, failed assignment attempts, and validation exceptions when a durable ticket exists.

### Routing and automatic assignment flow

Recommended flow:

Create ticket -> persist Received event -> classify -> automatic department or Customer Complaint Unit fallback -> persist Queued event -> transactionally select eligible Staff -> assign or leave queued -> notify department and assigned Staff.

Eligibility: Staff role; active employment; login enabled; valid department membership; recent login/heartbeat; available status; workload below capacity; no conflicting assignment lock.

Selection order: highest priority; oldest queued ticket; lowest active workload ratio; least recently assigned; stable round-robin sequence; UID as final deterministic tie-breaker.

Atomic assignment:

- Read ticket and candidates inside a Firestore transaction.
- Re-read candidate state inside the transaction.
- Confirm ticket remains unassigned and queued.
- Reserve assignment state atomically.
- Write ticket assignment, event, action, and notification in the transaction.
- Retry conflicts.
- If no candidate remains eligible, leave ticket queued.

A failed notification must not undo assignment. Notifications must be retryable and idempotent.

### Complaint lifecycle/state-transition rules

Recommended customer-visible states: Received, Queued, Assigned, Additional Information Required, Under Investigation, Action in Progress, Resolved, Closed, and Reopened.

Suggested transitions:

| From | Destinations |
|---|---|
| Received | Queued |
| Queued | Assigned |
| Assigned | Under Investigation; Additional Information Required |
| Under Investigation | Action in Progress; Additional Information Required |
| Action in Progress | Resolved |
| Additional Information Required | Under Investigation |
| Resolved | Closed; Reopened |
| Closed | Reopened |
| Reopened | Queued; Assigned |

Every transition writes an immutable actor-attributed event. Reopened preserves prior resolution/closure timestamps. Closed requires resolution and closure reason. Customer response to an information request returns the ticket to investigation. Failed prediction never creates an invisible state.

### Notification events

Recommended events: complaint received; complaint queued; department assigned; Staff assigned; additional information requested; customer information received; investigation started; action started; complaint resolved; complaint closed; complaint reopened; high-priority complaint queued; assignment deferred because all Staff are busy; assignment retry failed; Admin system alert.

Manager-specific notification types should not remain in active V2.

### Admin analytics aggregation strategy

Do not repeatedly scan all tickets from the browser. Store immutable ticket/audit events and maintain analyticsDaily/{yyyy-mm-dd} aggregates with department, category, language, status, priority, routing outcome, Staff, counts, and duration sums.

Custom ranges should query bounded daily aggregates, combine them with bounded ticket/event drill-down, enforce a maximum range and pagination, and calculate exact details only on drill-down.

Analytics should distinguish volume, response time, resolution time, reopen rate, queue age, assignment rate, fallback rate, language distribution, model evidence, and Staff workload evidence. Staff performance is evidence and context, not automatic bonus or punishment.

### Privacy-safe CSV export boundary

Export only: ticketReference; createdDate; departmentDisplayName; category; language; priority; status; routingOutcome; predictionConfidenceBand; assignedStaffHistoricalId; assignmentCount; firstResponseDuration; resolutionDuration; reopenCount.

Do not export complaint text by default, emails, phone numbers, UIDs, account/card numbers, NRC/passport identifiers, passwords, PINs, tokens, raw model internals, or unredacted audit payloads. Escape CSV values, protect against spreadsheet formula injection, and audit every export.

## D. Myanmar dataset/model readiness

### Verified repository facts

Reusable assets include the CFPB cleaning/mapping pipeline, TF-IDF plus MultinomialNB implementation, artifact integrity/version checks, confidence fallback concept, PII redaction, synthetic validation harness, stratified splitting, per-class metrics/confusion matrix, and exact-normalized duplicate partitioning.

Relevant paths: scripts/cfpb_cleaning.py; scripts/cfpb_label_mapping.py; scripts/train_department_baseline.py; scripts/evaluate_department_model.py; scripts/bilingual_inference.py; ml-api/app/model.py; evaluation/day18/*; data/processed/*.

V1 evidence reports 3,822,576 mapped records, 200,000 modeling records, 72.87% fraud_security, macro-F1 0.6923, transfer/payment recall 0.437, card/ATM precision 0.547, general support F1 0.563, 10.8% below-threshold predictions, and uncalibrated confidence.

Myanmar evidence reports 30 synthetic validation cases, 11/30 correct classification with the original translation pipeline, 14/30 usable translations at score 1 or 2, no approval for Myanmar production readiness, and 9/30 routing correctness for the non-adopted NLLB development candidate.

Evidence: evaluation/day18/model_evaluation_v1.json; docs/myanmar_pipeline.md; data/processed/myanmar_pipeline_v1_owner_review.json.

### Recommendations: what must change

- Use an eight-category target taxonomy.
- Replace CFPB proxy labels with banking-service labels.
- Add Myanmar and mixed-language examples.
- Define translation-quality acceptance.
- Calibrate or validate fallback thresholds.
- Report per-language and per-category metrics.
- Detect near-duplicates.
- Privacy-review every example.
- Version artifacts as dataset_v2, mapping_v2, and model_v2.

### Unknowns requiring confirmation: missing data

Missing or unverified data includes Myanmar banking complaints; English examples for mobile banking, POS, remittance, restrictions, and branch service; human labels; multiple Myanmar annotators; agreement statistics; transliterated/mixed-language examples; unsupported-language samples; priority/lifecycle labels; assignment workload data; and AYA-specific mappings.

### Proposed dataset schema

case_id; source_type real_public/translated/synthetic; source_reference; source_license; raw_text_available false; text_redacted; language; language_mix; unicode_normalization_version; category_id; secondary_category_id; priority; contains_sensitive_marker; sensitive_marker_type; annotator_ids_hash; annotation_round; label_confidence; adjudicated; split; duplicate_group_id; near_duplicate_group_id; created_at.

Retain only privacy-reviewed text or controlled secure artifacts outside the repository. Repository artifacts should be aggregate manifests and synthetic examples.

### Labeling process

1. Define category inclusion/exclusion rules.
2. Create bilingual guidance.
3. Label English and Myanmar independently.
4. Add a second annotator for disagreement.
5. Adjudicate.
6. Measure per-class agreement.
7. Retain an explicit Customer Complaint Unit/other class.
8. Freeze the test set before tuning.
9. Separate translated and synthetic evaluation from training.
10. Record source and license metadata.

### Safe dataset acquisition options

Use publicly licensed complaint datasets after license review, public AYA complaint-channel wording only as process reference, owner-authored synthetic Myanmar cases, human-authored reviewed translations, and public Myanmar banking terminology subject to licensing/privacy review.

Do not scrape or import customer-specific data. Public AYA material does not prove private department ownership.

### Evaluation and acceptance gates

Before automatic routing: confirm the eight-category macro-F1 target; define per-class precision/recall thresholds, especially fraud and fallback; report English/Myanmar/mixed metrics; test unsupported-language, low-confidence, translation-failure, and classifier-failure fallbacks; pass exact and near-duplicate leakage checks; complete calibration/threshold analysis; pass privacy review; freeze artifact hashes/metadata; and test automatic routing against a locked set.

### Unknowns requiring confirmation

The repository cannot verify whether categories match AYA internal departments, whether AYA uses the proposed lifecycle, AYA private SLA/staffing/capacity/escalation rules, Cloud Firestore behavior, active Staff availability, real Myanmar classifier performance, Cloud billing usage, or whether public AYA processes have changed.

## E. Phased migration plan

### Recommendations

#### Phase 0 — Contract freeze

Scope: approve taxonomy IDs, role removal, Customer Complaint Unit semantics, lifecycle/audit vocabulary, and public-reference boundary.

Likely files: PROJECT_PLAN.md; docs/*; README.md.

Tests: contract/schema compatibility.

Migration: none. Rollback: retain V1 contract as archived baseline. Completion: owner-approved contracts exist before implementation.

#### Phase 1 — Shared domain contracts

Scope: V2 IDs, roles, lifecycle enums, V1 compatibility aliases, and immutable Staff identity.

Likely files: ml-api/app/schemas.py; account_state.py; frontend/src/lib/department-labels.ts; frontend/src/lib/i18n.ts.

Tests: schema validation, V1 reads, unknown category handling, bilingual labels.

Migration: add version metadata; do not rewrite tickets. Rollback: V1 compatibility layer. Completion: all services read V1 and V2 versioned documents.

#### Phase 2 — Taxonomy and dataset preparation

Scope: freeze mappings, build English/Myanmar/mixed corpus, create manifests, evaluate ambiguity.

Likely files: data/mapping/*; scripts/*; docs/label_mapping.md; docs/myanmar_pipeline.md.

Tests: deterministic mapping, exact/near-duplicate leakage, per-class evaluation, privacy scans.

Migration: none to Firestore. Rollback: retain V1 model/mapping for historical interpretation. Completion: locked V2 dataset and metrics approved.

#### Phase 3 — Routing and fallback replacement

Scope: replace manual review with automatic department or Customer Complaint Unit fallback, preserve failure reasons and prediction evidence.

Likely files: ml-api/app/routing.py; ticketing.py; notifications.py; main.py.

Tests: reliable, low-confidence, Myanmar failure, classifier exception, durable-ticket, and no-loss tests.

Migration: map existing manual-review tickets to Customer Complaint Unit with original fields and a migration event.

Rollback: stop V2 routing without deleting evidence. Completion: every submitted ticket has a durable routing outcome.

#### Phase 4 — Staff assignment and department queues

Scope: workspaces, eligibility, availability, atomic assignment, busy queue fallback, individual attribution.

Likely files: new service under ml-api/app/; staff_workflow.py; ticketing.py; notifications.py; firebase/firestore.rules; firestore.indexes.json.

Tests: concurrent race, capacity, priority/age, least workload, round-robin, busy queue, disabled-history, cross-department denial.

Migration: backfill queue fields from departmentId; leave existing assignedStaffId null unless explicitly migrated.

Rollback: disable assignment while preserving queues/history. Completion: no duplicate active owners and every unassigned ticket visible.

#### Phase 5 — Manager removal

Scope: remove Manager from active authorization/UI, preserve historical actors, replace notifications/routes.

Likely files: manager_workflow.py; main.py; notifications.py; frontend/src/lib/manager-workflow.ts; Manager components/tests; firebase/firestore.rules.

Tests: Manager login denial, historical Manager audit rendering, no manual-review endpoints, no Manager notifications.

Migration: disable or explicitly disposition Manager profiles; retain Manager actions immutably.

Rollback: isolate archived V1 path until V2 acceptance. Completion: no active V2 path depends on Manager.

#### Phase 6 — Admin operations and analytics

Scope: department CRUD; Staff profiles; disablement; historical identity; ticket/action/audit inspection; filtered analytics/drill-down; privacy-safe CSV.

Likely files: ml-api/app/admin_*; main.py; new analytics/export modules; frontend Admin components/libs.

Tests: Admin-only access, allowlist, CSV injection, ranges/filters, audit immutability, no automatic HR decisions.

Migration: create aggregates from history using bounded checkpoints.

Rollback: disable analytics/export routes while retaining operational records. Completion: Admin can inspect/export approved evidence.

#### Phase 7 — Lifecycle and customer experience

Scope: V2 lifecycle, reopen/closure rules, customer-facing status text.

Likely files: schemas.py; customer_workflow.py; staff_workflow.py; customer UI; notification contracts.

Tests: transition matrix, invalid transitions, customer information response, reopen, notification consistency.

Migration: submitted -> Received or Queued; triaged -> Queued; in_progress -> Action in Progress; awaiting_customer -> Additional Information Required; resolved -> Resolved; closed -> Closed.

Rollback: preserve legacyStatus. Completion: every customer state has transition and notification policy.

#### Phase 8 — Emulator acceptance and deployment boundary review

Scope: complete local Emulator verification, no Cloud connection, Spark feasibility review without billing.

Tests: Auth, rules, routing, assignment, lifecycle, notifications, analytics, export, recovery.

Rollback: return to verified Emulator baseline. Completion: V2 local prototype is demonstrable and limitations documented.

## F. Cost and deployment boundary

### Verified repository facts

Current architecture is compatible with no billing because Auth, Firestore, FastAPI, and model execution are local and no Cloud runtime is connected.

Likely separate-environment or billing-dependent features: background assignment workers; scheduled aggregation; Cloud Functions; Cloud Run/hosted FastAPI; hosted translation; email/SMS; large CSV generation; BigQuery/streaming analytics; managed backups/PITR; and production hosting beyond approved no-cost limits.

Firebase documentation states Cloud Functions for Firebase requires Blaze, and linking billing automatically upgrades Spark to Blaze. References: https://firebase.google.com/docs/projects/billing/firebase-pricing-plans and https://firebase.google.com/docs/functions/quotas

Spark-compatible demonstration options: keep routing/assignment in local FastAPI; use explicit Admin operations rather than workers; use Firestore transactions; use bounded aggregates; use synthetic data; do not import CFPB data into Firestore; defer Cloud until owner approval for billing, hosting, credentials, and keyless identity.

A production-grade always-on automatic assignment service cannot be honestly claimed under the current Emulator-only boundary.

## G. Open decisions and blockers

### Unknowns requiring confirmation

1. Final V2 category IDs and localized names.
2. Whether Customer Complaint Unit is a department or special queue.
3. Whether all eight categories are routing departments or some are subcategories.
4. Whether historical V1 IDs remain readable indefinitely.
5. Disposition of Manager profiles after removal.
6. Admin visibility of historical Manager actions.
7. Staff employment states and login/availability semantics.
8. Active-login and heartbeat timeout.
9. Capacity definition and priority weighting.
10. Whether Staff may manually claim queued tickets.
11. Whether Admin may reassign tickets.
12. Whether Staff see all department tickets or assigned tickets only.
13. Customer reopen window and eligibility.
14. Closure requirements and customer confirmation.
15. SLA and escalation rules.
16. Fraud/scam priority policy.
17. Whether fraud may be automatically assigned.
18. Myanmar translation acceptance threshold.
19. Whether V2 must retain TF-IDF plus MultinomialNB.
20. Direct Myanmar classification versus approved translation.
21. Minimum per-class/per-language metrics.
22. Whether public complaint text may be retained and where.
23. Annotation ownership and reviewer availability.
24. Near-duplicate method and leakage threshold.
25. Complaint-text visibility for Staff/Admin/exports.
26. Audit retention period.
27. Notification retention and permanence of queue events.
28. Analytics frequency and staleness.
29. Custom date-range maximum.
30. CSV approval and redaction policy.
31. Whether Cloud staging is allowed during V2.
32. Whether billing, Blaze, hosted API, Cloud Functions, Cloud Run, or email service may be used.
33. Approved production execution environment.
34. Whether AYA process is only UX reference or also escalation wording.
35. Confirmation that no design claims AYA private departments, queues, staffing, or systems.

Primary blockers are the unapproved V2 taxonomy, absent Myanmar-labeled dataset, lack of an approved automatic-assignment execution environment, and unresolved Spark-versus-background-worker deployment boundary.
