# ComplaintGuard Model Hunting Plan

## 1. Purpose

This plan defines a controlled research phase for improving ComplaintGuard's
weakest classification cases without changing the known-good application. It
covers short English complaints, Myanmar complaints, six-department accuracy,
confidence safety, CPU feasibility, offline operation, licensing, and integration
cost. Planning does not authorize training, downloading, dependency changes,
artifact replacement, application integration, or use of paid services.

Ordinary accuracy is insufficient because the held-out data is strongly
imbalanced, confidence is uncalibrated, minority-department errors matter, and a
system may improve raw accuracy while making automatically accepted predictions
less safe. Macro and per-department results, review coverage, calibration, and
operational regressions are therefore mandatory.

## 2. Protected baseline

- Known-good commit and `origin/main`:
  `083feec699b4aeaa19f1b8ab45faeb22c2f35636`.
- Annotated tag: `pre-model-hunting-checkpoint-v1`, resolving to that commit.
- Current research branch: `research/model-hunting`, initially at the same
  commit.
- Production artifact: ignored
  `models/generated/cfpb_department_model_v1.joblib`.
- Required artifact SHA-256:
  `BAFC086FE5B11BDCC5CBC4F04F3F3F222DE8CBAD27FE66D62A6685CC30F953D5`.
- Production model remains TF-IDF + `MultinomialNB(alpha=0.5)`. Candidate work
  must write to new, candidate-specific ignored locations and must never alter
  the production path or overwrite baseline evidence.
- The label IDs, API schemas, `0.60` operational review policy, manager
  override, original-prediction evidence, Firebase rules, and verified customer,
  staff, and manager workflows remain protected.

Recovery uses a new branch from the annotated tag after preserving any local
work; never use `git reset --hard`. The complete safe procedure is in
`pre_model_hunting_checkpoint.md`.

## 3. Current classifier architecture

The v1 pipeline reads the ignored two-column mapped dataset
`data/interim/cfpb/cfpb_training_v1.csv`, validated by
`data/processed/cfpb_training_v1_manifest.json`. A seed-`20260727` single-pass
reservoir selects 200,000 of 3,822,576 mapped rows. SHA-256 of the seed and exact
normalized narrative assigns train, validation, or test; only training receives
a deterministic 30,000-per-class cap.

The selected feature/model configuration is word TF-IDF with 1-2 grams,
100,000 maximum features, `min_df=3`, `max_df=0.98`, sublinear term frequency,
float32 matrices, and Multinomial Naive Bayes alpha 0.5. Text normalization is
Unicode NFKC, case-folding, and whitespace collapse. Earlier dataset cleaning
performs conservative URL and obvious identifier redaction; it is PII reduction,
not anonymization.

The six labels, in fixed order, are:

1. `transfer_payment`
2. `account_support`
3. `card_atm`
4. `fraud_security`
5. `loan_credit`
6. `general_support`

`FrozenDepartmentClassifier` verifies model/dataset/mapping version, labels,
normalization, fallback, components, classes, and artifact hash. Confidence is
the maximum `predict_proba` output and is not calibrated reliability. The
artifact's validation-selected threshold is 0.0; trusted operational routing
uses 0.60. An English prediction below 0.60 stays unassigned for manual review.

`POST /predict` is English-only diagnostic inference. Authenticated
`POST /tickets` creates a durable PII-reduced ticket before trusted routing.
English input goes directly to the classifier. Myanmar/mixed input uses the
local pinned `Helsinki-NLP/opus-mt-mul-en` revision
`848eae0c1676cfce9bb791c200e8228e5a6396ff`, then the English classifier; its
result is review evidence only and is never automatically routed. Translation
or classification failure leaves a recoverable manual-review ticket.

The existing model is CPU-compatible and local. Recorded Day 9 end-to-end
model-selection/finalization time was 187.107 seconds, with held-out test
transformation 9.063 seconds and prediction 0.073 seconds. These batch timings
are not a standardized single-request latency benchmark; Stage 0 must define
one before candidate latency comparisons.

## 4. Verified baseline results

The authoritative Day 18 file is
`../evaluation/day18/model_evaluation_v1.json`, SHA-256
`F6B3A872396BA8A8DB874BDB0CA00F839A4515C1C77E935CE13CD02D488DAE06`.
Locked Day 9 evidence is
`../data/processed/cfpb_model_v1_metrics.json`, SHA-256
`99FC40B8E791FE65FF7ED22E8E5A731ED650351AD577D27322E95F2BDD1550D8`.

| Metric | Baseline |
|---|---:|
| Accuracy | 0.827934 |
| Balanced accuracy / macro recall | 0.736204 |
| Macro precision | 0.707515 |
| Macro F1 | 0.692345 |
| Weighted precision | 0.866300 |
| Weighted recall | 0.827934 |
| Weighted F1 | 0.837764 |

The held-out test contains 29,942 records and was excluded from fitting and
selection. Per-department metrics and the fixed 6x6 matrix remain mandatory
comparison evidence. The model misses the 0.70 macro-F1 project target.

At the separate Day 18 operational analysis threshold of 0.60, 3,235 held-out
records (10.8042%) fall below threshold and 26,707 (89.1958%) are accepted;
23,541 accepted predictions are correct. These descriptive test results must
not be reused to tune a candidate threshold.

The frozen Myanmar validation has 30 synthetic cases: owner review found 14/30
usable Marian translations and 11/30 correct downstream labels. The separate
base-NLLB development set produced 23/30 pass-or-partial translations and 9/30
correct labels. Neither passed acceptance or changed production behavior.

## 5. Problems being investigated

- Sparse word features can be weak for very short or paraphrased complaints.
- `Mobile transfer failed` is low-confidence/manual-review; a longer clear
  transfer example is wrongly classified as Account Support at high confidence.
- Transfer recall is 0.436945; 252 of 563 held-out Transfer & Payment records
  were predicted as Account Support.
- Class imbalance makes overall accuracy optimistic relative to minority-class
  behavior and macro F1.
- Maximum Naive Bayes probability is uncalibrated; high confidence can be wrong.
- The English CFPB proxy-label domain differs from short operational wording and
  Myanmar translated wording.
- Current Marian and base-NLLB Myanmar evidence failed translation and routing
  acceptance.
- There is no frozen, sufficiently broad short-English benchmark or standardized
  per-request CPU latency benchmark yet.

## 6. Candidate approach categories

All entries are research candidates only. Exact package/model revisions,
licenses, download sizes, memory use, and offline terms must be verified from
authoritative metadata before approval to acquire anything.

| Category | Provisional shortlist | Rationale and boundary |
|---|---|---|
| A. Existing baseline | Frozen word TF-IDF + MultinomialNB v1 | Required control; zero integration change and valid final choice. |
| B. Stronger classical ML | Character TF-IDF or word+character features with calibrated linear SVM, logistic regression, or SGD; ComplementNB as a low-cost imbalance-aware check | Uses the existing English training contract and CPU-friendly sparse matrices. Probability/calibration support and installed-library availability must be checked before implementation. |
| C. Multilingual sentence embeddings + classifier | A compact multilingual MiniLM-class sentence encoder plus logistic/linear classifier; a compact multilingual E5-class encoder as a separate option | Dense semantic features may help short paraphrases and cross-language input. Exact checkpoint, license, Myanmar coverage, size, CPU memory, and offline cache requirements are unverified. MiniLM is not production today. |
| D. Lightweight multilingual transformer classifier | A compact multilingual encoder such as Distil-mBERT-class or compact XLM-R-class model fine-tuned only on approved training data | Direct multilingual learning is possible but CPU training/inference and memory may exceed this machine's practical limits. Exact checkpoint/license must be approved first. |
| E. Myanmar-to-English then baseline | Existing pinned Marian control; pinned base NLLB evidence; a newly approved compact Myanmar-to-English checkpoint, if one can be licensed and run within limits | Preserves the English classifier but translation error compounds classification error. Marian and base NLLB already failed; the unavailable LoRA adapter is not a candidate unless provenance and availability are reverified. |
| F. Hybrid + manual review | Baseline or candidate plus calibrated abstention; agreement gate between independent models; language-specific manual-review policy | May improve accepted-prediction safety without claiming every complaint can be auto-routed. Manual review and manager override are retained, never removed. |

Repository guidance requires TF-IDF + Multinomial Naive Bayes as the project
approach. Alternative candidates therefore remain comparative research unless
the owner explicitly approves a scope change; they cannot silently replace the
required production model.

## 7. Fixed evaluation datasets

| Dataset | Status and use | Required protection |
|---|---|---|
| English train | Seeded v1 training partition; natural 140,781 before the existing cap | Candidate fitting only. Record any cap, resampling, augmentation, and extra data. |
| English validation | Fixed 29,277-record v1 partition | Candidate, hyperparameter, threshold, and calibration selection only. |
| English final test | Fixed 29,942-record v1 held-out partition | One final locked evaluation per approved candidate after selection; never iterative tuning. |
| Short-English benchmark | Not yet frozen; current repository has targeted synthetic regressions only | Stage 1 must author privacy-safe cases independently, review label ambiguity, deduplicate against all training/validation/test normalized text where local data permits, version/hash the set, and freeze it before candidate results are viewed. It is evaluation-only. |
| Myanmar frozen validation | `../data/mapping/myanmar_test_cases_v1.json`, 30 synthetic cases | Existing final validation evidence; never train, tune, translate into training, or repeatedly select on it. |
| Myanmar development | `../data/mapping/myanmar_checkpoint_dev_v1.json`, 30 separate synthetic cases | May compare translation candidates during development, but must not become training data. Its recorded SHA-256 is `D21F05CE31C64CA4E3D9C14F0267B5B542E35BF6C120C9E49EF6DAB5339CF2EC`. |

The user requested the same Myanmar evaluation set for every candidate. Before
experiments, the owner must decide whether candidate selection uses only the
development set followed by a single frozen-validation run (recommended), or a
newly authored development set. Repeated selection on the frozen 30-case
validation is prohibited.

## 8. Metrics and comparison protocol

Every candidate uses the same label order and reports, for each fixed dataset:

- accuracy, balanced accuracy, macro precision, macro recall, macro F1, and
  weighted metrics for continuity;
- per-department precision, recall, F1, and support;
- a fixed-order 6x6 confusion matrix;
- manual-review count and coverage at a threshold selected on development or
  validation data only;
- automatically accepted count, coverage, correct count, and conditional
  accuracy, with confidence intervals where practical;
- calibration evidence appropriate to the score: reliability bins, Brier score,
  and expected calibration error, with calibration fitted on validation only;
- cold start, warm single-item p50/p95/max, and fixed-batch CPU latency after
  warm-up, using the same machine, process/thread settings, repetitions, and
  measurement harness;
- peak process memory where measurable, serialized model/cache size, and
  dependency footprint;
- offline reload success after acquisition, integration changes, license and
  attribution suitability, and failure/fallback behavior.

Threshold comparisons must use a predeclared validation grid or policy.
Candidates must show the coverage-versus-accepted-accuracy curve; comparing
models at different review coverage without disclosure is invalid. Test-set
confidence analysis is reporting only and cannot choose thresholds.

## 9. Dataset leakage protections

- Preserve seed `20260727`, v1 mapping, split function, partition membership,
  and all recorded hashes. Do not relabel candidates differently.
- Fit vectorizers, encoders, classifiers, calibration layers, and any learned
  preprocessing only on training data. Use validation only for selection.
- Hash normalized text and prove exact duplicates cannot cross train,
  validation, test, short-English, or Myanmar evaluation boundaries. Record
  near-duplicate detection limitations and add a documented similarity audit
  before experiments if feasible.
- Never add an evaluation complaint, its translation, correction, paraphrase,
  embedding, pseudo-label, or augmented version to training. Translating an
  evaluation example is inference output only.
- Do not use the final English test or frozen Myanmar validation repeatedly to
  rank candidates. Keep an experiment registry recording every access and
  reserve final evaluation for approved finalists.
- Create candidate-specific output directories with non-overwrite publication.
  Never write to `data/processed/cfpb_model_v1_metrics.json`,
  `evaluation/day18/`, `models/generated/cfpb_department_model_v1.joblib`,
  Day 10 evidence, or any preserved cleaning/mapping artifact.
- Every experiment records training rows, sources, hashes, caps, augmentation,
  and exclusions. Extra data is permitted only after approval and must be
  disclosed; compare an equal-data ablation so a model does not receive an
  undocumented advantage.
- Results containing narratives stay ignored/local. Only privacy-reviewed
  aggregate metrics and synthetic cases may become eligible for Git.

## 10. Experiment stages

### Stage 0: Reconfirm baseline integrity

- **Inputs:** checkpoint tag, frozen model, manifests, locked metrics/evaluation,
  current tests.
- **Actions:** verify Git and hashes; run focused classifier/bilingual tests;
  define an isolated non-overwriting result root and standardized CPU benchmark;
  record hardware/software/thread controls.
- **Outputs:** baseline integrity manifest and baseline latency/memory report.
- **Acceptance:** all hashes/contracts match and mandatory tests pass.
- **Stop:** any mismatch, dirty protected file, missing ignored prerequisite, or
  benchmark that cannot measure candidates consistently.
- **Rollback:** delete only newly created ignored experiment outputs after
  validating their exact experiment directory; return via a recovery branch
  from the checkpoint tag if code changes later become authorized.

### Stage 1: Build and validate short-English evaluation data

- **Inputs:** six-label definition, verified failure modes, independent
  synthetic authoring guidance; no candidate predictions.
- **Actions:** create balanced short/ambiguous/paraphrased cases, dual-review
  labels and ambiguity, scan privacy, normalize/hash, audit exact/near overlap,
  version and freeze before any model is scored.
- **Outputs:** privacy-safe short-English evaluation JSON, manifest, hash, and
  validation tests in new paths.
- **Acceptance:** every label represented; provenance, ambiguity policy, schema,
  duplicate checks, and owner approval recorded.
- **Stop:** ambiguous labels cannot be resolved, overlap is found, real customer
  data appears, or cases were authored after viewing candidate outputs.
- **Rollback:** preserve the rejected draft outside locked paths or remove only
  the new uncommitted draft with explicit review; baseline remains untouched.

### Stage 2: Build and validate Myanmar evaluation data

- **Inputs:** frozen validation and separate development cases, owner reviews,
  six-label contract.
- **Actions:** audit hashes/separation and decide the development/final-validation
  protocol before candidate use. Add new synthetic development cases only if
  approved; never edit existing evidence.
- **Outputs:** protocol manifest and, if approved, a new versioned development
  set with independent semantic review instructions.
- **Acceptance:** no frozen-case reuse, translation leakage, real data, or label
  inconsistency; final set access policy approved.
- **Stop:** candidate selection has already seen proposed final cases or semantic
  labels are unreliable.
- **Rollback:** abandon only new drafts; retain all locked Day 10 evidence.

### Stage 3: Run low-cost classical baselines

- **Inputs:** existing training/validation partitions and frozen evaluation
  protocol; approved algorithms already available or separately approved.
- **Actions:** start with character TF-IDF + a linear classifier and an equal-data
  baseline reproduction; use fixed candidate grids and seeds; do not test-tune.
- **Outputs:** candidate-specific ignored models and aggregate development
  metrics/configuration manifests.
- **Acceptance:** reproducible, six labels, no leakage, CPU feasible, validation
  improvement, and output non-overwrite checks.
- **Stop:** dependency change needed without approval, resource ceiling exceeded,
  provenance mismatch, or no meaningful development improvement.
- **Rollback:** remove only candidate-specific ignored outputs or abandon the
  experiment branch changes; production artifact/path stays unchanged.

### Stage 4: Evaluate multilingual or translation candidates

- **Inputs:** approved pinned revisions/licenses, approved development datasets,
  resource budget, isolated caches.
- **Actions:** acquire only after separate approval; verify hashes/license;
  evaluate embeddings, lightweight transformers, or translation pipelines in
  isolated environments and offline mode.
- **Outputs:** candidate manifests, translation/semantic reviews, routing
  metrics, latency, memory, size, and failure analysis.
- **Acceptance:** license and attribution acceptable, offline reload succeeds,
  CPU/resource limits hold, and development results justify final evaluation.
- **Stop:** paid/network-only operation, unclear/restrictive license, unavailable
  revision, unsafe output, insufficient memory/disk, or failed quality gate.
- **Rollback:** delete only the verified candidate cache/environment after
  recording results; never alter the Marian cache or production dependencies.

### Stage 5: Compare confidence and manual-review behavior

- **Inputs:** validation scores from surviving candidates and the baseline.
- **Actions:** calibrate only on validation, predeclare thresholds, compare
  reliability and accepted-accuracy/coverage curves, and retain Myanmar manual
  review unless explicit quality acceptance exists.
- **Outputs:** calibration metrics and a common-threshold/common-coverage report.
- **Acceptance:** candidate is no less safe at comparable coverage and does not
  hide failures through excessive abstention.
- **Stop:** calibration uses final test data, scores lack stable semantics, or
  apparent gains disappear at matched review coverage.
- **Rollback:** discard candidate calibration artifacts; keep operational 0.60
  baseline policy unchanged.

### Stage 6: Integration trial behind a feature flag or separate adapter

- **Inputs:** approved finalist and frozen adapter/API contracts.
- **Actions:** add a default-off research adapter or offline comparison command;
  never replace the production artifact/path. Verify sanitized failures and
  manual fallback.
- **Outputs:** isolated adapter, contract/regression tests, and integration report.
- **Acceptance:** default behavior byte-for-contract compatible; label/schema,
  audit, ownership, and fallback behavior preserved.
- **Stop:** production default changes, rules/data migrations are needed, or
  failures can bypass manual review.
- **Rollback:** disable/remove the research adapter; checkpoint model remains the
  default without data migration.

### Stage 7: Regression testing

- **Inputs:** default-off integration trial and known-good test matrix.
- **Actions:** run frontend, API, classifier/bilingual, Firebase rules/Auth/
  adapters/Playwright, build, artifact, secret, and forbidden-file checks.
- **Outputs:** exact regression report and changed-file audit.
- **Acceptance:** all mandatory suites pass; expected failures remain honest;
  model/data/cache files remain ignored.
- **Stop:** any security, department isolation, workflow, localization, build,
  privacy, or baseline-default regression.
- **Rollback:** remove/disable only candidate integration changes and rerun the
  checkpoint verification.

### Stage 8: Candidate selection or retain the existing model

- **Inputs:** approved final results and decision matrix.
- **Actions:** compare evidence without test-set retuning; document tradeoffs and
  owner decision. Promotion requires a separately approved migration plan.
- **Outputs:** decision record: promote for a later controlled integration, run
  more development work, or retain v1.
- **Acceptance:** all proposed criteria are approved and met, or baseline
  retention is explicitly selected.
- **Stop:** evidence is incomplete, incomparable, license/resource status is
  unresolved, or gains are not meaningful.
- **Rollback:** retain/reselect the tagged v1 baseline; no runtime rollback is
  necessary because Model Hunting never replaced it.

## 11. Proposed acceptance criteria

These thresholds are **proposed, not approved**. Stage 1/2 dataset sizes and
baseline scores must be frozen before final thresholds are adopted.

- Preserve all six labels, prediction/routing schemas, and application/security
  contracts; pass every current mandatory regression suite.
- On the locked English benchmark, macro F1 should improve by at least 0.01
  absolute over 0.692345, with accuracy regression no worse than 0.01 absolute
  and no department F1 regression worse than 0.03 unless explicitly justified.
- On the frozen short-English benchmark, improve macro F1 or balanced accuracy
  by at least 0.05 absolute, or reduce harmful confident errors materially at
  matched automatic-acceptance coverage. Exact target becomes valid only after
  the baseline is measured on the frozen set.
- Myanmar promotion beyond manual-review-only requires at least 24/30 usable
  translations and 24/30 correct department labels on the frozen validation,
  consistent with existing provisional evidence, plus no department below 3/5.
  A direct multilingual candidate needs an equivalent owner-reviewed semantic
  and routing gate.
- At matched coverage, automatically accepted accuracy must be no worse than the
  baseline and calibration (Brier/ECE and reliability bins) must be safer or
  comparable. A candidate cannot pass merely by reviewing nearly everything.
- Proposed local performance ceiling: warm p95 classification latency no more
  than 1 second per complaint and peak process memory no more than 4 GiB on the
  verified development machine. Translation candidates may propose a separately
  approved slower ceiling, but current NLLB development mean near 5 seconds is
  not automatically acceptable. These ceilings require owner approval.
- Candidate and required runtime assets must fit an approved disk budget, reload
  offline, cost USD 0, avoid paid APIs, and have a license approved for the
  academic prototype and intended distribution.
- Keeping the current TF-IDF + MultinomialNB model is a fully valid result if no
  candidate meets every gate or the gain does not justify risk/complexity.

## 12. CPU, storage, licensing, and offline constraints

- Evaluation must run on CPU or a separately approved free temporary research
  environment; production inference must remain practical on local CPU.
- The recorded computer has 7.78 GiB RAM. Prior local NLLB acquisition was
  blocked by a 12 GiB gate. No candidate may bypass a documented RAM/disk gate.
- Candidate environments and caches must be isolated and ignored. Do not change
  current production requirements during research.
- No paid API, billing-required service, paid GPU, or production cloud setup.
- Pin model/repository revision and record file hashes, physical size, framework
  versions, license identifier/text/source, attribution, use restrictions, and
  whether redistribution of weights or derived artifacts is allowed.
- A recognizable model name is not license verification. Every provisional
  transformer/embedding/translation candidate remains blocked until its exact
  revision and authoritative license are reviewed.
- After initial acquisition, offline reload and inference must succeed with
  network access disabled. Failure must produce manual review, not fabricated
  output.

## 13. Risk register and rollback strategy

| Risk | Control | Stop/rollback |
|---|---|---|
| Test-set overfitting | Registry of accesses; validation-only selection; final test only for approved finalists | Reject contaminated result; retain v1. |
| Evaluation leakage | Normalized hashes, split membership, translation/paraphrase prohibition | Quarantine candidate data/output; rebuild only new research artifacts. |
| Label/domain inconsistency | Fixed mapping/version/order and equal-data disclosures | Reject incomparable run. |
| Accuracy hides minority harm | Macro/per-class/matrix and matched-coverage reporting | Reject unacceptable department regression. |
| Misleading confidence | Validation-only calibration and reliability metrics | Retain/expand manual review. |
| Myanmar semantic failure | Independent owner review and manual-review default | Stop automatic-routing consideration. |
| CPU/RAM/disk exhaustion | Preflight gates, isolated environment/cache, bounded sample first | Stop before acquisition/run; remove only candidate cache after verification. |
| License uncertainty | Authoritative license review before download | Do not acquire or distribute. |
| Production regression | Default-off adapter, full application/security tests | Disable/remove adapter and verify tagged baseline. |
| Evidence overwrite/privacy | New non-overwriting paths; aggregate-only tracked output | Stop on collision or narrative exposure; preserve locked artifacts. |

Rollback always begins by preserving and inspecting work. Create a new recovery
branch from `pre-model-hunting-checkpoint-v1`; do not reset destructively,
overwrite artifacts, or discard unrelated work.

## 14. Experiment-result recording template

```markdown
# Model Hunting Experiment Result

- Experiment ID:
- Date/time/timezone:
- Git commit:
- Candidate/category:
- Candidate version/revision and hashes:
- License, source, and review status:
- Dataset names, roles, row counts, and hashes:
- Configuration/hyperparameters:
- Random seed(s):
- Hardware/OS/runtime/thread configuration:

## Metrics

- Accuracy / balanced accuracy:
- Macro precision / recall / F1:
- Weighted precision / recall / F1:
- Per-department precision / recall / F1 / support:
- Confusion matrix (fixed label order):
- Manual-review count and coverage:
- Accepted count, coverage, correct count, and accuracy:
- Calibration method, Brier score, ECE, and reliability bins:
- Short-English results:
- Myanmar development/final results and semantic review:

## Resources

- Cold start:
- Warm single-item p50/p95/max latency:
- Fixed-batch latency:
- Peak memory:
- Serialized model size / total cache and dependency size:
- Offline reload result:

## Quality and decision

- Failures and error analysis:
- Regression commands and exact results:
- Protected-file/hash audit:
- Decision: reject / continue / finalist / retain baseline
- Notes and limitations:
```

## 15. Decision matrix template

No weighting is approved yet. Raw values and hard-gate failures must remain
visible; a weighted total cannot override security, license, leakage, or offline
failures.

| Candidate | English accuracy | English macro F1 | Worst department delta | Short-English macro F1 | Myanmar correct/usable | Review coverage | Accepted accuracy | Calibration | Warm p95 CPU | Peak RAM | Total size | Offline | License | Integration | Regressions | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| Frozen v1 control | 0.827934 | 0.692345 | reference | TBD | 11/30, 14/30 via Marian | 10.8042% below 0.60 on held-out analysis | 23,541/26,707 | uncalibrated | TBD standardized | TBD | 13,311,363-byte model | Yes | existing project use | Existing | Passed checkpoint | Retain/control |
| Candidate | | | | | | | | | | | | | | | | |

## 16. First experiment recommendation

The first experiment should be **Stage 0 plus Stage 1 only**, not model training:

1. Reconfirm hashes and establish the reproducible CPU latency/memory harness
   against the frozen v1 model.
2. Author, independently review, overlap-audit, version, hash, and freeze a
   balanced synthetic short-English benchmark before viewing candidate output.
3. Run the frozen v1 baseline once on that new benchmark to establish the weak-
   area reference.

After separate approval, the first trained candidate should be a low-cost
character TF-IDF + linear classifier in a new ignored output path, using exactly
the current training and validation membership. It is recommended before a
multilingual transformer because it tests the short-text hypothesis with lower
CPU, storage, dependency, licensing, and integration risk. The exact linear
algorithm, calibration method, grid, resource limit, and dependency status must
be approved before implementation.

## 17. Approval gate

This document authorizes no experiment. Before Stage 0/1 execution, the owner
must approve the dataset protocol, proposed acceptance thresholds, benchmark
method, output locations, and privacy review. Before any model download,
training, package installation, Colab use, or integration, the owner must also
approve the exact candidate/revision, authoritative license, resource budget,
environment, command, data access, and cleanup plan.

No candidate may replace the known-good model until final evidence and a
separate promotion/migration request are approved. Until then, production/demo
behavior remains the tagged TF-IDF + MultinomialNB v1 system.
