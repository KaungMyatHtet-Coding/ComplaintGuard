# ComplaintGuard: Bilingual Financial Complaint Classification, Routing, and Evidence

## Abstract

ComplaintGuard is an academic financial-complaint workflow that combines a
large historical-data pipeline, TF-IDF text representation, Multinomial Naive
Bayes classification, Firebase operational storage, and role-based web
workflows. The project maps Consumer Financial Protection Bureau (CFPB)
Product/Issue categories to six transparent proxy departments and evaluates a
frozen classifier on a genuine 29,942-record held-out test partition. The model
achieved accuracy `0.827934`, macro-F1 `0.692345`, and weighted-F1 `0.837764`.
The macro-F1 target of `0.70` was not achieved and is not presented as achieved.

The application supports customer submission and tracking, department-scoped
staff processing, manager review, operational analytics, and aggregate model
evidence. English predictions may route automatically when they meet an
operational review threshold. Myanmar and mixed-language submissions use local
translation/classification evidence but always require manual review because
translation quality was not accepted. The supported operating mode is a local
Firebase-emulator demonstration, not a public production deployment.

## 1. Problem statement

Financial-service complaints must be understood, assigned, tracked, discussed,
and resolved. Manual routing can be inconsistent, while an English-only workflow
creates an additional barrier for Myanmar-speaking users. ComplaintGuard studies
whether a transparent lecture algorithm can provide useful routing evidence
without hiding uncertainty or placing the historical corpus in operational
cloud storage.

The system is not a bank, legal decision-maker, allegation verifier, or fully
automated resolution system. Its model labels are policy proxies and its output
supports human workflow rather than guaranteeing the correct organizational
owner.

## 2. Objectives and scope

The objectives were to:

1. profile and clean a large CFPB snapshot reproducibly;
2. map records deterministically to six stable proxy departments;
3. train and evaluate TF-IDF with Multinomial Naive Bayes without test leakage;
4. preserve English/Myanmar input while reporting language limitations;
5. store only synthetic operational demo data in Firestore;
6. enforce customer, staff, and manager boundaries in the UI, API, and rules;
7. expose real held-out evidence rather than invented dashboard percentages;
8. remain within a USD 0 academic/demo boundary.

Public deployment, production Firebase verification, SMS, real banking data,
admin operations, live historical-neighbor search, and enterprise controls are
outside the delivered system.

## 3. Users and proxy departments

Customers submit and follow their own complaints. Department staff work only on
tickets assigned to their profile's department. Managers review uncertain
routing and view operational/model analytics. The admin role can authenticate
but currently has only an empty administration shell; no admin endpoint or
management operation is implemented.

The stable proxy departments are:

- `transfer_payment` — Transfer & Payment
- `account_support` — Account Support
- `card_atm` — Card & ATM
- `fraud_security` — Fraud & Security
- `loan_credit` — Loan & Credit
- `general_support` — General Support

These labels are deterministic project policy, not CFPB labels or verified
institutional ground truth.

## 4. System architecture

ComplaintGuard separates offline historical analysis from live operations.
Offline scripts profile, clean, map, sample, split, train, and evaluate local
CSV/model data. Historical narratives, matrices, vocabulary, model files, and
similarity indexes remain ignored and outside Firestore.

The live system contains:

- a Next.js/TypeScript English/Myanmar frontend;
- Firebase Authentication for demo identities;
- Firestore for synthetic operational tickets, messages, events, and feedback;
- a trusted FastAPI service using Firebase Admin and the frozen classifier;
- build-time aggregate Day 18 evidence for manager analytics.

The verified environment uses isolated Auth and Firestore emulators. The API
loads a local ignored model and the browser calls the local API. No Vercel,
Hugging Face Space, production Firebase rules, or public URL is verified.

## 5. Role workflows

After email/password authentication, the frontend reads the authenticated
user's active Firestore profile and resolves one of four roles. A customer sends
only complaint text, locale, and an idempotency action ID with a Firebase token.
FastAPI verifies the token and active customer role, derives ownership, reduces
obvious sensitive patterns, and creates a durable submitted ticket.

Routing then detects language and invokes the frozen model. Accepted English
predictions become `triaged`, receive a department, and use
`routingSource: model`. Low-confidence English results and all Myanmar/mixed
results remain `submitted`, have no department, and use
`routingSource: manual_review`. A manager can assign a valid department without
rewriting the original prediction.

Department staff list only exact-department tickets. Staff can begin work,
await a customer, resume work, resolve with a summary, reply, and submit
reassignment/escalation requests. Messages, status changes, and events use
trusted transactions and idempotency actions. Customers can view their own
history, participate in messages, and submit one feedback record after
resolution. No email, push, or SMS notification is implemented.

## 6. Dataset and snapshot limitations

The source is the official CFPB Consumer Complaint Database archive captured on
20 July 2026. The immutable snapshot contained `17,034,951` rows, of which
`3,823,413` had a non-null complaint narrative. After required-field and
narrative usability checks, `3,822,576` records remained and all were mapped.

Counts describe that exact snapshot. The public database changes over time,
complaints are consumer-provided, allegation truth is not established, and
narrative availability creates selection bias. Historical text is PII-reduced,
not guaranteed anonymous, and is not published in the application or report.

## 7. Cleaning and department mapping

Cleaning uses bounded chunks, Unicode normalization, whitespace cleanup, URL
removal, conservative sensitive-pattern reduction, required Product/Issue/text
checks, date/provenance validation, and disk-backed duplicate handling. The
reconciled cleaner rejected `13,210,233` missing/unusable narratives, `2,135`
invalid Complaint IDs, and seven missing Issues under mutually exclusive
precedence.

Mapping uses Product and Issue only. Exact Product+Issue rules have first
precedence, Product fallbacks second, and General Support last. Narrative text
never creates its own label. The mapped distribution is strongly imbalanced:

| Department | Mapped records |
|---|---:|
| Transfer & Payment | 85,180 |
| Account Support | 198,831 |
| Card & ATM | 241,219 |
| Fraud & Security | 2,785,444 |
| Loan & Credit | 305,355 |
| General Support | 206,547 |

Fraud & Security represents about 72.87% of mapped records, largely reflecting
the retained CFPB taxonomy and mapping policy. It is a limitation, not evidence
that this department is intrinsically more important.

## 8. Algorithm and training methodology

A fixed seed (`20260727`) selected a bounded uniform reservoir of `200,000`
mapped records. Text was normalized with Unicode NFKC, case folding, and
whitespace collapse. Exact normalized narrative groups were assigned by SHA-256
to partitions so an exact duplicate group could not cross partitions.

The natural training partition contained `140,781` records. A training-only
30,000-per-class cap reduced the fitted set to `68,034`. Validation contained
`29,277`; test contained `29,942`. Validation and test were not balanced.

The final representation uses word one/two-gram TF-IDF, `min_df=3`,
`max_df=0.98`, sublinear term frequency, float32, and at most `100,000`
features. Multinomial Naive Bayes used `alpha=0.5`. Four predeclared candidates
and five thresholds were compared on validation only. The selected model was
then evaluated on test once. Day 18 loaded this same artifact, called transform
and prediction only, and reconciled the recomputed results with locked Day 9
metrics; it did not retrain or tune.

## 9. Leakage controls and reproducibility

- Labels use Product/Issue, never narrative words.
- TF-IDF fitting uses training records only.
- Training-only class capping does not alter validation/test distributions.
- SHA-256 group splitting prevents exact normalized duplicate crossover.
- Test data was excluded from feature fitting, candidate selection, and
  threshold selection.
- Day 18 results cannot be used to tune frozen model v1.

Near-duplicate detection was not implemented. Proxy-label noise and training
undersampling remain sources of uncertainty.

## 10. Held-out evaluation

| Metric | Result |
|---|---:|
| Accuracy | 0.827934 |
| Macro precision | 0.707515 |
| Macro recall | 0.736204 |
| Macro F1 | 0.692345 |
| Weighted precision | 0.866300 |
| Weighted recall | 0.827934 |
| Weighted F1 | 0.837764 |

Accuracy and weighted metrics are influenced by the large Fraud & Security
class. Macro-F1 gives every department equal weight and remains below the
project target.

| Department | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Transfer & Payment | 0.984000 | 0.436945 | 0.605166 | 563 |
| Account Support | 0.658333 | 0.827990 | 0.733479 | 1,622 |
| Card & ATM | 0.547253 | 0.762634 | 0.637236 | 1,959 |
| Fraud & Security | 0.966249 | 0.850847 | 0.904883 | 21,736 |
| Loan & Credit | 0.588560 | 0.896842 | 0.710711 | 2,375 |
| General Support | 0.500693 | 0.641968 | 0.562597 | 1,687 |

Transfer has high precision but low recall: 252 of 563 true Transfer records
were predicted as Account. The full matrix, with true rows and predicted
columns, is:

| True \ Predicted | Transfer | Account | Card | Fraud | Loan | General |
|---|---:|---:|---:|---:|---:|---:|
| Transfer | 246 | 252 | 35 | 12 | 17 | 1 |
| Account | 1 | 1,343 | 179 | 39 | 56 | 4 |
| Card | 0 | 140 | 1,494 | 198 | 102 | 25 |
| Fraud | 2 | 255 | 890 | 18,494 | 1,080 | 1,015 |
| Loan | 0 | 30 | 67 | 113 | 2,130 | 35 |
| General | 1 | 20 | 65 | 284 | 234 | 1,083 |

## 11. Confidence and historical similarity

Confidence is the maximum Naive Bayes class probability for one input. It is
uncalibrated and is not model accuracy or guaranteed correctness. At the later
operational threshold of `0.60`, `3,235` held-out predictions were below the
threshold (`1,249` correct and `1,986` incorrect); `26,707` were at/above it
(`23,541` correct and `3,166` incorrect). High confidence therefore still
contains errors.

The local historical-similarity foundation stores frozen TF-IDF vectors for
exactly `29,942` held-out records with `100,000` features and compares queries
using cosine similarity. It contains no narrative strings or raw Complaint IDs.
The 30.7 MB index is ignored, sensitive analytical material and is not loaded by
the application. No live neighbor or similarity percentage is displayed.

## 12. English and Myanmar behavior

Direct `/predict` accepts English only. The authenticated ticket workflow can
run local pinned Myanmar-to-English translation before the frozen classifier.
However, owner review found that the evaluated translation approaches did not
meet the accepted quality/routing thresholds. Therefore all Myanmar/mixed
ticket predictions are evidence for manager review only and never automatic
routing. This preserves access without claiming reliable bilingual semantics.

## 13. Firebase, API authorization, and privacy

The frontend controls visibility but is not the security boundary. FastAPI
verifies Firebase tokens and active roles, binds customer ownership, validates
staff department membership, and rechecks protected mutations transactionally.
Firestore rules separately permit customer-owned reads, exact-department staff
reads, and manager operational reads while denying direct protected writes.

Emulator tests cover these local boundaries. They do not prove production
deployment or enterprise security. Deterministic redaction reduces obvious
password/PIN/account/card/long-number patterns but cannot guarantee
anonymization. Complaint text remains sensitive. No approved retention/deletion
workflow, rate limiting, monitoring, disaster recovery, penetration test, or
independent audit exists.

The Day 18/19 evaluation JSON is aggregate non-sensitive build-time evidence.
It does not contain operational customer data. Manager-only UI visibility must
not be confused with backend protection of that bundled aggregate.

## 14. Testing methodology and results

Testing is layered across synthetic unit tests, API/service tests, Firestore
rules, real emulator adapters, frontend component tests, artifact reconciliation,
and Playwright browser E2E. The E2E uses generated local credentials and
synthetic complaints to exercise high/low routing, role isolation, staff/customer
messages, and manager override.

Day 20 final command results are recorded only in
`docs/final_test_report.md`. Historical milestone counts remain provenance, not
a substitute for current verification. Production deployment was not tested.

## 15. Supported operating mode

The final supported mode is a local emulator-based academic demonstration with
four terminals: Firebase emulators, seed, FastAPI, and Next.js. A fresh clone
also requires the ignored frozen model with its documented hash. The repository
does not contain an ML deployment manifest or public URL, so it must not be
described as fully or hybrid deployed.

## 16. Limitations and future work

Major limitations include proxy-label validity, strong imbalance, bounded
sampling, training undersampling, near-duplicates, uncalibrated confidence,
unaccepted Myanmar translation quality, local-only model/index artifacts,
sensitive operational text, absent retention controls, empty admin shell, and
unverified public deployment.

Evidence-based future work could include institution-reviewed labels, calibrated
confidence, stronger bilingual evaluation, near-duplicate analysis, an approved
retention/deletion policy, safe artifact packaging, production authorization
verification, rate limiting/monitoring, and explicitly designed admin operations.
Any new model must use a new version and untouched evaluation protocol rather
than tuning model v1 on its held-out results.

## 17. Conclusion

ComplaintGuard demonstrates a defensible connection between large-data
processing, a transparent lecture algorithm, NoSQL operational workflows, and
role-based web interaction. Its strongest result is not a perfect score but a
reproducible evidence chain: exact snapshot counts, deterministic proxy mapping,
leakage-controlled partitions, real below-target held-out metrics, explicit
manual review, and local authorization tests. Its deployment, bilingual quality,
privacy, and administrative limitations are deliberately visible rather than
replaced by unsupported claims.

## References

1. Consumer Financial Protection Bureau, *Consumer Complaint Database*, official
   archive endpoint recorded in `docs/dataset_profile.md`:
   `https://files.consumerfinance.gov/ccdb/complaints.csv.zip`. Snapshot identity,
   retrieval date, size and SHA-256 are recorded locally because the archive changes.
2. ComplaintGuard, `data/cfpb_snapshot_profile.json`, aggregate snapshot profile.
3. ComplaintGuard, `data/processed/cfpb_training_v1_manifest.json`, deterministic
   mapping and dataset manifest.
4. ComplaintGuard, `data/processed/cfpb_model_v1_metrics.json`, frozen model
   selection and locked evaluation evidence.
5. ComplaintGuard, `evaluation/day18/model_evaluation_v1.json`, authoritative
   held-out evaluation artifact.
6. ComplaintGuard, `docs/myanmar_pipeline.md`, pinned translation evaluation and
   owner review.

Formal bibliographic citations for TF-IDF, Multinomial Naive Bayes,
scikit-learn, Firebase, and FastAPI must be verified against authoritative
publisher/project pages before external submission; no unverified author, year,
edition, or URL is invented here.
