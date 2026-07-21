# ComplaintGuard

ComplaintGuard is a planned bilingual web system that accepts financial-service complaints in English or Myanmar, classifies them with TF-IDF and Multinomial Naive Bayes, and routes them to an appropriate support department. Customers track tickets, department staff process assigned complaints, and managers view a small operational dashboard.

The repository has completed **Day 3: dataset acquisition and data dictionary**. It contains a minimal Next.js foundation and aggregate-only CFPB snapshot documentation, but no cleaning, sampling, mapping implementation, EDA notebook, ML implementation, Firebase integration, or FastAPI service. See [`PROJECT_PLAN.md`](PROJECT_PLAN.md) for the full schedule, [`docs/dataset_profile.md`](docs/dataset_profile.md) for the snapshot profile, and [`docs/data_dictionary.md`](docs/data_dictionary.md) for the source fields.

## Core constraints

- USD 0 total cost; no paid APIs or billing-required services.
- Firebase Authentication and Cloud Firestore Spark for live/demo operational data.
- Historical CFPB CSV/Parquet data for offline analysis and model training; the full dataset is not stored in Firestore or Git.
- TF-IDF plus Multinomial Naive Bayes for complaint classification.
- English and Myanmar input, using a free/open-source translation path where needed.
- Synthetic demo data only; no secrets or real financial details in the repository.

## Architecture summary

| Area | Planned technology | Purpose |
|---|---|---|
| Web app | Next.js + Tailwind CSS | Bilingual customer, staff, and manager interfaces |
| Operational data | Firebase Authentication + Cloud Firestore Spark | Demo users, tickets, messages, and events |
| ML service | Python + FastAPI | Preprocessing, translation, classification, and confidence |
| Data mining | scikit-learn TF-IDF + MultinomialNB | Required department classifier |
| Historical data | CFPB CSV/Parquet | Reproducible analysis and training outside Firestore |
| Free deployment | Vercel Hobby + Hugging Face Spaces CPU | Planned public demonstration |

## Repository layout

```text
frontend/       Planned Next.js application
ml-api/         Planned FastAPI inference service
notebooks/      Planned numbered data and model notebooks
data/mapping/   Planned CFPB-to-department mappings
data/processed/ Small reproducible samples only
models/         Small versioned model artifacts, if repository limits allow
firebase/       Planned Firestore rules and indexes
docs/           Project documentation and task board
report/         Final report material
presentation/   Final presentation material
```

Unimplemented directories contain `.gitkeep` placeholders so the planned structure can be versioned.

## Local setup

Checked on Windows on 21 July 2026:

| Tool | Observed state |
|---|---|
| Git | 2.43.0.windows.1 |
| Node.js | v22.17.0 |
| npm / npx | 10.9.2 |
| Python | 3.12.0 |
| pip | 26.1.2 |
| Root virtual environment | Python 3.12.0; no packages installed on Day 2 |
| Java | 24.0.2 |
| Firebase CLI, Jupyter, Ruff, Black, Docker, uv | Not found |

PowerShell's current execution policy blocks some npm `.ps1` launchers; use the `.cmd` shims. Complete commands and troubleshooting are in [`docs/local_setup.md`](docs/local_setup.md).

## Verified frontend commands

From Windows PowerShell:

```powershell
Set-Location D:\ComplaintGuard\frontend
npm.cmd install
npm.cmd run dev
npm.cmd run lint
npm.cmd run build
```

The lint and build commands are Day 2 verification gates. There is no frontend test script yet.

Create and activate the single root Python environment with:

```powershell
Set-Location D:\ComplaintGuard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

No Python packages are required or installed on Day 2. `requirements-dev.txt` records lightweight future test/lint tools only.

## Data and secrets

Do not commit the raw CFPB dataset. Keep local raw downloads under `data/raw/`, which Git ignores. The official source, snapshot hash, validation, extraction, and chunked profiling procedure are recorded in [`data/README.md`](data/README.md). Only small, privacy-reviewed samples may enter `data/processed/` on a later scheduled day.

Copy `.env.example` to a local `.env.local` only when configuration begins. Replace placeholders locally and never commit the resulting file. Firebase must remain on the Spark plan with billing disabled.

## Current workflow

The single active developer owns implementation and performs a self-review checkpoint before moving a task to Done. Track current work in [`docs/task_board.md`](docs/task_board.md). No official team member is assumed to be available unless they actively join.
