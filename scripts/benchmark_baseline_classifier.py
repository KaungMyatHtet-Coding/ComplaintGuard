"""Measure the frozen ComplaintGuard classifier on deterministic CPU inputs."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ML_API_ROOT = REPOSITORY_ROOT / "ml-api"
if str(ML_API_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_API_ROOT))

from app.config import MODEL_SHA256
from app.model import FrozenDepartmentClassifier

SCHEMA_VERSION = "1.0"
DEFAULT_SEED = 20260813
DEFAULT_WARMUP_RUNS = 20
DEFAULT_MEASURED_RUNS = 500
DEFAULT_MODEL_PATH = (
    REPOSITORY_ROOT / "models/generated/cfpb_department_model_v1.joblib"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT / "evaluation/model_hunting/baseline_performance_v1.json"
)
SYNTHETIC_INPUTS = (
    "My bank transfer was deducted but the recipient did not receive it.",
    "I cannot sign in to my online banking account.",
    "The cash machine kept my debit card.",
    "There is a purchase I did not authorize on my account.",
    "My loan payment was recorded incorrectly.",
    "I need help understanding a fee on my statement.",
)


@dataclass(frozen=True)
class BenchmarkConfig:
    model_path: Path = DEFAULT_MODEL_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    expected_model_sha256: str = MODEL_SHA256
    warmup_runs: int = DEFAULT_WARMUP_RUNS
    measured_runs: int = DEFAULT_MEASURED_RUNS
    seed: int = DEFAULT_SEED


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_set_sha256(inputs: tuple[str, ...] = SYNTHETIC_INPUTS) -> str:
    serialized = json.dumps(
        list(inputs), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def validate_config(config: BenchmarkConfig) -> None:
    if config.warmup_runs < 0:
        raise ValueError("warmup runs must be zero or greater")
    if config.measured_runs <= 0:
        raise ValueError("measured runs must be greater than zero")
    if not config.model_path.is_file():
        raise FileNotFoundError("frozen model artifact is missing")
    if config.output_path.exists():
        raise FileExistsError("refusing to overwrite benchmark output")
    if config.model_path.resolve() == config.output_path.resolve():
        raise ValueError("benchmark output must not be the model artifact")


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("latency values must not be empty")
    if not 0.0 < percentile <= 100.0:
        raise ValueError("percentile must be greater than zero and at most 100")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100.0 * len(ordered)) - 1)
    return ordered[index]


def latency_summary(latencies_ms: list[float]) -> dict[str, float]:
    if not latencies_ms:
        raise ValueError("latency values must not be empty")
    return {
        "median_ms": statistics.median(latencies_ms),
        "p95_ms": percentile_nearest_rank(latencies_ms, 95.0),
        "minimum_ms": min(latencies_ms),
        "maximum_ms": max(latencies_ms),
    }


def _windows_process_memory() -> dict[str, Any] | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    if not get_process_memory_info(
        get_current_process(), ctypes.byref(counters), counters.cb
    ):
        return None
    return {
        "method": "Windows GetProcessMemoryInfo PROCESS_MEMORY_COUNTERS_EX",
        "working_set_bytes": int(counters.WorkingSetSize),
        "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
        "private_usage_bytes": int(counters.PrivateUsage),
        "limitation": (
            "OS-reported process working-set values include the Python runtime and "
            "already-loaded libraries; peak growth can be zero if an earlier process "
            "peak was higher."
        ),
    }


def process_memory() -> dict[str, Any]:
    windows = _windows_process_memory()
    if windows is not None:
        return windows
    return {
        "method": "unavailable",
        "working_set_bytes": None,
        "peak_working_set_bytes": None,
        "private_usage_bytes": None,
        "limitation": (
            "No reliable process-memory method was available from the standard "
            "library on this platform; no package was installed."
        ),
    }


def measure_calls(
    predict: Callable[[str], Any], inputs: tuple[str, ...], run_count: int
) -> list[float]:
    latencies_ms: list[float] = []
    for index in range(run_count):
        started_ns = time.perf_counter_ns()
        predict(inputs[index % len(inputs)])
        latencies_ms.append((time.perf_counter_ns() - started_ns) / 1_000_000)
    return latencies_ms


def run_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    validate_config(config)
    model_hash_before = sha256_file(config.model_path)
    if model_hash_before.lower() != config.expected_model_sha256.lower():
        raise ValueError(
            "frozen model SHA-256 mismatch: "
            f"expected {config.expected_model_sha256.upper()}, "
            f"actual {model_hash_before.upper()}"
        )

    memory_before = process_memory()
    load_started_ns = time.perf_counter_ns()
    classifier = FrozenDepartmentClassifier.load(
        config.model_path, expected_sha256=config.expected_model_sha256
    )
    loading_ms = (time.perf_counter_ns() - load_started_ns) / 1_000_000
    memory_after_load = process_memory()

    warmup_latencies = measure_calls(
        classifier.predict, SYNTHETIC_INPUTS, config.warmup_runs
    )
    measured_latencies = measure_calls(
        classifier.predict, SYNTHETIC_INPUTS, config.measured_runs
    )
    memory_after_inference = process_memory()

    model_hash_after = sha256_file(config.model_path)
    if model_hash_after != model_hash_before:
        raise RuntimeError("frozen model artifact changed during benchmarking")

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "benchmark": "frozen_v1_cpu_inference",
        "configuration": {
            "seed": config.seed,
            "warmup_runs": config.warmup_runs,
            "measured_runs": config.measured_runs,
            "input_count": len(SYNTHETIC_INPUTS),
            "input_order": "fixed; measured calls cycle through the input tuple",
            "cpu_only": True,
            "network_required": False,
            "model_loading_included_in_inference": False,
        },
        "inputs": {
            "source": "repository-owned synthetic non-sensitive English text",
            "sha256": input_set_sha256(),
            "serialization": "compact UTF-8 JSON array in fixed tuple order",
            "texts_in_output": False,
        },
        "model": {
            "path": config.model_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256_before": model_hash_before,
            "sha256_after": model_hash_after,
            "size_bytes": config.model_path.stat().st_size,
            "version": classifier.model_version,
            "artifact_threshold": classifier.threshold,
        },
        "timings": {
            "model_loading_ms": loading_ms,
            "warmup": {
                "run_count": config.warmup_runs,
                **(latency_summary(warmup_latencies) if warmup_latencies else {}),
            },
            "single_request_inference": {
                "run_count": config.measured_runs,
                **latency_summary(measured_latencies),
            },
            "batch_inference": {
                "supported": False,
                "reason": (
                    "FrozenDepartmentClassifier.predict accepts one complaint; the "
                    "production prediction interface has no batch contract."
                ),
            },
        },
        "memory": {
            "before_model_load": memory_before,
            "after_model_load": memory_after_load,
            "after_inference": memory_after_inference,
        },
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "operating_system": platform.system(),
            "os_release": platform.release(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "logical_cpu_count": os.cpu_count(),
        },
        "limitations": [
            "This is one local CPU environment and does not represent all computers.",
            (
                "Timing includes Python-call, normalization, vectorization, "
                "probability, and validation overhead but excludes process startup "
                "and model loading."
            ),
            "Thread scheduling, power state, and other local workload can affect timing.",
        ],
    }
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with config.output_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return result


def parse_args() -> BenchmarkConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--warmup-runs", type=int, default=DEFAULT_WARMUP_RUNS)
    parser.add_argument("--measured-runs", type=int, default=DEFAULT_MEASURED_RUNS)
    args = parser.parse_args()
    return BenchmarkConfig(
        model_path=args.model,
        output_path=args.output,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )


def main() -> int:
    config = parse_args()
    try:
        result = run_benchmark(config)
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    timings = result["timings"]["single_request_inference"]
    print(
        f"Baseline benchmark completed: load={result['timings']['model_loading_ms']:.3f} ms "
        f"median={timings['median_ms']:.3f} ms p95={timings['p95_ms']:.3f} ms"
    )
    print(f"Wrote non-overwriting result to {config.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
