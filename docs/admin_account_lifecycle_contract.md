# Admin Account Lifecycle Contract - Approved R2C0 Boundary

## Purpose and status

This document records the approved future contract for trusted Admin account
lifecycle operations. R2C0 is documentation and contract approval only. It
does not implement routes, schemas, Firestore rules or indexes, action records,
Auth operations, UI controls, migrations, tests, or runtime behavior.

The current local application exposes the approved safe all-role directory
projection and the R2B read-only account-detail drawer. R2C3A adds only the
trusted Customer, Staff, and Manager lifecycle routes described below; no
browser control or Emulator/runtime verification is claimed. Deletion and
Admin-target lifecycle mutation remain unavailable.

R2C3A now implements the trusted pure/fake-tested backend
`POST /admin/users/{accountRef}/disable` workflow for Customer, Staff, and
Manager targets. It has no frontend control and has not been verified against
the Emulator or a runtime environment. Admin-target disablement remains
unavailable and is deferred to R2C3B because it requires the separate global
last-active-Admin concurrency guard.

R2C4A now implements the trusted pure/fake-tested backend
`POST /admin/users/{accountRef}/reactivate` workflow for Customer, Staff, and
Manager targets. Reactivation requires durable proof of the same target's
completed trusted disable action; inactive `pending_setup` profiles and
unproven inactive profiles cannot be activated. Admin lifecycle mutation,
frontend controls, and runtime verification remain unavailable.

R2C5 now implements the trusted pure/fake-tested backend
`POST /admin/users/{accountRef}/reassign-department` workflow for active Staff
targets. It changes only the Staff profile department after a bounded,
transactional check for explicitly assigned unresolved work. Unassigned queue
work does not block and no complaint is moved or modified. The current runtime
has no assignedStaffId writer; any future assignment feature must participate
in this same lifecycle transaction/guard boundary before it is enabled.

The contract applies to Customer, Staff, Manager, and carefully governed Admin
profiles. Firebase Console/IAM ownership is separate from the application
`role: admin` and is never granted by these operations.

## Invariants

- Every mutation uses a trusted backend route and a verified Firebase ID token.
- Every mutation requires a bounded idempotency key, a trusted action record
  with controlled state transitions, and immutable backend-only audit events;
  absence or reuse with a changed request fails safely.
- Authorization requires a strict, active Admin profile with a null department.
- The target is resolved from a backend-issued opaque account reference only
  after actor authorization succeeds.
- The request never accepts a UID, email, Firebase document path, Auth record,
  claim, password, credential, or arbitrary account selector.
- Public registration remains Customer-only.
- The existing Admin provisioning route remains Staff/Manager-only and creates
  disabled, passwordless, inactive `pending_setup` accounts. Lifecycle
  operations do not activate or replace the owner-only local activation helper.
- Role changes are forbidden. A lifecycle route cannot change Customer, Staff,
  Manager, or Admin role.
- Customer department is always null; Staff has exactly one of the six
  authoritative departments; Manager and Admin department remain null.
- Permanent deletion remains deferred until retention, anonymization,
  complaint/message/event ownership, audit preservation, cascade, and recovery
  policies are separately approved.
- No frontend response exposes raw UID, Auth internals, claims, credentials,
  password state, provider state, action internals, or private ticket data.

## Profile state and action state

The existing profile state is represented by the strict boolean `active` and
the safe derived `setupStatus`. `pending_setup` remains the state for a newly
provisioned disabled/passwordless Staff or Manager account. A lifecycle
operation must not turn `pending_setup` into an active account; the trusted
owner activation workflow remains separate.

The future lifecycle action record uses a separate state machine. These states
are trusted persistence values, not browser claims:

| Action state | Meaning | Retry/terminal behavior |
|---|---|---|
| `reserved` | Validated request and idempotency key reserved. | Continue only the same operation. |
| `profile_inactivated` | Disable transaction committed the inactive profile. | Continue Auth disablement. |
| `auth_disable_pending` | Profile is inactive; Auth disablement or token revocation is incomplete or unknown. | Retry the same action after trusted Auth inspection. |
| `auth_enable_pending` | Reactivation Auth enablement is incomplete or unknown while the profile remains inactive. | Retry the same action after trusted Auth inspection. |
| `profile_activation_pending` | Auth enablement succeeded or is safely recoverable, but profile activation is incomplete. | Retry profile activation while authorization remains denied. |
| `completed` | Required Auth/profile state and audit finalization completed. | Same request returns the existing result. |
| `conflict` | Idempotency, state, target, concurrency, or policy precondition conflicts. | Never overwrite; a new approved request is required. |
| `failed` | Safe terminal validation or policy failure with no mutation claimed. | Do not retry as a mutation unless a new request is valid. |

The action record stores only safe operational metadata: action domain/version,
opaque action reference, actor and target references in trusted persistence,
request and idempotency fingerprints, operation type, target profile role,
department values where required, lifecycle state, safe result code, and
server-created timestamps. Raw credentials, tokens, claims, arbitrary reasons,
complaint data, message data, or Auth provider records are prohibited.

Profile changes and action-state changes that belong to the same Firestore
phase are written in one trusted transaction. The mutable action coordinator
has controlled state transitions; immutable audit events are append-only and
backend-only. Firebase Auth calls are outside that transaction and are
recovered through the action state below.

## R2C2B persistence contract

R2C2B uses exactly these backend-only top-level collections; no subcollections,
aliases, client access, rules, or indexes are added:

- `adminAccountLifecycleActions/{actionRef}` — mutable action coordination,
  keyed by the existing deterministic lowercase SHA-256 `actionRef`.
- `adminAccountLifecycleTargetGuards/{targetGuardRef}` — durable per-target
  serialization guard, keyed by a new domain-separated/versioned lowercase
  SHA-256 of the local project/environment boundary and trusted target UID.
- `adminAccountLifecycleAuditEvents/{eventRef}` — create-once immutable audit
  event, keyed by a domain-separated/versioned lowercase SHA-256 binding the
  action reference and accepted transition identity.

Reservation creates the action and its guard atomically after reading both
destinations. A rejected reservation never changes another action's guard.
Completion marks the owned guard inactive in the same transaction as the
completed action and audit event. A conflict marks only its own guard inactive;
a failed action retains its owned guard as blocked; retryable nonterminal states
retain active ownership. Guard `version` is a bounded monotonically increasing
guard-generation version, independent of the action state version. An inactive
guard may be reacquired only by a new action in the same transaction after an
explicit version-checked read; `createdAt` remains immutable while ownership
fields and `updatedAt` change. Guards are never deleted. Force unlock,
operator recovery, profile mutation, Firebase Auth mutation, routes, and UI
remain unavailable.

## Lifecycle transitions

| Operation | Allowed target | Required precondition | Result |
|---|---|---|---|
| Disable | Customer, Staff, Manager; Admin only under safeguards | Complete active profile, valid opaque reference, no blocking active work | Profile becomes inactive, then Auth is disabled and sessions are revoked. |
| Reactivate | Customer, Staff, Manager; Admin only under safeguards | Complete inactive profile, valid opaque reference, not `pending_setup` | Auth is enabled first, then the profile becomes active. |
| Staff reassignment | Staff only | Complete Staff profile, new approved department, assignment-impact checks pass | Department changes without changing role or moving historical complaints. |
| Role change | None | Never allowed | Safe conflict/validation response; no write. |
| Permanent deletion | None in this contract | Retention and recovery policy approval is absent | Deferred; no route or mutation. |

An already inactive complete profile may receive an idempotent disable result.
An already active complete profile may receive an idempotent reactivate result
only when the trusted Auth/profile state is consistent. `pending_setup`,
malformed, missing, or inconsistent profiles fail closed and are not coerced.

## Disable sequence and recovery

1. Verify the bearer token and load the actor profile. Require a strict active
   Admin before reading or resolving the target.
2. Validate the opaque account reference, resolve it to the trusted target
   profile, and validate target role, profile shape, state, actor/target
   separation, last-Admin protection, and work-impact policy.
3. Reserve the deterministic action using the idempotency key and request
   fingerprint. This reservation is a separate committed Firestore
   transaction that creates/retains the action and active target guard. A
   conflicting reuse fails without changing the target or another action's
   guard.
4. In a subsequent Firestore transaction, confirm the expected profile
   action/guard version and state,
   set the application profile to `active: false`, and record
   `profile_inactivated`. Application authorization therefore fails closed
   before the external Auth step. If this transaction fails, the prior
   reservation may remain persisted with its active guard; the same validated
   request retries that action and no Auth call is made.
5. Disable the Firebase Auth identity and revoke refresh tokens through the
   trusted Firebase Admin adapter. No Auth data is returned to the browser.
6. Record `completed` only after the Auth operation is confirmed. If the Auth
   call fails or its result is unknown, retain the inactive profile, record
   `auth_disable_pending`, and return a safe retryable failure.

A retry continues the same action. It must inspect trusted state, avoid
reattaching a second operation, and finalize the existing action when the
required state already holds. Existing sessions are denied by strict active
profile checks after the profile step; the exact token-revocation behavior
still requires local runtime verification and is not claimed here.

If Auth disablement succeeds but action finalization or a later persistence
write fails, recovery must inspect trusted Auth state and append/finalize the
same audit/action record. It must never reactivate the profile merely to undo a
partial audit failure, and it must not return completed until the required
disablement and audit finalization are recorded. If the result remains
uncertain, the profile stays inactive and the action remains retryable and
operator-visible.

## Reactivate sequence and recovery

1. Verify the active strict Admin and resolve/validate the target as above.
2. Reserve or recover the same action for the same idempotency key and request.
3. Keep the profile inactive while enabling the Firebase Auth identity.
4. If Auth enablement fails or is unknown, leave the profile inactive and
   record `auth_enable_pending` with no active-profile write.
5. After Auth enablement is confirmed, activate the profile in a trusted
   transaction with an expected-state/version check, then record `completed`.
6. If profile activation fails, strict profile authorization continues to deny
   access. A retry recovers the same action and never creates a second target.

The implementation must distinguish an Auth-enabled but profile-inactive
recovery state from a completed active account. It must never report success
from Auth enablement alone.

## Admin safeguards

- The verified actor and target must be different. An Admin cannot disable or
  reactivate their own account.
- Disabling an Admin requires proving that at least one other valid, active,
  complete Admin remains. If the count cannot be established because of a
  malformed or unavailable profile, fail closed rather than risk disabling the
  last valid Admin.
- The last-Admin check must be performed in the same trusted transaction that
  inactivates the target, with a transactional read/precondition over the
  complete valid-active-Admin set or an equivalent serialized guard. A stale
  frontend count, prior directory page, or cached overview can never authorize
  the operation. Concurrent disable requests must conflict or serialize so
  that zero valid active Admins cannot result.
- Reactivating another Admin is still strict-Admin-only and audited; it does
  not grant the actor a role-management or Firebase IAM capability.
- A target Admin with a null department and strict profile fields remains the
  only supported Admin shape. Malformed Admin records cannot satisfy the
  last-Admin safeguard.

## Staff department reassignment

Reassignment accepts only a Staff target and one of:

`transfer_payment`, `account_support`, `card_atm`, `fraud_security`,
`loan_credit`, or `general_support`.

The role remains `staff`; no Customer, Manager, or Admin department may be
created. Customer, Manager, and Admin targets are rejected. Historical tickets
are not retroactively moved and their original ownership, events, and audit
history are preserved.

Before implementation, the trusted backend must perform a concurrency-safe
work-impact check. Reassignment is blocked only when the target Staff account
is explicitly assigned to one or more unresolved complaints. Those complaints
must be resolved or reassigned by a Manager through the separately authorized
workflow before the Staff department change is retried. An unresolved
complaint that is unassigned to that Staff member does not block reassignment;
it remains in its existing department queue for other authorized Staff.
Reassignment must not automatically move, reroute, or modify any complaint.
The implementation performs this check in the reassignment transaction with a
bounded local scan of at most 200 ticket documents (201 are requested to detect
overflow). A scan overflow or malformed ticket fails closed. The current
runtime has no assignedStaffId writer; any future assignment feature must join
this same lifecycle transaction/guard boundary before it is enabled.

Department reassignment is one audited, idempotent operation with an expected
profile-state/version check. A retry with the same request returns the same
result; a changed department or changed target under the same key conflicts.

## Opaque account reference

Future Admin APIs use a backend-issued reference in the form
`acct_v1_` followed by 64 lowercase hexadecimal characters generated from
cryptographically random bytes. It is not derived from or reversible to a UID,
email, document path, action ID, or idempotency key. The backend stores only a
trusted lookup hash/reference mapping and target UID; that mapping is not
browser-readable.

The reference is opaque and strictly format-validated, contains no raw UID,
email, role, or profile data, but it is not an
authorization credential, not a proof of Admin authority, and not encrypted or
signed. Its limitations are that possession may allow target lookup attempts
against an already-authorized endpoint and that reference secrecy alone is
not a security boundary. Authorization, target policy, rate limits, safe
errors, and audit records remain mandatory. Malformed references fail
validation; unknown, cross-account, or inaccessible references use safe
not-found behavior; conflicting target/action bindings fail with a safe
conflict. The reference is resolved only after strict active-Admin
authorization succeeds.

## Proposed future API contract

No routes are implemented by R2C0. A later trusted backend may expose separate
operations such as:

```text
POST /admin/accounts/{accountRef}/disable
POST /admin/accounts/{accountRef}/reactivate
POST /admin/accounts/{accountRef}/department
```

Request fields are limited to:

- `accountRef` from the path, strictly validated;
- `idempotencyKey`, bounded and supplied only for the trusted request;
- `departmentId` only for Staff reassignment, from the six-value allowlist;
- an optional bounded confirmation value if a later UI policy requires it.

The browser must never supply actor UID, target UID, email, profile fields,
Auth state, timestamps, action IDs, or arbitrary reasons.

Safe success responses contain only an opaque account reference, operation
type, safe lifecycle action state, safe profile-state label, and a server
timestamp if the browser needs it. They do not return UID, Auth state,
credentials, claims, provider data, action internals, or ticket information.

Proposed safe mappings are:

| Condition | Response |
|---|---|
| Missing/invalid token | `401 authentication_required` |
| Missing, malformed, inactive, or unsupported actor profile | Established safe `403` authorization denial |
| Unknown or inaccessible account reference | `404 account_not_found` without existence detail |
| Invalid role/department/state, last-Admin/self-target/work-impact policy failure | `409 lifecycle_conflict` or `422 invalid_request` according to the established API taxonomy |
| Idempotency key reused with different target/action/request | `409 idempotency_conflict` |
| Auth/profile recovery incomplete | `503 service_unavailable` with a retryable safe code |
| Unexpected trusted persistence failure | `503 service_unavailable` |

Responses and logs must not expose UID, email, path, raw request values,
exception details, Firebase errors, or whether another account owns a guessed
reference.

## R2C3A disable implementation status

The trusted disable route accepts only `{ "idempotencyKey": "..." }` with no
unknown fields and returns only `accountRef`, `operation`, `status`, and
`profileState`. Authorization completes before opaque-reference resolution,
profile access, lifecycle reservation, or Auth operations. Customer, Staff, and
Manager targets use the recoverable `profile_inactivated` and
`auth_disable_pending` states; Auth disablement and refresh-token revocation
remain outside Firestore transactions. Admin targets return the safe
`admin_disable_not_available` conflict and perform no lifecycle write.

No lifecycle notification is created. No frontend control, Emulator/runtime
verification, Cloud support, or operator force-unlock behavior is claimed.

## R2C4A reactivation implementation status

The trusted reactivation route accepts only `{ "idempotencyKey": "..." }` and
returns only `accountRef`, `operation`, `status`, and `profileState`. It may
reactivate only an inactive Customer, Staff, or Manager whose inactive profile,
inactive target guard, completed disable action, and immutable completed-disable
audit event form one validated lineage. The reactivation action stores the
previous disable action reference as trusted persistence metadata before the
guard is transferred.

Reactivation advances through `auth_enable_pending` and
`profile_activation_pending`; application authorization remains denied until
the final transaction activates the profile and releases the guard. Auth
enablement is performed by trusted UID only and remains outside Firestore
transactions. Pending owner activation remains separate. No frontend control,
Emulator/runtime verification, Cloud support, notification, or operator unlock
behavior is claimed.

## R2C5 department reassignment implementation status

The route accepts exactly `{ "idempotencyKey": "...", "departmentId":
"..." }`, using the six approved department IDs, and returns exactly
`accountRef`, `operation`, `status`, and `departmentId`. It uses
`reserved -> completed` for a safe reassignment, or an audited conflict that
releases only its owned guard when explicitly assigned unresolved work is
found. Same-department requests return `409 department_unchanged` without a
lifecycle write. Customer, Manager, Admin, pending Staff, and inactive Staff
targets are not reassigned. No Auth operation, complaint mutation, frontend
control, notification, operator unlock, or runtime verification is included.

## R2C6 lifecycle recovery continuation status

The trusted backend adds exactly
`POST /admin/users/{accountRef}/lifecycle-recovery`. Its strict request is a
discriminated operation object: `disable`, `reactivate`, or
`reassign_department` with one approved `departmentId`. It accepts no
idempotency key or lifecycle reference and never creates or reserves an
action. The target guard discovers only the current action, and continuation
requires the same verified Admin actor that created it. Completed actions are
rediscovered with the original safe response; supported incomplete states
resume through the existing orchestration. Conflict is reported safely, while
failed or blocked actions require future operator recovery. No action, guard,
audit reference, original key, or internal state is exposed.

This continuation path is pure/fake-tested only. Alternate-Admin recovery,
blocked-action unlock, frontend lifecycle controls, notifications, and
runtime/Emulator verification remain unavailable. No raw idempotency key needs
frontend storage for this endpoint.

## Notification boundary

R2C0 does not add lifecycle notification triggers. No Staff, Manager, or Admin
lifecycle notification is claimed to exist. A disabled user cannot read
in-app notifications because notification read APIs require a strict active
profile. Existing notifications may remain in trusted storage subject to the
existing retention contract; this document does not add cleanup or delivery.
Browser push, email, and SMS remain deferred pending provider, budget,
credentials, consent, retry, bounce, and localization approval.

## Verification and preserved boundaries

This contract requires future pure/fake and local runtime tests for strict
authorization ordering, self/last-Admin safeguards, role/department invariants,
idempotent retries, transaction preconditions, Auth/Firestore partial failure
recovery, session fail-closed behavior, action-record immutability, and safe
response fields. None are implemented by R2C0.

`cloud_staging_not_adopted`, the no-budget/no-billing Cloud deferral, the local
Emulator default, Customer-only registration, Staff/Manager-only provisioning,
the owner-only local activation helper, Customer ownership, Staff department
isolation, Manager-only technical evidence, and all frozen model/evaluation,
V1/V2, similarity, threshold, and hash artifacts remain unchanged.

Historical checkpoint text remains historical evidence and is not rewritten to
claim lifecycle implementation. Browser, Emulator, Firebase CLI, Cloud, and
production verification remain incomplete.
