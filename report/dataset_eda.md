# Dataset and Exploratory Data Analysis — Initial Draft

ComplaintGuard uses the corrected Day 5 CFPB corpus produced by cleaning run `e1996a2c34d0457fa08b83864b4f1a9d`. The cleaned input contains seven columns and 3,822,576 retained complaints. Day 6 processes this approximately 4.5 GB CSV sequentially and publishes only aggregate tables and charts.

The retained data spans 2015-03-19 through 2026-06-30. Annual volume peaks in 2025 at 1,221,752 retained complaints, while January 2025 is the largest month at 172,901. The 2026 value is partial-year and should not be interpreted as a completed annual comparison.

Product and Issue are strongly concentrated. The leading Product accounts for 43.70% of retained complaints and the top five Products account for 84.87%. The leading Issue accounts for 31.51%, while the top five account for 69.44% across 173 observed Issues. The leading Product–Issue pair alone represents 21.73%, showing strong concentration in the leading joint category.

Narrative length is right-skewed: the median is 666 characters, the mean is 1,018, p90 is 2,113, p95 is 2,988, and the maximum is 35,990. The 500–999 character bucket is largest at 30.64%. Median and percentiles use the deterministic lower nearest-rank convention at one-based rank `floor((n - 1) * p) + 1`, without interpolation.

These findings describe retained CFPB submissions, not all consumers or product users, and counts do not prove population complaint rates or service quality. CFPB coverage, taxonomies, and reporting patterns change over time. Day 5 rejected 13,210,233 rows without usable narratives, creating material selection bias in retained-text analysis. Day 7 subsequently quantified a strongly imbalanced deterministic proxy-label distribution; it is documented separately and is not a model result.

The six aggregate charts are stored under `report/figures/day6/`, with source tables and exact findings in `data/eda/day6/`.
