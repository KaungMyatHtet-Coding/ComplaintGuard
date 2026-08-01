# Firestore Access Matrix

This Day 4 matrix was owner-approved on 21 July 2026. Authorization must be enforced by Firestore rules and trusted backend code, never by frontend visibility alone.

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
