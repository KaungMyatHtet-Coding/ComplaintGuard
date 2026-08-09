from __future__ import annotations

import joblib
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

from scripts.historical_similarity import find_similar, load_index


def test_similarity_is_deterministic_bounded_and_non_text(tmp_path) -> None:
    vectorizer = TfidfVectorizer().fit(["card payment failed", "mortgage loan payment"])
    matrix = vectorizer.transform(["card payment failed", "mortgage loan payment"])
    index_path = tmp_path / "index.joblib"
    joblib.dump(
        {
            "schema_version": 1,
            "method": "cosine_similarity_on_l2_normalized_tfidf",
            "model_version": "v1",
            "dataset_version": "v1",
            "mapping_version": "v1",
            "reference_partition": "held_out_test",
            "matrix": matrix,
            "labels": ("card_atm", "loan_credit"),
            "example_ids": ("a", "b"),
            "contains_narratives": False,
        },
        index_path,
    )
    result = find_similar(
        "card payment problem",
        vectorizer=vectorizer,
        index=load_index(index_path),
        top_k=2,
    )
    assert result["prediction_confidence_included"] is False
    assert result["neighbors"][0]["department_label"] == "card_atm"
    assert 0 <= result["neighbors"][0]["cosine_similarity"] <= 1
    assert all(item["contains_narrative"] is False for item in result["neighbors"])


def test_similarity_rejects_empty_query(tmp_path) -> None:
    vectorizer = TfidfVectorizer().fit(["card payment"])
    index = {
        "matrix": vectorizer.transform(["card payment"]),
        "labels": ("card_atm",),
        "example_ids": ("a",),
        "model_version": "v1",
    }
    with pytest.raises(ValueError):
        find_similar("  ", vectorizer=vectorizer, index=index)
