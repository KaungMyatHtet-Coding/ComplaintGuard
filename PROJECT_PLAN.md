# ComplaintGuard Project Plan

> **Project title:** ComplaintGuard — Bilingual Financial Complaint Classification, Routing and Analytics System  
> **Project period:** 20 July 2026 – 10 August 2026 (22 calendar days)  
> **Final deadline:** 10 August 2026  
> **Target cost:** USD 0  
> **Languages:** English and Myanmar  
> **Required database:** NoSQL (Firebase Cloud Firestore)  
> **Main data-mining algorithm:** TF-IDF + Multinomial Naive Bayes

---

## 1. Project Goal

ComplaintGuard သည် financial service company တစ်ခုအတွက် customer complaint များကို English သို့မဟုတ် Myanmar ဘာသာဖြင့် လက်ခံပြီး complaint စာသားအပေါ်မူတည်၍ သက်ဆိုင်ရာ department သို့ အလိုအလျောက်ခွဲပို့ပေးမည့် web-based system ဖြစ်သည်။

System သည် အောက်ပါ real-world problems များကို ဖြေရှင်းရန်ရည်ရွယ်သည်။

- Complaint များကို manual အနေဖြင့်ဖတ်ပြီး department ခွဲပို့ရသည့်အချိန်ကိုလျှော့ချရန်
- မှားယွင်းသော department သို့ complaint ပို့မိခြင်းကိုလျှော့ချရန်
- Customer ကို ticket status နှင့် department reply များကြည့်နိုင်စေရန်
- Department staff ကို assigned complaint queue ကိုစနစ်တကျကိုင်တွယ်နိုင်စေရန်
- Manager ကို complaint trend၊ workload နှင့် recurring problems များသိရှိနိုင်စေရန်
- Myanmar user များအတွက် English-only barrier ကိုလျှော့ချရန်

## 2. Confirmed Technical Decisions

### 2.1 System architecture

| Layer | Technology | Cost | Purpose |
|---|---|---:|---|
| Frontend | Next.js + Tailwind CSS | Free | Responsive bilingual web application |
| Frontend hosting | Vercel Hobby | Free | Public URL and QR-accessible demo |
| NoSQL database | Firebase Cloud Firestore Spark | Free | Users, departments, complaints, messages and events |
| Authentication | Firebase Authentication | Free | Customer, staff and manager login |
| ML backend | Python FastAPI on Hugging Face Spaces CPU | Free | Text preprocessing, translation and classification |
| Data analysis | Python, Pandas and optionally PySpark | Free | Dataset cleaning, EDA and large-data processing |
| Data mining | TF-IDF + Multinomial Naive Bayes | Free | Complaint department classification |
| Translation | Open-source Myanmar-to-English model such as NLLB | Free | Myanmar complaint support without paid APIs |
| Version control | Git and GitHub | Free | Team collaboration and source history |

### 2.2 Dataset and NoSQL decision

- Historical CFPB dataset ကို CSV/Parquet အနေဖြင့် data cleaning, EDA နှင့် model training အတွက်သုံးမည်။
- Dataset အားလုံးကို Firestore သို့ import လုပ်ရန်မလိုပါ။
- Firestore NoSQL တွင် deployed application ၏ live/demo data ကိုသိမ်းမည်။
- Teacher ကခွင့်ပြုထားသောကြောင့် dataset ကို NoSQL ထဲမထည့်ခြင်းသည် accepted scope ဖြစ်သည်။
- အချိန်ပိုရမှသာ cleaned dataset sample အနည်းငယ်ကို demonstration collection အဖြစ်ထည့်မည်။ ဒါက stretch goal ဖြစ်ပြီး core requirement မဟုတ်ပါ။

### 2.3 No paid services

Project တွင် OpenAI API, Claude API, Google Translate paid API, SMS authentication, paid cloud function, custom domain သို့မဟုတ် paid GPU မသုံးရ။ Firebase ကို Spark plan အဖြစ်ထားပြီး billing account မချိတ်ရ။

---

## 3. Project Scope

### 3.1 Must-have features

- [ ] English/Myanmar language switch
- [ ] Customer, Department Staff နှင့် Manager/Admin roles
- [ ] Email/password သို့မဟုတ် prepared demo account login
- [ ] Customer complaint submission
- [ ] Myanmar/English text preprocessing
- [ ] TF-IDF + Naive Bayes classification
- [ ] Department prediction နှင့် confidence score
- [ ] Low-confidence complaint ကို General Support သို့ပို့ခြင်း
- [ ] Firestore NoSQL ထဲ complaint ticket သိမ်းခြင်း
- [ ] Customer complaint history နှင့် status tracking
- [ ] Staff assigned-ticket dashboard
- [ ] Staff reply, status update, reassign/escalate
- [ ] Ticket-based customer/staff message thread
- [ ] Manager analytics dashboard
- [ ] Model evaluation report
- [ ] Public Vercel deployment
- [ ] Teacher စမ်းသပ်နိုင်မည့် QR code နှင့် demo accounts

### 3.2 Stretch goals — core work ပြီးမှသာလုပ်ရန်

- [ ] Complaint attachment upload
- [ ] CSV/PDF operational report export
- [ ] Email notification
- [ ] Advanced keyword/association analysis using Apriori
- [ ] Cleaned historical dataset sample collection in NoSQL
- [ ] Dark mode
- [ ] Customizable SLA rules

### 3.3 Explicitly out of scope

- Real banking transactions
- Payment gateway integration
- Full company business operations
- Real customer account/card data
- Full generative-AI chatbot
- SMS/phone authentication
- Paid APIs and paid hosting
- Native Android/iOS application

---

## 4. User Roles and Core Workflow

### 4.1 Customer

1. Language ရွေးမည်။
2. Login သို့မဟုတ် demo customer account ဝင်မည်။
3. Complaint message နှင့် optional service/date/reference ထည့်မည်။
4. System က language detection, privacy cleaning, translation နှင့် classification လုပ်မည်။
5. Ticket ID, predicted department နှင့် current status ရမည်။
6. Department reply များဖတ်ပြီး message ပြန်ပို့နိုင်မည်။
7. Resolved ဖြစ်ပြီးနောက် rating/feedback ပေးနိုင်မည်။

### 4.2 Department Staff

1. Staff account ဖြင့် login ဝင်မည်။
2. ကိုယ့် department သို့ assigned ဖြစ်သော complaint များကိုသာမြင်မည်။
3. Priority/status/date ဖြင့် filter လုပ်နိုင်မည်။
4. Complaint ကို `In Progress` သို့ပြောင်းနိုင်မည်။
5. Customer ကို reply ပြန်နိုင်မည်။
6. လိုအပ်လျှင် reassign သို့မဟုတ် escalate လုပ်နိုင်မည်။
7. ဖြေရှင်းပြီးပါက `Resolved` သို့ပြောင်းမည်။

### 4.3 Manager/Admin

1. Complaint အားလုံးနှင့် department workload ကြည့်နိုင်မည်။
2. Total, open, resolved, high-priority နှင့် overdue complaint များကြည့်နိုင်မည်။
3. Department/category အလိုက် trend နှင့် average resolution time ကြည့်နိုင်မည်။
4. Recurring problems နှင့် complaint spikes များရှာနိုင်မည်။
5. Department, role နှင့် category mapping များစီမံနိုင်မည်။

### 4.4 Complaint lifecycle

```text
Submitted
  → Classified
  → Assigned
  → In Progress
  → Waiting for Customer (optional)
  → Resolved
  → Closed
```

Exceptional states: `Manual Review`, `Reassigned`, `Escalated`, `Reopened`.

---

## 5. Department Classification Plan

| Model label | Department | Example complaints |
|---|---|---|
| `transfer_payment` | Transfer & Payment | Transfer not received, payment failure |
| `account_support` | Account & KYC Support | Login, locked account, identity verification |
| `card_atm` | Card & ATM Support | Card payment, ATM withdrawal, lost card |
| `fraud_security` | Fraud & Security | Unauthorized transaction, scam, account takeover |
| `loan_credit` | Loan & Credit | Repayment, interest, loan servicing |
| `general_support` | General Support | Ambiguous or low-confidence complaint |

Dataset ၏ `Product` နှင့် `Issue` fields မှ `department_label` ကို deterministic mapping table ဖြင့်ဖန်တီးမည်။ Model သည် `Consumer complaint narrative` မှ `department_label` ကို predict လုပ်မည်။

---

## 6. Firestore NoSQL Design

### 6.1 Collections

```text
users/{userId}
departments/{departmentId}
complaints/{complaintId}
complaints/{complaintId}/messages/{messageId}
complaints/{complaintId}/events/{eventId}
feedback/{feedbackId}
dashboard_stats/{periodId}
```

### 6.2 Main complaint document

```json
{
  "customerId": "uid",
  "originalText": "...",
  "normalizedText": "...",
  "translatedText": "...",
  "detectedLanguage": "my",
  "predictedCategory": "money_transfer",
  "predictedDepartmentId": "transfer_payment",
  "confidence": 0.87,
  "assignedDepartmentId": "transfer_payment",
  "priority": "medium",
  "status": "assigned",
  "createdAt": "server timestamp",
  "updatedAt": "server timestamp",
  "resolvedAt": null
}
```

### 6.3 Required security rules

- Customer သည် မိမိ complaint နှင့် messages များကိုသာဖတ်နိုင်ရမည်။
- Department staff သည် မိမိ assigned department ၏ complaints များကိုသာဖတ်/ပြင်နိုင်ရမည်။
- Manager/Admin သည် complaints အားလုံးကိုဖတ်နိုင်ရမည်။
- Customer သည် prediction, assigned department, priority နှင့် resolved timestamp ကိုတိုက်ရိုက်ပြောင်းလို့မရရ။
- Complaint text length ကိုကန့်သတ်ပြီး sensitive information မထည့်ရန် UI warning ပြရမည်။

---

## 7. Data and Machine-Learning Plan

### 7.1 Data preparation

- Dataset download နှင့် immutable raw copy ထားခြင်း
- Column names, missing values, duplicates နှင့် class distribution စစ်ခြင်း
- Narrative မရှိသော rows များအတွက် documented decision ချခြင်း
- Department mapping table ပြုလုပ်ခြင်း
- URLs, excessive whitespace နှင့် unusable text ဖယ်ရှားခြင်း
- Personally identifiable information များကိုမသိမ်းရန်/မပြရန်စစ်ဆေးခြင်း
- Reproducible cleaned dataset ကို CSV သို့မဟုတ် Parquet အဖြစ်ထုတ်ခြင်း

### 7.2 Exploratory data analysis

- Complaint volume by year/month
- Top financial products and issues
- Department class distribution
- Submission channel distribution
- Timely-response distribution, where available
- Narrative length distribution
- Frequent words/terms by category
- Missing-value and duplicate summary

### 7.3 Model training

1. Train/validation/test split ပြုလုပ်မည်။ Stratified split ကိုဦးစားပေးမည်။
2. TF-IDF vectorizer ဖြင့် complaint narrative ကို numeric features ပြောင်းမည်။
3. Multinomial Naive Bayes baseline model train မည်။
4. Hyperparameters ဖြစ်သော `ngram_range`, `min_df`, `max_features` နှင့် `alpha` ကိုစမ်းသပ်မည်။
5. Accuracy တစ်ခုတည်းမဟုတ်ဘဲ precision, recall, macro-F1 နှင့် confusion matrix ဖြင့်တိုင်းတာမည်။
6. Class imbalance နှင့် misclassified examples များကိုသုံးသပ်မည်။
7. Validated confidence threshold အောက်တွင် `general_support/manual_review` သို့ပို့မည်။
8. Final vectorizer, classifier, label mapping နှင့် metadata ကို versioned artifacts အဖြစ်သိမ်းမည်။

### 7.4 Bilingual pipeline

```text
English complaint → Cleaning → Naive Bayes → Department
Myanmar complaint → Unicode normalization → Translation → Cleaning → Naive Bayes → Department
```

Myanmar test sentences ကို department တစ်ခုလျှင် အနည်းဆုံး 5 ခု ပြင်ဆင်ပြီး translation/classification result ကို manual review လုပ်မည်။ Translation အဆင်မပြေသော example များနှင့် limitation ကို report ထဲတွင် ရိုးသားစွာရေးမည်။

---

## 8. Daily Schedule and Deliverables

## Phase 1 — Requirements, Data and Design

### Day 1 — Monday, 20 July: Scope freeze and project setup

- [ ] Final project title, problem statement, users and departments အတည်ပြုရန်
- [ ] Must-have, stretch နှင့် out-of-scope features အတည်ပြုရန်
- [ ] Team member roles နှင့် communication channel သတ်မှတ်ရန်
- [ ] Git repository ဖန်တီးရန်
- [ ] Folder structure နှင့် README စတင်ရန်
- [ ] Task board: Backlog, In Progress, Review, Done ဖန်တီးရန်

**End-of-day deliverable:** Approved one-page scope, repository and assigned roles.

### Day 2 — Tuesday, 21 July: Environment and architecture

- [x] Frontend/backend/ML local environments setup လုပ်ရန်
- [x] Next.js starter run ရန်
- [x] Python virtual environment နှင့် dependencies setup ရန်
- [x] Firebase project ကို Spark plan ဖြင့်ဖန်တီးရန်
- [x] Hugging Face နှင့် Vercel free accounts စစ်ဆေးရန်
- [x] Architecture diagram နှင့် data flow ရေးရန်

**End-of-day deliverable:** Every member can run the starter project locally.

### Day 3 — Wednesday, 22 July: Dataset acquisition and data dictionary

- [x] CFPB dataset download ရန်
- [x] Raw dataset ကိုမပြောင်းဘဲ backup copy ထားရန်
- [x] Dataset size, row count, columns, types, missing values စစ်ရန်
- [x] Project တွင်အသုံးပြုမည့် columns သတ်မှတ်ရန်
- [x] Data dictionary ရေးရန်
- [x] Initial class mapping discussion ပြုလုပ်ရန်

**End-of-day deliverable:** Raw dataset, data profile and data dictionary.

### Day 4 — Thursday, 23 July: NoSQL schema and UI wireframes

- [ ] Firestore collections/documents design အတည်ပြုရန်
- [ ] Role-based access matrix ရေးရန်
- [ ] Firestore development rules စတင်ရန်
- [ ] Customer, Staff and Manager screens wireframe ဆွဲရန်
- [ ] English/Myanmar translation key structure သတ်မှတ်ရန်

**End-of-day deliverable:** NoSQL schema, access matrix and approved wireframes.

### Day 5 — Friday, 24 July: Data-cleaning pipeline

- [x] Missing narratives, duplicates နှင့် invalid rows ကိုစစ်ရန်
- [x] Reusable cleaning functions ရေးရန်
- [x] Text normalization စတင်ရန်
- [x] Cleaned dataset output ထုတ်ရန်
- [x] Cleaning decisions နှင့် before/after counts မှတ်တမ်းတင်ရန်

**End-of-day deliverable:** Reproducible cleaning notebook/script and cleaned data.

**Completed evidence:** The corrected full-dataset pair is `data/interim/cfpb/complaints_cleaned_corrected.csv` with `data/cfpb_cleaning_corrected_report.json`. Run `e1996a2c34d0457fa08b83864b4f1a9d` processed 17,034,951 rows in 171 chunks, retained 3,822,576 rows, rejected 13,212,375 rows, and passed production completed-pair validation.

### Day 6 — Saturday, 25 July: Exploratory data analysis

- [x] Required summary tables ပြုလုပ်ရန်
- [x] အနည်းဆုံး meaningful charts 6 ခုဖန်တီးရန်
- [x] Key findings ကို chart တစ်ခုစီအောက်တွင်ရေးရန်
- [x] Class imbalance နှင့် possible bias ရှာရန်
- [x] Report ၏ Dataset and EDA sections စတင်ရန်

**End-of-day deliverable:** EDA notebook, charts and first findings.

**Completed evidence:** Day 6 production EDA for corrected cleaning run `e1996a2c34d0457fa08b83864b4f1a9d` processed 3,822,576 of 3,822,576 rows and published ten reconciled aggregate files plus six readable charts. Targeted Day 6 tests passed 27 tests, the complete relevant suite passed 144 tests, correction verification completed, and the second strict read-only re-review passed with no Critical or Major findings.

### Day 7 — Sunday, 26 July: Department-label mapping and data freeze

- [x] Product/Issue → Department mapping အတည်ပြုရန်
- [x] Mapping coverage စစ်ရန်
- [x] Unmapped rows အတွက် General Support rule ထည့်ရန်
- [x] Final ML dataset ဖန်တီးရန်
- [x] Training dataset version `v1` freeze လုပ်ရန်

**End-of-day deliverable:** Final label mapping and versioned training dataset.

**Completed evidence:** Mapping version `v1` labeled 3,822,576 of 3,822,576 corrected rows in 39 bounded chunks using Product/Issue only. Dataset version `v1` contains one valid label per row, publishes aggregate-only completion metadata, and keeps the 3,958,969,065-byte full output ignored and untracked. Exact rules labeled 275,838 rows, Product fallbacks labeled 3,340,191, and `general_support` labeled 206,547. Focused synthetic verification passed 22 tests and Ruff checks passed. Day 8 model work remains unstarted and requires separate authorization.

## Phase 2 — Model and Core Application

### Day 8 — Monday, 27 July: Baseline model

- [x] Train/validation/test split ပြုလုပ်ရန်
- [x] TF-IDF + Multinomial Naive Bayes baseline train ရန်
- [x] Baseline metrics နှင့် confusion matrix ထုတ်ရန်
- [x] Misclassification patterns ကို aggregate confusion counts ဖြင့် privacy-safe စစ်ရန်
- [x] Baseline result ကို documentation ရေးရန်

**End-of-day deliverable:** Reproducible baseline model and evaluation results.

**Completed evidence:** Dataset/mapping `v1` was validated across 3,822,576 rows in 39 chunks. One fixed, seeded experiment selected 200,000 rows, grouped exact normalized duplicates before a 70/15/15 split, capped only training classes, fit 100,000 word/ngram TF-IDF features, and evaluated `MultinomialNB(alpha=1.0)` on 29,942 untouched test rows. Accuracy was 0.838989 and macro-F1 was 0.688484; the 0.70 target was not achieved. Nineteen focused synthetic tests, Ruff checks, privacy inspection, and metric reconciliation passed. Day 9 remains unstarted and requires separate authorization.

### Day 9 — Tuesday, 28 July: Model improvement and finalization

- [x] TF-IDF and Naive Bayes hyperparameters စမ်းရန်
- [x] Class imbalance handling စမ်းရန်
- [x] Confidence threshold ကို validation data ဖြင့်ရွေးရန်
- [x] Final model ကို test set ပေါ်တွင်တစ်ကြိမ် evaluate လုပ်ရန်
- [x] Model, vectorizer, labels and version metadata export လုပ်ရန်

**End-of-day deliverable:** Frozen model `v1`, metrics table and error analysis.

**Completed evidence:** Four predeclared TF-IDF/MultinomialNB candidates and five confidence thresholds were compared using validation macro-F1 only on the unchanged Day 8 sample and duplicate-group partitions. `lower_alpha` (`alpha=0.5`, training cap 30,000, threshold 0.0) won validation and was evaluated on 29,942 test rows exactly once. Frozen model `v1` achieved accuracy 0.827934, balanced accuracy 0.736204 and macro-F1 0.692345, improving Day 8 macro-F1 by 0.003861 but not meeting the 0.70 target. Aggregate metrics, fixed-order confusion analysis, version/integrity metadata, 12 focused tests and Ruff checks passed. Day 10 was separately authorized after Day 9 completion and is tracked below.

### Day 10 — Wednesday, 29 July: Myanmar pipeline

- [x] Myanmar Unicode normalization ထည့်ရန်
- [x] Myanmar-to-English translation model စမ်းရန်
- [x] English/Myanmar language detection ပြုလုပ်ရန်
- [x] Department တစ်ခုလျှင် Myanmar examples အနည်းဆုံး 5 ခုစမ်းရန်
- [x] Translation quality နှင့် response time မှတ်တမ်းတင်ရန်
- [x] Slow/failure state အတွက် user-friendly message ပြင်ဆင်ရန်

**End-of-day deliverable:** Working bilingual inference pipeline and test sheet.

**In-progress evidence:** The local PyTorch-only
`Helsinki-NLP/opus-mt-mul-en` pipeline is pinned to revision
`848eae0c1676cfce9bb791c200e8228e5a6396ff`, loads offline, and produced a
30-case synthetic review sheet. Runtime measurement and structured
slow/failure behavior passed. Owner review found only 14/30 usable translations
and only 11/30 predicted departments matched the approved synthetic
expectations; both required 24/30 thresholds failed. Diagnosis reproduced
unrelated output on a separate synthetic development case and found a
checkpoint-quality limitation rather than a missing language prefix, corrupt
cache, or loader defect. Candidate research found no credible stronger
Myanmar-to-English replacement within the original 400 MB physical-cache
boundary. The owner approved a candidate-specific 2.6 GB ceiling for later
evaluation of the pinned NLLB-200 600M base plus Myanmar-to-English LoRA
adapter. Local acquisition was blocked by the approved 12 GB RAM gate, so the
separate 30-case synthetic development set was evaluated in free Colab. The
intended LoRA adapter was unavailable and was not used; only pinned base NLLB
was evaluated. Translation executed for 30/30 cases with zero empty/error
outputs, deterministic repeats passed 3/3, and routing correctness was 9/30
(30%). Owner semantic review recorded 13 pass, 10 partial, and 7 fail; the
23/30 pass-plus-partial result was below the prior 24/30 usable threshold.
This is development evidence, not frozen-validation evidence. Myanmar
production readiness was not approved, and no final Myanmar translation route
was accepted. Day 10 therefore remains In Progress. Day 11 was separately
authorized and completed without changing the recorded Day 10 evidence.

### Day 11 — Thursday, 30 July: ML API

- [x] FastAPI service ဖန်တီးရန်
- [x] `/health` endpoint ပြုလုပ်ရန်
- [x] `/predict` endpoint ပြုလုပ်ရန်
- [x] Input validation, maximum length နှင့် error handling ထည့်ရန်
- [x] Prediction response schema အတည်ပြုရန်
- [x] Local API tests ရေးရန်

**End-of-day deliverable:** Tested local ML API returning department and confidence.

**Completed evidence:** The local API validates and integrity-checks frozen
model `v1`, exposes typed `/health` and `/predict` responses, enforces the six
stable department IDs, rejects missing, empty, whitespace-only, wrong-type,
over-limit, unsupported-script, Myanmar and mixed input with structured errors,
and never persists request text. Myanmar remains explicitly marked as a
development baseline that is not production-ready. Fifteen focused API tests
and 208 API/affected regression tests passed; Ruff check and format verification
passed. A synthetic request verified real frozen-model loading and the response
contract. Day 12 is tracked below.

### Day 12 — Friday, 31 July: Frontend foundation and authentication

- [x] Responsive application layout ပြုလုပ်ရန်
- [x] English/Myanmar language switch ပြုလုပ်ရန်
- [x] Firebase Authentication ချိတ်ရန်
- [x] Role-based navigation ပြုလုပ်ရန်
- [x] Demo customer, staff and manager accounts ပြင်ဆင်ရန်
- [x] Unauthorized-route protection စတင်ရန်

**End-of-day deliverable:** Users can log in and see the correct role dashboard shell.

**Completed 29 July 2026:** The Next.js frontend provides responsive home,
login and protected dashboard shells; reviewed English/Myanmar UI catalogs; a
configuration-gated modular Firebase email/password flow; active Firestore user
profile validation for `customer`, `staff`, `manager` and `admin`; role-aware
navigation; structured loading/configuration/authentication/permission states;
and explicit reminders that UI routing does not replace Firestore rules or
trusted-backend authorization. Nine focused synthetic tests, ESLint,
TypeScript checking and the production build passed. Live verification confirmed
that prepared customer, staff and manager accounts authenticate against their
matching `users/{uid}` profiles and open the correct dashboard shells; signed-out
dashboard access redirects to login; English/Myanmar switching works; and a
clean restart produces no hydration mismatch. No configuration values or demo
credentials are tracked. Day 12 status: Done. Day 13 has not started.

### Day 13 — Saturday, 1 August: Complaint submission integration

- [x] Existing Day 12 design ဖြင့် bilingual customer complaint form ပြုလုပ်ရန်
- [x] Firebase ID token, active customer role နှင့် owner UID ကို trusted FastAPI backend တွင် verify/bind လုပ်ရန်
- [x] Complaint ကို validate, normalize, PII-redact လုပ်ပြီး pending-classification Firestore ticket အဖြစ်သိမ်းရန်
- [x] Generated ticket ID နှင့် `submitted` status ပြရန်
- [x] Loading, validation, authentication, permission, persistence နှင့် unexpected-error states ထည့်ရန်
- [ ] ML classification, confidence နှင့် department routing ကို နောက် scheduled integration work တွင် ချိတ်ရန်

**End-of-day deliverable:** End-to-end customer submission creates a protected
pending-classification ticket and returns its ID. The ticket remains
`departmentId: null` and `routingSource: pending`; no ML result or department
assignment is fabricated.

Day 13 completed on 1 August 2026. The frontend sends only `complaintText` and
`inputLocale` with the Firebase ID token. The FastAPI endpoint verifies the
token and active customer profile, derives ownership, validates and redacts
text, and creates a protected Firestore ticket using server timestamps. Direct
client writes remain denied. Verification passed with 27 backend tests, 16
frontend tests, Ruff, ESLint, strict TypeScript, the production build, Firebase
Admin import verification, and `git diff --check`.

### Day 14 — Sunday, 2 August: Staff dashboard

- [x] Department-scoped assigned complaints list ပြုလုပ်ရန်
- [x] Status, priority, date filters ထည့်ရန်
- [x] Complaint detail screen ပြုလုပ်ရန်
- [x] Trusted reply နှင့် approved lifecycle status updates ထည့်ရန်
- [x] Staff `request_reassignment` နှင့် `request_escalation` audit requests ထည့်ရန်
- [x] Immutable complaint message/event audit history သိမ်းရန်
- [x] Privacy-safe synthetic routed/triaged fixture ဖြင့် automated workflow စမ်းရန်

**End-of-day deliverable:** In deterministic synthetic/adapter verification,
authorized department staff can receive, process, reply to, request management
review for, and resolve an already-routed complaint. Production ML routing is
not implemented; normal Day 13 submissions remain `submitted` with
`departmentId: null` and `routingSource: pending`.

Day 14 completed in automated/synthetic scope on 2 August 2026. Every endpoint
verifies the Firebase token, active staff role, valid staff department, and
exact ticket department. Valid staff transitions are limited to `triaged` →
`in_progress`, `in_progress` → `awaiting_customer`, `awaiting_customer` →
`in_progress`, and `in_progress` → `resolved`. Replies are author-bound and
PII-redacted; mutations use action IDs for idempotency; resolution and its event
are transactional. Reassignment and escalation are audit requests only and do
not change protected ticket state. Verification passed with 66 backend tests,
27 frontend tests, Ruff, ESLint, strict TypeScript, the production build, and
`git diff --check`. Firebase Emulator and live Firestore verification remain
outstanding because the CLI/test setup and runtime credentials are unavailable.

### Day 15 — Monday, 3 August: Customer tracking and messaging

**Completed implementation evidence:** Customer-owned history/detail, status
visibility, participant messaging, resolved feedback, and backend ownership
enforcement are implemented and covered by frontend/backend tests. Later local
emulator/browser verification exercised the integrated customer/staff flow.

- [ ] Customer complaint history page ပြုလုပ်ရန်
- [ ] Ticket detail and status timeline ပြုလုပ်ရန်
- [ ] Customer/staff message thread ပြုလုပ်ရန်
- [ ] Resolved complaint feedback/rating ထည့်ရန်
- [ ] Customer access security စမ်းရန်

**End-of-day deliverable:** Complete customer-to-staff ticket conversation flow.

## Phase 3 — Analytics, Integration, Deployment and Submission

### Day 16 — Tuesday, 4 August: Manager dashboard

**Completed implementation evidence:** Manager-only operational totals,
department workload, average resolution time, low-confidence review, and
transactional department override are implemented. Broader designed manager
priority/reopen/close operations and admin operations are not implemented.

- [ ] Total/open/resolved complaint cards ပြုလုပ်ရန်
- [ ] Complaints by department chart ပြုလုပ်ရန်
- [ ] Complaints by category/status chart ပြုလုပ်ရန်
- [ ] Trend and average resolution time ပြုလုပ်ရန်
- [ ] High-priority unresolved list ပြုလုပ်ရန်
- [ ] Empty/small demo dataset states ကိုစစ်ရန်

**End-of-day deliverable:** Manager can monitor operational complaint trends.

### Day 17 — Wednesday, 5 August: Full integration and security

- [x] Frontend, Firestore and ML backend end-to-end ချိတ်ရန်
- [x] Firestore production security rules အပြီးသတ်ရန်
- [x] Secrets ကို environment variables သို့ရွှေ့ရန်
- [x] Customer/staff/manager permission tests ပြုလုပ်ရန်
- [x] Sensitive information warning/redaction စမ်းရန်
- [x] Seed demo complaints and users ပြင်ဆင်ရန်

**End-of-day deliverable:** Feature-complete release candidate with role security.

**Local/emulator verification completed 8 August 2026:** The trusted backend uses the frozen
TF-IDF/Multinomial Naive Bayes model for genuine English and Myanmar inference. Accepted
high-confidence English predictions route transactionally; low-confidence, Myanmar and
mixed-language predictions remain unrouted for manager review. Auth and Firestore Emulator
tests plus browser E2E verify customer, staff and manager identity/authorization boundaries,
submission idempotency, routing, review and lifecycle behavior. The configurable `0.60`
threshold is an operational policy, not a statistically calibrated threshold. Frozen-model
macro-F1 remains below `0.70`, Myanmar translation quality remains below its target, and live
Firebase/production deployment is not verified. Day 17 is accepted only as a local/emulator-
verified milestone.

### Day 18 — Thursday, 6 August: Deployment deadline

**Owner-authorized revised Day 18 scope completed 9 August 2026:** Before the
remaining deployment work, Day 18 established reproducible real-model evidence.
The unchanged frozen model was evaluated on the reconstructed 29,942-record
held-out test partition with seed `20260727`; no retraining occurred. Accuracy
was 0.827934 and macro-F1 was 0.692345, so the 0.70 target remains unmet. Stable
aggregate JSON/CSV artifacts, confidence analysis, non-text correct/error
examples, and a local privacy-preserving TF-IDF cosine-similarity index covering
exactly 29,942 historical records are documented in
`docs/model_evaluation.md`. This evidence work does not claim deployment or
completion of the original deployment checklist below.

- [ ] ML backend ကို Hugging Face Spaces ပေါ်တင်ရန်
- [ ] Frontend ကို Vercel ပေါ်တင်ရန်
- [ ] Production environment variables ထည့်ရန်
- [ ] Mobile and desktop public URL စမ်းရန်
- [ ] QR code ဖန်တီးပြီး phone ဖြင့် scan စမ်းရန်
- [ ] Cold-start behavior နှင့် recovery message စမ်းရန်

**End-of-day deliverable:** Public deployed system and tested QR code.  
**Important:** ဒီနေ့နောက်ပိုင်း feature အသစ်ကြီးမထည့်တော့ရ။ Bug fixes နှင့် submission work ပဲလုပ်ရမည်။

### Day 19 — Friday, 7 August: System testing and bug fixing

**Owner-authorized revised Day 19 scope completed 9 August 2026:** Day 19 added
the authenticated manager Model & Dataset Analytics experience and reusable
privacy-safe Dataset Evidence panels. The UI consumes only validated aggregate
Day 18 evidence, does not expose narratives or complaint IDs, and reports the
historical-similarity index as local-only and undeployed. The existing
operational analytics and role boundaries remain unchanged.

Day 19 was merged to `main` through merge commit `629fc5d` after frontend,
TypeScript, ESLint, production-build, focused ML/backend preservation,
artifact-integrity, privacy, and Git checks passed.

- [ ] Functional test cases အားလုံး run ရန်
- [ ] English and Myanmar input test ရန်
- [ ] Role/permission test ရန်
- [ ] Slow network/mobile screen test ရန်
- [ ] Classification failure and low-confidence test ရန်
- [ ] Critical/high bugs အားလုံးပြင်ရန်

**End-of-day deliverable:** Tested release candidate and completed test report.

### Day 20 — Saturday, 8 August: Final report and documentation

**Owner-authorized revised Day 20 scope completed 9 August 2026:** Reconcile
current documentation, prepare a local-emulator demo guide, consolidate claims
and test evidence, create report/presentation sources, and run final verification.
This does not authorize retraining, deployment, admin features, new
infrastructure, or changes to Day 17/18 evidence. All available mandatory local
and emulator checks pass. The full scripts suite remains unavailable in `.venv`
because Matplotlib is absent. Public deployment, QR code, production Firebase,
retention/deletion, and admin operations remain incomplete.

- [x] Abstract, problem statement and objectives အပြီးသတ်ရန်
- [x] Dataset, cleaning and EDA sections အပြီးသတ်ရန်
- [x] NoSQL design, architecture and algorithm explanation ရေးရန်
- [x] Model evaluation and confusion matrix ထည့်ရန်
- [ ] System screenshots and user workflows ထည့်ရန်
- [x] Limitations, ethics/privacy and future work ရေးရန်
- [x] README setup/deployment instructions အပြီးသတ်ရန်

**End-of-day deliverable:** Complete report draft and technical documentation.

### Day 21 — Sunday, 9 August: Presentation and rehearsal

- [ ] Presentation slides အပြီးသတ်ရန်
- [ ] QR code, public URL and demo credentials ထည့်ရန်
- [ ] 5–10 minute live-demo script ရေးရန်
- [ ] Team member speaking sections ခွဲရန်
- [ ] Full rehearsal အနည်းဆုံး 2 ကြိမ်လုပ်ရန်
- [ ] Backup screenshots/video/local demo ပြင်ဆင်ရန်
- [ ] Report and slides proofreading လုပ်ရန်

**End-of-day deliverable:** Submission-ready package and rehearsed presentation.

### Day 22 — Monday, 10 August: Final verification and submission

- [ ] Hugging Face Space နှင့် deployed website ကိုစောစော warm up လုပ်ရန်
- [ ] QR code ကို phone/mobile data ဖြင့်နောက်ဆုံးစမ်းရန်
- [ ] Demo accounts နှင့် sample complaints စမ်းရန်
- [ ] Report, slides, source code and required forms တင်ရန်
- [ ] Git repository final release/tag ပြုလုပ်ရန်
- [ ] Submitted files အားလုံးဖွင့်ကြည့်၍ corrupt မဖြစ်ကြောင်းစစ်ရန်

**End-of-day deliverable:** Final submission completed before the deadline.

---

## 9. Suggested Team Responsibilities

Team size မသတ်မှတ်ရသေးသောကြောင့် role template ကို 4-person team အတွက်ရေးထားသည်။ Team member နည်းလျှင် roles များပေါင်းယူနိုင်သည်။

| Role | Primary responsibilities | Secondary responsibilities |
|---|---|---|
| Member A — Project Lead/Documentation | Scope, task board, report, slides, integration tracking | Testing and presentation |
| Member B — Data/ML | Dataset, cleaning, EDA, mapping, Naive Bayes, evaluation | ML API and bilingual testing |
| Member C — Frontend | UI/UX, bilingual screens, customer/staff/manager dashboards | Mobile testing and deployment |
| Member D — Backend/NoSQL | Firebase Auth, Firestore schema/rules, API integration | Security, seed data and deployment |

### If there are 3 members

- Member A: Project lead + documentation + testing
- Member B: Data/ML + ML API
- Member C: Frontend + Firebase/NoSQL + deployment

### Team working rule

- Task တစ်ခုစီတွင် owner တစ်ယောက်နှင့် reviewer တစ်ယောက်ရှိရမည်။
- နေ့တိုင်းအဆုံးတွင် completed work ကို repository ထဲ commit/push လုပ်ရမည်။
- Main branch သို့ untested code တိုက်ရိုက်မထည့်ရ။
- Blocker တစ်ခုကို 2 နာရီကျော်မဖြေရှင်းနိုင်ပါက team channel တွင်ချက်ချင်းတင်ပြရမည်။
- Deadline နောက်ဆုံးနေ့အထိ feature development မဆွဲထားရ။

---

## 10. Daily Check-in Template

နေ့တိုင်း 10–15 မိနစ် check-in လုပ်ပြီး အောက်ပါ format ကိုသုံးပါ။

```text
Yesterday completed:
- ...

Today will complete:
- ...

Blockers:
- ...

Evidence/link:
- Commit, screenshot, notebook output or deployed URL
```

Task တစ်ခုသည် screenshot/commit/test output ကဲ့သို့ evidence မရှိလျှင် `Done` မသတ်မှတ်ရ။

---

## 11. Testing Plan

### 11.1 Functional tests

- English complaint submits successfully
- Myanmar complaint translates and classifies successfully
- High-confidence complaint reaches predicted department
- Low-confidence complaint reaches General Support
- Customer receives ticket ID and can view status
- Assigned staff can view and update the ticket
- Unassigned staff cannot access the ticket
- Manager can view all departments
- Staff reply appears in customer message thread
- Resolved ticket records timestamp and accepts feedback

### 11.2 ML tests

- Empty text rejected
- Extremely long text rejected or truncated safely
- English and Myanmar language detection tested
- Each department has representative test examples
- Confidence values are between 0 and 1
- Unknown/ambiguous text triggers manual review
- Model artifact and label mapping versions match

### 11.3 Security tests

- Unauthenticated user cannot read complaints
- Customer cannot access another customer's complaint
- Customer cannot change assigned department or role
- Staff cannot grant themselves manager access
- Secrets are not committed to Git
- Real account/card numbers are not used in demo data

### 11.4 Deployment tests

- Public URL works on phone and desktop
- QR code opens the correct URL
- English/Myanmar fonts render correctly
- Hugging Face cold start displays a useful loading/error state
- Demo can be completed using mobile data
- Backup screenshots/video/local demo are available

---

## 12. Success Criteria

The project is considered successful when all of the following are true:

- [ ] At least one lecture algorithm, Multinomial Naive Bayes, is correctly implemented and explained.
- [ ] Large historical complaint dataset is cleaned and analyzed reproducibly.
- [ ] Model evaluation includes accuracy, precision, recall, macro-F1 and confusion matrix.
- [ ] English and Myanmar complaints can be submitted.
- [ ] Complaint is automatically routed or sent to manual review.
- [ ] Firestore NoSQL stores all operational application data.
- [ ] Customer, Staff and Manager roles work with correct permissions.
- [ ] Manager dashboard communicates at least four useful operational insights.
- [ ] The deployed system is accessible from a QR code.
- [ ] The complete project runs without a paid API or paid hosting plan.
- [ ] Report clearly states dataset limitations, translation limitations and privacy considerations.

Target model performance is **macro-F1 ≥ 0.70** after reasonable mapping and tuning. This is a target, not a result to fabricate. If the target is not met, the team must report the real score and explain class imbalance, label mapping and error patterns.

---

## 13. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Dataset is too large for a team laptop | Medium | High | Use selected columns, chunked loading, Parquet and optional PySpark |
| Department labels are unclear | High | High | Freeze a documented mapping by 26 July; send low-confidence cases to manual review |
| Class imbalance lowers model performance | High | Medium | Use stratified split, macro-F1, class analysis and balanced sampling where justified |
| Myanmar translation is slow/inaccurate | High | High | Test early on 29 July, restrict message length, warm backend, document limitations |
| Hugging Face free Space sleeps | High | Medium | Warm up before demo; show loading message; prepare backup screenshots/video |
| Firebase quota is exceeded | Low | Medium | Store only operational data; do not import full historical dataset; minimize repeated reads |
| Firestore rules expose data | Medium | High | Implement role rules, use emulator/testing and test cross-user access by 5 August |
| Team integration is delayed | Medium | High | Freeze API schema early, integrate customer flow by 1 August and deploy by 6 August |
| Feature scope becomes too large | High | High | Enforce must-have list; no new major features after 6 August |
| Live demo internet fails | Medium | High | Keep local demo, screenshots and short recorded backup demo |
| Report is delayed | Medium | High | Write dataset/EDA sections during Days 5–9; do not leave all writing to 8 August |

---

## 14. Required Project Artifacts

Recommended repository structure:

```text
complaintguard/
├── frontend/                 # Next.js application
├── ml-api/                   # FastAPI inference service
├── data/
│   ├── README.md             # Dataset download instructions; avoid committing huge raw files
│   ├── mapping/              # Product/Issue to department mapping
│   └── processed/            # Small reproducible samples only
├── notebooks/
│   ├── 01_data_profile.ipynb
│   ├── 02_cleaning_eda.ipynb
│   └── 03_model_training.ipynb
├── models/                   # Small final model artifacts if repository limits allow
├── firebase/
│   ├── firestore.rules
│   └── firestore.indexes.json
├── docs/
│   ├── architecture.md
│   ├── data_dictionary.md
│   ├── test_plan.md
│   └── demo_script.md
├── report/
├── presentation/
├── .env.example
├── PROJECT_PLAN.md
└── README.md
```

Final submission package should include:

- Source code repository
- Dataset source and access instructions
- Cleaning/EDA/model notebooks
- Final model metrics and confusion matrix
- Firestore NoSQL schema and security rules
- Deployed Vercel URL
- Hugging Face backend URL or deployment documentation
- QR code
- Demo credentials
- Test report
- Final written report
- Presentation slides
- Backup screenshots or short demo recording

---

## 15. Report Outline

1. Abstract
2. Introduction and background
3. Problem statement
4. Project objectives
5. Scope and limitations
6. Related systems/research
7. Dataset description and data dictionary
8. Data cleaning and preprocessing
9. Exploratory data analysis and findings
10. Department-label mapping
11. TF-IDF and Naive Bayes methodology
12. Model evaluation and error analysis
13. English/Myanmar language pipeline
14. System requirements and architecture
15. NoSQL database design
16. User roles and workflows
17. Implementation
18. Testing and results
19. Deployment
20. Privacy, ethics and limitations
21. Future improvements
22. Conclusion
23. References

---

## 16. Presentation Demo Script Outline

1. Problem and target users — 45 seconds
2. Dataset and key analysis findings — 1.5 minutes
3. Naive Bayes methodology and metrics — 1.5 minutes
4. Customer submits a Myanmar complaint — 1 minute
5. Automatic classification and routing — 45 seconds
6. Department staff responds and resolves — 1 minute
7. Customer checks status — 30 seconds
8. Manager dashboard and business insights — 1 minute
9. NoSQL architecture, limitations and conclusion — 1 minute

Recommended live-demo complaint:

> “မနေ့က ငွေလွှဲထားတာ ကျွန်တော့် account ထဲက ငွေဖြတ်သွားပေမဲ့ လက်ခံသူဆီ မရောက်သေးပါဘူး။”

Expected route: `Transfer & Payment Department` or `General Support` if confidence is below the validated threshold.

---

## 17. Final Submission Checklist

### Product

- [ ] Public app URL works
- [ ] QR code works
- [ ] All three roles work
- [ ] English/Myanmar UI works
- [ ] Classification and manual-review fallback work
- [ ] NoSQL reads/writes and security rules work
- [ ] Manager dashboard displays meaningful data

### Academic requirements

- [ ] Large dataset source is documented
- [ ] Data analysis includes meaningful findings
- [ ] Lecture algorithm is explained and evaluated
- [ ] Big-data processing approach is explained
- [ ] NoSQL design is explained
- [ ] Limitations are honestly reported

### Submission materials

- [ ] Report
- [ ] Slides
- [ ] Source code
- [ ] README
- [ ] Test evidence
- [ ] Model metrics
- [ ] QR code and demo credentials
- [ ] Backup demo material

---

## 18. Immediate Next Actions

Today, the team should complete these actions before starting implementation:

1. Team members and responsibilities ဖြည့်ရန်။
2. Final company name and department names အတည်ပြုရန်။
3. Git repository ဖန်တီးပြီး ဒီ `PROJECT_PLAN.md` ကို root တွင်ထည့်ရန်။
4. CFPB dataset download source နှင့် intended columns ကိုအတည်ပြုရန်။
5. Firebase Spark project ဖန်တီးမည့် team account သတ်မှတ်ရန်။
6. Daily 10–15 minute check-in time သတ်မှတ်ရန်။
7. July 26 data freeze, August 6 deployment freeze နှင့် August 10 deadline ကို team အားလုံးကအတည်ပြုရန်။

The safest strategy is: **finish a small complete system first, deploy by 6 August, and improve only when the end-to-end workflow is already stable.**

---

## Maintenance and Validation Phase

This post-Day-20 phase preserves all completed historical milestones. It does
not authorize model retraining, held-out-test tuning, production deployment, or
automatic Myanmar routing.

- [x] Reconcile the reported Mobile Transfer misclassification against the
  existing emulator ticket and hash-verified frozen model.
- [x] Add initial short user-style routing regressions, including the confirmed
  Transfer & Payment versus Account Support defect.
- [ ] Complete short user-style regression cases across all six departments.
- [ ] Expand Transfer & Payment versus Account Support boundary tests.
- [ ] Add accuracy-by-text-length analysis without tuning on held-out data.
- [ ] Evaluate probability calibration using validation data only.
- [x] Define and test that manager override remains available for a controlled
  wrong-high-confidence prediction.
- [ ] Perform non-destructive emulator export/import restart verification.
- [x] Document safe emulator export/import commands and destructive-command
  warnings.
- [x] Keep Myanmar and mixed-language automatic routing blocked.
- [x] Preserve the frozen Day 18 artifact and held-out test set unchanged.
- [ ] Keep production Firebase deployment verification explicitly incomplete.

### Phase 2A — controlled classifier-improvement research

- [x] Reconstruct and protect the original seed-`20260727` held-out partition.
- [x] Create grouped fit/calibration/validation partitions from original
  training rows only, using fixed seed `20260810`.
- [x] Compare the bounded CPU-friendly NB, ComplementNB, Logistic Regression,
  and Linear SVC matrix using development validation evidence only.
- [x] Record length, duplicate-risk, feature-boundary, and validation-only
  calibration evidence in research-only artifacts.
- [x] Conclude that no candidate passes every gate; ComplementNB improves the
  transfer boundary but exceeds the per-class Loan/Credit regression limit.
- [ ] Obtain approval before one locked finalist receives one held-out test
  evaluation.
- [ ] Decide whether any finalist should replace frozen production model v1.

Phase 2A does not change production model v1, the `0.60` routing policy,
Myanmar/mixed-language manual review, Day 18 evidence, or Firebase behavior.
