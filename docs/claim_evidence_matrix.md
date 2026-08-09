# Final Claim-to-Evidence Matrix

Use the wording in this matrix for the report, slides, demo, and oral defense.
Day-specific documents are historical context; machine-readable artifacts are
the source of truth for numeric claims.

| Allowed claim | Exact source | Application/document location | Verification | Limitation / allowed wording |
|---|---|---|---|---|
| The frozen snapshot contains 17,034,951 rows. | `evaluation/day18/model_evaluation_v1.json` → `dataset_pipeline.raw_records` | Manager dataset pipeline; final report | `test_evaluate_department_model.py`; TS artifact tests | Say “20 July 2026 snapshot,” not current CFPB total. |
| 3,823,413 raw rows had non-null narratives. | `dataset_pipeline.raw_records_with_non_null_narrative` | Final report | TS reconciliation | Availability count, not usability count. |
| 3,822,576 usable records were mapped to six proxy departments. | `usable_narrative_records`, `successfully_mapped_records`; `data/processed/cfpb_training_v1_manifest.json` | Manager pipeline; mapping section | Mapping tests and evaluator | Proxy labels from Product/Issue, not institutional ground truth. |
| Modeling selected 200,000 records and fitted 68,034. | `selected_modeling_records`; `partitions.training_used_for_fit.rows` | Manager pipeline; methodology | Evaluator and TS parser | Never say model trained on all raw or mapped records. |
| Validation contains 29,277 and held-out test contains 29,942. | `partitions.validation.rows`, `partitions.test.rows` | Analytics/report | Evaluator reconciliation | Test was excluded from fitting/selection; Day 18 later audited it. |
| Accuracy is 0.827934 and macro-F1 is 0.692345. | `metrics.accuracy`, `metrics.macro.f1` | Manager cards/report | Locked Day 9 reconciliation and frontend tests | The 0.70 macro-F1 target was not achieved. |
| Weighted F1 is 0.837764. | `metrics.weighted.f1` | Manager card/report | Artifact tests | Explain majority-class influence. |
| Six-department metrics and the 6×6 matrix are held-out evidence. | `metrics.per_department`, `metrics.confusion_matrix` | Manager tables/report | CSV/JSON reconciliation tests | Rows are true labels; columns predicted labels. |
| Exact normalized duplicates do not cross partitions. | `partitions.exact_normalized_duplicates_cross_partitions=false`; `split_method` | Evaluation/report | Evaluator tests | Near-duplicates were not detected. |
| `0.60` is the operational review threshold. | `confidence_analysis.operational_analysis_threshold`; `ml-api/app/config.py` | Confidence UI/Dataset Evidence | Routing and TS tests | Not calibrated probability and not the Day 9 selected threshold. |
| Confidence is an uncalibrated per-prediction output. | `confidence_analysis.definition`; model evaluation documentation | Dataset Evidence and analytics | UI tests | Never call confidence accuracy or guaranteed correctness. |
| Myanmar/mixed submissions require manual review. | `ml-api/app/routing.py`; `docs/myanmar_pipeline.md` | Ticket routing state/report | `ml-api/tests/test_ml_routing.py` | No claim of production-ready semantic understanding. |
| Similarity is cosine search over 29,942 frozen TF-IDF vectors with 100,000 features. | `historical_similarity.*` | Manager/Dataset Evidence/report | Similarity and TS parser tests | Local-only ignored index; no live neighbors or raw/mapped-corpus coverage. |
| Evaluation artifacts contain no narrative or raw Complaint ID. | `privacy.contains_narratives=false`, `contains_complaint_ids=false` | Day 19 evidence boundary | Parser/privacy tests and tracked audit | Aggregate build-time data is non-sensitive, not secret manager data. |
| Customer/staff/manager authorization works locally. | `firebase/firestore.rules`, FastAPI actor checks | Role workflows | `firebase/run-emulator-tests.ps1` | Emulator-tested only; not production security certification. |
| Admin operations are not implemented. | `frontend/src/components/protected-dashboard.tsx`; absence of admin endpoints | README/report | Role policy tests and route audit | Admin is an authenticated empty shell. |
| Supported operation is local emulator-based demonstration. | `firebase.json`, emulator harness, no deployment manifests | README/demo/report | Firebase/E2E verification | No public URL, QR code, or production Firebase claim. |

## Prohibited claims

- “Trained on all 17 million complaints” or all 3.8 million mapped complaints.
- “Similarity covers all CFPB complaints” or is deployed.
- “Confidence is accuracy,” calibrated reliability, or correctness probability.
- “The macro-F1 target was achieved.”
- “Myanmar understanding/routing is production-ready.”
- “Admin operations are implemented.”
- “ComplaintGuard is publicly deployed” or has a verified QR code.
- “Redaction guarantees anonymization.”
- “Security is production-grade, enterprise-certified, independently audited, or
  proven outside the local emulator environment.”
- Any statistic, citation, screenshot, neighbor, complaint narrative, Complaint
  ID, user study, or deployment result not present in verified evidence.
