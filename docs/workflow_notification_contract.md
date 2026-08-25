# Workflow, History, Notification, Assignment, and Response-Target Contract

## Status and scope

This document records the owner-approved R0.1 contract for future local
implementation. R0.1 is documentation and contract approval only. It does not
implement application code, API routes, schemas, Firestore rules, indexes,
notifications, assignment, SLA calculations, UI, scheduled workers, or runtime
behavior.

The current application remains the local Firebase Emulator prototype. The
current Customer API, Staff workflow, Admin directory, and Manager analytics
remain unchanged. Browser and Emulator verification for the relevant Admin and
account workflows remains incomplete.

Cloud staging remains deferred. `cloud_staging_not_adopted`, the no-budget/no-
billing boundary, the frozen model and evaluation evidence, and the Manager
technical-evidence boundary remain enforced.

## Approved Admin account governance contract

An active, strictly authorized application Admin may later list Customer,
Staff, Manager, and Admin profiles through a trusted backend. Firebase
Console/IAM ownership is not an application Admin role.

The safe browser projection is limited to:

- `displayName`
- `email`
- `role`
- `locale`
- localized department
- profile `active` state
- derived setup status

Email visibility is approved for strict active-Admin account governance. UIDs,
Auth provider records, tokens, claims, internal action records, complaint
narratives, messages, and private ticket information remain prohibited.

A future individual account view must use an opaque account reference, never a
Firebase UID. Future display-name editing, locale editing, Staff department
reassignment, disable, and reactivate actions require trusted backend
authorization, validation, audit records, idempotency/concurrency protection,
and Auth/profile consistency. No direct frontend profile or authorization
writes are permitted.

If Staff has active assigned tickets, disable operations must initially fail
safely and require reassignment first. Staff department reassignment has the
narrower approved future rule that only unresolved complaints explicitly
assigned to the target Staff member block the change. Unassigned unresolved
complaints remain in their existing department queue; no complaint is
automatically moved, rerouted, or modified. A trusted concurrency-safe check
must return `409` if assignment changes during the operation, and a Manager
must resolve or reassign the affected complaints before retry. Permanent deletion remains deferred until retention,
anonymization, complaint/message/event ownership, audit preservation, cascade,
and recovery policies are approved.

## Approved Staff allocation contract

This is approved design, not implemented behavior.

- Staff may view the authorized department queue.
- Department Queue and My Work are separate views.
- Active Staff may claim an eligible unassigned ticket in their own department.
- Claiming must be atomic and concurrency-safe.
- Two Staff members must not successfully claim the same ticket.
- Assigned Staff is the primary actor permitted to reply or perform workflow
  transitions.
- Other Staff in the department retain read access according to policy but may
  not independently mutate an assigned ticket.
- A strict Manager may assign or reassign tickets to active Staff in the target
  department.
- Assignment and reassignment require trusted validation, explicit
  confirmation, idempotency, and safe audit events.
- Automatic Staff assignment is not approved.
- Disabled Staff must not retain active assignments.
- A future department change blocks only on unresolved complaints explicitly
  assigned to the target Staff member; unresolved unassigned complaints remain
  in the department queue. This is approved design, not implemented behavior.

The current Staff implementation remains department-level: it has no claim or
assignment enforcement, and current mutations are authorized by department
scope rather than assigned Staff ownership.

## Approved Customer History contract

Future Customer browser responses must be a server-side, ownership-bound
projection. They must exclude:

- `customerId`
- `predictedDepartmentId`
- `predictionConfidence`
- `routingSource`
- message IDs
- sender UIDs
- raw event names
- event/action IDs
- actor IDs
- model rationale
- internal reassignment or escalation reasons

Approved History features across the staged sequence:

- owned tickets only;
- deterministic cursor pagination;
- status and department filters (R2C10B-B0 only; future implementation);
- created, updated, and resolved timestamps;
- unread reply indicator/count;
- public response-target state;
- Customer-safe timeline;
- participant messages without internal IDs or UIDs;
- no technical model or dataset evidence.

Date-range filtering and exact-reference list lookup are not B-B features. They
are deferred to R2C10B-C and require separate query, index, and cost review.
Full-text search remains prohibited; any later reference lookup must not become
raw full-text complaint search.

### R2C10B-B0 exact Customer History filter approval

This is documentation-only approval. R2C10B-A is implemented locally; B-B
status/department filters, version-2 cursors, filter controls, and three new
ticket indexes are future work and are not implemented or deployed.

The future `GET /customer/tickets` route accepts only optional `pageSize`,
`cursor`, `status`, and `departmentId` after B-B implementation. `pageSize` is
an ASCII decimal integer, defaults to `25`, is bounded to `1`-`50`, and occurs
at most once. `cursor` is a version-2 opaque cursor, maximum `512` ASCII
characters, and occurs at most once. `status` and `departmentId` each occur at
most once; omission means all. Their exact allowlists are:

- Status: `submitted`, `triaged`, `in_progress`, `awaiting_customer`,
  `resolved`, `closed`.
- Department: `transfer_payment`, `account_support`, `card_atm`,
  `fraud_security`, `loan_credit`, `general_support`.

Both filters are logical AND. The UI All option omits the parameter. Empty,
repeated, extra, whitespace, trimmed, case-folded, aliased, coerced, and
comma-separated values return `422`. Filters are server-side and ownership-
bound; no Customer UID or ownership field is client-supplied.

Authorization is Bearer authentication, token validation, Customer profile
validation, `role == customer`, `active == true` and `accountState == active`,
then page-size/filter/cursor validation, then the ownership-bound query.
Unauthorized callers receive no filter/cursor details and cause no ticket query.

The exact version-2 cursor and canonical query-contract inputs are authoritative
in `docs/firestore_schema.md`. Version-1 A cursors are rejected after
authorization; B-B cursors use version exactly `2`, preserve the existing five
decoded keys and `createdAt`/document-ID boundary, and bind to the exact
Customer, filter combination/value, projection, bounds, and ordering. Four
filter shapes are distinct: unfiltered, status only, department only, and both.

Initial search must not introduce raw full-text complaint searching.

Approved Customer timeline labels are:

- Complaint received
- Complaint assigned to a service team
- Team started reviewing
- More information requested
- Response from ComplaintGuard team
- Your reply
- Complaint resolved
- Complaint closed
- Complaint reopened, only if later implemented

Customer reply event completeness must be addressed in the future backend
contract. The current Customer reply transaction writes a message and updates
the ticket but does not write a ticket event.

## Approved durable notification contract

Notifications will use a future top-level `notifications` collection. They are
created only by trusted backend code and are authenticated and recipient-bound.

Safe browser fields are limited to:

- opaque notification reference;
- stable notification type;
- severity;
- category;
- optional safe public ticket reference;
- title localization key;
- body localization key;
- small allowlisted parameters;
- allowlisted navigation target;
- `createdAt`;
- `readAt`;
- derived unread state;
- policy version where required.

Trusted persistence may contain `recipientUid` and deduplication material, but
neither may be returned to the browser. Notifications must not contain
complaint narratives, credentials, tokens, actor IDs, raw event IDs, model
rationale, or arbitrary free-form text.

Approved notification concepts:

| Audience | Concepts |
|---|---|
| Customer | complaint received, department assigned, Staff reply, information requested, status change, resolution, response target approaching, response target overdue |
| Staff | new department complaint, assignment, Customer reply, high priority, target approaching, overdue, Manager reassignment, escalation update |
| Manager | manual review, unassigned case, high priority, overdue, escalation request, workload observation |
| Admin | pending account/setup issue, safe account/system operational alert, aggregate department workload observation |

Localization uses stable English/Myanmar message keys. Parameters may contain
only allowlisted department, status, priority, count, public ticket reference,
or date values.

Approved future APIs are:

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{notificationRef}/read
POST /notifications/read-all
```

Mark-read operations must be recipient-bound and idempotent. Event-driven
notifications should be written transactionally with their source mutation
where practical. Derived SLA/workload notifications require a future trusted
worker or equivalent recovery process.

Application notifications have an initial retention policy of 90 days. This
does not alter or shorten audit-event retention. Cleanup automation is deferred
until a trusted worker exists, and the absence of automatic cleanup must remain
documented.

R2C0 does not add account-lifecycle notification triggers. Staff, Manager, and
Admin lifecycle notifications must not be described as implemented. A disabled
profile cannot read in-app notifications because notification APIs require a
strict active profile. Browser push, email, and SMS remain deferred under the
delivery boundary below.

Durable in-app notifications are the first approved delivery mechanism. They
are visible while using the app or after reopening it, but do not provide a
reliable immediate alert while the app/browser is fully closed. Browser
notifications are a later opt-in enhancement. Email and SMS remain deferred
until provider, budget, credentials, consent/privacy, retry, bounce, and
localization policies are approved.

## Approved response-target contract

Model confidence must never be used as a response-time estimate.

The approved initial operational-goal candidate is:

| Priority | Target |
|---|---|
| urgent | 2 business hours |
| high | 4 business hours |
| normal | 1 business day |

No `low` priority is added by R0.1.

Initial calculation policy:

- timezone: `Asia/Yangon`;
- business hours: Monday through Friday, 09:00–17:00;
- public-holiday exclusion is not initially implemented and must be disclosed;
- targets are operational goals, not guaranteed reply promises;
- manual-review time starts at complaint submission;
- reassignment does not reset the target;
- missing or invalid legacy timestamps produce unavailable, not guessed,
  deadlines;
- read-time approaching/overdue state may precede proactive alerts;
- proactive alerts and escalation require a future trusted scheduled worker;
- no scheduled worker is approved in R0.1;
- waiting-on-Customer pause semantics and resolution targets remain separate
  policy work;
- first Staff response should eventually be persisted explicitly rather than
  inferred indefinitely from message history.

## Analytics and evidence boundary

Admin may later receive aggregate, privacy-safe governance information:

- account counts;
- Staff counts by department;
- workload/backlog;
- status and priority distributions;
- manual-review volume;
- aging/overdue after definitions exist;
- data completeness;
- safe model/dataset governance summary.

Manager retains ticket-level low-confidence review, routing evidence,
confidence, overrides, frozen evaluation, V1/V2 evidence, equations, and
technical limitations. Admin must not receive raw complaint narratives or
Manager ticket-level technical evidence through the governance dashboard.

## Implementation boundary

R0.1 records approved contracts only. It does not claim implementation of:

- all-role Admin directory behavior;
- individual account detail;
- account lifecycle mutations;
- Customer History projection;
- notification persistence or APIs;
- assignment or claim enforcement;
- response-target calculation;
- escalation or workload alerts;
- browser notifications;
- email or SMS;
- redesigned navigation or shell;
- scheduled workers;
- Firestore rules or indexes.

## R2C10C-0 Customer detail and message-safety approval

R2C10C-0 approves documentation and future boundaries only; it does not claim
implementation of the three C slices. The current local detail, message, and
feedback routes use trusted API projections and ownership checks. Feedback is
currently limited to resolved/closed tickets with PII-redacted comments and
existing backend same-action idempotency. Current message reads are unbounded,
and the frontend does not yet retain one action ID across an uncertain retry.

Future slices are **R2C10C-1** message fingerprint idempotency, stable frontend
attempts, abort/session/ticket isolation, strict message parsing, and bounded
reads; **R2C10C-2** strict detail projection, removal of priority, safe
persistence errors, authenticated body validation, and strict nested parsing;
and **R2C10C-3** accessible English/Myanmar current-status and next-action
presentation.

The future detail projection excludes priority, all Customer/Staff/Manager or
actor UIDs, assignment fields, model/routing metadata, raw event names,
event/message/action/idempotency references, internal reasons, private notes,
and unknown or extra fields. Malformed owned persistence fails with safe `503`
and no partial response; missing and cross-Customer tickets remain the same
safe `404`.

Authorization order is Bearer header, token, profile, strict Customer role,
`active=true`, strict `accountState=active`, path/ownership, request-body
contract, then persistence. Unauthorized callers receive no schema detail and
trigger no ticket/message/feedback lookup. An authenticated raw-body boundary
may be required where framework validation otherwise runs first.

Only `messageText` and `actionId` are accepted. The normalized/redacted request
fingerprint binds the trusted Customer, owned ticket, action ID, message
request, and contract domain. Same-fingerprint retries return the original
safe result; conflicting action reuse returns `409 idempotency_conflict`.
Action IDs/fingerprints are backend-only. Uncertain outcomes reuse one
memory-only frontend action ID, while late responses are rejected after abort,
unmount, ticket change, sign-out, or Customer change.

The future V1 conversation read is capped at 100 participant-visible messages:
read at most 101 ordered documents (`createdAt ASC`, document ID `ASC`), return
at most 100, and fail closed with `503` for a 101st message or malformed data.
Unbounded streams are forbidden; pagination remains deferred and no new
composite index is approved by this slice.

Trusted ticket `status`, never the final timeline item, drives current-status
guidance. Timeline entries are historical public projections and may be
incomplete. Guidance for all six statuses must not promise deadlines,
assignment outcomes, reopening, resolution, or automatic responses.

Customer messages do not themselves transition status or create a new Customer
notification. Existing notification behavior is unchanged; no scheduler, SLA,
unread counter, proactive notification, reopening behavior, or deadline
mechanism is added.
