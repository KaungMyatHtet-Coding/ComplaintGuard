# Phase 3.7 — Dataset approval form

Use this form only after reviewing the Phase 3.5 and Phase 3.6 documentation and aggregate evidence. Select exactly one decision for every item: **Approve**, **Reject**, or **Pending**. A blank answer means Pending. Approval of this pack does not enable routing, deploy anything, or establish production adequacy.

Project: ComplaintGuard V2
Taxonomy version: `v2`
Dataset/manifest reference: ____________________
Review date: ____________________
Teacher/project-supervisor role reference (no private identifier required): ____________________

## Taxonomy approval

| Decision item | Approve | Reject | Pending | Conditions or aggregate evidence reference |
|---|:---:|:---:|:---:|---|
| Eight IDs are acceptable for the pilot: `account_branch_services`, `cards_atm_pos`, `mobile_internet_banking`, `transfers_payments_remittance`, `loans_credit`, `fraud_scam_unauthorized`, `kyc_verification_restrictions`, `general_complaints`. | ☐ | ☐ | ☐ | |
| English and Myanmar category names are acceptable. | ☐ | ☐ | ☐ | |
| Category definitions, inclusion/exclusion rules, examples, and ambiguity guidance are acceptable. | ☐ | ☐ | ☐ | |

## Pilot size and language approval

The values below are **pilot proposals only**. Fifty records per category and 400 total are not claims of production adequacy, statistical sufficiency, or model readiness.

| Decision item | Approve | Reject | Pending | Conditions or aggregate evidence reference |
|---|:---:|:---:|:---:|---|
| Proposed pilot target: 50 accepted records per category. | ☐ | ☐ | ☐ | |
| Proposed pilot total: 400 accepted records. | ☐ | ☐ | ☐ | |
| Proposed Myanmar-language coverage is meaningful for the pilot; state the approved numeric definition: __________. | ☐ | ☐ | ☐ | |
| English records are reported separately with an approved target: __________. | ☐ | ☐ | ☐ | |
| Mixed-language records are reported separately with an approved target: __________. | ☐ | ☐ | ☐ | |

## Source, privacy, purpose, and retention

| Decision item | Approve | Reject | Pending | Conditions or aggregate evidence reference |
|---|:---:|:---:|:---:|---|
| Every source and collection method is lawful, ethical, documented, and approved. | ☐ | ☐ | ☐ | |
| License or consent evidence permits the stated pilot purpose. | ☐ | ☐ | ☐ | |
| Per-record privacy review and redaction method are adequate. | ☐ | ☐ | ☐ | |
| Permitted dataset purpose is explicitly limited to: ____________________. | ☐ | ☐ | ☐ | |
| Retention period, access boundary, withdrawal handling where applicable, and deletion method are approved: ____________________. | ☐ | ☐ | ☐ | |

## Human review and leakage

| Decision item | Approve | Reject | Pending | Conditions or aggregate evidence reference |
|---|:---:|:---:|:---:|---|
| Reviewer A role and independence are approved. | ☐ | ☐ | ☐ | |
| Reviewer B role and independence are approved. | ☐ | ☐ | ☐ | |
| Third-adjudicator role and decision process are approved. | ☐ | ☐ | ☐ | |
| Aggregate evidence shows zero unresolved disagreements. | ☐ | ☐ | ☐ | |
| Aggregate evidence shows zero duplicate groups crossing partitions. | ☐ | ☐ | ☐ | |

## Phase boundary decision

Phase 4 model experimentation may begin only if the supervisor explicitly approves it after every prerequisite is satisfied. Approval here authorizes experimentation only; it does not authorize deployment, automatic routing, production use, paid services, or changing the frozen V1 classifier.

- Phase 4 model experimentation: ☐ Approve ☐ Reject ☐ Pending
- `phase4Authorization` remains `false` unless the final recorded decision is Approve and all stated conditions are satisfied.
- V2 automatic routing remains disabled regardless of this decision.

Overall dataset approval: ☐ Approve ☐ Reject ☐ Pending
Required follow-up or rejection reasons: ____________________________________
Role-level approval recorded by: `teacher_or_project_supervisor` / other approved role: __________
Approval record location/hash: ____________________________________
