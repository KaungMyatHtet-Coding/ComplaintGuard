# Firestore Access Matrix

This Day 4 matrix was owner-approved on 21 July 2026. Authorization must be enforced by Firestore rules and trusted backend code, never by frontend visibility alone.

## Implementation-status boundary

The tables below preserve the original access design. The current scope is
classified as follows:

- **Implemented and locally verified:** customer ownership, department staff
  isolation, manager review/override, and deny-by-default direct mutations.
- **Recognized role but operational feature not implemented:** the `admin` role
  resolves through authentication and has a dashboard shell, but no operational
  Admin dashboard or API exists.
- **Designed/planned:** broader assignment, priority, escalation, reopen/close,
  role management, and department administration.
- **Future Cloud staging work:** trusted provisioning, Cloud rules/indexes,
  deployment configuration, and production-equivalent security evidence.

Public self-registration is planned and, when implemented, will create only
customer accounts. Privileged accounts and department membership require
trusted provisioning.

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
in frontend visibility, trusted FastAPI checks, and Firestore rules, and are
verified locally with emulator and browser tests.

### Customer — implemented locally

- Authenticates through the current local setup, submits complaints, views only
  owned tickets, exchanges participant messages, views resolution, and submits
  feedback.
- Cannot view another customer's tickets.
- Public self-registration is planned, not implemented.

### Department Staff — implemented locally within department scope

- Sees only tickets assigned to the staff member's department, views authorized
  details, sends replies, uses currently implemented workflow transitions, and
  resolves complaints with required resolution information.
- Cannot see null-department manual-review tickets or tickets in other
  departments.
- Designed assignment, priority, escalation, reopen, and close operations are
  not all implemented.

### Manager — limited operational implementation

- Can view operational analytics and low-confidence/manual-review tickets,
  override department routing, preserve original prediction evidence, and view
  manager-authorized operational data.
- General account provisioning, full staff assignment management, complete
  priority management, general reopen/close administration, and system
  administration are not implemented.
- The current UI requires a non-empty manager override reason, while the
  backend request schema permits the reason to be optional. Backend enforcement
  is planned for a later implementation phase.

The `admin` role currently has only authenticated profile resolution and an
administration dashboard shell. No admin UI, administration endpoint, demo seed
identity, role management, department management, or emergency correction
workflow is implemented. Rows above that describe future authority boundaries,
not delivered admin functionality. Trusted staff/manager/admin provisioning and
platform management are planned for Phase 4. The Admin must never rewrite
original model prediction evidence. Production Firebase deployment is
unverified.
