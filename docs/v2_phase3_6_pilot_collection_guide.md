# Phase 3.6 — Pilot collection and human annotation guide

This package prepares a human-run pilot. It contains no real complaint corpus, does not count templates as evidence, does not train or evaluate a model, and keeps V2 automatic routing disabled.

## Templates and field dictionary

Working templates live in Git-ignored locations:

- `data/v2/intake/pilot_intake_template.jsonl` and `.csv`: duplicate the explicitly synthetic example row, assign a new non-identifying `recordId`, replace the example text only with authorized privacy-reviewed material, and complete its provenance.
- `data/v2/reviewer-a/reviewer_a_template.csv`: Reviewer A independently fills `reviewerACategory` and review time.
- `data/v2/reviewer-b/reviewer_b_template.csv`: Reviewer B independently fills `reviewerBCategory` and review time without seeing A's choice.
- `data/v2/annotations/adjudication_template.csv`: merge the two labels, set the disagreement state, and complete adjudication where needed.

The example rows are synthetic instructions, not customer records or dataset evidence.

| Field | Simple meaning | Privacy rule |
|---|---|---|
| `recordId` | A locally generated non-identifying record key. | Never use a customer ID, transaction ID, account number, name, or contact detail. |
| `complaintText` | The authorized, privacy-reviewed complaint description. | Never retain names, phones, email, account/card/transaction numbers, address, NRC/passport, credentials, or indirect identifying details. |
| `language` | `my`, `en`, or `mixed`. | Do not encode identity in this field. |
| `proposedCategoryId` | Collector's preliminary choice among the eight V2 IDs. | It is not the final human label and must not contain free text. |
| `sourceType` | `real_public`, `translated`, or `synthetic`. | Translated/synthetic never means real Myanmar customer data. |
| `sourceName` | Approved dataset or organization-level source name. | Never put a customer or reviewer name here. |
| `sourceReference` | Non-personal license/consent approval reference. | Never use a complaint, customer, account, or transaction reference. |
| `collectionDate` | ISO date `YYYY-MM-DD`. | Date only; no identity details. |
| `licenseOrConsentStatus` | One approved status from the intake schema. | `pending` or assumed permission is rejected. |
| `privacyReviewStatus` | Must be `passed` after per-record human review. | Never mark passed merely because regex redaction ran. |
| `metadata` | Annotator-independent origin language, translation method, and non-identifying source family. | No reviewer/customer identity or free-form private notes. |
| `taxonomyVersion` | Must be `v2`. | Never repurpose a V1 label. |
| Reviewer labels | Independent `reviewerACategory` and `reviewerBCategory`. | Category IDs only; no reviewer names. |
| `disagreementState` | `not_reviewed`, `agreed`, `disagreed_unresolved`, or `adjudicated`. | Do not hide unresolved cases. |
| Final adjudicated label | The adjudicator's V2 category plus concise decision reason and time. | Reason explains taxonomy evidence without copying complaint text or identity. |

## Eight-category collection and decision guide

Every example below is synthetic and is not a customer record.

### `account_branch_services` — Account & Branch Services / အကောင့်နှင့် ဘဏ်ခွဲဝန်ဆောင်မှုများ

General account opening, closing, access, cash-counter, maintenance, or branch-service issues belong here. App defects, card/ATM faults, and identity-verification restrictions do not. It is commonly confused with KYC when access is blocked: choose KYC when verification or documents caused the restriction; otherwise choose account/branch service. Synthetic English: “The branch could not update my account details.” Synthetic Myanmar: “ဘဏ်ခွဲမှာ အကောင့်အချက်အလက် ပြင်လို့မရပါ။” Annotate the service causing the complaint, not merely the place where it happened.

### `cards_atm_pos` — Cards, ATM & POS / ကတ်၊ ATM နှင့် POS

Card activation/delivery, ATM cash or retained-card issues, and POS declines belong here. Customer-denied transactions, app login, and account-only service do not. It is commonly confused with fraud: if the person says the activity was not authorized or is suspicious, choose fraud. Synthetic English: “The ATM kept my card.” Synthetic Myanmar: “ATM က ကျွန်တော့်ကတ်ကို သိမ်းထားပါတယ်။” Choose this category for channel operation, not unauthorized activity.

### `mobile_internet_banking` — Mobile & Internet Banking / မိုဘိုင်းနှင့် အင်တာနက်ဘဏ်လုပ်ငန်း

App/web login, outages, and digital-feature defects belong here. Transfer outcomes, KYC blocks, and account takeover do not. It is commonly confused with transfer/payment when a transfer was attempted in the app: choose transfer when the complaint is about money movement; choose mobile banking when the channel itself fails. Synthetic English: “The banking app closes after login.” Synthetic Myanmar: “ဘဏ် app က ဝင်ပြီးတာနဲ့ ပိတ်သွားပါတယ်။” Focus on the primary failed service.

### `transfers_payments_remittance` — Transfers, Payments & Remittance / ငွေလွှဲ၊ ငွေပေးချေမှုနှင့် ပြည်တွင်း/ပြည်ပငွေပို့ခြင်း

Intended transfers, payments, and remittances that are pending, failed, duplicated, or misposted belong here. Unauthorized activity, ATM cash faults, and loan-policy questions do not. It is commonly confused with fraud and mobile banking: denied activity always goes to fraud; app-only defects go to mobile banking. Synthetic English: “My intended transfer is still pending.” Synthetic Myanmar: “ကျွန်တော် လွှဲထားတဲ့ငွေ မရောက်သေးပါ။” Confirm that the sender intended the transaction.

### `loans_credit` — Loans & Credit / ချေးငွေနှင့် အကြွေးဝန်ဆောင်မှု

Loan applications, repayment posting, interest, fees, schedules, and servicing belong here. Ordinary account fees, unauthorized debits, and identity verification do not. It is commonly confused with transfers when a repayment is missing: choose loans when the issue is the loan account or repayment application. Synthetic English: “My loan payment was not posted.” Synthetic Myanmar: “ချေးငွေပြန်ဆပ်ထားတာ စာရင်းမဝင်သေးပါ။” Label the product being serviced.

### `fraud_scam_unauthorized` — Fraud, Scam & Unauthorized Transactions / လိမ်လည်မှုနှင့် ခွင့်ပြုချက်မရှိသော ငွေလွှဲမှုများ

Scams, phishing, account takeover, credential compromise, or activity the person denies authorizing belong here. Known delayed transfers, ordinary declines, and fee disputes without fraud do not. It is commonly confused with every transaction channel; fraud takes precedence whenever authorization or safety is disputed. Synthetic English: “I did not authorize this debit.” Synthetic Myanmar: “ဒီငွေဖြတ်မှုကို ကျွန်တော် ခွင့်မပြုခဲ့ပါ။” Do not request or copy credentials or financial identifiers while annotating.

### `kyc_verification_restrictions` — KYC, Verification & Account Restrictions / KYC၊ အထောက်အထားစိစစ်မှုနှင့် အကောင့်ကန့်သတ်ချက်များ

Document/identity verification, profile mismatch, compliance review, and resulting restrictions belong here. Technical outages, branch conduct alone, and account takeover do not. It is commonly confused with account support when access is blocked: choose KYC only when verification/restriction is the cause. Synthetic English: “My account remains restricted after document review.” Synthetic Myanmar: “စာရွက်စာတမ်း စစ်ပြီးပေမယ့် အကောင့်ကန့်သတ်ထားဆဲပါ။” Never copy identity-document values.

### `general_complaints` — Customer Complaint Unit / ဖောက်သည်တိုင်ကြားမှုဌာန

Ambiguous, cross-category, unsupported, service-conduct, or otherwise unclassifiable cases belong here. A single clearly supported category does not. It is commonly confused with all categories when evidence is incomplete; use it instead of guessing, and send multi-topic uncertainty to adjudication. Synthetic English: “I need help deciding which team handles this complaint.” Synthetic Myanmar: “ဒီတိုင်ကြားချက်ကို ဘယ်ဌာနကိုပို့ရမလဲ မရှင်းပါ။” Record why evidence was insufficient without copying complaint text.

## Pilot proposal — pending human approval

The planning target is 50 accepted records in each category and 400 total. It also requires meaningful Myanmar coverage, separate English and mixed-language reporting, two independent reviews per record, zero unresolved disagreements before locking, and zero duplicate-group leakage across partitions. “Meaningful Myanmar coverage” requires a human-approved numeric definition. These are pilot planning values, not the existing production-readiness thresholds and not evidence of model readiness.

## Source register

`data/mapping/v2_source_approval_register_schema.json` defines an aggregate-only register. One row per source records organization/role-level source ownership, collection method, license/consent and privacy decisions, permitted purpose, retention decision, reviewer approval state, accepted aggregate count, rejection count, and approval date. It prohibits complaint text, record IDs, customer identities, and reviewer identities.

## Manual workflow

1. Collector obtains explicit authority and prepares local intake records.
2. Privacy reviewer checks every record and removes direct and indirect identifiers.
3. The local intake command rejects invalid records, redacts supported patterns, and creates ignored prepared data plus aggregate evidence.
4. Reviewer A labels independently.
5. Reviewer B labels independently without seeing A's choice.
6. Different labels are isolated as `disagreed_unresolved`.
7. A third adjudicator chooses the final category and records a non-sensitive reason.
8. Agreement metrics are calculated; unresolved or invalid annotations block readiness.
9. Exact and near-duplicate groups are formed before deterministic partitioning and remain together.
10. Only after all human approvals are recorded are the dataset hash and aggregate manifest locked. No model work follows without separate authorization.

## Pilot validation command

```powershell
.\.venv\Scripts\python.exe scripts/prepare_v2_dataset.py `
  --input data/v2/intake/pilot.jsonl `
  --prepared-output data/v2/prepared/pilot.v2.jsonl `
  --annotations data/v2/annotations/pilot_adjudicated.csv `
  --manifest data/processed/pilot_v2_aggregate_manifest.json `
  --readiness-report data/processed/pilot_v2_readiness_report.json
```

The prepared output is refused unless Git reports its destination as ignored. The command prints no complaint records and writes only aggregate manifest/readiness files outside ignored paths. A blocked report is the expected result until approved data, completed reviews, approved thresholds, and a locked hash exist.

## Rollback and stopping point

Remove only the Phase 3.6 guide, source-register schema, focused tests, and Phase 3.6 CLI additions. Leave ignored human working files in place unless their owner separately chooses to remove them. V1, Firestore, authentication, Manager/Staff workflows, runtime, models, and routing need no rollback because this phase does not touch them. Stop here; Phase 4 is not authorized.
