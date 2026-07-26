# Day 6 CFPB Exploratory Data Analysis

## Reproducible method

Day 6 reads `data/interim/cfpb/complaints_cleaned_corrected.csv` sequentially in configurable chunks. The pipeline validates the exact seven-column Day 5 schema and corrected cleaning run `e1996a2c34d0457fa08b83864b4f1a9d`, then retains only counters and a narrative-length histogram. It never publishes Complaint IDs, narratives, or complaint-level rows.

Run from the repository root:

```powershell
python scripts/cfpb_eda.py `
  --input data/interim/cfpb/complaints_cleaned_corrected.csv `
  --cleaning-report data/cfpb_cleaning_corrected_report.json `
  --output-dir data/eda/day6 `
  --chart-dir report/figures/day6 `
  --chunk-size 100000
```

The pipeline requires exactly 3,822,576 processed rows, strictly validates each canonical `YYYY-MM-DD` value as a real calendar date within 2011-12-01 through 2026-07-20, reconciles every aggregation, builds charts only from small aggregate tables, and refuses to overwrite existing results.

Both output packages are fully staged and validated before publication. The chart directory is published first and the aggregate directory is published last. Consumers must regard an EDA run as complete only when `data/eda/day6/eda_metadata.json` exists and has `status: completed`; that authoritative marker is not exposed until both output packages exist. Caught failures roll back packages created by the current attempt, and cleanup failures are reported explicitly.

Narrative percentiles use the lower nearest-rank convention: for `n` observations and probability `p`, the sorted observation at one-based rank `floor((n - 1) * p) + 1` is selected without interpolation. The reported median, p90, and p95 use this same deterministic convention.

## Scope and interpretation

The outputs describe retained CFPB submissions, not all consumers, product users, or underlying service-quality rates. Product and Issue taxonomies and complaint-reporting behavior can change over time. Day 5 rejected 13,210,233 rows without usable narratives, so retained-text EDA is subject to strong selection bias. Counts do not establish whether allegations are true or how common problems are in the customer population.

Department-label distribution is intentionally not analyzed: the label does not exist yet, and its deterministic Product/Issue mapping is separately scheduled for Day 7.

## Initial evidence

- Retained dates span 2015-03-19 through 2026-06-30. The 2026 count is partial-year and must not be compared as a completed year.
- 2025 has the highest retained annual volume at 1,221,752 complaints; January 2025 is the peak month at 172,901.
- The leading Product category represents 43.70% of retained complaints; the top five Products represent 84.87% across 21 categories.
- The leading Issue represents 31.51%; the top five Issues represent 69.44% across 173 categories, leaving a substantial long tail.
- Narrative length is right-skewed: median 666 characters, mean 1,018, p90 2,113, p95 2,988, and maximum 35,990. The largest fixed bucket is 500–999 characters at 30.64%.
- The leading Product–Issue pair represents 21.73%, showing strong concentration in the leading joint category.
- Day 5 rejected 13,210,233 rows for missing or unusable narratives. EDA of retained narratives therefore describes a selected subset and can underrepresent consumers or complaint types less likely to include publishable text.

## Outputs

- `data/eda/day6/`: small reconciled aggregate CSV tables and `eda_metadata.json`.
- `report/figures/day6/`: six aggregate-only PNG charts.
- `notebooks/02_cleaning_eda.ipynb`: GitHub-readable narrative that loads only those small artifacts.
- `report/dataset_eda.md`: initial Dataset and EDA report-section draft.

Day 6 implementation, initial verification, correction verification, and the second strict read-only re-review are complete. Day 6 status is Done. Day 7 mapping remains unstarted and unauthorized.
