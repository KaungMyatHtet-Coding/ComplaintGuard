"""Query a privacy-minimized local historical TF-IDF similarity index."""

from __future__ import annotations

import argparse
import json
import math
import unicodedata
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.sparse import spmatrix


class SimilarityError(RuntimeError):
    """Raised when a similarity index or query is unsafe or incompatible."""


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def load_index(path: Path) -> dict[str, Any]:
    value = joblib.load(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SimilarityError("similarity index schema is incompatible")
    if value.get("method") != "cosine_similarity_on_l2_normalized_tfidf":
        raise SimilarityError("similarity method is incompatible")
    if value.get("contains_narratives") is not False:
        raise SimilarityError("similarity index privacy contract is invalid")
    matrix = value.get("matrix")
    labels = value.get("labels")
    example_ids = value.get("example_ids")
    if not isinstance(matrix, spmatrix):
        raise SimilarityError("similarity matrix is invalid")
    if not isinstance(labels, tuple) or not isinstance(example_ids, tuple):
        raise SimilarityError("similarity reference metadata is invalid")
    if matrix.shape[0] != len(labels) or len(labels) != len(example_ids):
        raise SimilarityError("similarity index rows do not reconcile")
    return value


def find_similar(
    text: str,
    *,
    vectorizer: Any,
    index: dict[str, Any],
    top_k: int = 5,
) -> dict[str, Any]:
    """Return cosine scores and non-text neighbor metadata for one query."""
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("similarity query is empty")
    if top_k <= 0 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")
    query = vectorizer.transform([normalized])
    matrix = index["matrix"]
    if query.shape[1] != matrix.shape[1]:
        raise SimilarityError("query vectorizer and index dimensions differ")
    scores = np.asarray((matrix @ query.T).toarray()).reshape(-1)
    if not np.isfinite(scores).all():
        raise SimilarityError("similarity scores are invalid")
    positions = np.argsort(-scores, kind="stable")[: min(top_k, len(scores))]
    neighbors = [
        {
            "rank": rank,
            "historical_example_id": index["example_ids"][int(position)],
            "department_label": index["labels"][int(position)],
            "cosine_similarity": float(scores[int(position)]),
            "contains_narrative": False,
        }
        for rank, position in enumerate(positions, start=1)
    ]
    for neighbor in neighbors:
        score = neighbor["cosine_similarity"]
        if not math.isfinite(score) or score < -1e-6 or score > 1.000001:
            raise SimilarityError("cosine similarity is outside its expected range")
    return {
        "method": "cosine_similarity_on_l2_normalized_tfidf",
        "reference_records": int(matrix.shape[0]),
        "model_version": index["model_version"],
        "prediction_confidence_included": False,
        "neighbors": neighbors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    artifact = joblib.load(args.model)
    result = find_similar(
        args.text,
        vectorizer=artifact["vectorizer"],
        index=load_index(args.index),
        top_k=args.top_k,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
