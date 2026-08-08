"""Trusted bilingual inference and operational routing policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.language import detect_language, normalize_input
from app.model import LABELS, FrozenDepartmentClassifier

TRANSLATION_CHECKPOINT = "Helsinki-NLP/opus-mt-mul-en"
TRANSLATION_REVISION = "848eae0c1676cfce9bb791c200e8228e5a6396ff"


class Translator(Protocol):
    def translate(self, text: str) -> str: ...


class RoutingInferenceError(RuntimeError):
    """A sanitized inference failure that must leave the ticket unrouted."""

    def __init__(self, code: str, detected_language: str) -> None:
        super().__init__(code)
        self.code = code
        self.detected_language = detected_language


@dataclass(frozen=True)
class RoutingPrediction:
    department_id: str
    confidence: float
    detected_language: str
    requires_manual_review: bool
    manual_review_reason: str | None
    model_version: str


class OfflineMyanmarTranslator:
    """Lazy, local-only translator pinned to the evaluated Day 10 revision."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or Path(
            os.getenv(
                "COMPLAINTGUARD_HF_CACHE",
                Path.home() / ".cache" / "complaintguard" / "huggingface",
            )
        )
        self._tokenizer = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                TRANSLATION_CHECKPOINT,
                revision=TRANSLATION_REVISION,
                cache_dir=self.cache_dir,
                local_files_only=True,
            )
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                TRANSLATION_CHECKPOINT,
                revision=TRANSLATION_REVISION,
                cache_dir=self.cache_dir,
                local_files_only=True,
                use_safetensors=False,
            )
            self._model.eval()
        except Exception as exc:
            raise RoutingInferenceError("translation_model_unavailable", "my") from exc

    def translate(self, text: str) -> str:
        self._load()
        try:
            import torch

            encoded = self._tokenizer(
                [text], return_tensors="pt", truncation=True, max_length=512
            )
            with torch.inference_mode():
                generated = self._model.generate(
                    **encoded, max_new_tokens=256, num_beams=4, do_sample=False
                )
            translated = self._tokenizer.batch_decode(
                generated, skip_special_tokens=True
            )[0]
        except Exception as exc:
            raise RoutingInferenceError("translation_failed", "my") from exc
        normalized = normalize_input(translated)
        if not normalized:
            raise RoutingInferenceError("translation_empty", "my")
        return normalized


class TrustedRoutingInference:
    """Run real inference and apply the explicit operational review policy."""

    def __init__(
        self,
        classifier: FrozenDepartmentClassifier,
        *,
        confidence_threshold: float,
        translator: Translator | None = None,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("routing confidence threshold must be between 0 and 1")
        self.classifier = classifier
        self.confidence_threshold = confidence_threshold
        self.translator = translator

    def predict(self, complaint_text: str) -> RoutingPrediction:
        language = detect_language(complaint_text)
        if language not in {"en", "my", "mixed"}:
            raise RoutingInferenceError("unsupported_input", language)
        classifier_text = complaint_text
        if language in {"my", "mixed"}:
            if self.translator is None:
                raise RoutingInferenceError("translation_model_unavailable", language)
            try:
                classifier_text = self.translator.translate(complaint_text)
            except RoutingInferenceError as exc:
                raise RoutingInferenceError(exc.code, language) from exc
        try:
            prediction = self.classifier.predict(classifier_text)
        except Exception as exc:
            raise RoutingInferenceError("classification_failed", language) from exc
        if prediction.department_id not in LABELS:
            raise RoutingInferenceError("unknown_prediction_label", language)

        # Day 10 translation quality was not accepted, so genuine Myanmar
        # predictions are review evidence only and never automatic routing.
        myanmar_review = language in {"my", "mixed"}
        low_confidence = prediction.confidence < self.confidence_threshold
        reason = (
            "myanmar_translation_not_approved"
            if myanmar_review
            else "low_prediction_confidence"
            if low_confidence
            else None
        )
        return RoutingPrediction(
            department_id=prediction.department_id,
            confidence=prediction.confidence,
            detected_language=language,
            requires_manual_review=myanmar_review or low_confidence,
            manual_review_reason=reason,
            model_version=self.classifier.model_version,
        )
