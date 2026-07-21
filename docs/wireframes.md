# Day 4 Low-Fidelity Wireframes

These implementation-neutral Markdown wireframes were owner-approved on 21 July 2026. They do not represent implemented frontend screens.

## Shared behavior

- Header: product name, English/Myanmar selector, current role, and sign out.
- Every protected view verifies authorization independently of navigation visibility.
- Loading states use a stable page frame and progress message; empty states explain the next useful action; errors preserve safe input where possible and offer retry.
- Mobile layouts stack panels and keep the primary action visible. Desktop layouts may use a list/detail split. Tables must become labeled cards on narrow screens.
- Inputs warn against passwords, PINs, full account/card numbers, and other sensitive information.
- English is the fallback locale when a Myanmar key is unavailable.

## Customer experience

### Submit complaint

Purpose: submit an English or Myanmar operational complaint and obtain a ticket.

```text
+--------------------------------------------------+
| ComplaintGuard             [English | Myanmar]  |
+--------------------------------------------------+
| Submit a complaint                              |
| Do not enter passwords, PINs, or full numbers.  |
|                                                  |
| Complaint                                        |
| [ multiline text area                         ] |
| [ character count ]                              |
|                                      [Submit]    |
+--------------------------------------------------+
```

Primary information: privacy warning, selected input language, complaint text, validation feedback. Actions: submit or return to ticket history. Boundary: creates a ticket only for the authenticated customer through the trusted redacting backend; routing fields are not editable.

States: loading during validation/routing; empty text disables submission; validation errors remain inline; service failure shows retry without claiming ticket creation; success displays ticket ID, department or manual-review route, and status.

### My tickets

Purpose: list only the authenticated customer's tickets.

Primary information: ticket ID, created date, department, status, last update. Actions: open ticket, submit another complaint. Empty state explains that no complaints have been submitted. Error state never falls back to another customer's data.

### Ticket detail and conversation

Purpose: view one owned ticket and exchange participant messages.

Primary information: ticket ID, status, current department, timeline safe for customer display, messages. Actions: send a redacted message and request reopen; customer cannot directly change status, priority, assignment, routing, or prediction.

Responsive layout: metadata precedes conversation on mobile; desktop may show metadata beside the message thread.

## Staff experience

### Department queue

Purpose: show tickets only for the active staff member's assigned department.

```text
+--------------------------------------------------+
| Department queue: [department name]             |
| [Status filter] [Priority filter] [Search ID]   |
+--------------------------------------------------+
| Ticket | Status | Priority | Updated | Assignee |
| ...                                              |
+--------------------------------------------------+
```

Primary information: ticket ID, status, priority, age/updated time, assignment. Actions: filter, open a ticket, request claim/escalation as permitted. Boundary: no cross-department results; changing a client filter must not broaden server authorization.

States: skeleton rows while loading; clear no-ticket state; permission error distinct from network error; pagination/retry on large queues.

### Staff ticket workspace

Purpose: process a permitted department ticket.

Primary information: operational complaint text, participant messages, status, priority, assignment, audit timeline visible to staff. Actions: reply, begin work, await customer, resolve with a safe summary, or request escalation. Staff cannot directly reroute departments, change priority, reopen, rewrite predictions, or mutate audit events.

Responsive layout: actions collapse into a clearly labeled menu on mobile; destructive or terminal transitions require confirmation.

## Manager experience

### Operational overview

Purpose: view derived operational workload without treating summaries as authoritative data.

Primary information: total/open/resolved counts, department workload, status/department distribution, trend, average resolution time, and high-priority unresolved tickets. Actions: filter by operational date/department and open a ticket. Loading and error states label summaries as unavailable rather than displaying stale values as current.

### Manager queue

Purpose: inspect all operational tickets and perform management actions.

Primary information: department, staff assignment, status, priority, escalation, prediction and current routing. Actions: assign/reassign, reroute, set priority, escalate, open ticket. Empty filters provide a reset action.

### Manager ticket workspace

Purpose: supervise and correct workflow without rewriting the original model result.

Primary information: ticket details, original prediction/confidence, current routing, assignment, messages, immutable audit events. Actions: assign/reassign, override routing, set priority, escalate, resolve, reopen, close, and reply through trusted endpoints. Each controlled action records an audit event.

Boundary: manager cannot change user roles or department membership. Administrative identity management is outside these Day 4 manager wireframes.

## Approval checklist

- Customer views disclose only owned tickets and permitted messages.
- Staff views are bounded by assigned department.
- Manager operational actions match the access matrix and lifecycle.
- No screen exposes translated/normalized text, historical narratives, secrets, or unnecessary PII.
- Loading, empty, validation, permission, network, and service-error states are represented.
- Mobile and desktop behavior is plausible without prescribing a frontend framework implementation.
