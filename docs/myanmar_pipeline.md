# Day 10 local Myanmar inference pipeline

Day 10 implements a local bilingual preprocessing boundary around the frozen
Day 9 department classifier. It remains **In Progress** because owner review
found only 14/30 usable translations and only 11/30 correct classifications;
both provisional acceptance requirements were 24/30.

## Frozen contracts

- Translation checkpoint: `Helsinki-NLP/opus-mt-mul-en`
- Immutable revision:
  `848eae0c1676cfce9bb791c200e8228e5a6396ff`
- Source/target language contract: Myanmar (`mya`) to English (`eng`)
- Translation runtime: PyTorch through `AutoTokenizer` and
  `AutoModelForSeq2SeqLM`
- Frozen classifier: `models/generated/cfpb_department_model_v1.joblib`
- Frozen classifier SHA-256:
  `bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5`

Ordinary inference sets Hugging Face and Transformers offline controls and
loads the exact revision with `local_files_only=True` and
`use_safetensors=False`. It does not call hosted inference or silently select
another checkpoint or revision.

## Cache policy and cleanup

The approved pinned revision contains seven unique physical files totaling
313,309,691 bytes:

| File | Bytes |
|---|---:|
| `pytorch_model.bin` | 310,385,901 |
| `vocab.json` | 1,423,947 |
| `target.spm` | 791,194 |
| `source.spm` | 706,917 |
| `config.json` | 1,395 |
| `generation_config.json` | 293 |
| `tokenizer_config.json` | 44 |

The initial AutoModel setup also cached conversion revision
`f5c88837d58e937af4fa5a77015027305e4226f5`, containing a separate
310,361,472-byte `model.safetensors`. Hugging Face's revision-aware cache
deletion strategy removed that revision, its unique blob, and its PR reference.
The approved revision and all seven referenced blobs remained intact. Snapshot
symlinks are views of these blobs and are not counted again as physical model
content.

Strict offline loading subsequently succeeded without a network request. The
independent cold-load check took 1.221 seconds.

## Normalization and routing

Input is normalized with Unicode NFC and collapsed whitespace. Myanmar is not
transliterated. Detection uses Unicode script ranges U+1000–U+109F,
U+A9E0–U+A9FF, and U+AA60–U+AA7F:

- English/Latin without Myanmar bypasses translation.
- Myanmar translates the complete normalized input.
- Mixed Myanmar/Latin translates the complete normalized input.
- Empty, punctuation-only, and unsupported scripts are not classified.

Translation failure never sends Myanmar text to the English classifier. Missing,
timed-out, failed, or empty translation returns `manual_review_required`,
`classification_performed=false`, and the safe routing destination
`general_support`. Error codes are stable and omit input, exception details,
model internals, and local paths. Successful translation taking over five
seconds adds the non-fatal `translation_slow` warning. Low classifier confidence
continues to use the separate frozen Day 9 fallback contract.

## Synthetic validation evidence

The privacy-safe input cases are in
`data/mapping/myanmar_test_cases_v1.json`. The generated review sheet is
`data/processed/myanmar_pipeline_v1_results.json`. All inputs and expected
intents are synthetic; neither file contains CFPB narratives, Complaint IDs,
contact details, credentials, or customer records.

The one offline validation run recorded:

- cases: 30, five per department
- translation failures: 0
- `translation_slow` warnings: 0
- cold model load: 2.311 seconds
- first translation: 1.938 seconds
- warm p50: 0.897 seconds
- warm p95 (nearest rank): 2.002 seconds
- warm maximum: 3.172 seconds
- correct department predictions: 11/30

Per-department correct predictions were:

| Expected department | Correct | Total |
|---|---:|---:|
| `transfer_payment` | 0 | 5 |
| `account_support` | 2 | 5 |
| `card_atm` | 3 | 5 |
| `fraud_security` | 3 | 5 |
| `loan_credit` | 3 | 5 |
| `general_support` | 0 | 5 |

The provisional prediction requirement of 24/30 overall and at least 3/5 per
department was not met. This result is not hidden or corrected.

## Owner-approved human review

The original inference results remain unchanged. The owner-approved preliminary
review is `data/processed/myanmar_pipeline_v1_preliminary_review.json`, and the
schema-normalized final evidence is
`data/processed/myanmar_pipeline_v1_owner_review.json`. The final evidence maps
the approved fields without rewriting their contents:

- `preliminary_score` to `score`
- `meaning_issue` to both `reviewer_note` and `meaning_loss`
- `suggested_translation` to `suggested_correction`

The approved distribution is 5 score-2, 9 score-1, and 16 score-0. Only 14/30
(46.67%) translations were usable at score 1 or 2, below the required 24/30.
Classification remained 11/30 (36.67%), also below 24/30.

## Diagnosis

The exact tokenizer reports `source_lang=mul`, `target_lang=eng`, no supported
language-code tokens, and no prefix tokens. This many-source-to-English model
therefore does not require a Myanmar source prefix. Target-language prefixes
apply to the inverse one-source-to-many model family, not this fixed-English
target checkpoint.

The implementation supplies the complete normalized sentence, truncates only
beyond 512 tokenizer units, uses deterministic four-beam generation without
sampling, limits output to 256 new tokens, and decodes while removing model
special tokens. These settings do not inject a source-language token and match
the checkpoint contract.

Cache inspection showed all seven pinned files with 313,309,691 unique physical
bytes. The PyTorch model loaded repeatedly with strict offline controls. This
rules out a missing file, fallback revision, silent network access, or
incomplete cache as the observed cause.

The separate development-only file
`data/mapping/myanmar_diagnostic_cases_v1.json` contains ten newly worded
synthetic diagnostics and does not reuse the 30 validation cases. On
`diagnostic_incorrect_notice_10`, the translator deterministically produced
`Could not close temporary folder: %s` twice. Other diagnostics showed
software-oriented substitutions such as list subjects, layers, and backup
files. The exact repeated unrelated output on new input demonstrates a
checkpoint quality/domain-contamination limitation rather than nondeterministic
decoding or an application loader defect.

Of the 19 incorrect classifications, 10 accompanied score-0 unusable
translations. Nine occurred after translations scored usable; three of those
had score 2 and are the strongest direct evidence of a separate frozen
classifier/domain-label limitation. The other six score-1 cases retain mixed
attribution because important wording was imperfect or omitted. Six score-0
translations happened to produce the expected label and must not be treated as
meaningful end-to-end success.

Translation correction alone is not supported as a plausible route to 24/30.
Only 5/14 currently usable translations classified correctly. Reaching 24
without addressing classifier behavior would require 13 of the 16 currently
unusable cases to become correct after translation repair, an 81.25% success
rate that is inconsistent with the observed 35.71% correctness on usable
translations.

The minimal recommended remediation is an owner-selected, locally runnable,
Myanmar-to-English checkpoint evaluated on a separate synthetic development
set, followed by a fresh frozen validation run. The Day 9 classifier must remain
unchanged during translation selection. If usable translations still route
incorrectly, classifier remediation requires a separately authorized training
and validation design rather than keyword rules or post-processing tuned to the
30 validation cases.

## Checkpoint candidate preflight

Research found no credible stronger Myanmar-to-English checkpoint within the
original 400 MB physical-cache limit. The selected research candidate is:

- base: `facebook/nllb-200-distilled-600M` at immutable revision
  `f8d333a098d19b4fd9a8b18f94170487ad3f821d`
- adapter:
  `banyaroo/nllb-200-distilled-600m-mya_Mymr-eng_Latn-lora` at immutable
  revision `75a3b55efd4802aa1ef7051577354162926e4085`
- language contract: `mya_Mymr` source and `eng_Latn` target
- license: CC-BY-NC-4.0 for both base and adapter; reuse must retain
  attribution, identify changes, link the license, and remain noncommercial

The adapter metadata declares the selected NLLB base. The required FP32 base
runtime files total 2,482,646,304 bytes; the Hub lists the adapter package as
4.83 MB. The expected unique candidate cache is approximately 2.49 GB, within
the owner-approved candidate-only 2.6 GB ceiling. This is not a claim that the
candidate satisfies the former 400 MB limit.

The earlier “45 GB” RAM notation meant **4–5 GB** of estimated inference-process
memory. Acquisition planning assumes at least 8 GB system RAM, with 12 GB
practical and 16 GB preferred for Windows CPU inference. A safe acquisition
requires about 2.49 GB final candidate storage, approximately 4.98 GB temporary
candidate storage if staged and finalized copies coexist, and at least 6.5 GB
free when the retained 313,309,691-byte Marian cache and a safety margin are
included.

The adapter was trained with `transformers==4.51.3`, `peft==0.15.2`, and
`accelerate==1.6.0`. The current environment has Python 3.12.0, torch 2.9.1,
transformers 4.57.6, and sentencepiece 0.2.1; PEFT and Accelerate are absent.
For reproducible evaluation, the planned candidate environment must pin
`peft==0.15.2` and `accelerate==1.6.0`. Because the adapter's recorded stack and
PEFT compatibility guidance use Transformers earlier than 4.52, an isolated
candidate environment pinned to `transformers==4.51.3` is safer than changing
the existing Day 10 environment. No dependency was installed or changed during
this preflight.

`data/mapping/myanmar_checkpoint_dev_v1.json` freezes 30 newly authored
development-only cases, five per department. Its SHA-256 is
`d21f05ce31c64ca4e3d9c14f0267b5b542e35bf6c120c9e49ef6dab5339cf2ec`.
It does not copy the frozen validation cases. Local candidate acquisition was
not attempted because the machine failed the approved 12 GB RAM gate. The
development set was later executed in free Colab. The intended pinned LoRA
adapter repository was unavailable and the adapter was not used; the completed
evaluation covers pinned base NLLB only. The current Marian implementation and
cache remain unchanged.

## Free-Colab development workflow

Local NLLB acquisition was correctly blocked because the development computer
has 7.78 GiB physical RAM, below the approved 12 GB gate. The preparation
notebook `notebooks/day10_nllb_colab_evaluation.ipynb` moved only the approved
candidate development evaluation to a temporary free Google Colab CPU runtime.
It was executed without accessing the frozen validation set.

The notebook accepts exactly:

- `myanmar_checkpoint_dev_v1.json`, SHA-256
  `d21f05ce31c64ca4e3d9c14f0267b5b542e35bf6c120c9e49ef6dab5339cf2ec`
- `cfpb_department_model_v1.joblib`, SHA-256
  `bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5`
- `cfpb_model_v1_metrics.json`, SHA-256
  `99fc40b8e791fe65ff7ed22e8e5a731ed650351ad577d27322e95f2bdd1550d8`

The joblib contains the fitted TF-IDF vectorizer, frozen MultinomialNB
classifier, fixed labels, confidence threshold, fallback, normalization
contract, and version metadata. No training CSV, CFPB source data, or complaint
record is needed. The metrics JSON supplies aggregate integrity and runtime
metadata.

Before installation or acquisition, the notebook enforces 12 GB physical RAM
and 6.5 GB free disk. It installs only approved temporary-runtime candidate
dependencies and uses a notebook-local cache. The intended LoRA repository was
unavailable, so it was not acquired or used. The executed candidate was
`facebook/nllb-200-distilled-600M` at immutable revision
`f8d333a098d19b4fd9a8b18f94170487ad3f821d`. The base model reloaded offline.
The notebook evaluated only `myanmar_checkpoint_dev_v1.json`; it did not locate
or load frozen validation evidence.

The returned files are:

- `evaluation/day10/myanmar_nllb_base_dev_results.json`
- `evaluation/day10/myanmar_nllb_base_dev_summary.json`
- `evaluation/day10/myanmar_nllb_base_colab_manifest.json`
- `evaluation/day10/myanmar_nllb_base_semantic_review.json`

Translation executed for 30/30 cases with zero empty/error outputs, while
routing correctness was 9/30 (30%). Owner semantic review recorded 13 pass, 10
partial and 7 fail. Pass plus partial was 23/30, below the prior 24/30 usable
threshold. These files remain synthetic development evidence rather than
frozen-validation evidence. Myanmar production readiness was not approved, no
final Myanmar translation route was accepted, and Day 10 remains In Progress.
Day 11 is Done and Day 12 remains unstarted.

## Reproduction

After the approved checkpoint files already exist in the external cache:

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\python.exe scripts/run_myanmar_validation.py validate `
  --classifier models/generated/cfpb_department_model_v1.joblib `
  --cases data/mapping/myanmar_test_cases_v1.json `
  --output data/processed/myanmar_pipeline_v1_results.json
```

The evidence publisher refuses to overwrite an existing review sheet. The
download subcommand is setup-only and was not rerun after cache cleanup.

## Limitations

The Marian checkpoint is small enough for local CPU use, but its owner-reviewed
translation quality failed. Base NLLB executed all 30 development translations,
but its owner-reviewed 23/30 usable result remained below the 24/30 threshold
and downstream routing correctness was only 9/30. The intended LoRA adapter was
unavailable and was not used. The frozen classifier was trained on English
proxy labels, and translated wording can alter its routing behavior. The frozen
validation cases must not be used for training, tuning, keyword rules, or model
selection. Myanmar production readiness is not approved, no final route has
been accepted, Day 10 remains In Progress, Day 11 is Done, and Day 12 remains
unstarted.
