"""Day 10 local English/Myanmar translation and frozen-model inference."""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np

CHECKPOINT = "Helsinki-NLP/opus-mt-mul-en"
CHECKPOINT_REVISION = "848eae0c1676cfce9bb791c200e8228e5a6396ff"
MODEL_VERSION = "v1"
MAPPING_VERSION = "v1"
DATASET_VERSION = "v1"
LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
MYANMAR_RANGES = ((0x1000, 0x109F), (0xA9E0, 0xA9FF), (0xAA60, 0xAA7F))
SLOW_TRANSLATION_SECONDS = 5.0
DEFAULT_TRANSLATION_TIMEOUT_SECONDS = 30.0


class TranslatorProtocol(Protocol):
    cold_load_seconds: float

    def translate(self, text: str) -> tuple[str, float]: ...


class ClassifierProtocol(Protocol):
    def classify(self, english_text: str) -> dict[str, Any]: ...


class ArtifactError(RuntimeError):
    """Raised for missing, corrupt, or incompatible local artifacts."""


@dataclass(frozen=True)
class LanguageDetection:
    language: str
    error_code: str | None = None


def default_cache_dir() -> Path:
    """Return a user-local cache outside the repository."""
    configured = os.environ.get("COMPLAINTGUARD_HF_CACHE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "complaintguard" / "huggingface"


def normalize_input(value: str) -> str:
    """Apply NFC and safe whitespace normalization without transliteration."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def _is_myanmar(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in MYANMAR_RANGES)


def detect_language(value: str) -> LanguageDetection:
    """Classify English, Myanmar, mixed, empty, or unsupported script."""
    normalized = normalize_input(value)
    if not normalized:
        return LanguageDetection("invalid", "invalid_empty")
    myanmar = any(_is_myanmar(character) for character in normalized)
    latin = any(
        "LATIN" in unicodedata.name(character, "")
        and unicodedata.category(character).startswith("L")
        for character in normalized
    )
    letters = [
        character
        for character in normalized
        if unicodedata.category(character).startswith("L")
    ]
    if not letters:
        return LanguageDetection("invalid", "invalid_no_letters")
    unsupported = any(
        not _is_myanmar(character) and "LATIN" not in unicodedata.name(character, "")
        for character in letters
    )
    if unsupported:
        return LanguageDetection("unsupported", "unsupported_script")
    if myanmar and latin:
        return LanguageDetection("mixed")
    if myanmar:
        return LanguageDetection("my")
    if latin:
        return LanguageDetection("en")
    return LanguageDetection("unsupported", "unsupported_script")


def _safe_failure(
    language: str,
    error_code: str,
    message: str,
    *,
    translation_seconds: float | None = None,
) -> dict[str, Any]:
    return {
        "status": "manual_review_required",
        "detected_language": language,
        "department": "general_support",
        "confidence": None,
        "fallback": True,
        "fallback_reason": "translation_failure"
        if language in {"my", "mixed"}
        else "invalid_input",
        "classification_performed": False,
        "translation_performed": False,
        "translation_seconds": translation_seconds,
        "warnings": [],
        "error": {"code": error_code, "message": message},
    }


class FrozenClassifier:
    """Validated adapter for the ignored frozen Day 9 model artifact."""

    def __init__(self, artifact: dict[str, Any]) -> None:
        if artifact.get("model_version") != MODEL_VERSION:
            raise ArtifactError("classifier model version is incompatible")
        if artifact.get("dataset_version") != DATASET_VERSION:
            raise ArtifactError("classifier dataset version is incompatible")
        if artifact.get("mapping_version") != MAPPING_VERSION:
            raise ArtifactError("classifier mapping version is incompatible")
        if tuple(artifact.get("labels", ())) != LABELS:
            raise ArtifactError("classifier label order is incompatible")
        if artifact.get("fallback_label") != "general_support":
            raise ArtifactError("classifier fallback contract is incompatible")
        threshold = artifact.get("confidence_threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ArtifactError("classifier confidence threshold is invalid")
        self.vectorizer = artifact["vectorizer"]
        self.classifier = artifact["classifier"]
        self.threshold = float(threshold)

    @classmethod
    def load(cls, path: Path) -> FrozenClassifier:
        if not path.is_file():
            raise ArtifactError("classifier artifact is missing")
        try:
            artifact = joblib.load(path)
        except Exception as exc:
            raise ArtifactError("classifier artifact cannot be loaded") from exc
        if not isinstance(artifact, dict):
            raise ArtifactError("classifier artifact structure is invalid")
        return cls(artifact)

    def classify(self, english_text: str) -> dict[str, Any]:
        try:
            from scripts.train_department_baseline import normalize_text
        except ModuleNotFoundError:
            from train_department_baseline import normalize_text

        normalized = normalize_text(english_text)
        if not normalized:
            raise ValueError("English classifier input is empty")
        matrix = self.vectorizer.transform([normalized])
        probabilities = self.classifier.predict_proba(matrix)[0]
        index = int(np.argmax(probabilities))
        department = str(self.classifier.classes_[index])
        confidence = float(probabilities[index])
        fallback = confidence < self.threshold
        if fallback:
            department = "general_support"
        if department not in LABELS:
            raise ArtifactError("classifier emitted an unsupported department")
        return {
            "department": department,
            "confidence": confidence,
            "fallback": fallback,
            "fallback_reason": "low_classifier_confidence" if fallback else None,
        }


class OfflineTranslator:
    """Local-only AutoTokenizer/AutoModel translator at the frozen revision."""

    def __init__(self, cache_dir: Path) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        started = time.perf_counter()
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                CHECKPOINT,
                revision=CHECKPOINT_REVISION,
                cache_dir=cache_dir,
                local_files_only=True,
            )
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                CHECKPOINT,
                revision=CHECKPOINT_REVISION,
                cache_dir=cache_dir,
                local_files_only=True,
                use_safetensors=False,
            )
            self.model.eval()
        except Exception as exc:
            raise ArtifactError(
                "local translation model is missing, corrupt, or incompatible"
            ) from exc
        self.cold_load_seconds = time.perf_counter() - started

    def translate(self, text: str) -> tuple[str, float]:
        import torch

        started = time.perf_counter()
        encoded = self.tokenizer(
            [text],
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        with torch.inference_mode():
            generated = self.model.generate(
                **encoded,
                max_new_tokens=256,
                num_beams=4,
                do_sample=False,
            )
        translated = self.tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        return normalize_input(translated), time.perf_counter() - started


class BilingualInference:
    """Route validated English/Myanmar input through the frozen contract."""

    def __init__(
        self,
        classifier: ClassifierProtocol,
        translator: TranslatorProtocol | None,
        *,
        timeout_seconds: float = DEFAULT_TRANSLATION_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("translation timeout must be positive")
        self.classifier = classifier
        self.translator = translator
        self.timeout_seconds = timeout_seconds

    def infer(self, value: str) -> dict[str, Any]:
        normalized = normalize_input(value)
        detection = detect_language(normalized)
        if detection.error_code:
            message = (
                "Enter a complaint using English or Myanmar letters."
                if detection.error_code != "invalid_empty"
                else "Enter a complaint before continuing."
            )
            return _safe_failure(detection.language, detection.error_code, message)
        english_text = normalized
        translation_seconds: float | None = None
        warnings: list[str] = []
        translation_performed = False
        if detection.language in {"my", "mixed"}:
            if self.translator is None:
                return _safe_failure(
                    detection.language,
                    "translation_model_unavailable",
                    "Myanmar translation is unavailable. Your complaint requires manual review.",
                )
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self.translator.translate, normalized)
            try:
                english_text, translation_seconds = future.result(
                    timeout=self.timeout_seconds
                )
            except FutureTimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                return _safe_failure(
                    detection.language,
                    "translation_timeout",
                    "Translation took too long. Your complaint requires manual review.",
                    translation_seconds=self.timeout_seconds,
                )
            except Exception:  # noqa: BLE001 - sanitize translator boundary errors.
                executor.shutdown(wait=False, cancel_futures=True)
                return _safe_failure(
                    detection.language,
                    "translation_failed",
                    "Translation failed. Your complaint requires manual review.",
                )
            executor.shutdown(wait=True)
            if not english_text:
                return _safe_failure(
                    detection.language,
                    "translation_empty",
                    "Translation produced no usable text. Your complaint requires manual review.",
                    translation_seconds=translation_seconds,
                )
            translation_performed = True
            if (
                translation_seconds is not None
                and translation_seconds > SLOW_TRANSLATION_SECONDS
            ):
                warnings.append("translation_slow")
        try:
            classification = self.classifier.classify(english_text)
        except Exception:  # noqa: BLE001 - sanitize classifier boundary errors.
            return _safe_failure(
                detection.language,
                "classification_failed",
                "Classification failed. Your complaint requires manual review.",
                translation_seconds=translation_seconds,
            )
        return {
            "status": "completed",
            "detected_language": detection.language,
            "department": classification["department"],
            "confidence": classification["confidence"],
            "fallback": classification["fallback"],
            "fallback_reason": classification["fallback_reason"],
            "classification_performed": True,
            "translation_performed": translation_performed,
            "translation_seconds": translation_seconds,
            "warnings": warnings,
            "error": None,
            "english_text": english_text,
            "normalized_input": normalized,
        }


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def run_synthetic_sheet(
    cases: list[dict[str, Any]],
    pipeline: BilingualInference,
    output_path: Path,
    *,
    checkpoint_cache_size_bytes: int,
) -> dict[str, Any]:
    """Run approved synthetic cases and atomically publish review evidence."""
    if output_path.exists():
        raise FileExistsError("refusing to overwrite Day 10 test-sheet evidence")
    if len(cases) < 30:
        raise ValueError("at least 30 synthetic cases are required")
    expected_counts = {
        label: sum(case.get("expected_department") == label for case in cases)
        for label in LABELS
    }
    if min(expected_counts.values()) < 5:
        raise ValueError("each department requires at least five synthetic cases")
    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    translation_times: list[float] = []
    classification_correct = {label: 0 for label in LABELS}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in seen_ids:
            raise ValueError("synthetic case IDs must be unique strings")
        seen_ids.add(case_id)
        result = pipeline.infer(str(case.get("input_text", "")))
        expected = str(case.get("expected_department", ""))
        correct = (
            result["classification_performed"] and result["department"] == expected
        )
        if correct:
            classification_correct[expected] += 1
        if result["translation_seconds"] is not None:
            translation_times.append(float(result["translation_seconds"]))
        results.append(
            {
                "case_id": case_id,
                "synthetic_input": case["input_text"],
                "expected_english_intent": case["expected_english_intent"],
                "expected_department": expected,
                "normalized_input": result.get("normalized_input"),
                "detected_language": result["detected_language"],
                "english_translation": result.get("english_text"),
                "predicted_department": result["department"],
                "confidence": result["confidence"],
                "fallback": result["fallback"],
                "fallback_reason": result["fallback_reason"],
                "classification_performed": result["classification_performed"],
                "classification_correct": bool(correct),
                "translation_seconds": result["translation_seconds"],
                "warnings": result["warnings"],
                "error": result["error"],
                "translation_review_score": None,
                "translation_review_result": "pending_owner_review",
            }
        )
    first_translation = translation_times[0] if translation_times else None
    warm = translation_times[1:]
    total_correct = sum(classification_correct.values())
    evidence = {
        "schema_version": 1,
        "status": "pending_owner_review",
        "checkpoint": CHECKPOINT,
        "revision": CHECKPOINT_REVISION,
        "cache_size_bytes": checkpoint_cache_size_bytes,
        "model_version": MODEL_VERSION,
        "dataset_version": DATASET_VERSION,
        "mapping_version": MAPPING_VERSION,
        "case_count": len(results),
        "expected_department_counts": expected_counts,
        "runtime_seconds": {
            "cold_model_load": getattr(pipeline.translator, "cold_load_seconds", None),
            "first_translation": first_translation,
            "warm_p50": statistics.median(warm) if warm else None,
            "warm_p95_nearest_rank": _nearest_rank(warm, 0.95),
            "warm_max": max(warm) if warm else None,
            "slow_warning_threshold": SLOW_TRANSLATION_SECONDS,
        },
        "classification": {
            "correct": total_correct,
            "total": len(results),
            "per_department_correct": classification_correct,
            "per_department_total": expected_counts,
            "provisional_acceptance": (
                total_correct >= 24
                and all(classification_correct[label] >= 3 for label in LABELS)
            ),
        },
        "translation_review": {
            "score_0": 0,
            "score_1": 0,
            "score_2": 0,
            "pending": len(results),
            "acceptance": None,
            "note": "Owner review is required; no human score was fabricated.",
        },
        "privacy": {
            "synthetic_only": True,
            "contains_real_complaints": False,
            "contains_complaint_ids": False,
            "contains_credentials": False,
        },
        "cases": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return evidence


def directory_size(path: Path) -> int:
    """Return physical file bytes without double-counting snapshot symlinks."""
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and not item.is_symlink()
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
