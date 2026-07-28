"""Validated loader and predictor for the frozen Day 9 classifier."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)


class ModelArtifactError(RuntimeError):
    """Raised when the frozen artifact is absent, corrupt, or incompatible."""


@dataclass(frozen=True)
class Prediction:
    department_id: str
    confidence: float
    fallback: bool
    fallback_reason: str | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_classifier_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class FrozenDepartmentClassifier:
    """Prediction-only wrapper around the immutable model-v1 joblib."""

    def __init__(self, artifact: dict[str, Any]) -> None:
        if artifact.get("model_version") != "v1":
            raise ModelArtifactError("model version is incompatible")
        if artifact.get("dataset_version") != "v1":
            raise ModelArtifactError("dataset version is incompatible")
        if artifact.get("mapping_version") != "v1":
            raise ModelArtifactError("mapping version is incompatible")
        if tuple(artifact.get("labels", ())) != LABELS:
            raise ModelArtifactError("model labels are incompatible")
        if artifact.get("fallback_label") != "general_support":
            raise ModelArtifactError("model fallback is incompatible")
        if artifact.get("normalization") != "NFKC + casefold + whitespace collapse":
            raise ModelArtifactError("model normalization is incompatible")
        threshold = artifact.get("confidence_threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ModelArtifactError("model confidence threshold is invalid")
        if not 0.0 <= float(threshold) <= 1.0:
            raise ModelArtifactError("model confidence threshold is out of range")
        try:
            self.vectorizer = artifact["vectorizer"]
            self.classifier = artifact["classifier"]
        except KeyError as exc:
            raise ModelArtifactError("model components are missing") from exc
        if not callable(getattr(self.vectorizer, "transform", None)):
            raise ModelArtifactError("model vectorizer is invalid")
        if not callable(getattr(self.classifier, "predict_proba", None)):
            raise ModelArtifactError("model classifier is invalid")
        classifier_classes = tuple(str(value) for value in self.classifier.classes_)
        if len(classifier_classes) != len(LABELS) or set(classifier_classes) != set(
            LABELS
        ):
            raise ModelArtifactError("classifier classes are incompatible")
        self.model_version = str(artifact["model_version"])
        self.threshold = float(threshold)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_sha256: str,
    ) -> FrozenDepartmentClassifier:
        if not path.is_file():
            raise ModelArtifactError("model artifact is missing")
        if _sha256(path) != expected_sha256:
            raise ModelArtifactError("model artifact integrity check failed")
        try:
            artifact = joblib.load(path)
        except Exception as exc:
            raise ModelArtifactError("model artifact cannot be loaded") from exc
        if not isinstance(artifact, dict):
            raise ModelArtifactError("model artifact structure is invalid")
        return cls(artifact)

    def predict(self, text: str) -> Prediction:
        normalized = _normalize_classifier_text(text)
        if not normalized:
            raise ValueError("classifier input is empty")
        matrix = self.vectorizer.transform([normalized])
        probabilities = np.asarray(self.classifier.predict_proba(matrix)[0])
        if probabilities.shape != (len(LABELS),):
            raise ModelArtifactError("classifier probability shape is invalid")
        if not np.isfinite(probabilities).all():
            raise ModelArtifactError("classifier probabilities are invalid")
        index = int(np.argmax(probabilities))
        confidence = float(probabilities[index])
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ModelArtifactError("classifier confidence is invalid")
        department = str(self.classifier.classes_[index])
        fallback = confidence < self.threshold
        if fallback:
            department = "general_support"
        if department not in LABELS:
            raise ModelArtifactError("classifier emitted an unsupported department")
        return Prediction(
            department_id=department,
            confidence=confidence,
            fallback=fallback,
            fallback_reason="low_classifier_confidence" if fallback else None,
        )
