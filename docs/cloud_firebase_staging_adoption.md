# Cloud Firebase Staging Adoption Checkpoint

Status: Phase 2D documentation and technical-verification preparation. Cloud
staging is adopted as an owner-approved project boundary, but the application
is not connected and the technical migration remains blocked.

## Approved audit record

- Dedicated staging project: `complaintguard`.
- Owner adoption approval: granted.
- Billing posture: Spark/no-cost plan; no billing account is linked.
- Firestore: `(default)` database in `asia-southeast1`.
- Firebase web app: registered.
- Authorized domains: only the three Firebase defaults.
- Auth providers: Email/Password and Google are enabled in Console. Google
  sign-in is not adopted by the application.
- Owner-controlled identities: three private-email test identities exist, with
  matching `users/{uid}` profiles. They represent one customer, one
  `general_support` staff member, and one manager; all profiles are active.
  Email addresses, UIDs, and credentials are intentionally not recorded here.
- No Admin identity exists.
- Only the `users` collection exists. There are no tickets, messages,
  feedback, or complaint records.
- Existing Cloud data is owner-controlled staging identity data, not a
  production dataset.
- No composite Firestore indexes exist.
- App Check is not registered or enforced.
- Managed backup/PITR is unavailable on Spark.
- Usage is minimal and one human owner has project access.
- No Cloud application connection has occurred.

The three identities are synthetic demo identities controlled by the owner.
Future Cloud complaint records must also be synthetic-only, privacy-reviewed,
and limited to the operational MVP. Never import the historical CFPB dataset,
raw complaint narratives, real financial/customer information, passwords,
PINs, full account/card numbers, tokens, or credentials into staging.

## Phase status and boundary

Phase 2A, Phase 2B, and Phase 2C are complete. The private Console audit and
owner adoption decision are complete as Phase 2D entry evidence. Overall Phase
2 remains in progress because no application connection, Cloud rules/index
deployment, or Cloud workflow verification has occurred.

Project adoption is not application connection. The repository must continue to
enforce `cloud_staging_not_adopted`; no frontend, FastAPI, seed, or test path
may use the Cloud project yet. The verified application remains the local
Firebase Emulator prototype.

## Technical-verification preparation

### Query-to-index matrix

This matrix covers Firestore SDK query/read sites in application adapters,
frontend auth/profile loading, and Firebase fixture verification. Transaction
reads and document reads are listed where they affect the later verification
scope. Fixture queries are local/emulator-only and are not Cloud application
workflow evidence.

| Query site | Path and operation | Predicates / ordering | Composite index? | Reason |
|---|---|---|---|---|
| Customer ticket history | `tickets`; `where customerId == uid`; `order_by createdAt DESC` | Equality + descending order | Yes | Compound customer history query. |
| Customer ticket detail | `tickets/{ticketId}` document read | None | No | Direct document lookup. |
| Customer messages | `tickets/{ticketId}/messages`; `order_by createdAt ASC` | Single-field order | No | Single-field/subcollection ordering. |
| Staff department queue | `tickets`; `where departmentId == departmentId` | One equality predicate | No | Status, priority, and date filters are applied after the scoped read. |
| Staff ticket detail | `tickets/{ticketId}` document read | None | No | Direct document lookup. |
| Staff messages/events | `tickets/{ticketId}/messages` and `/events`; `order_by createdAt ASC` | Single-field order | No | Single-field/subcollection ordering. |
| Manager all tickets | `tickets`; stream | None | No | Unfiltered collection read. |
| Manager low-confidence list | `tickets`; stream, then in-memory confidence/manual-review filter | None in Firestore | No | Filtering is intentionally performed after the read. |
| Auth/profile loading | `users/{uid}` document read | None | No | Direct profile lookup. |
| Ticket transactions | Ticket, action, event, message, feedback document reads | None | No | Transaction document reads do not create composite-index requirements. |
| Fixture inspection | `users`, `tickets`, `feedback`, `fixtureMeta`; collection-group `messages`, `events`, `actions` | Unfiltered reads | No | Emulator fixture contract only. |
| Fixture subcollections | `tickets/{ticketId}/{messages,events,actions}`; collection reads | None | No | Emulator fixture contract only. |

The repository has no implemented Firestore `limit`, cursor, listener, or
additional compound query. Manager and staff reads may need redesign before a
larger Cloud dataset; adding filters or pagination must trigger a fresh index
review rather than relying on this matrix.

### Local `firestore.indexes.json` preparation

The local manifest is now prepared and referenced by `firebase.json`. It is
not Cloud evidence: it has not been deployed, and the customer ticket query
has not been run against Cloud. The local manifest must remain subject to
owner review before any future deployment.

```json
{
  "indexes": [
    {
      "collectionGroup": "tickets",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "customerId", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "DESCENDING" }
      ]
    }
  ],
  "fieldOverrides": []
}
```

Before deployment, run the customer-history query only against a controlled
synthetic Cloud fixture after separate owner approval, confirm the SDK's index
requirement, review quota and cost exposure, and retain evidence that the
local manifest and deployed index definition match. No Cloud query has been
tested in this slice.

### Rules comparison and later method

The private audit reports that the deployed rules structurally match the
repository's deny-by-default rules in `firebase/firestore.rules`: authenticated
user self-profile reads, department reads, customer ownership reads, assigned
staff reads, manager reads, deliberate dashboard reads, and denied client
writes/fallback access. On that logical evidence, they appear semantically
identical for the reported rule paths and conditions.

This is not byte-for-byte equality evidence. The deployed Console
representation was not independently retrieved or normalized in the
repository, and no Cloud operation is authorized in this checkpoint. Later,
with owner approval, obtain the deployed source through a read-only rules
inspection path, normalize only documented line-ending/whitespace differences,
compare it with the repository file, and retain hashes plus the exact
normalization procedure outside secrets. A separate controlled emulator compile
and rule-test run must still prove behavior; neither comparison proves the
other.

### Minimum read-only verification credential strategy

Do not create or download credentials now. Later verification should use one
owner-approved, short-lived OAuth/access credential for a dedicated temporary
read-only principal with only the Firebase rules and Firestore metadata/read
permissions needed to inspect project identity, database location, deployed
rules, and indexes. Keep it in the operator's private credential store or
process memory, never in Git, `.env` files, screenshots, logs, or this
repository. Confirm the exact narrow IAM role set with the owner immediately
before use; do not use an owner credential for routine verification and do not
grant write, Auth-admin, billing, service-account, or deployment permissions.

## Remaining gates before removing `cloud_staging_not_adopted`

The guard may be removed only after all of the following are documented with
controlled evidence and separately approved by the owner:

1. Environment contracts target only `complaintguard` for Cloud and retain a
   distinct emulator project/hosts; no secret or credential is committed.
2. Cloud Auth and web configuration are connected through a reviewed,
   privately stored setup; Google sign-in is either explicitly adopted and
   tested or remains disabled in application behavior.
3. Deployed rules are normalized/byte-compared to the reviewed repository
   rules, then tested for customer ownership, staff department isolation,
   manager access, denied writes, and invalid/disabled identities.
4. The required customer-history index is reviewed, approved, deployed only if
   needed, and recorded with quota/cost review. No unreviewed composite index
   is added.
5. Cloud test data is synthetic-only, limited to an approved fixture, and the
   existing owner-controlled identities are preserved. No Admin identity is
   assumed until separately approved and provisioned through a trusted path.
6. App Check, Spark backup limitations, retention/deletion, logging, rollback,
   and quota monitoring have explicit accepted limitations or approved plans.
7. A controlled read-only verification has passed, followed by separately
   approved, narrowly scoped application connection tests. No actual Cloud
   complaint workflow is currently tested; a later synthetic end-to-end test
   must cover submission, routing/manual review, ownership, department
   isolation, messages, transitions, feedback, and rollback/cleanup.
8. The local emulator remains the tested fallback, and the guard-removal diff
   itself has owner review, security review, and full repository verification.

Until every gate passes, Cloud staging remains technically blocked and the
local emulator is the only verified operating mode.

## Rollback and safe operations

The rollback point is the current emulator-only behavior and the approved
baseline. Do not point local seed/reset/export/import scripts at Cloud. Do not
run Firebase CLI, deploy rules or indexes, change providers/domains, create
identities/documents, seed complaint data, enable App Check, attach billing, or
use credentials as part of this checkpoint. If a later approved test fails,
disconnect the application, preserve the Cloud identity-only baseline, and
return runtime configuration to the emulator without deleting owner data.
