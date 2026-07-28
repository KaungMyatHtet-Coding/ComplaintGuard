# ComplaintGuard local ML API

Day 11 exposes the frozen Day 9 TF-IDF and Multinomial Naive Bayes classifier
through a local FastAPI service.

## Scope and privacy

- `GET /health` reports service and model readiness without exposing paths.
- `POST /predict` accepts one English complaint and returns a stable department
  ID, classifier probability, detected language, model version, and fallback
  state.
- Myanmar and mixed input are detected but rejected with the structured
  `myanmar_not_production_ready` error. Day 10 translation is development
  evidence and is not an approved production path.
- The API does not persist requests, translations, predictions, datasets, or
  model artifacts. It does not connect to Firestore.
- Do not submit passwords, PINs, full card/account numbers, or other sensitive
  information.

The maximum input length is 5,000 Unicode code points before normalization.
Empty, whitespace-only, wrong-type, unsupported-script, extra-field, and
over-limit requests receive structured errors without echoing complaint text.

## Local setup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ml-api/requirements.txt
cd ml-api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The default model is the ignored
`models/generated/cfpb_department_model_v1.joblib`. Startup verifies its
SHA-256, model/dataset/mapping versions, label order, normalization, confidence
threshold, fallback, vectorizer, and classifier before serving predictions.
Missing, corrupt, or incompatible artifacts leave `/health` in `degraded`
state and make `/predict` return `model_unavailable`.

## Tests

```powershell
cd ml-api
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

All test text is fictional and synthetic.
