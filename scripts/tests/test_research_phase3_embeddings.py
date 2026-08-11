from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from research_phase3_embeddings import (
    EMBEDDING_BATCH_SIZE,
    MODEL_NAME,
    TRAIN_PER_CLASS_CAP,
    EmbeddingConfig,
    ResearchError,
    atomic_write_json,
    configure_determinism,
    encode_texts,
    short_text_summary,
    train_embedding_classifier,
    validate_research_paths,
)


class FakeEncoder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
        self.calls.append({"texts": texts, **kwargs})
        return np.array(
            [[float(index), float(index + 1), 1.0] for index, _ in enumerate(texts)],
            dtype=np.float32,
        )


def test_embedding_config_uses_declared_cpu_research_defaults() -> None:
    config = EmbeddingConfig()

    assert config.model_name == MODEL_NAME == "all-MiniLM-L6-v2"
    assert config.batch_size == EMBEDDING_BATCH_SIZE == 256
    assert config.train_per_class_cap == TRAIN_PER_CLASS_CAP == 30_000


def test_encode_texts_normalizes_through_encoder_contract() -> None:
    encoder = FakeEncoder()
    config = EmbeddingConfig(batch_size=2)

    embeddings = encode_texts(encoder, ["short text", "another text"], config)

    assert embeddings.shape == (2, 3)
    assert embeddings.dtype == np.float32
    assert encoder.calls == [
        {
            "texts": ["short text", "another text"],
            "batch_size": 2,
            "convert_to_numpy": True,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }
    ]


def test_encode_texts_rejects_non_finite_embeddings() -> None:
    class NonFiniteEncoder:
        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            return np.array([[np.nan, 1.0] for _ in texts])

    with pytest.raises(ResearchError, match="non-finite"):
        encode_texts(NonFiniteEncoder(), ["example"], EmbeddingConfig())


def test_short_text_summary_preserves_phase2b_bucket_results() -> None:
    summary = short_text_summary(
        [
            {
                "minimum_characters": 0,
                "maximum_characters": 100,
                "count": 11,
                "macro_f1": 0.55,
            },
            {
                "minimum_characters": 101,
                "maximum_characters": 300,
                "count": 7,
                "macro_f1": 0.66,
            },
            {
                "minimum_characters": 301,
                "maximum_characters": 600,
                "count": 4,
                "macro_f1": 0.71,
            },
        ]
    )

    assert summary == {
        "0_100": {
            "minimum_characters": 0,
            "maximum_characters": 100,
            "count": 11,
            "macro_f1": 0.55,
        },
        "101_300": {
            "minimum_characters": 101,
            "maximum_characters": 300,
            "count": 7,
            "macro_f1": 0.66,
        },
    }


def test_short_text_summary_requires_expected_buckets() -> None:
    with pytest.raises(ResearchError, match="short-text"):
        short_text_summary([])


def test_train_embedding_classifier_uses_balanced_logistic_regression() -> None:
    embeddings = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [1.0, 1.0],
            [1.1, 1.0],
        ],
        dtype=np.float32,
    )
    labels = np.array(
        ["account_support", "account_support", "transfer_payment", "transfer_payment"]
    )

    classifier = train_embedding_classifier(
        embeddings, labels.tolist(), EmbeddingConfig()
    )

    assert classifier.class_weight == "balanced"
    assert classifier.random_state == 20260810
    assert classifier.predict(embeddings).tolist() == labels.tolist()


@pytest.mark.parametrize(
    "protected_name",
    ["held_out_test.csv", "held-out-test.csv", "original_validation.csv"],
)
def test_protected_input_paths_are_rejected(
    tmp_path: Path, protected_name: str
) -> None:
    with pytest.raises(ResearchError, match="protected evaluation partition"):
        validate_research_paths(
            tmp_path / protected_name,
            tmp_path / "manifest.json",
            tmp_path / "result.json",
        )


def test_research_paths_must_be_distinct(tmp_path: Path) -> None:
    shared = tmp_path / "same.json"
    with pytest.raises(ResearchError, match="must be distinct"):
        validate_research_paths(shared, tmp_path / "manifest.json", shared)


def test_atomic_write_json_publishes_complete_json(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "artifact.json"
    atomic_write_json(output, {"status": "completed", "aggregate_only": True})

    assert output.read_text(encoding="utf-8") == (
        '{\n  "status": "completed",\n  "aggregate_only": true\n}\n'
    )
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_atomic_write_json_refuses_overwrite_and_cleans_temp(tmp_path: Path) -> None:
    output = tmp_path / "artifact.json"
    output.write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        atomic_write_json(output, {"status": "replacement"})

    assert output.read_text(encoding="utf-8") == "preserve me\n"
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


def test_configure_determinism_repeats_numpy_sequence() -> None:
    first_metadata = configure_determinism(1234)
    first = np.random.random(4)
    second_metadata = configure_determinism(1234)
    second = np.random.random(4)

    assert np.array_equal(first, second)
    assert first_metadata["python_random_seed"] == 1234
    assert first_metadata["numpy_random_seed"] == 1234
    assert second_metadata == first_metadata
