# Phase 3.7 — Reviewer instructions

## Your task

Read one privacy-reviewed complaint at a time and choose one V2 category. Use the main service or harm described, not a single keyword. Do not change the complaint or add private details. If the evidence is unclear or covers several unrelated services, choose `general_complaints` rather than guessing.

The eight choices are:

1. `account_branch_services`: account opening, closing, maintenance, cash-counter, or branch service.
2. `cards_atm_pos`: card operation, ATM cash/retained card, or merchant POS problems.
3. `mobile_internet_banking`: mobile-app or web-banking login, outage, or feature failure.
4. `transfers_payments_remittance`: an intended transfer, payment, bill payment, or remittance is delayed, failed, duplicated, or posted incorrectly.
5. `loans_credit`: loan application, repayment posting, interest, fees, schedule, or servicing.
6. `fraud_scam_unauthorized`: scam, phishing, account takeover, credential compromise, or activity the person says was not authorized.
7. `kyc_verification_restrictions`: identity/document verification, profile mismatch, compliance review, or a related restriction.
8. `general_complaints`: ambiguous, multi-topic, unsupported, service-conduct, or otherwise unclear cases.

Fraud takes precedence when authorization or safety is disputed. For an app transfer, choose transfers/payments when the money movement failed and mobile/internet banking when the channel itself failed. For blocked account access, choose KYC only when verification or documents caused the restriction; otherwise use account/branch services.

## Independent review

Reviewer A records a category without seeing Reviewer B's choice. Reviewer B separately reads the same approved record and records a category without seeing Reviewer A's choice. Reviewers must not negotiate before both labels are locked. Their role codes and review timestamps may be controlled outside aggregate evidence; personal names are not required in the dataset.

If both reviewers choose the same category, mark the record `agreed`. If they choose different categories, mark it `disagreed_unresolved` and isolate it from dataset locking. A third authorized adjudicator reviews the complaint, taxonomy guidance, and both labels, selects the final category, and records a short reason that explains the category boundary without copying complaint text. The state then becomes `adjudicated`. The adjudicator must not resolve uncertainty by majority guessing.

## Language labels

- `my`: the meaningful complaint content is Myanmar script/language.
- `en`: the meaningful complaint content is English.
- `mixed`: both Myanmar and English contribute meaningful content. An English product name inside an otherwise Myanmar complaint does not automatically make it mixed.

Apply the same eight category definitions in every language. Do not call machine- or human-translated text a real Myanmar customer complaint. Preserve `sourceType=translated`. Synthetic examples remain `synthetic`. Language quality uncertainty should be documented through the approved review process; do not silently rewrite meaning.

## Privacy rules

Never retain or copy names, phone numbers, email addresses, home/work addresses, account numbers, card numbers, transaction/reference IDs, NRC/passport numbers, credentials, PINs, passwords, tokens, exact identity-document details, or indirect identifying combinations. Stop and send the record back to the privacy reviewer if any appears. Do not put complaint text or private details in reviewer notes, disagreement reasons, filenames, record IDs, source references, screenshots, chat, or aggregate reports.

Translated and synthetic records are useful only when clearly labeled. They cannot be called real complaints because they were not direct, authorized customer reports in their displayed form. Mislabeling them would falsely inflate real-data evidence and hide translation or authoring limitations.
