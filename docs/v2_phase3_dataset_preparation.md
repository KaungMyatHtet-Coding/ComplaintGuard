# V2 taxonomy and dataset preparation evidence

This local-only phase freezes the eight provisional ComplaintGuard Myanmar-banking category IDs in `data/mapping/myanmar_banking_taxonomy_v2.json`. They are not claims about AYA Bank's internal departments. The taxonomy contains English and Myanmar names and definitions, inclusion/exclusion rules, synthetic bilingual examples, and ambiguity guidance. It does not enable V2 or Myanmar automatic routing and does not replace the frozen V1 classifier.

## Dataset record contract

Private, privacy-reviewed source records stay outside Git and use JSON Lines with required `case_id`, `text`, `source_type`, `source_reference`, `source_license`, `language`, and `category_id`. Optional review fields may include `secondary_category_id`, `priority`, `language_mix`, `annotator_ids_hash`, `annotation_round`, `label_confidence`, and `adjudicated`.

- `real_public`: real complaint material from a public, license-reviewed source; none is currently approved or included.
- `translated`: a reviewed translation derived from a separately authorized source; translated text is never presented as real Myanmar customer text.
- `synthetic`: owner/reviewer-authored demonstration text; it is never customer data.

Allowed language values are `myanmar`, `english`, and `mixed`. Source provenance and license/consent metadata are mandatory. A future manifest reports every source type and language separately.

## Privacy, duplicates, and partitioning

`scripts/prepare_v2_dataset.py` applies Unicode NFKC and whitespace normalization plus conservative email, phone, and long-number redaction before fingerprinting. It validates taxonomy/source/language allowlists and emits counts only: it never writes complaint text, case IDs, source references, annotator identifiers, or personal identifiers to the aggregate manifest.

Exact duplicates use SHA-256 of normalized case-folded redacted text. Near duplicates use a declared `SequenceMatcher` threshold (default `0.90`). Exact and near relationships are joined into groups before splitting. Each complete group is reproducibly assigned by its minimum fingerprint to train/calibration/validation/held-out using fixed 70/10/10/10 buckets, preventing related records from crossing partitions. This deterministic method must be reassessed for scale and Myanmar semantic duplicates before a substantial corpus is used.

## Current evidence and blockers

`data/processed/myanmar_dataset_v2_manifest.json` records zero approved records. It therefore produces no model quality, per-language, per-category, calibration, agreement, accuracy, precision, recall, macro-F1, or confusion-matrix result. Zero duplicate findings mean no records were processed, not that a future corpus is leak-free.

Blocked inputs are a legally and ethically approved Myanmar banking complaint source; license/consent review; English and mixed-language coverage; independent bilingual annotators and adjudication; agreement thresholds; accepted per-class/per-language gates; and a locked privacy-reviewed corpus. Until these exist and pass review, Myanmar/mixed input remains in the V1 safe review behavior and V2 routing stays inactive.

## V1 preservation and rollback

All V2 artifacts use new names and versions. No V1 mapping, model artifact, metric, evaluation evidence, ticket, Firestore rule, index, or operational record is modified. Rollback is removal of only the new V2 taxonomy, preparation script, test, manifest, and this documentation; runtime behavior is unchanged because no application imports them.
