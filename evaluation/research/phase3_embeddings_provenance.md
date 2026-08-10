# Phase 3 Embeddings Provenance

Phase 3 dense-embedding results are exploratory research evidence only. Neither
observed run is selected, promoted, or evaluated against the protected original
validation or held-out test partitions.

## Earlier Batch-64 Artifact

- SHA-256: `BB13267A95510BE49398830C2E4CFDD07197F87225FE100B34D51BDAFEDE34CB`
- The exact file is no longer recoverable from safe project-local locations.
- Validation macro-F1: `0.684972`
- Weighted-F1: `0.802321`
- Short-text (`0-100` characters) macro-F1: `0.413874`

## Current Batch-256 Artifact

- SHA-256: `F152B27A21E17B51EFA4262432AA45303FB4DCAE1F0855FC1F788932B1A87FA6`
- Size: `11,161` bytes
- Modification time: `2026-08-11T02:58:06.8692154+06:30`
- Validation macro-F1: `0.684701`
- Weighted-F1: `0.801802`
- Short-text (`0-100` characters) macro-F1: `0.410486`
- Short-text (`101-300` characters) macro-F1: `0.579292`
- Aggregate-only artifact; the protected original validation and held-out test
  partitions remained unevaluated.

The batch-256 artifact was likely produced by a previously interrupted worker
that completed asynchronously, but that explanation is not directly proven.
It must not be treated as superseding the batch-64 result.

## Interpretation And Provenance Limits

Neither observed result reaches the `0.70` macro-F1 target. Neither result is a
finalist or production candidate, and Phase 3 remains exploratory.

The current artifact predates the hardened reproducibility metadata. It lacks a
run timestamp, encoder revision or snapshot hash, Torch and Transformers
versions, and explicit deterministic-settings metadata. Preserve both sets of
recorded facts as provenance; do not regenerate either artifact merely to make
them comparable.
