# Firestore Operational Schema

## Status and boundaries

This schema was designed on Day 4 and subsequently implemented for the local
demo workflows. Auth/Firestore Emulator tests now cover ownership, exact staff
department scope, manager reads, trusted workflow adapters, and denied direct
client writes. This is emulator evidence, not production rules-deployment
verification or an independent security audit.

Lifecycle and action descriptions below distinguish implemented local behavior
from the original design. Future schema or rules changes require separate
review and approval in Phases 2–4.

R0.1 adds approved future contract boundaries without changing the current
schema or rules. No notification, History projection, assignment, SLA, or
lifecycle collection is implemented by this checkpoint.

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
| `locale` | string | yes | user-controlled through trusted backend; no direct client write | `en` or `my`; consumed by the current profile loader |
| `role` | string | yes | admin/trusted backend only | One of the four role IDs |
| `departmentId` | string or null | yes | admin/trusted backend only | Required for staff; null for non-staff roles |
| `active` | boolean | yes | admin/trusted backend only | Access status |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last trusted update |

Role, department, active status, ownership, and timestamps are never ordinary client-writable fields. Authentication credentials remain in Firebase Authentication, not this document.

Public registration is Customer-only. Firebase Auth creates the identity and the
trusted backend completes `users/{uid}` with `role: customer`,
`departmentId: null`, and `active: true`; public input cannot select a role,
department, active state, UID, timestamps, or claims. A definitely missing
profile is represented in the frontend as recoverable `profile_incomplete`.
Privileged, inactive, and malformed profiles are not publicly repairable, and
direct client profile writes remain denied.

Pending Staff and Manager profiles are created only by the trusted
`POST /admin/users` workflow after active Admin authorization. They begin with
`active: false`; Staff requires exactly one of the six approved departments and
Manager requires `departmentId: null`. Their Auth identities begin disabled,
passwordless, and without custom claims. The local owner-only activation helper
sets credentials while disabled, enables Auth, and then changes only `active` and
`updatedAt`. The bootstrap and activation scripts are committed but unexecuted.

### `adminProvisioningActions/{actionId}`

This trusted backend-only collection records safe provisioning lifecycle
metadata. Existing catch-all Firestore rules deny direct client access. The
document ID is lowercase SHA-256 of canonical UTF-8 JSON containing the fixed
domain/version, verified actor UID, and normalized idempotency key; raw UIDs and
keys are never used as document IDs. Records contain only verified actor and
known target UIDs, action/key and request fingerprints, operation/lifecycle
status, safe result codes, and server timestamps. Passwords, tokens, claims,
headers, and full credential-bearing requests are never stored. Same actor/key/
request retries are idempotent; a changed request conflicts, while different
Admin actors remain isolated. Partial failures preserve disabled Auth and
inactive profiles for safe recovery.

### `departments/{departmentId}`

Canonical operational department metadata. Document IDs must use the six stable IDs.

| Field | Type | Required | Authority | Meaning |
|---|---|---:|---|---|
| `nameKey` | string | yes | admin/trusted backend only | Translation key for display name |
| `active` | boolean | yes | admin/trusted backend only | Whether assignment is permitted |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last trusted update |

Authenticated users may read department metadata. An admin may request changes only through an audited trusted backend; direct client writes are denied.

The six IDs above are the backend authority until a separately approved
department-metadata collection is formally implemented. Frontend localized
labels are presentation only. Staff must select exactly one valid department;
Manager, Admin, and Customer profiles require `departmentId: null`.

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

### Approved future `notifications/{notificationId}`

R0.1 approves a future top-level notification collection. It is not implemented
and no index is deployed or added by this checkpoint.

Trusted persistence may contain `recipientUid` and deduplication material, but
these fields must never be returned to the browser. The safe browser projection
may contain only an opaque notification reference, stable type, severity,
category, optional safe public ticket reference, localization keys,
allowlisted parameters and navigation target, `createdAt`, `readAt`, derived
unread state, and policy version where required.

Notifications are trusted-backend-created, recipient-bound, idempotent, and
free of complaint narratives, credentials, tokens, actor IDs, raw event IDs,
model rationale, and arbitrary free-form text. Application notifications have
an approved initial retention period of 90 days; this does not shorten
audit-event retention. Cleanup automation remains deferred until a trusted
worker exists.

Likely future query indexes are recipient plus created time and recipient plus
read state plus created time. They remain a proposal until the real API query
contract is implemented and locally measured.

## Relationships and query boundaries

- A user is identified by Firebase Authentication UID.
- A staff user's `departmentId` references `departments/{departmentId}`.
- A ticket's `customerId` references its owner and `departmentId` references its current queue.
- `assignedStaffId`, when set, references an active staff user in the same department; rules cannot safely validate all cross-document invariants in every multi-step workflow, so trusted backend transactions must enforce this.
- Messages and events inherit access from their parent ticket.
- Required indexes will be defined when real queries are implemented, not guessed on Day 4.

R0.1 approves future deterministic Customer cursor pagination, status,
department, date-range, and safe public ticket-reference filters. Raw full-text
complaint search is not approved. The future Customer response must be a
server-side projection that excludes customer IDs, model fields, message or
sender IDs, raw event/action names and IDs, actor IDs, model rationale, and
internal reassignment/escalation reasons.

## Lifecycle

States are `submitted`, `triaged`, `in_progress`, `awaiting_customer`, `resolved`, and `closed`.

Allowed transitions:

| From | To | Authorized actor |
|---|---|---|
| new document | `submitted` | trusted submission backend |
| `submitted` | `triaged` | trusted routing backend, manager; requires a valid non-null department |
| `triaged` | `in_progress` | assigned-department staff, manager |
| `in_progress` | `awaiting_customer` | assigned staff, manager |
| `awaiting_customer` | `in_progress` | assigned staff or manager through trusted backend; a customer reply creates a participant message but does not itself perform this full status transition |
| `in_progress` | `resolved` | assigned staff, manager |
| `resolved` | `in_progress` | manager only (reopen) |
| `resolved` | `closed` | manager or trusted expiry workflow |

No other transitions are allowed. Customers cannot directly change status. Admin is not a routine workflow operator; emergency administrative correction must use an audited trusted-backend path rather than broad direct writes.

### Current implementation status

- **Implemented and locally verified:** initial ticket submission; model
  auto-routing for qualifying English complaints; low-confidence English manual
  review; Myanmar/mixed manual review; staff department visibility; staff and
  customer participant messaging; currently implemented staff transitions;
  resolution; feedback; and manager routing override with original prediction
  evidence preserved.
- **Implemented through a limited trusted route:** staff workflow resumption
  after a customer reply, which is performed by the staff transition endpoint.
  The customer reply itself only creates the participant message.
- **Designed but not implemented:** manager reopen, manager close, broad
  priority management, broad assignment management, full escalation
  administration, and Admin-controlled lifecycle operations.
- **Planned for Cloud staging:** trusted provisioning, Cloud rules/indexes,
  deployment configuration, and corresponding security evidence.

## Controlled actions

- Assignment/reassignment: designed for manager use through a trusted backend;
  broad assignment management is not currently implemented. Staff may claim
  only if a later transactional backend safely proves same-department eligibility.
  R0.1 approves an atomic same-department Staff claim and Manager
  assignment/reassignment, with explicit confirmation, idempotency, safe audit
  events, and no automatic Staff assignment. Disable or department-change must
  initially fail when active assignments exist.
- Department rerouting: manager through a trusted backend; model output may set initial routing through the inference backend.
- Priority and escalation: designed for manager use through a trusted backend;
  broad management is not currently implemented.
- Resolve: assigned-department staff or manager through a trusted backend; a resolution event is required.
- Reopen: designed for manager use through a trusted backend; not currently
  implemented.
- Manager override reason: the frontend requires a non-empty reason, while the
  backend schema currently permits an optional reason. This contract must be
  reconciled before Cloud staging acceptance.
- Prediction fields: inference backend only and immutable to ordinary clients. A manager override changes routing fields but does not rewrite the original prediction.
- Role/department administration: designed for Admin use through a trusted
  backend, with minimal scope and audit records; not currently implemented.

R0.1 approves future response-target presentation using urgent/high/normal
operational goals, Asia/Yangon Monday-Friday 09:00–17:00 business hours, no
initial public-holiday exclusion, and unavailable results for invalid legacy
timestamps. Model confidence is never an SLA estimate. Read-time calculation
may precede proactive alerts; proactive alerts require a future trusted
scheduled worker.

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
