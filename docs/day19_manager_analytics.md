# Day 19 Manager Analytics and Dataset Evidence

## Evidence delivery

`evaluation/day18/model_evaluation_v1.json` remains the single source of truth.
Next.js Turbopack does not resolve client imports outside `frontend/`, so the
frontend uses a deterministic build step rather than a manually maintained
copy:

1. `frontend/scripts/sync-model-evaluation.mjs` reads the committed Day 18 JSON.
2. It requires schema version 1 and completed status, then writes an exact
   byte-for-byte copy to `frontend/src/generated/model_evaluation_v1.json`.
3. It rereads and compares the generated file with the source. The sync runs
   automatically before development, tests, type checking, lint and builds.
4. `frontend/src/lib/model-evaluation.ts` strictly parses and reconciles the
   complete runtime schema. Invalid evidence throws; the UI never substitutes
   fallback metrics.
5. Tests independently reconcile the generated primary artifact with the
   committed supporting JSON and CSV artifacts.

The generated JSON contains non-sensitive aggregate academic evaluation data.
The dashboard UI is shown only through the existing authenticated manager
workflow, but the bundled aggregate itself is not a backend-protected resource.

## Manager analytics

The existing operational overview and low-confidence review remain in
`/dashboard`. Managers additionally see:

- overall held-out metrics and test count;
- raw-to-test dataset pipeline counts;
- six-department precision, recall, F1, support and class distribution;
- correct/incorrect confidence bins and threshold group totals;
- the complete true-row/predicted-column confusion matrix;
- model version, timestamp, seed, partition and leakage evidence;
- limitations and the historical-similarity deployment status.

Visualizations use semantic tables, accessible CSS bars and numeric labels.
No chart package or runtime analytics request was added.

## Complaint Dataset Evidence

Customer details, staff details and the manager override detail use the same
component. It displays only already-authorized ticket fields: predicted
department, prediction confidence, routing source and assigned department. A
missing confidence remains pending/unavailable and never becomes zero.

Prediction confidence is described as an uncalibrated output for one complaint,
not accuracy or guaranteed correctness. Manual-review wording is derived only
from the existing routing source. No optional backend field was added.

## Historical similarity boundary

No live similarity search is deployed. The UI states that the ignored local
index uses cosine similarity over frozen TF-IDF vectors, has 100,000 features,
and covers exactly 29,942 held-out records. It does not claim coverage of the
mapped or raw corpus and shows no neighbor, narrative, raw CFPB Complaint ID or
similarity percentage.
