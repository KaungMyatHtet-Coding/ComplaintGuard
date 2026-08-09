# Repository Guidelines

## Source of Truth and Current Phase

`PROJECT_PLAN.md` is the source of truth for scope, architecture, schedule, and success criteria. The project is currently in Day 20 finalization after Days 1–19 were implemented and merged. Day-specific documents are historical evidence; current operating instructions live in the root README and `docs/local_setup.md`. Preserve the frozen model, Day 18 evidence, Firebase/role boundaries, and completed complaint workflows. Day 20 is documentation, verification, demo-readiness, and academic-delivery work—not authorization for retraining, new infrastructure, deployment, or major features.

One developer is currently active even though the official team has five members. Optimize decisions for a small, demonstrable MVP and a short deadline. The active developer owns each task and performs a documented self-review before marking it done; the other official members may review or present later but are not assumed to be available for implementation.

## Non-Negotiable Constraints

- Total project cost must remain USD 0. Do not add paid APIs, paid hosting, billing-required Firebase features, SMS authentication, paid GPUs, or a custom domain.
- Use Firebase Cloud Firestore on the Spark plan for operational application data. Do not import the full historical dataset into Firestore or attach a billing account.
- Use historical CFPB complaint data in CSV or Parquet form for analysis and training.
- Use TF-IDF with Multinomial Naive Bayes as the required classification approach.
- Support English and Myanmar; document translation quality and free-tier limitations honestly.
- Never commit secrets, credentials, `.env` files, raw CFPB data, or real financial/customer information.
- Prefer synthetic demo identities and account details.

## Project Structure

- `frontend/`: planned Next.js and Tailwind CSS web application.
- `ml-api/`: planned Python FastAPI preprocessing and inference service.
- `notebooks/`: numbered profiling, EDA, and model-training notebooks.
- `data/mapping/`: deterministic CFPB Product/Issue-to-department mappings.
- `data/processed/`: only small, reproducible, privacy-reviewed samples.
- `models/`: versioned, repository-size-appropriate model artifacts.
- `firebase/`: Firestore rules and indexes.
- `docs/`: scope, architecture, data dictionary, tests, and demo documentation.
- `report/` and `presentation/`: final submission material.

Keep tests close to their component (`frontend/**/__tests__/`) or in service-level `tests/` directories.

## Current Commands

Describe commands as verified only after running them successfully in the current worktree:

- `cd frontend && npm run dev`: frontend development server; synchronizes committed aggregate evaluation evidence first.
- `cd frontend && npm run lint`: frontend lint checks.
- `cd frontend && npm test`: Vitest frontend tests.
- `cd ml-api && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`: FastAPI service using the ignored frozen model artifact.
- `cd ml-api && ..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider`: backend tests.
- `cd firebase && npm test`: isolated Auth/Firestore rules, adapters, and browser E2E verification.

Check the local environment before installing any dependency. Record setup commands in `README.md` when implementation begins.

## Coding and Data Conventions

Use 2-space indentation for TypeScript, JSON, and CSS and 4 spaces for Python. Use `PascalCase` for React components, `camelCase` for TypeScript symbols, and `snake_case` for Python modules and functions. Keep these label IDs stable across mappings, APIs, models, and Firestore:

- `transfer_payment`
- `account_support`
- `card_atm`
- `fraud_security`
- `loan_credit`
- `general_support`

Configure ESLint/Prettier for the frontend and Ruff or Black for Python when those environments are created.

## Quality, Security, and Review

Test role boundaries, bilingual input, low-confidence routing, and complaint lifecycle transitions. Name Python tests `test_*.py` and frontend tests `*.test.ts(x)`. ML evaluation must report accuracy, precision, recall, macro-F1, and a confusion matrix. The macro-F1 target of 0.70 is a target, never a result to fabricate.

Firestore authorization must be enforced in security rules, not only in the UI. Emulator tests must prove that customers cannot access other customers' tickets and staff cannot access departments not assigned to them. Validate complaint length and warn users not to submit passwords, PINs, full account/card numbers, or other sensitive information.

Before marking work complete, review changed files, run the checks available for that phase, and record evidence. Use concise imperative commit subjects such as `docs: define Day 1 project scope` or `feat(frontend): add complaint form`. Do not merge or present untested work as complete.
