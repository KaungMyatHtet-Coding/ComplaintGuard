# ComplaintGuard

ComplaintGuard is a planned bilingual web system that accepts financial-service complaints in English or Myanmar, classifies them with TF-IDF and Multinomial Naive Bayes, and routes them to an appropriate support department. Customers track tickets, department staff process assigned complaints, and managers view a small operational dashboard.

The repository is currently at **Day 1: scope freeze and project setup**. It intentionally contains no application code or installed project dependencies yet. See [`PROJECT_PLAN.md`](PROJECT_PLAN.md) for the full schedule and [`docs/project_scope.md`](docs/project_scope.md) for the frozen MVP scope.

## Core constraints

- USD 0 total cost; no paid APIs or billing-required services.
- Firebase Authentication and Cloud Firestore Spark for live/demo operational data.
- Historical CFPB CSV/Parquet data for offline analysis and model training; the full dataset is not stored in Firestore or Git.
- TF-IDF plus Multinomial Naive Bayes for complaint classification.
- English and Myanmar input, using a free/open-source translation path where needed.
- Synthetic demo data only; no secrets or real financial details in the repository.

## Planned architecture

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

Empty directories contain `.gitkeep` placeholders so the Day 1 structure can be versioned. They are not implementation files.

## Local environment observed on Day 1

Checked on Windows on 20 July 2026 without installing or changing software:

| Tool | Observed state |
|---|---|
| Git | 2.43.0.windows.1 |
| Node.js | v22.17.0 |
| npm / npx | Available through PowerShell launchers |
| Python | 3.12.0 |
| pip | 26.1.2 |
| Uvicorn | 0.51.0 |
| pytest | 8.3.4 |
| Java | 24.0.2 |
| Firebase CLI, Jupyter, Ruff, Black, Docker, uv | Not found |

PowerShell's current execution policy blocks some npm `.ps1` launchers; the `.cmd` shims may be needed. Environment compatibility and dependency versions will be decided on Day 2 before anything is installed.

## Development commands

There are no working build, test, or development commands yet because Day 1 does not include implementation or package manifests. Planned commands are documented in `AGENTS.md`; they must be verified after scaffolding on Day 2.

## Data and secrets

Do not commit the raw CFPB dataset. Keep local raw downloads under `data/raw/`, which Git ignores, and record the official source and reproducible download procedure when dataset work begins. Only small, privacy-reviewed samples may enter `data/processed/`.

Copy `.env.example` to a local `.env.local` only when configuration begins. Replace placeholders locally and never commit the resulting file. Firebase must remain on the Spark plan with billing disabled.

## Current workflow

The single active developer owns implementation and performs a self-review checkpoint before moving a task to Done. Track the short Day 1 board in [`docs/task_board.md`](docs/task_board.md). No official team member is assumed to be available unless they actively join.
