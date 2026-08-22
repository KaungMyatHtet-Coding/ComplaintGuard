# Dashboard and Account Audit — Approved R0.1 Boundary

## Purpose

This document consolidates the read-only dashboard/account audit and the
focused workflow audit. It records approved future direction; it does not
describe new application behavior as implemented.

R0.1 is documentation and contract approval only. No application code, API
route, schema, Firestore rule, index, notification, assignment, SLA
calculation, UI, or runtime behavior was changed by R0.1.

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
- Frozen model, evaluation, V1/V2, similarity, threshold, and hash evidence
  remains unchanged.
- Cloud work remains deferred and `cloud_staging_not_adopted` remains enforced.

## Verification boundary

R0.1 was verified by documentation review only. No service, Emulator, browser,
Firebase CLI, Cloud resource, account, data source, or external network was
accessed. Browser/Emulator verification of the current Admin provisioning and
directory flows remains incomplete.
