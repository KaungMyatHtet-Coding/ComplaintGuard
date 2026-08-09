# Firestore Operational Schema

## Status and boundaries

This schema was designed on Day 4 and subsequently implemented for the local
demo workflows. Auth/Firestore Emulator tests now cover ownership, exact staff
department scope, manager reads, trusted workflow adapters, and denied direct
client writes. This is emulator evidence, not production rules-deployment
verification or an independent security audit.

Firestore is the source of truth for live application tickets and their workflow. It must never contain the historical CFPB dataset, historical narratives, training or evaluation data, model-normalized text, translated text, prompts, feature data, or model artifacts. Dashboard summaries, if later needed, are derived operational data and are never authoritative.

The application may retain only the minimum PII-redacted complaint text submitted directly to ComplaintGuard, preserved in the original submitted language. A trusted backend must redact PII before persistence. Production deployment requires an approved configurable retention and deletion policy; Day 4 intentionally does not invent a retention duration.

## Stable identifiers

Valid roles are `customer`, `staff`, `manager`, and `admin`. Valid department IDs are:

- `transfer_payment`
- `account_support`
- `card_atm`
- `fraud_security`
- `loan_credit`
- `general_support`

Day 7 finalized deterministic CFPB Product/Issue mapping version `v1`. No label is derived from a complaint narrative. The historical labeled dataset remains local and must never enter Firestore.

## Collections

### `users/{userId}`

Operational profile keyed by the Firebase Authentication UID.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `displayName` | string | yes | user-controlled through trusted backend; no direct client write | Synthetic/demo display name |
| `preferredLocale` | string | yes | user-controlled through trusted backend; no direct client write | `en` or `my` |
| `role` | string | yes | admin/trusted backend only | One of the four role IDs |
| `departmentId` | string or null | yes | admin/trusted backend only | Required for staff; null for customer |
| `active` | boolean | yes | admin/trusted backend only | Access status |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last trusted update |

Role, department, active status, ownership, and timestamps are never ordinary client-writable fields. Authentication credentials remain in Firebase Authentication, not this document.

### `departments/{departmentId}`

Canonical operational department metadata. Document IDs must use the six stable IDs.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `nameKey` | string | yes | admin/trusted backend only | Translation key for display name |
| `active` | boolean | yes | admin/trusted backend only | Whether assignment is permitted |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last trusted update |

Authenticated users may read department metadata. An admin may request changes only through an audited trusted backend; direct client writes are denied.

### `tickets/{ticketId}`

Authoritative operational ticket. Auto-generated IDs are preferred.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `customerId` | string | yes | immutable after trusted creation | Owner UID |
| `complaintText` | string | yes | trusted backend after PII redaction | Minimum PII-redacted user-submitted text preserved in the original submitted language |
| `inputLocale` | string | yes | immutable after creation | `en` or `my` |
| `departmentId` | string or null | yes | trusted routing backend; manager may request routing action | `null` only while submitted and pending classification; otherwise one of the six stable department IDs |
| `assignedStaffId` | string or null | yes | trusted backend; manager may request assignment | Assigned active staff UID |
| `status` | string | yes | transition-controlled | Lifecycle state |
| `priority` | string | yes | manager/trusted backend | `normal`, `high`, or `urgent` |
| `predictedDepartmentId` | string or null | yes | trusted inference backend only | Original model prediction |
| `predictionConfidence` | number or null | yes | trusted inference backend only | Value from 0 through 1 |
| `routingSource` | string | yes | trusted backend only | `pending`, `model`, `manual_review`, or `manager_override`; `pending` is a routing state, not a department |
| `escalated` | boolean | yes | manager/trusted backend | Escalation marker |
| `resolutionSummary` | string or null | yes | permitted resolver through trusted workflow | Operational resolution note; no sensitive data |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last workflow update |
| `resolvedAt` | timestamp or null | yes | trusted backend | Set on resolution, cleared on reopen |

Clients must not directly create tickets because server-side PII redaction, prediction, ownership binding, and immutable-field enforcement require trusted backend code. Customers submit through that backend. Customers cannot alter ownership, routing, assignment, priority, prediction, escalation, lifecycle, resolution, or audit fields.

A newly submitted ticket has `departmentId: null`, `status: submitted`, and
`routingSource: pending` until trusted classification/routing code completes.
Only that trusted code may replace `null` with one of the six stable department
IDs. A ticket must have a valid non-null department before it leaves the
pending submitted state. No synthetic department such as `unassigned` or
`pending` is valid.

### `tickets/{ticketId}/messages/{messageId}`

Ticket-scoped conversation. This prevents global message queries and makes the parent ticket the authorization boundary.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `authorId` | string | yes | immutable/auth-bound | Sender UID |
| `authorRole` | string | yes | trusted backend | Role snapshot for display/audit |
| `body` | string | yes | trusted backend after redaction | Minimum operational message text |
| `visibility` | string | yes | trusted backend | Day 4 supports `participants` only |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |

Customers may read messages only under their own ticket. Assigned-department staff and managers may read permitted tickets. Ordinary clients cannot update or delete messages. Message creation should pass through a trusted backend for PII redaction and author binding; the initial rules therefore deny client writes.

### `tickets/{ticketId}/events/{eventId}`

Immutable audit event scoped to a ticket.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `type` | string | yes | trusted backend | Lifecycle, routing, assignment, or escalation event |
| `actorId` | string | yes | trusted backend | Authenticated actor or service identity |
| `actorRole` | string | yes | trusted backend | Actor role snapshot |
| `fromValue` | string or null | yes | trusted backend | Previous controlled value |
| `toValue` | string or null | yes | trusted backend | New controlled value |
| `createdAt` | timestamp | yes | trusted backend | Immutable event time |

Customers may read participant-safe events for their own ticket only if the later backend guarantees every stored event is safe for customer visibility. Until that contract exists, initial rules expose events only to staff in the assigned department and managers. Admin access, if administratively necessary, must use an audited trusted-backend path. Ordinary clients can never create, update, or delete audit events.

### Optional `dashboardSummaries/{summaryId}`

This future collection may cache aggregate counts derived exclusively from operational tickets. It is not required on Day 4, is not a source of truth, must contain no complaint text or historical CFPB aggregates, and is writable only by trusted backend code. Managers and admins may read it; all other access is denied.

## Relationships and query boundaries

- A user is identified by Firebase Authentication UID.
- A staff user's `departmentId` references `departments/{departmentId}`.
- A ticket's `customerId` references its owner and `departmentId` references its current queue.
- `assignedStaffId`, when set, references an active staff user in the same department; rules cannot safely validate all cross-document invariants in every multi-step workflow, so trusted backend transactions must enforce this.
- Messages and events inherit access from their parent ticket.
- Required indexes will be defined when real queries are implemented, not guessed on Day 4.

## Lifecycle

States are `submitted`, `triaged`, `in_progress`, `awaiting_customer`, `resolved`, and `closed`.

Allowed transitions:

| From | To | Authorized actor |
|---|---|---|
| new document | `submitted` | trusted submission backend |
| `submitted` | `triaged` | trusted routing backend, manager; requires a valid non-null department |
| `triaged` | `in_progress` | assigned-department staff, manager |
| `in_progress` | `awaiting_customer` | assigned staff, manager |
| `awaiting_customer` | `in_progress` | customer reply through trusted backend, assigned staff, manager |
| `in_progress` | `resolved` | assigned staff, manager |
| `resolved` | `in_progress` | manager only (reopen) |
| `resolved` | `closed` | manager or trusted expiry workflow |

No other transitions are allowed. Customers cannot directly change status. Admin is not a routine workflow operator; emergency administrative correction must use an audited trusted-backend path rather than broad direct writes.

## Controlled actions

- Assignment/reassignment: manager through a trusted backend; staff may claim only if a later transactional backend safely proves same-department eligibility.
- Department rerouting: manager through a trusted backend; model output may set initial routing through the inference backend.
- Priority and escalation: manager through a trusted backend.
- Resolve: assigned-department staff or manager through a trusted backend; a resolution event is required.
- Reopen: manager through a trusted backend.
- Prediction fields: inference backend only and immutable to ordinary clients. A manager override changes routing fields but does not rewrite the original prediction.
- Role/department administration: admin through a trusted backend, with minimal scope and audit records.

## Privacy and retention controls

- Warn users not to submit passwords, PINs, full account/card numbers, or other sensitive information.
- Enforce length and content validation before persistence.
- Perform server-side PII redaction before storing ticket or message text.
- Never persist translations, normalized text, prompts, training text, or historical narratives.
- Define a configurable retention period and deletion workflow before production deployment.
- Cascade deletion of ticket subcollections through trusted backend tooling; deleting a Firestore parent does not automatically delete its subcollections.

## Initial rules limitations

- Firestore rules are not filters. Customer ticket queries must include `customerId == request.auth.uid`, and staff queries must include the staff profile's `departmentId`; otherwise Firestore rejects the query rather than returning a filtered subset.
- Rules document reads used for authorization consume quota and require the referenced profile to exist. Query and index design must be measured when implementation begins.
- The Admin SDK bypasses Firestore rules. Every trusted-backend endpoint must repeat authentication, role, ownership, department, transition, validation, redaction, and audit checks.
- Cross-document assignment validity, redaction, retention deletion, immutable audit creation, and atomic lifecycle/event writes require trusted backend transactions or jobs.
- `firebase/firestore.rules` is deny-by-default and is compiled/exercised by the
  local emulator harness. It is not verified as deployed to production.
- Redaction reduces obvious sensitive patterns but does not guarantee
  anonymization; stored operational complaint text remains sensitive.
- No approved retention/deletion workflow, rate limiting, production monitoring,
  disaster recovery, penetration test, or independent audit exists.
