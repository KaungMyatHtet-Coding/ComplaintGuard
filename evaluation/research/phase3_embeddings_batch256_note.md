# Phase 3 Batch-256 evidence note

## Status and preservation boundary

`phase3_embeddings_experiment.json` is an aggregate-only, exploratory
Batch-256 result. Its SHA-256 is
`F152B27A21E17B51EFA4262432AA45303FB4DCAE1F0855FC1F788932B1A87FA6`.
It is not a finalist, does not replace the frozen production model, and does
not authorize a routing, threshold, mapping, Firebase, or held-out-evaluation
change.

The file is valid JSON and declares schema version `1`. It predates the current
Phase 3 runner's schema version `2` provenance output, so it is preserved as
historical evidence rather than rewritten to imitate a newer run.

## Facts recorded directly in the artifact

- The artifact declares `status: completed`, `research_only: true`, and both
  `original_validation_evaluated` and `held_out_test_evaluated` as `false`.
- It identifies the source as `cfpb_training_v1.csv`, SHA-256
  `71a5ffda7914664a2b6803d92a6327bbe8e2438036e4420d3b30b95928241848`, with
  3,822,576 rows, and records the fixed development partitions: 99,200 fit,
  21,909 calibration, and 19,672 development-validation rows.
- It records `all-MiniLM-L6-v2`, CPU, batch size 256, normalized 384-dimensional
  embeddings, a balanced Logistic Regression with `C=1.0`, a 30,000-row
  training cap, and sigmoid calibration.
- It records aggregate metrics, length metrics, raw and calibrated confidence
  diagnostics, and privacy flags that exclude narratives, Complaint IDs, and
  row-level predictions.

## Independently verifiable current inputs

- The dataset SHA-256 and development partition counts agree with the committed
  Phase 2A/2B aggregate evidence and the locked Phase 3 harness.
- The committed Phase 3 harness uses the same model name, CPU device, batch
  size, embedding normalization, Logistic Regression `C=1.0`, 30,000-row cap,
  sigmoid calibration, and development seed `20260810`.

Agreement with current code does not prove the historical worker used every
current implementation detail. It is corroboration only.

## Provenance not recorded in the Batch-256 artifact

The historical schema-v1 JSON does not record:

- result creation timestamp;
- requested encoder revision, resolved encoder revision, or encoder snapshot
  SHA-256;
- Transformers version;
- Torch version, Torch seed, or deterministic-algorithms setting;
- an explicit experiment ID or runner revision/source commit;
- synthetic-regression details or aggregate safety-gate results;
- a declared finalist decision beyond its research-only status.

These fields remain unknown for this historical run. They must not be inferred
from filesystem timestamps, the current cache, or later code. A future
authorized rerun may emit current provenance, but must publish a new artifact
rather than overwrite this evidence.
