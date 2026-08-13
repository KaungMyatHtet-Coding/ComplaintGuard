"""Tests for the frozen-classifier CPU benchmark harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.benchmark_baseline_classifier import (
    SYNTHETIC_INPUTS,
    BenchmarkConfig,
    input_set_sha256,
    latency_summary,
    measure_calls,
    percentile_nearest_rank,
    run_benchmark,
    validate_config,
)


def test_input_hash_is_stable_and_uses_canonical_serialization() -> None:
    expected = hashlib.sha256(
        json.dumps(
            list(SYNTHETIC_INPUTS),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert input_set_sha256() == expected
    assert input_set_sha256() == input_set_sha256()


def test_latency_metrics_use_measured_values_only() -> None:
    values = [8.0, 1.0, 4.0, 2.0, 20.0]
    assert latency_summary(values) == {
        "median_ms": 4.0,
        "p95_ms": 20.0,
        "minimum_ms": 1.0,
        "maximum_ms": 20.0,
    }
    assert percentile_nearest_rank(list(range(1, 101)), 95.0) == 95


def test_warmup_calls_are_separate_from_measured_calls() -> None:
    calls: list[str] = []

    def predict(text: str) -> None:
        calls.append(text)

    warmup = measure_calls(predict, ("one", "two"), 3)
    measured = measure_calls(predict, ("one", "two"), 2)
    assert len(warmup) == 3
    assert len(measured) == 2
    assert calls == ["one", "two", "one", "one", "two"]


@pytest.mark.parametrize("warmup,measured", [(-1, 1), (0, 0), (1, -1)])
def test_invalid_run_counts_are_rejected(
    tmp_path: Path, warmup: int, measured: int
) -> None:
    model = tmp_path / "model.joblib"
    model.write_bytes(b"unchanged")
    config = BenchmarkConfig(
        model_path=model,
        output_path=tmp_path / "result.json",
        warmup_runs=warmup,
        measured_runs=measured,
    )
    with pytest.raises(ValueError):
        validate_config(config)


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    model = tmp_path / "model.joblib"
    output = tmp_path / "result.json"
    model.write_bytes(b"model")
    output.write_text("protected", encoding="utf-8")
    with pytest.raises(FileExistsError):
        validate_config(BenchmarkConfig(model_path=model, output_path=output))
    assert output.read_text(encoding="utf-8") == "protected"


def test_real_harness_records_required_fields_and_preserves_model(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    model = repository_root / "models/generated/cfpb_department_model_v1.joblib"
    if not model.is_file():
        pytest.skip("ignored frozen model artifact is not installed")
    before = hashlib.sha256(model.read_bytes()).hexdigest()
    output = tmp_path / "result.json"
    result = run_benchmark(
        BenchmarkConfig(
            model_path=model,
            output_path=output,
            warmup_runs=2,
            measured_runs=8,
        )
    )
    after = hashlib.sha256(model.read_bytes()).hexdigest()

    assert before == after == result["model"]["sha256_before"]
    assert result["model"]["sha256_after"] == before
    assert result["configuration"]["cpu_only"] is True
    assert result["configuration"]["network_required"] is False
    assert result["configuration"]["warmup_runs"] == 2
    assert result["configuration"]["measured_runs"] == 8
    assert result["configuration"]["input_count"] == len(SYNTHETIC_INPUTS)
    assert result["inputs"]["sha256"] == input_set_sha256()
    assert result["timings"]["warmup"]["run_count"] == 2
    assert result["timings"]["single_request_inference"]["run_count"] == 8
    assert result["timings"]["batch_inference"]["supported"] is False
    assert result["environment"]["python_version"]
    assert result["memory"]["after_inference"]["method"]
    assert output.is_file()
    assert "http" not in json.dumps(result).lower()
