# Dashboard and Account Audit — Approved R0.1 Boundary

## Purpose

This document consolidates the read-only dashboard/account audit and the
focused workflow audit. It records approved future direction; it does not
describe new application behavior as implemented.

R0.1 is documentation and contract approval only. No application code, API
route, schema, Firestore rule, index, notification, assignment, SLA
calculation, UI, or runtime behavior was changed by R0.1.

The Current implementation paragraph below is the preserved R0.1 snapshot.
Later local R1/R2 slices supersede its shell, directory, and account-detail
status; those later slices still do not implement lifecycle mutation.

## Current implementation

The verified current application remains a local Firebase Emulator prototype.
The current shell is shared by all roles, but it has no approved collapsible
sidebar, durable notification center, dedicated Customer History route,
response-target calculation, Staff claim path, Manager assignment path, or
proactive alert worker.

The current Admin directory is read-only and Staff/Manager-only. The current
Customer API returns a broader internal contract than the approved future
Customer projection and still requires data minimization before a dedicated
History surface can be implemented.

The current Staff workflow is department-level. Staff can view and mutate
department-visible work through the existing trusted path; assignment ownership
is not currently enforced. Existing `assignedStaffId` data must not be treated
as implemented My Work authorization.

The current Manager workspace retains ticket-level routing review and technical
model evidence. That boundary remains unchanged.

## Approved future direction

The approved contracts are defined in
[`workflow_notification_contract.md`](workflow_notification_contract.md).
They cover:

- all-role safe Admin governance;
- trusted account lifecycle safeguards;
- Department Queue versus My Work;
- Customer-safe History and timeline projection;
- durable in-app notifications;
- response-target policy;
- aggregate Admin analytics;
- Manager technical evidence.

All future behavior requires trusted backend authorization, validation, audit
records, idempotency/concurrency protection, and local-only verification before
being described as implemented.

The detailed R2C0 lifecycle contract is recorded in
[`admin_account_lifecycle_contract.md`](admin_account_lifecycle_contract.md).
It is future design only; the current directory remains read-only and the
current provisioning flow remains Staff/Manager-only.

The R0.1 current snapshot above predates R2A and R2B. The current local
prototype now has the strict-Admin all-role read-only directory and the
read-only account-detail drawer. Those slices do not add lifecycle mutation;
browser and Emulator verification remain incomplete.

## R2C8D0 account-state documentation approval

R2C8D0 approves documentation and contract work only. The current seven-file
R2C8C frontend slice remains uncommitted and unchanged by this checkpoint. A
future trusted profile contract will replace the ambiguous public `setupStatus`
with `accountState`: `active`, `pending_setup`, `disabled`, or
`inactive_unverified`. The `active` boolean remains the access primitive.

Pending setup is reserved for newly prepared Staff/Manager accounts awaiting
trusted activation. Disabled means intentionally lifecycle-disabled. Inactive
status unavailable means inactive lineage is missing, malformed, or ambiguous;
it must not be presented as pending activation or completed disablement.
Recovery required and trusted operator review are actor-bound lifecycle drawer
states, not directory-global account states or overview counts. No application,
migration, Emulator, Cloud, or runtime behavior is implemented or verified by
R2C8D0.

## Security and privacy invariants

- Public registration remains Customer-only.
- No direct frontend profile, role, department, assignment, or authorization
  writes are permitted.
- Active Admin authorization remains strict and trusted-backend enforced.
- Customer ownership and Staff department isolation remain mandatory.
- UIDs, Auth provider records, tokens, claims, internal action records,
  complaint narratives, messages, and private ticket information remain
  prohibited from Admin browser projections.
- Customer responses must exclude internal IDs, sender UIDs, model fields,
  raw event names, and internal reasons.
- Permanent deletion remains deferred.
- Disable/reactivate, Staff reassignment, opaque account targeting, and
  Firebase Auth/Firestore recovery remain approved future contracts only; no
  lifecycle control is currently implemented.
- The approved future Staff reassignment check blocks only unresolved
  complaints explicitly assigned to the target Staff member. Unassigned
  unresolved complaints remain in their existing department queue; no complaint
  is automatically moved, rerouted, or modified. The trusted check must be
  concurrency-safe and return `409` for a concurrent assignment change, with
  Manager resolution or reassignment required before retry.
- Frozen model, evaluation, V1/V2, similarity, threshold, and hash evidence
  remains unchanged.
- Cloud work remains deferred and `cloud_staging_not_adopted` remains enforced.

## Verification boundary

R0.1 was verified by documentation review only. No service, Emulator, browser,
Firebase CLI, Cloud resource, account, data source, or external network was
accessed. Browser/Emulator verification of the current Admin provisioning and
directory flows remains incomplete.
