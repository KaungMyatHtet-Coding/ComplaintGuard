# Phase 3.5 — Myanmar dataset acquisition and annotation foundation

This phase provides local intake and annotation tooling only. It does not collect data, train or evaluate a model, change V1, enable V2 routing, or begin Phase 4.

## Ethical acquisition

Permitted candidates are owner-authored synthetic complaints, publicly licensed complaint records after written license/privacy review, human-reviewed translations of an authorized source, de-identified opt-in records covered by an approved consent notice, or an approved institutional-partner dataset. Consent should identify purpose, languages, retention, access, withdrawal where feasible, and whether classifier development is allowed.

Prohibited methods include scraping private messages, support channels, social accounts, leaked datasets, or customer portals; copying operational Firestore tickets; purchasing data without approval; inferring consent; or retaining names, contact details, account/card/transaction references, addresses, NRC/passport identifiers, credentials, or other private identifiers. Translated and synthetic records remain explicitly non-real; public text is not automatically licensed or privacy-safe.

## Folder and Git boundary

- `data/v2/intake/`: user-provided raw JSONL/CSV.
- `data/v2/prepared/`: redacted prepared JSONL containing complaint text.
- `data/v2/annotations/`: dual-review working sheets.
- `data/v2/exports/`: any complaint-text export.
- `data/v2/reviewer-*/`: reviewer-specific working material.
- `data/mapping/`: committed schemas, taxonomy, proposed configuration, and synthetic annotation fixture only.
- `data/processed/`: aggregate-only manifests and reports.

The five complaint/reviewer locations are ignored by Git. Do not force-add them. Aggregate manifests must not contain complaint text, record IDs, provenance values, or reviewer identities.

## Intake contract and command

`data/mapping/v2_dataset_intake_schema.json` is the versioned strict schema. Unknown fields fail. Every candidate requires `recordId`, `complaintText`, language (`my`, `en`, or `mixed`), one frozen V2 proposed category, source type, source name/reference, ISO collection date, approved license/consent status, passed privacy review, annotator-independent `metadata`, and `taxonomyVersion: v2`. Minimum/maximum lengths are proposals pending human approval.

From the repository root, using only a user-provided local file:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_v2_dataset.py `
  --input data/v2/intake/candidates.jsonl `
  --prepared-output data/v2/prepared/candidates.v2.jsonl `
  --manifest data/processed/candidates.v2.aggregate.json
```

CSV is also accepted; its `metadata` cell contains a JSON object. The command performs no network operation. It validates each record, applies Unicode NFKC, redacts detected names introduced by explicit name phrases, email, phone/long financial numbers, NRC/passport references, transaction/reference IDs, and street-style addresses, groups exact/near duplicates before deterministic partitioning, writes only accepted redacted records, and emits aggregate rejection reason counts without rejected text or identifiers. Automated redaction is defense in depth and does not replace human privacy review.

## Dual review and adjudication

`data/mapping/v2_annotation_schema.json` defines independent Reviewer A and B category fields, language, disagreement state, adjudicated final category, decision reason, timestamps, and taxonomy version. Reviewers label independently. Matching labels become `agreed`; different labels become `disagreed_unresolved`. A third authorized adjudicator records a final category, concise non-sensitive reason, timestamp, and `adjudicated`. Reviewer identity/access records remain outside aggregate evidence. The committed fixture is synthetic and contains no complaint text or reviewer identities.

## Agreement equations

Raw agreement is `matching A/B labels / dual-reviewed records × 100`. Cohen's kappa is `κ = (p_o - p_e) / (1 - p_e)`, where `p_o` is observed agreement and `p_e = Σ(category A proportion × category B proportion)`. When no dual-reviewed data exists, agreement and kappa are `not available`; when `p_e = 1`, kappa is undefined and remains null. Aggregates also report the directed A-to-B confusion counts, Reviewer-A per-category reviewed counts, per-language reviewed counts, and unresolved disagreement count.

## Readiness gates

`data/mapping/v2_dataset_readiness_gates_proposed.json` is clearly marked `proposed_pending_human_approval`. Its sample-count and length values are proposals, not accepted gates. Readiness requires human approval of that configuration plus: approved provenance/license for every record; passed privacy review; zero unresolved disagreements; zero duplicate groups crossing partitions; approved minimum counts for all categories, Myanmar, and mixed language; documented class balance; deterministic grouping/partitioning; and a locked dataset SHA-256 and manifest. A missing or unapproved threshold makes readiness false.

## Limitations, approvals, and rollback

Regex redaction cannot reliably detect every personal name, Myanmar address, identifier format, semantic duplicate, or indirect identity clue. Pairwise near-duplicate comparison is intended for a bounded MVP and needs a reviewed scalable method for a large corpus. No dataset currently exists, so agreement, coverage, class balance, privacy completion, and lock/hash gates remain blocked.

Before any later model or routing phase, the owner, domain reviewer, privacy reviewer, and ML reviewer must approve acquisition authority, consent/license evidence, retention/access, taxonomy, annotation/adjudication procedure, numeric readiness thresholds, a privacy-reviewed locked dataset and hash, and aggregate evidence. Phase 4 is not authorized by this document.

Rollback: remove only the Phase 3.5 schemas, proposed gate configuration, synthetic annotation fixture, documentation, tests, and the Phase 3.5 additions to the preparation script and `.gitignore`. Do not remove ignored user datasets during rollback. V1 and runtime behavior require no rollback because they are untouched.
