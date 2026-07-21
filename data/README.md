# Data Directory

## Raw CFPB snapshot

Download the free official Consumer Complaint Database archive from:

```text
https://files.consumerfinance.gov/ccdb/complaints.csv.zip
```

Place it at `data/raw/cfpb/complaints.csv.zip` and extract `complaints.csv` beside it. `data/raw/` and archive/CSV formats are ignored by Git. Never force-add the raw archive, extracted CSV, complaint narratives, or complaint-level records.

The Day 3 snapshot downloaded on 20 July 2026 has archive SHA-256:

```text
2bdb13b1e412c6b659a94f74874d03ef6f610543b0d8e6538c7e30d1dd3d8eea
```

Validate and profile it from the repository root:

```powershell
python scripts/profile_cfpb.py
```

The profiler requires the dependency declared in `requirements-data.txt`; the verified Day 3 run used the already-installed pandas 2.2.3. The command verifies the ZIP CRC, checks the extracted size, and processes the CSV in 100,000-row chunks. It writes aggregate-only metadata to `data/cfpb_snapshot_profile.json`. See `docs/dataset_profile.md` and `docs/data_dictionary.md` for the reviewed Day 3 results.

## Directory policy

- `raw/`: ignored immutable downloads and extracted working copies.
- `mapping/`: future reviewed deterministic mappings, created only on the scheduled day.
- `processed/`: future small, reproducible, privacy-reviewed artifacts only.

Day 3 performs acquisition and profiling only. Cleaning, sampling, translation, feature engineering, and model work are intentionally deferred.
