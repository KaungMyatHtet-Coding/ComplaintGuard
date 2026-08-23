# Firestore Access Matrix

This Day 4 matrix was owner-approved on 21 July 2026. Authorization must be enforced by Firestore rules and trusted backend code, never by frontend visibility alone.

## Implementation-status boundary

The tables below preserve the original access design. The current scope is
classified as follows:

- **Implemented and locally verified:** customer ownership, department staff
  isolation, manager review/override, and deny-by-default direct mutations.
- **Implemented and pure-tested, runtime pending:** the `admin` role requires a
  strict active profile. Admin authorization, the pending Staff/Manager
  provisioning API, and the Admin provisioning dashboard are implemented. The
  local bootstrap and activation helpers are committed but unexecuted.
- **Implemented and automated-frontend-tested, browser visual verification
  pending:** UI/UX Slices A-D preserve the existing role boundaries. Customer
  details exclude technical model evidence, Staff has accessible workflow tabs
  including Staff-authorized Model Data, Login/Register have the shared secure
  theme and form polish, and Manager has the readable Model & Dataset Analytics
  presentation. No Customer, Staff, or Admin access was added to Manager-only
  technical evidence.
- **Current versus approved future:** the local read-only Admin directory now
  supports the approved Customer, Staff, Manager, and Admin safe projection,
  and R2B provides a read-only account-detail drawer from parsed directory
  rows. R2C3A adds the trusted, pure/fake-tested Customer, Staff, and Manager
  disable workflow, and R2C4A adds the trusted, pure/fake-tested Customer,
  Staff, and Manager reactivation workflow only for accounts proven disabled by
  that lifecycle workflow. R2C5 adds the pure/fake-tested active-Staff
  department reassignment workflow. No frontend control or Emulator
  verification is claimed. Admin lifecycle mutation, pending owner activation,
  role changes, and deletion remain unavailable.
- **Designed/planned:** deletion, password reset/invitation, Customer
  management, Admin creation, broader assignment, priority, escalation,
  reopen/close, and department administration.
- **Future Cloud staging work:** trusted provisioning, Cloud rules/indexes,
  deployment configuration, and production-equivalent security evidence.

Public self-registration is implemented as Customer-only. It accepts no role,
department, active state, UID, timestamps, or claims; Firebase Auth creates the
identity and the trusted backend creates the fixed Customer profile. A genuinely
missing profile is recoverable through `profile_incomplete`, while privileged,
inactive, and malformed profiles cannot use public recovery. Direct client
profile writes remain denied. Registration Emulator E2E remains pending because
the Firebase CLI did not reach a safe isolated runtime.

## Access predicates

- **Own ticket:** authenticated UID equals `ticket.customerId`.
- **Assigned department:** ticket has a non-null stable department ID and the active staff profile has `departmentId == ticket.departmentId`. Pending unclassified tickets are not staff-readable.
- **Manager:** active profile role is `manager`.
- **Admin:** active profile role is `admin`.
- **Trusted backend:** verified server environment using the Admin SDK; it bypasses Firestore rules and must independently validate, authorize, redact, transact, and audit every operation.

## Document access

| Resource/action | Customer | Staff | Manager | Admin |
|---|---|---|---|---|
| Read own user profile | Yes | Yes | Yes | Yes |
| Read another user profile | No | No | Operationally necessary views only through trusted backend | Administrative views only through trusted backend |
| Update own display name/locale | Later restricted endpoint or exact-field rule | Same | Same | Same |
| Change role, department, or active status | No | No | No | Trusted audited backend only |
| Read departments | Authenticated | Authenticated | Authenticated | Authenticated |
| Write departments | No | No | No | Trusted audited backend only |
| Create ticket | Trusted submission backend for self | No | Trusted backend if operationally required | No routine action |
| Read ticket | Own only | Assigned department only | All operational tickets | Administratively necessary views through trusted backend only |
| Update ordinary ticket fields directly | No | No | No | No |
| Read participant messages | Own ticket only | Assigned department only | All permitted tickets | Administratively necessary views through trusted backend only |
| Create message | Trusted redacting backend on own ticket | Trusted redacting backend for assigned department | Trusted redacting backend | No routine action |
| Update/delete message | No | No | No | Audited exceptional backend only |
| Read audit events | Not initially exposed | Assigned department only | All operational tickets | Administratively necessary views through trusted backend only |
| Create/update/delete event | No | No | No | Create only through trusted audited backend; no mutation |
| Read dashboard summaries | No | No | Yes | Yes |
| Write dashboard summaries | No | No | Trusted backend only | Trusted backend only |

## Workflow authority

| Action | Customer | Assigned-department staff | Manager | Admin |
|---|---|---|---|---|
| Submit complaint | For self through trusted backend | No | No routine action | No routine action |
| Reply | Own ticket through trusted backend | Permitted ticket through trusted backend | Permitted through trusted backend | No routine action |
| Assign/reassign staff | No | No direct write | Yes, through trusted backend | No routine action |
| Change department | No | No | Yes, through trusted backend | Emergency correction through audited backend only |
| Set priority | No | No | Yes, through trusted backend | No routine action |
| Escalate | No | Request only | Yes, through trusted backend | No routine action |
| Move to in progress | No | Yes, through trusted backend | Yes | No routine action |
| Await customer | No | Yes, through trusted backend | Yes | No routine action |
| Resolve | No | Yes, through trusted backend | Yes | No routine action |
| Reopen | Request only | Request only | Yes, through trusted backend | No routine action |
| Close | No | No | Yes, through trusted backend | No routine action |
| Modify model prediction | No | No | No; may override routing without rewriting prediction | No |
| Manage roles/departments | No | No | No | Yes, through trusted audited backend |

## Protected fields

Ordinary clients cannot directly write `customerId`, `role`, `departmentId`, `assignedStaffId`, `priority`, `status`, `predictedDepartmentId`, `predictionConfidence`, `routingSource`, `escalated`, `resolutionSummary`, timestamps, audit fields, or author identity. Initial Day 4 rules intentionally deny ticket, message, and event client writes until trusted backend endpoints implement the approved controls.

On trusted creation, `departmentId` is `null` while `routingSource` is
`pending`. Only trusted classification/routing code may set it to one of the
six operational department IDs, and it must do so before the ticket enters a
routed state. `pending` and `unassigned` are not department IDs. The existing
staff rule requires the staff profile's string department to equal the ticket
department, so it does not grant staff access to a null department.

Managers have broad operational visibility but do not administer identities. Admin manages role and department configuration but is not granted routine complaint-processing power. This separation limits privilege and makes exceptional corrections auditable.

## Current implementation status

The customer, assigned-department staff, and manager boundaries are implemented
in frontend visibility, trusted FastAPI checks, and Firestore rules, and the
underlying workflow boundaries are verified locally with emulator and browser
tests. This does not constitute browser-based visual verification of UI/UX
Slices A-D.

R0.1 records approved future policy only. The current Customer API still has a
future data-minimization projection requirement: Customer responses must later
exclude customer IDs, model fields, message/sender IDs, raw event/action names
and IDs, actor IDs, model rationale, and internal reassignment/escalation
reasons. The current Staff workflow remains department-level and does not
enforce claim or assignment ownership. Durable in-app notifications, Customer
History pagination/unread state, response-target calculation, proactive alerts,
and all-role Admin listing remain unimplemented.

### Customer — implemented locally

- Authenticates through the current local setup, submits complaints, views only
  owned tickets, exchanges participant messages, views resolution, and submits
  feedback.
- Cannot view another customer's tickets.
- Public self-registration is Customer-only and implemented locally; its
  registration Emulator E2E remains pending.

### Department Staff — implemented locally within department scope

- Sees only tickets assigned to the staff member's department, views authorized
  details, sends replies, uses currently implemented workflow transitions, and
  resolves complaints with required resolution information.
- Cannot see null-department manual-review tickets or tickets in other
  departments.
- Designed assignment, priority, escalation, reopen, and close operations are
  not all implemented. R0.1 approves Department Queue versus My Work, atomic
  Staff claim, Manager assignment/reassignment, and blocking Staff disable or
  department change while active assignments exist; these are future design,
  not current behavior.

### Manager — limited operational implementation

- Can view operational analytics and low-confidence/manual-review tickets,
  override department routing, preserve original prediction evidence, and view
  manager-authorized operational data.
- Can view the Manager-only frozen model equations and separate aggregate-safe
  controlled V1/V2 evidence in Model & Dataset Analytics. V1 and V2 are
  synthetic, small-sample demonstrations, not official accuracy or live-user
  performance; the V2 `2/2 (100%)` routed-case value is always paired with
  `2/6` automatic-route coverage.
- This technical evidence presentation does not grant access to Customers,
  Staff, or Admins. It does not expose complaint text, case rationale, private
  identifiers, or credentials.
- The Manager analytics presentation includes ordinary section navigation,
  readable metric tables/bars, and accessible confusion-matrix descriptions;
  these are automated-test verified but not browser/device visually verified.
- General account provisioning, full staff assignment management, complete
  priority management, general reopen/close administration, and system
  administration are not implemented.
- The current UI requires a non-empty manager override reason, while the
  backend request schema permits the reason to be optional. Backend enforcement
  is planned for a later implementation phase.

The `admin` role is distinct from Firebase Console/IAM ownership. An active
Admin may prepare only pending Staff or Manager accounts through the trusted
`POST /admin/users` workflow and its bilingual dashboard. New Auth identities
are disabled, passwordless, and claimless; profiles are inactive, with Staff
requiring one approved department and Manager requiring `departmentId == null`.
Managers handle complaint operations, routing review, and analytics but cannot
provision accounts. Public registration cannot create Staff, Manager, or Admin;
Admin cannot create Customer or another Admin in the first version. The Admin
must never rewrite original model prediction evidence. Production Firebase
deployment is unverified.

R0.1 additionally approves future strict-Admin visibility of Customer, Staff,
Manager, and Admin profiles using only display name, email, role, locale,
localized department, profile active state, derived setup status, and an opaque
account reference for detail navigation. UIDs, Auth provider records, tokens,
claims, internal actions, complaint narratives, messages, and private ticket
information remain prohibited.

## R2C0 future account lifecycle boundary

R2C0 approves a future trusted backend lifecycle contract only; it does not
change the current read-only directory or provisioning behavior. A strict,
active Admin may later request disable/reactivate for complete Customer, Staff,
and Manager profiles, and for other Admin profiles only when the actor is not
the target and at least one other valid active Admin remains after disablement.
Malformed or unavailable Admin data must fail closed rather than weaken that
safeguard.

R2C3A implements only Customer, Staff, and Manager disablement through the
trusted backend route. Admin disablement remains deferred to R2C3B because it
requires the separate global last-active-Admin concurrency guard. R2C4A
implements reactivation for targets proven disabled by that workflow, and R2C5
implements active-Staff department reassignment through a bounded transaction.
Lifecycle notifications remain unimplemented.

Staff department reassignment is implemented as pure-tested Staff-only
governance. It accepts only
the six authoritative department IDs, never changes role, never assigns a
department to Customer, Manager, or Admin, and never retroactively moves
complaints. The trusted, concurrency-safe operation blocks only when
the target Staff account is explicitly assigned to one or more unresolved
complaints. Unresolved complaints that are unassigned to that Staff member
remain in their existing department queue for other authorized Staff. No
complaint is automatically moved, rerouted, or modified. The current runtime
has no assignedStaffId writer after ticket creation; any future assignment
feature must participate in the same transaction/guard boundary before it is
enabled. No runtime or Emulator verification is claimed.

No role change, permanent deletion, password/claims operation, Auth-provider
inspection, direct frontend write, or Firebase IAM operation is permitted.
Future targeting uses a backend-issued opaque account reference only after
strict Admin authorization. The reference is not authorization and is not
signed or encrypted; strict validation, safe errors, trusted resolution,
idempotency, concurrency checks, controlled action records, and immutable
backend-only audit events remain required.
