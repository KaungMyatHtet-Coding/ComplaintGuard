# ComplaintGuard MVP Project Scope

## Final problem statement

Financial-service complaints are slow and error-prone to route manually, and an English-only process creates an additional barrier for Myanmar-speaking customers. ComplaintGuard will provide a small bilingual web workflow that accepts an English or Myanmar complaint, applies privacy-aware preprocessing, classifies its department using TF-IDF and Multinomial Naive Bayes, and creates a Firestore ticket that the customer and authorized staff can follow through resolution.

The system is an academic/demo operational tool, not a real banking platform. It uses historical CFPB CSV/Parquet data only for offline analysis and model training. Cloud Firestore stores only live or synthetic demo application data.

## Users

| User | Essential need |
|---|---|
| Customer | Submit a complaint in English or Myanmar and track its ticket, replies, and status |
| Department staff | See only tickets assigned to their department, reply, update status, and reassign or escalate when necessary |
| Manager/Admin | See all demo complaints and a small set of workload and trend summaries; manage approved mappings/roles where required |

One developer is active. That developer owns planning, data/ML, frontend, Firestore, testing, deployment, and documentation sequentially. The five-person official team remains an administrative fact but is not a delivery dependency.

## Departments and stable IDs

| ID | Display name | Typical scope |
|---|---|---|
| `transfer_payment` | Transfer & Payment | Missing transfers and payment failures |
| `account_support` | Account & KYC Support | Login, account lock, and identity verification |
| `card_atm` | Card & ATM Support | Card payments, ATM withdrawals, and lost cards |
| `fraud_security` | Fraud & Security | Unauthorized transactions, scams, and account takeover |
| `loan_credit` | Loan & Credit | Repayment, interest, and loan servicing |
| `general_support` | General Support | Ambiguous or low-confidence complaints and manual review |

## Must-have MVP features

- English/Myanmar language switch and complaint input.
- Prepared demo login for Customer, Department Staff, and Manager/Admin roles using Firebase Authentication.
- Customer complaint submission with length validation and a warning against sensitive data.
- English/Myanmar preprocessing; Myanmar input follows an open-source, zero-cost translation path before English classification.
- Department prediction and confidence from TF-IDF plus Multinomial Naive Bayes.
- A validation-selected confidence threshold that routes uncertain complaints to `general_support`/manual review.
- Firestore Spark storage for operational demo tickets, messages, and lifecycle events.
- Customer ticket ID, complaint history, status tracking, and customer/staff message thread.
- Staff queue restricted to the assigned department, with reply, status update, reassign, and escalate actions.
- Small manager dashboard covering total/open/resolved counts, department workload, category/status distribution, trends, average resolution time, and a high-priority unresolved list. The UI may combine these into a minimal number of views.
- Model evaluation reporting accuracy, precision, recall, macro-F1, and a confusion matrix; the 0.70 macro-F1 value is a target, not a promised result.
- Firestore security rules and emulator evidence for cross-user and cross-department access restrictions.
- Free public demo deployment, QR code, and synthetic demo accounts, subject to the documented limits of Vercel Hobby and Hugging Face Spaces CPU.

## Historical data and model boundary

- Use the historical CFPB Consumer Complaint Database in CSV or Parquet form for cleaning, EDA, mapping, and training.
- Use `Consumer complaint narrative` as model text and derive stable department labels deterministically from `Product` and `Issue`.
- Do not upload the complete historical dataset to Firestore or commit it to Git.
- Store only a small, reproducible, privacy-reviewed sample if it is later needed for demonstration.
- The required classifier is TF-IDF with Multinomial Naive Bayes. Optional algorithms may not displace or delay it.

## Out of scope

- Real banking transactions, balances, account servicing, or payment gateways.
- Real customer, account, card, PIN, password, or identity data.
- Production use by a financial institution or claims of production-grade translation/classification.
- Full company operations, native mobile applications, or a generative-AI chatbot.
- SMS/phone authentication, email notifications, file attachments, dark mode, customizable SLA rules, and CSV/PDF exports.
- Apriori or other advanced/secondary data-mining work before the complete MVP is stable.
- Importing the full CFPB dataset into Firestore.
- Paid APIs, paid hosting, paid GPUs, Firebase billing/Blaze features, or a custom domain.

## Definition of done

The MVP is done only when all of the following have reproducible evidence:

1. A customer can use a prepared demo account to submit both English and Myanmar examples, receive a ticket ID, and view status and messages.
2. The reproducible historical-data workflow documents its CFPB source, cleaning decisions, label mapping, and CSV/Parquet outputs without committing raw data.
3. TF-IDF plus Multinomial Naive Bayes is trained and evaluated honestly with accuracy, precision, recall, macro-F1, a confusion matrix, and error/imbalance discussion.
4. High-confidence complaints route to the predicted department; below-threshold or ambiguous complaints route to General Support/manual review.
5. Authorized staff can process only their department's tickets, and customers cannot read other customers' tickets or modify protected routing fields.
6. A manager can view all demo tickets and at least four useful operational insights.
7. Firestore contains operational demo data, while historical CFPB files remain outside Firestore and Git.
8. English/Myanmar behavior, complaint lifecycle transitions, role boundaries, error states, and mobile/desktop use have recorded tests.
9. A public demo and QR code work using free tiers, with cold-start/loading behavior and backup demo material documented.
10. Setup, limitations, privacy considerations, translation limitations, model results, and deployment steps are documented; no secret, credential, raw dataset, or real financial data is committed.

## Day 1 approval record

This document freezes the project title, problem, users, departments, must-have features, exclusions, and completion criteria from `PROJECT_PLAN.md`. It is optimized for one active developer by reducing parallel coordination and UI breadth, not by removing required academic or security outcomes. Stretch goals remain deferred until the end-to-end MVP is stable.

## Day 20 completion interpretation

The implemented and locally verified MVP covers customer, department staff, and
manager workflows. The admin role is an authenticated shell only. Myanmar/mixed
submissions require manager review, historical similarity is local-only, and
macro-F1 remains below target. Public deployment, QR code, production Firebase,
retention/deletion, and admin operations remain incomplete; therefore the
original definition-of-done items that require those capabilities must remain
unchecked. The supported operating mode is a local emulator-based academic demo.
