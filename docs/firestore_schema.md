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
| `accountState` | string | future required | trusted backend only | `active`, `pending_setup`, `disabled`, or `inactive_unverified`; stable account state, never authorization by itself |
| `createdAt` | timestamp | yes | trusted backend | Immutable creation time |
| `updatedAt` | timestamp | yes | trusted backend | Last trusted update |

Role, department, active status, ownership, and timestamps are never ordinary client-writable fields. Authentication credentials remain in Firebase Authentication, not this document.

### R2C8D0 durable account state

R2C8D0 approves the `accountState` contract as documentation and future
implementation scope only. No field, writer, rule, index, migration, test, or
runtime behavior is changed by this checkpoint. The four allowlisted values are
`active`, `pending_setup`, `disabled`, and `inactive_unverified`.

`active` requires `active=true`. `pending_setup` requires `active=false` and a
Staff or Manager role with validated trusted provisioning lineage. `disabled`
and `inactive_unverified` require `active=false`; Customer and Admin profiles
can never be `pending_setup`. The existing `active` boolean remains the access
and authorization primitive, and `accountState` is never sufficient authority
for mutation.

Lifecycle recovery remains actor-bound and separate from this profile field. Its
public projection is `none`, `recoverable`, `completed`, or
`operator_required`. Disable/recovery action and target-guard state must not be
stored in `accountState`.

The implementation slice must update Customer registration, Emulator
seed/bootstrap writers, Admin provisioning, trusted owner activation, disable
profile transactions, reactivation final transactions, strict profile tests and
fixtures, directory parsing/projection, and lifecycle validators. Reassignment
does not change `active` or `accountState`.

Legacy profiles require a separately approved trusted backfill. Active profiles
may deterministically receive `accountState=active`. Inactive profiles require
validated provisioning or lifecycle lineage; ambiguous or malformed profiles
must become `inactive_unverified` or fail closed. The backfill is local-Emulator
only initially, dry-run and bounded, idempotent, report-only for private values,
and must not mutate Auth, complaints, or tickets. Cloud execution is deferred.

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

### R2C2B trusted Admin lifecycle coordination

The following top-level collections are backend-only and are accessed only by
deterministic document lookup inside trusted Firestore transactions. They are
not exposed to clients and require no query indexes:

- `adminAccountLifecycleActions/{actionRef}` stores the mutable lifecycle
  coordination action. `actionRef` is the existing lowercase SHA-256 R2C2A
  reference. Completed records are preserved and never deleted. Reactivation
  records may include the strictly validated `previousActionRef` binding to
  their completed disable lineage.
- `adminAccountLifecycleTargetGuards/{targetGuardRef}` stores one durable
  target serialization guard. `targetGuardRef` is a domain-separated,
  versioned lowercase SHA-256 binding the local project/environment boundary
  and trusted target UID. Guard documents are never deleted; their validated
  state is `active`, `inactive`, or `blocked`. `version` is a bounded,
  monotonically increasing guard-generation version, independent of the
  action state version.
- `adminAccountLifecycleAuditEvents/{eventRef}` stores immutable accepted
  transition events. `eventRef` is a domain-separated, versioned lowercase
  SHA-256 binding the action reference, operation, from/to states, result code,
  transition version, and audit domain/version. Events are create-once and are
  never updated or deleted.

Reservation reads the action and target guard before creating both documents,
so an action cannot commit without its guard. Accepted transitions read the
action, guard, and audit destination before writing the incremented action,
the guard, and exactly one audit event. Completion marks the owned guard
`inactive` atomically. A conflict releases only the guard owned by that action;
a reservation rejected by another action never touches that other guard. A
a failed action retains its owned guard as `blocked`; retryable nonterminal
states retain `active` ownership. An inactive guard may be reacquired by a new
action only through the same transaction's read/version precondition; its
`createdAt` remains immutable while ownership fields and `updatedAt` change.
Force unlock, operator recovery, profile mutation, and Auth mutation remain
outside this checkpoint.

### R2C4A trusted reactivation

The trusted backend pure-tests Customer, Staff, and Manager reactivation only
when the inactive target guard, target profile, completed disable action, and
completed-disable audit event form a consistent lineage. Reservation transfers
the inactive guard to a new reactivation action atomically. Auth enablement is
outside Firestore; `auth_enable_pending` and `profile_activation_pending`
preserve retryable recovery while the profile remains inactive. The final
transaction reads action, guard, profile, lineage, and final audit destination
before atomically activating the profile, completing the action, creating the
immutable audit event, and releasing the guard. Pending owner activation,
Admin-target mutation, frontend controls, and runtime/Emulator verification
remain unavailable.

### R2C5 Staff department reassignment

The trusted pure-tested route is
`POST /admin/users/{accountRef}/reassign-department` for active Staff only.
It updates only `users/{uid}.departmentId` and `updatedAt`; role, identity,
profile fields, tickets, and history are preserved. The transaction reads at
most 201 ticket documents from the top-level `tickets` collection to detect a
bounded scan overflow. Only `assignedStaffId == targetUid` with status
`submitted`, `triaged`, `in_progress`, or `awaiting_customer` blocks. Resolved,
unassigned, and other-Staff tickets do not block, and no ticket is modified.
Malformed ticket state or overflow fails closed. The current runtime has no
writer that changes `assignedStaffId` after ticket creation; any future
assignment feature must use this same coordination boundary to prevent races.
The route has no Auth operation, frontend control, notification, rules/index
change, or runtime/Emulator verification.

### R2C6 lifecycle recovery continuation

The trusted backend-only route
`POST /admin/users/{accountRef}/lifecycle-recovery` discovers the current
action exclusively through the deterministic target guard and continues that
same action. It never accepts or derives a new idempotency key, reserves a new
action, transfers ownership to another Admin, or unlocks a blocked guard.
Only the original verified Admin actor may continue it. Completed actions are
read-only safe replays; supported incomplete states reuse the existing disable,
reactivation, or reassignment orchestration. Failed or blocked actions require
a future operator workflow. No new collection, index, rule, or frontend access
is introduced.

### R2C8A lifecycle recovery-status projection

The trusted read-only `GET /admin/users/{accountRef}/lifecycle-recovery-status`
route discovers the current target guard and owner action through direct
deterministic lookups only. After strict active-Admin authorization, it returns
exactly `accountRef`, `recoveryState`, `operation`, and `departmentId`. Public
states are `none`, `recoverable`, `completed`, and `operator_required`; no UID,
lifecycle reference, fingerprint, timestamp, result code, or internal state is
exposed. The projection is separate from advisory eligibility and does not
authorize a mutation. Another Admin receives the safe `none` shape. Existing
strict action, guard, profile, audit, and reactivation-lineage validation
remains required; malformed persistence fails closed. The route performs no
writes or Auth operations and adds no collection, index, rule, or frontend
access.

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

## R2C10B0/R2C10B-B0 Customer History contract

R2C10B0 approved the future Customer History boundary. R2C10B-A is now
implemented and locally verified. R2C10B-B0 is this documentation-only
approval of the exact future status/department filter, cursor, and index
contract. B-B0 does not implement filters, new indexes, frontend controls,
rules, or runtime behavior.

The implemented local R2C10B-A state includes bounded `GET /customer/tickets`
pagination with `pageSize` default `25` and range `1`-`50`, the strict six-field
projection, `createdAt DESC` plus document-ID `DESC` ordering, and a
Customer-bound version-1 cursor. Customer ticket, detail, and participant
message reads use trusted API projections. Direct client reads and writes of
raw tickets, ticket messages, and ticket events are denied by the repository's
Firestore rules. The approved unfiltered ticket index exists in the local
manifest. Cloud deployment and Cloud runtime verification remain absent.

The implemented frontend preserves Load More, abort and stale-response
protection, exact-reference deduplication, Customer-session isolation, and
R2C10A confirmed-submission reconciliation.

The pre-R2C10B-A legacy list response was the envelope `{tickets: [...]}` with
rows containing `id`, `status`, `priority`, `departmentId`, `summaryText`,
`createdAt`, `updatedAt`, and `resolvedAt`, subject to the old permissive
parser/schema behavior. It is retained as historical context and is not the
implemented R2C10B-A projection.

The approved sequence is:

- **R2C10B-A:** API-only Customer ticket/detail/participant-message reads;
  bounded unfiltered history pagination; a strict minimal list projection;
  deterministic cursors; strict frontend parsing; abort and stale-response
  protection; exact-reference deduplication; and Customer-session isolation.
- **R2C10B-B:** status and department filters, reviewed composite indexes,
  filter-bound cursors, and frontend filter controls.
- **R2C10B-C (deferred):** bounded date-range filtering and any exact-reference
  list lookup, each subject to separate index and cost review.

Full-text search, total counts, charts, analytics, exports, bulk actions,
message pagination, Staff/Admin history controls, assignment changes, Myanmar
complaint classification, and Cloud deployment remain out of scope.

### R2C10B-A API contract (implemented locally)

The implemented route is `GET /customer/tickets`. R2C10B-A accepts only:

- `pageSize`: optional integer, default `25`, minimum `1`, maximum `50`;
- `cursor`: optional opaque cursor of at most `512` ASCII characters.

Status, department, date, search, reference, sort, and other query parameters
are not accepted in R2C10B-A. The implemented authorization order is: validate the
Bearer token; validate a strict active Customer profile and valid `accountState`;
validate `pageSize` and `cursor`; then execute the ownership-bound ticket
query. Authorization must finish before any ticket query or cursor-based
document access. In particular, the implementation must not decode,
fingerprint-compare, or otherwise inspect the cursor before authentication and
Customer-profile authorization. An unauthorized caller receives only the
applicable `401` or `403`, even when the supplied cursor is malformed.

The exact successful response envelope is:

```json
{
  "tickets": [
    {
      "complaintId": "ticket_<32 lowercase hexadecimal characters>",
      "status": "submitted",
      "departmentId": "transfer_payment",
      "createdAt": "2026-08-25T10:00:00Z",
      "updatedAt": "2026-08-25T10:00:00Z",
      "resolvedAt": null
    }
  ],
  "nextCursor": null,
  "hasMore": false
}
```

Envelope keys are exactly `tickets`, `nextCursor`, and `hasMore`. Row keys are
exactly `complaintId`, `status`, `departmentId`, `createdAt`, `updatedAt`, and
`resolvedAt`. `nextCursor` is a non-empty bounded cursor only when `hasMore` is
`true`; `hasMore: false` requires `nextCursor: null`. Empty results are
`tickets: []`, `nextCursor: null`, and `hasMore: false`. Total counts are not
returned.

The existing status values remain `submitted`, `triaged`, `in_progress`,
`awaiting_customer`, `resolved`, and `closed`. `departmentId` is one of the
six approved departments or `null` only where the existing ticket lifecycle
permits an unrouted submitted ticket. `createdAt` and `updatedAt` are
timezone-aware RFC3339 timestamps. `resolvedAt` is a timezone-aware RFC3339
timestamp for `resolved` and `closed` tickets and `null` for unresolved
tickets. Malformed or contradictory persisted rows fail closed with a generic
safe service error; they are neither exposed nor silently skipped.

The list projection removes `summaryText`, `priority` unless a separately
reviewed Customer requirement proves it necessary, full complaint text,
Customer/Staff UIDs, `assignedStaffId`, message/action/event/notification/audit
identifiers, ML confidence or probabilities, routing/model metadata, internal
notes, and workflow fields. Full complaint text remains available only through
the separately authorized owned-detail API.

### R2C10B-A ordering, bounds, and cursor (implemented locally)

The implemented query is ownership-bound by `customerId == authenticated Customer
UID` and ordered newest-first by `createdAt DESC`, with Firestore document ID
`DESC` as the deterministic tie-breaker. It reads at most `pageSize + 1`
documents, returns at most `pageSize` public rows, and uses the extra row only
to determine `hasMore`. Unbounded streams and frontend filtering over an
unbounded collection are not approved.

The cursor is unsigned and unencrypted, consistent with existing local cursor
patterns. It is URL-safe Base64 without padding around strict canonical compact
UTF-8 JSON with exactly these keys, serialized in this order: `v`,
`customerBinding`, `contract`, `createdAt`, and `complaintId`. `v` is exactly
the integer `1`. `customerBinding` and `contract` are exactly 64 lowercase
SHA-256 hexadecimal characters. `createdAt` is the boundary timestamp and
`complaintId` is the boundary reference.

Canonical JSON uses UTF-8, no whitespace, JSON strings without alternate
escaping, finite JSON numbers in their shortest ordinary decimal form, and
recursively lexicographically sorted object keys for fingerprint inputs. The
cursor payload itself uses the explicit field order above. The Base64 encoder
must use the URL-safe alphabet, omit `=` padding, and reject any input with
padding or another alphabet. Decoding must decode once, validate the exact
payload types and values, re-encode canonically, and require the re-encoded
value to equal the supplied cursor byte-for-byte.

The Customer binding input is the canonical compact JSON object
`{"domain":"complaintguard:customer-history-cursor:v1","project":<trusted
project/environment boundary>,"uid":<verified authenticated Customer UID>}`.
The `project` value is supplied only by trusted server configuration; the local
boundary is `local-emulator:demo-complaintguard`, while any future Cloud value
requires separate approved deployment configuration. The UID is used only as
an input to the SHA-256 calculation and is never placed in the cursor.

The contract fingerprint input is the canonical compact JSON object
`{"domain":"complaintguard:customer-history-query:v1","pageSize":{"default":25,"min":1,"max":50},"projection":["complaintId","status","departmentId","createdAt","updatedAt","resolvedAt"],"query":{"filters":[],"order":[["createdAt","DESC"],["__name__","DESC"]]}}`.
The empty `filters` array is the explicit R2C10B-A contract boundary; later
filter slices must use a different contract version/fingerprint.

The cursor contains no raw UID, email, complaint text, token, page contents, or
private/internal data. It has a strict maximum length of `512`, exact fields
and types, a timezone-aware RFC3339 boundary timestamp, and a valid
complaint/document reference. It is bound to the authenticated Customer and
exact R2C10B-A sort/filter contract, but is never authorization. Malformed,
non-canonical, tampered, cross-Customer, wrong-version, wrong-filter, or
otherwise incompatible cursors fail safely before query execution without
revealing whether another Customer or ticket exists.

Pagination is boundary-based over a moving dataset. New tickets inserted
between requests may not appear until refresh, but traversal must never cross
ownership or filter boundaries. The frontend must deduplicate by exact
complaint reference across pages.

### R2C10B-A errors and read boundary (implemented locally)

Implemented safe mappings are `401` for missing or invalid authentication, `403` for
an authenticated user who is not a strict active Customer, `422` for malformed
`pageSize`, malformed/incompatible `cursor`, or unsupported/extra query
parameters, and `503` for malformed/inconsistent persisted tickets, bounded
query failure, or backend persistence unavailability. Raw Firestore,
cursor-decoding, UID, query, and validation details are never returned.

R2C10B-A approves an API-only Customer read boundary. Customer frontend code
must obtain ticket history, ticket detail, and participant-visible messages
through trusted API projections. The repository Firestore rules deny direct
client reads of raw tickets, ticket messages, and ticket events while leaving
direct client writes denied. Customer profile access, unrelated
approved collections, and the separately approved notification contract must
not change accidentally. Backend Firebase Admin access remains outside client
rules. No frontend direct-Firestore fallback is permitted.

Rules and API behavior remain separate boundaries. B-B0 does not modify rules;
future implementation and local Emulator verification remain required before
any later adoption claim.

### R2C10B-A frontend contract

The implemented frontend client uses a strict plain-object parser that rejects
arrays, class instances, inherited, accessor, non-enumerable, symbol, extra,
private, and malformed fields. It validates complaint references, statuses,
departments, timestamps, cursors, and `hasMore` relationships exactly.

History requests pass an `AbortSignal` and bind request generations to the
Customer UID/session, cursor, and page contract. Late responses are rejected
after filter changes, sign-out, Customer changes, selection changes, or
unmount. Rows are deduplicated by exact complaint reference. Initial load and
Load More have separate loading states; a Load More failure preserves validated
rows; a refresh replaces pages only after a valid response; sign-out or
Customer change aborts and clears history state.

R2C10A confirmed-submission refresh and exact selection remain preserved. If a
confirmed new complaint is absent from a refreshed page, confirmed success is
not replayed or converted into failure. R2C10B-A UI includes accessible
Load More, initial-loading, partial-page-loading, empty, safe-error, and retry
states in desktop/mobile layouts with English and Myanmar text. Status and
department controls belong to R2C10B-B, not R2C10B-A.

### R2C10B-B0 approved future filter contract

B-B0 approves documentation only. It does not claim that status or department
filters, filter indexes, or filter controls are implemented.

The future route remains `GET /customer/tickets` and accepts only these optional
parameters after B-B implementation: `pageSize`, `cursor`, `status`, and
`departmentId`. `pageSize` is an ASCII decimal integer, defaults to `25`, is
bounded to `1`-`50`, and occurs at most once. `cursor` is a version-2 opaque
cursor of at most `512` ASCII characters and occurs at most once.

`status` occurs at most once and accepts exactly `submitted`, `triaged`,
`in_progress`, `awaiting_customer`, `resolved`, or `closed`. Omission means all
statuses. `departmentId` occurs at most once and accepts exactly
`transfer_payment`, `account_support`, `card_atm`, `fraud_security`,
`loan_credit`, or `general_support`. Omission means all departments. Supplying
both filters is logical AND. The UI's All option is represented by omission.

Empty values, repeated values even when identical, extra parameters, whitespace,
trimming-based acceptance, case folding, aliases, numeric or Boolean coercion,
and comma-separated values are forbidden and return `422`. Filters are
server-side and ownership-bound; no Customer UID or ownership field is
client-supplied.

Authorization order is: Bearer authentication; token validation; Customer
profile loading and validation; `role == customer`; `active == true` and
`accountState == active`; page-size/filter/cursor validation; then the
ownership-bound Firestore query. Unauthorized callers receive no filter or
cursor details and cause no ticket query execution.

### R2C10B-B0 version-2 cursor contract

B-B cursors use version exactly `2`. Existing A version-1 cursors are rejected
with safe `422` after authorization; they are not upgraded or interpreted under
B-B. All B-B pages, including unfiltered pages, use the version-2 cursor
contract. Whenever `hasMore` is true, `nextCursor` is a version-2 cursor; final
pages use `nextCursor: null`. The cursor remains unsigned, unencrypted, opaque,
URL-safe Base64 without padding, and at most `512` ASCII characters. Strict
decode/re-encode byte equality is required.

The decoded cursor wire-object keys remain exactly and in this order: `v`,
`customerBinding`, `contract`, `createdAt`, and `complaintId`. Values are
respectively integer `2`, 64 lowercase SHA-256 hexadecimal characters, 64
lowercase SHA-256 hexadecimal characters, a canonical timezone-aware UTC RFC3339
timestamp ending in `Z`, and `ticket_[a-f0-9]{32}`. This fixed wire-object key
order is distinct from the recursively sorted object keys used when hashing
binding and query-contract inputs; the cursor payload itself is serialized in
the explicit wire order and is then Base64-encoded.

The version-2 Customer-binding input is the canonical compact JSON object:

```json
{"domain":"complaintguard:customer-history-cursor:v2","environment":"local-emulator","project":"demo-complaintguard","uid":"<verified authenticated Customer UID>"}
```

The trusted local environment is `local-emulator` and the trusted local project
ID is `demo-complaintguard`. A future Cloud environment/project pair requires
separate approved deployment configuration. Only the trusted domain/version,
environment, project ID, and verified Customer UID are inputs. The binding
contains no email, complaint content, token, cursor, filter, page data, or other
Customer data. The UID is only a SHA-256 input and never appears in the cursor;
the binding is never authorization.

The version-2 query contract input is:

```json
{
  "domain": "complaintguard:customer-history-query:v2",
  "pageSize": {
    "default": 25,
    "min": 1,
    "max": 50
  },
  "projection": [
    "complaintId",
    "status",
    "departmentId",
    "createdAt",
    "updatedAt",
    "resolvedAt"
  ],
  "query": {
    "filters": {
      "status": null,
      "departmentId": null
    },
    "order": [
      ["createdAt", "DESC"],
      ["__name__", "DESC"]
    ]
  }
}
```

Contract inputs use compact UTF-8 JSON, recursively sorted object keys, preserved
array order, no whitespace, and no trailing newline. Filter values are the
exact selected allowlisted string or JSON `null`. Requested page size is not
fingerprinted; the approved bounds contract is. Four filter shapes are required:
unfiltered, status only, department only, and status plus department. Each
selected status or department value produces its own exact fingerprint. A cursor
cannot cross any exact filter combination or value.

The cursor boundary remains the exact last returned `createdAt` and
`complaintId`. Cross-Customer, cross-filter, wrong-version, wrong-contract,
malformed, tampered, non-canonical, padded, or alternate-encoded cursors fail
safely with `422` before Firestore query execution. No error reveals a UID,
fingerprint, Customer existence, ticket existence, or decoded payload.

Pagination remains boundary-based for every filter shape: ownership equality and
the optional equality filters are applied first, followed by `createdAt DESC`
and `__name__ DESC`. The backend reads at most `pageSize + 1`, returns at most
`pageSize`, and derives `nextCursor` from the last returned row, never the
lookahead row. The lookahead row is the first candidate for the next page. A
final page has `hasMore: false` and `nextCursor: null`; equal timestamps remain
stable through the document-ID tie-breaker without duplicates or omissions.

### R2C10B-B0 minimal index approval

The implemented local unfiltered index remains:

```text
customerId ASC
createdAt DESC
__name__ DESC
```

B-B approves exactly these three future ticket indexes:

```text
customerId ASC
status ASC
createdAt DESC
__name__ DESC
```

```text
customerId ASC
departmentId ASC
createdAt DESC
__name__ DESC
```

```text
customerId ASC
status ASC
departmentId ASC
createdAt DESC
__name__ DESC
```

No other ticket index is approved. Date-range, exact-reference list, text-search,
alternative-ordering, speculative/combinatorial, and total-count indexes are
explicitly outside B-B. Manifest implementation/testing, local Emulator
verification, and any Cloud deployment require later approval; Cloud staging
remains not adopted.

For every query, `customerId == authenticated UID` is present. Supplied status
and department values add equality predicates, both together are ANDed, and
`createdAt DESC` plus `__name__ DESC` remain unchanged. The cursor boundary is
applied after those equality filters and both order fields. The read limit is
`pageSize + 1`; production must not post-filter or perform unbounded reads.
The six-field projection, fail-closed malformed-record behavior, no-count rule,
and `401`/`403`/`422`/`503` mappings remain unchanged.

### R2C10B-B0 frontend approval

Future B-B UI may add only visible Status and Department selects, UI-only All
options represented by omitted parameters, a Clear Filters button, a safe
visible filter summary, bilingual labels/help text, and the existing
loading/empty/error/retry/Load More behavior. It must add an explicit Closed
status label in English and Myanmar. Current A history falls back incorrectly
for Closed; B-B0 does not modify frontend code.

Filter changes must abort list and Load More requests, increment the request
generation, clear pages/cursor, reset `hasMore`, request a first page, and bind
responses to Customer UID, exact filter state, cursor, and generation. Stale
cross-filter responses are rejected and exact `complaintId` deduplication is
preserved. Detail requests are aborted on filter/session/selection changes;
selection is preserved only when the exact ticket remains in the validated
filtered result, otherwise the first result or no result is selected. A ticket
excluded by the active filter must never remain visible in detail.

R2C10A confirmed-submission success remains confirmed without replaying the
submission POST or converting filter-based absence into failure. The exact
reconciliation marker may remain while a filter excludes the new complaint and
may reconcile on a later matching refresh. No unrelated ticket is selected as
the submitted complaint.

Date ranges and exact-reference lookup remain R2C10B-C deferrals requiring
separate query, index, and cost review. Full-text search, counts, charts,
exports, bulk actions, saved or persisted filters, and Staff/Admin controls are
not part of B-B.

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
- **Implemented through pure/fake tests:** trusted `POST
  /admin/users/{accountRef}/disable` orchestration for Customer, Staff, and
  Manager targets, including recoverable profile/Auth phases. Admin-target
  disablement remains deferred to R2C3B; no frontend control or Emulator/runtime
  verification is claimed.
- **Implemented through pure/fake tests:** trusted `POST
  /admin/users/{accountRef}/reactivate` orchestration for Customer, Staff, and
  Manager targets proven disabled by the lifecycle workflow. Pending owner
  activation and Admin-target reactivation remain unavailable; no frontend
  control or Emulator/runtime verification is claimed.
- **Designed but not implemented:** manager reopen, manager close, broad
  priority management, broad assignment management, full escalation
  administration, Admin-target lifecycle operations, reactivate, reassignment,
  and deletion.
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

## R2C0 future lifecycle records (not implemented)

R2C0 does not add or migrate any Firestore collection. A later implementation
may use trusted-only lifecycle action records and an opaque account-reference
lookup. These records must remain inaccessible to direct clients under the
deny-by-default rules and must not be added to browser projections.

The future action record may contain only an action domain/version, opaque
action reference, trusted actor/target references, operation type, request and
idempotency fingerprints, safe role/department metadata where required,
lifecycle state, safe result code, and server timestamps. It must not contain
passwords, tokens, claims, credentials, arbitrary reasons, Auth provider
records, complaint/message/event data, or raw browser requests.

The future profile mutation must use expected-state/version checks and trusted
transactions for Firestore phases. Firebase Auth disable/enable and refresh
token revocation are outside a Firestore transaction and therefore require the
documented `auth_disable_pending`, `auth_enable_pending`, and
`profile_activation_pending` recovery states. No lifecycle field, index, rule,
or worker is implemented by R2C0. Permanent deletion and cleanup remain
deferred pending retention, anonymization, ownership, cascade, audit, and
recovery policy approval.
