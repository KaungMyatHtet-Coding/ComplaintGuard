# CFPB Data Dictionary

This dictionary documents the 16 columns observed in the 20 July 2026 raw CFPB snapshot. Logical types describe intended interpretation; the Day 3 profiler reads every field as a string to avoid lossy inference.

| Source column | Logical type | Meaning | Planned ComplaintGuard use | Privacy and quality note |
|---|---|---|---|---|
| Date received | Date | Date CFPB received the complaint | Later time-based aggregate EDA | Snapshot includes dates through 2026-07-20 |
| Product | Category | Financial product named by CFPB | Required deterministic label-mapping input and later EDA | 188 missing; taxonomy changes over time |
| Sub-product | Category | More specific product | Optional mapping and error-analysis context | 235,505 missing |
| Issue | Category | Main complaint issue named by CFPB | Required deterministic label-mapping input and later EDA | 248 missing; taxonomy changes over time |
| Sub-issue | Category | More specific issue | Optional mapping and error-analysis context | 929,418 missing |
| Consumer complaint narrative | Text | Consumer-provided complaint description when publication consent and CFPB review allow it | Required future model input after scheduled privacy review and cleaning | Sensitive free text; never expose raw values; 13,211,538 missing |
| Company public response | Text/category | Company's optional public response classification or text | Not a model feature | 8,010,319 missing |
| Company | Category | Company identified in the complaint | Later aggregate context only; not a model feature | Company naming may vary over time |
| State | Category | Consumer state or territory code | Optional aggregate EDA only | Location data; 62,823 missing |
| ZIP code | String identifier | Consumer ZIP code, sometimes masked or partial | Excluded from model features | Location identifier; preserve as string; never publish row-level values |
| Tags | Category | CFPB tags such as older American or servicemember | Optional aggregate EDA only | Potentially sensitive; 16,244,349 missing |
| Submitted via | Category | Channel used to submit the complaint | Later aggregate EDA | Six observed categories |
| Date sent to company | Date | Date CFPB sent the complaint to the company | Optional later operational EDA | 102,934 missing |
| Company response to consumer | Category | Resolution/response status reported by the company | Later aggregate EDA | 465,209 missing |
| Timely response? | Boolean-like category | Whether the company responded on time | Later aggregate EDA | Values observed: Yes and No |
| Complaint ID | Integer identifier | CFPB complaint identifier | Provenance and future duplicate checks; never a model feature | 2,135 missing in this snapshot; do not assume contiguous IDs |

## Derived field planned for a later day

`department_label` does not exist in the CFPB source. A later scheduled task will derive it deterministically from `Product` and `Issue` using the stable IDs `transfer_payment`, `account_support`, `card_atm`, `fraud_security`, `loan_credit`, and `general_support`. This Day 3 dictionary does not create or populate that field.
