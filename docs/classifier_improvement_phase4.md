# Phase 4 Classifier Research

## Status

Phase 4 is prepared but not executed. No Phase 4 development dataset, manifest,
or result artifact exists. P4-R0 remains an exploratory reproducibility
protocol; it is not a production candidate and does not authorize held-out
evaluation, model replacement, routing changes, threshold changes, mapping
changes, Firebase changes, or deployment.

## P4-R0 Scope

P4-R0 is a development-only reproducibility experiment for frozen
`sentence-transformers/all-MiniLM-L6-v2`. It is not a production candidate and
does not authorize P4-H1 fusion, P4-FT1 fine-tuning, routing changes, threshold
changes, mapping changes, Firebase changes, or held-out evaluation.

The runner accepts only the immutable cached revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. It passes that revision and
`local_files_only=True` to `SentenceTransformer`, hashes the resolved cached
snapshot, and fails rather than downloading or falling back to a floating
revision. CPU execution, seed `20260810`, batch size `256`, normalized
embeddings, the deterministic fraud-capped fit view, balanced `lbfgs`
Logistic Regression (`C=1.0`, `max_iter=2000`), and post-fit sigmoid
calibration are immutable.

## Locked Data Contract

Only the Phase 2B development artifact is eligible. The separately authorized
preparation command recreates the existing fixed 200,000-row reservoir
(`20260727`), original 70/15/15 split, and Phase 2A development 70/15/15 split
(`20260810`) before publishing only the permitted rows:

| Partition | Rows |
|---|---:|
| Fit | 99,200 |
| Calibration | 21,909 |
| Development validation | 19,672 |
| Deterministic capped fit | 56,675 |

The ignored row-level artifact is
`data/interim/cfpb/phase4_development_v1.csv`; its aggregate-only completion
manifest is `data/processed/phase4_development_v1_manifest.json`. The artifact
contains exactly 140,781 permitted rows and is never committed. Its SHA-256 is
verified by P4-R0 before parsing. The combined-source checksum is trusted source
manifest provenance at P4-R0 runtime; it is verified only by the separately
authorized preparation command.

The original validation (`29,277`) and held-out test (`29,942`) partitions are
excluded from the artifact and are not opened, hashed, encoded, predicted, or
used by P4-R0. P4-R0 rejects the combined source before memory, dataset, or
model work and refuses an existing output before loading or encoding.

## Output And Evaluation

The only future result path is
`evaluation/research/phase4_r0_minilm_reproducibility.json`. It is published
atomically and contains aggregate metrics, provenance, determinism metadata,
and privacy flags only. It must not contain narratives, complaint identifiers,
embeddings, row-level predictions, labels, or probabilities. Synthetic safety
is recorded only as aggregate counts; detailed synthetic cases exist in memory
only long enough for the unchanged Phase 2B safety-gate evaluator.

P4-R0 reports the Phase 2B metric set and applies its unchanged gates: macro
and weighted F1, per-class regression limits, Transfer/Account confusions,
Fraud and Loan protections, length buckets, calibrated confidence diagnostics,
and synthetic safety. A result is exploratory even if a single metric improves;
no finalist is named unless every gate passes under separate authorization.

## Memory Control

P4-R0 requires at least 7 GiB available RAM before reading the manifest and
again before streaming, encoder loading, and every embedding allocation. Its
conservative estimate reserves approximately 5.91 GiB: two fit-embedding/
scikit-learn copies (~166 MiB), 1.5 GiB for model and tokenization, 1.25 GiB
for streamed source and development text, 0.5 GiB for Python/calibration, and
2.5 GiB headroom for temporary arrays and allocator overhead. The 7 GiB floor
rounds this estimate up rather than accommodating the previously observed
2.88 GiB environment. The runner encodes fit, calibration, and validation
sequentially, deletes each embedding matrix once its consumer is finished, and
never persists embeddings. If the budget is unavailable, it fails before the
relevant stage.
