"""Synthetic tests for the Day 10 local bilingual inference boundary."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from scripts.bilingual_inference import (
    CHECKPOINT,
    CHECKPOINT_REVISION,
    LABELS,
    BilingualInference,
    LanguageDetection,
    detect_language,
    normalize_input,
    run_synthetic_sheet,
)
from scripts.finalize_myanmar_review import finalize_review


class SyntheticClassifier:
    def __init__(self, department: str = "general_support", fallback: bool = False):
        self.department = department
        self.fallback = fallback
        self.inputs: list[str] = []

    def classify(self, english_text: str) -> dict[str, Any]:
        self.inputs.append(english_text)
        return {
            "department": self.department,
            "confidence": 0.8,
            "fallback": self.fallback,
            "fallback_reason": ("low_classifier_confidence" if self.fallback else None),
        }


class SyntheticTranslator:
    cold_load_seconds = 0.25

    def __init__(
        self,
        translation: str = "synthetic translated request",
        runtime: float = 0.1,
        error: Exception | None = None,
    ) -> None:
        self.translation = translation
        self.runtime = runtime
        self.error = error
        self.inputs: list[str] = []

    def translate(self, text: str) -> tuple[str, float]:
        self.inputs.append(text)
        if self.error:
            raise self.error
        return self.translation, self.runtime


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  A\u0301   request\r\nnow  ", "Á request now"),
        ("English request", "English request"),
        ("ငွေ လွှဲ", "ငွေ လွှဲ"),
    ],
)
def test_normalization_is_nfc_and_collapses_whitespace(
    value: str, expected: str
) -> None:
    assert normalize_input(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Please review this payment.", LanguageDetection("en")),
        ("ငွေလွှဲမှုကို စစ်ဆေးပေးပါ။", LanguageDetection("my")),
        ("payment app မှာ ပြဿနာရှိပါတယ်။", LanguageDetection("mixed")),
        ("", LanguageDetection("invalid", "invalid_empty")),
        ("123 !!!", LanguageDetection("invalid", "invalid_no_letters")),
        ("支払いを確認", LanguageDetection("unsupported", "unsupported_script")),
    ],
)
def test_language_detection(value: str, expected: LanguageDetection) -> None:
    assert detect_language(value) == expected


def test_english_bypasses_translation() -> None:
    classifier = SyntheticClassifier("account_support")
    result = BilingualInference(classifier, None).infer("  Account   help ")
    assert result["status"] == "completed"
    assert result["translation_performed"] is False
    assert classifier.inputs == ["Account help"]


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("ငွေလွှဲမှုကို စစ်ဆေးပေးပါ။", "my"),
        ("payment app မှာ ပြဿနာရှိပါတယ်။", "mixed"),
    ],
)
def test_myanmar_and_mixed_translate_the_entire_normalized_input(
    text: str, language: str
) -> None:
    translator = SyntheticTranslator()
    classifier = SyntheticClassifier("transfer_payment")
    result = BilingualInference(classifier, translator).infer(f"  {text}  ")
    assert result["detected_language"] == language
    assert translator.inputs == [normalize_input(text)]
    assert classifier.inputs == ["synthetic translated request"]


@pytest.mark.parametrize(
    ("translator", "code"),
    [
        (None, "translation_model_unavailable"),
        (SyntheticTranslator(translation=""), "translation_empty"),
        (
            SyntheticTranslator(error=RuntimeError("private detail")),
            "translation_failed",
        ),
    ],
)
def test_translation_failure_requires_manual_review_without_sensitive_error(
    translator: SyntheticTranslator | None, code: str
) -> None:
    classifier = SyntheticClassifier("fraud_security")
    result = BilingualInference(classifier, translator).infer("ငွေလွှဲ မရပါ။")
    assert result["status"] == "manual_review_required"
    assert result["department"] == "general_support"
    assert result["classification_performed"] is False
    assert result["error"]["code"] == code
    assert "private detail" not in json.dumps(result)
    assert classifier.inputs == []


def test_translation_timeout_requires_manual_review() -> None:
    class SlowTranslator(SyntheticTranslator):
        def translate(self, text: str) -> tuple[str, float]:
            time.sleep(0.05)
            return super().translate(text)

    result = BilingualInference(
        SyntheticClassifier(), SlowTranslator(), timeout_seconds=0.001
    ).infer("ကတ် ပြဿနာရှိပါတယ်။")
    assert result["error"]["code"] == "translation_timeout"
    assert result["classification_performed"] is False


def test_slow_translation_is_nonfatal_warning() -> None:
    result = BilingualInference(
        SyntheticClassifier("loan_credit"),
        SyntheticTranslator(runtime=5.01),
    ).infer("ချေးငွေ ပြဿနာရှိပါတယ်။")
    assert result["status"] == "completed"
    assert result["department"] == "loan_credit"
    assert result["warnings"] == ["translation_slow"]


def test_low_classifier_confidence_remains_distinct_from_translation_failure() -> None:
    result = BilingualInference(
        SyntheticClassifier(fallback=True), SyntheticTranslator()
    ).infer("အကူအညီ လိုပါတယ်။")
    assert result["status"] == "completed"
    assert result["classification_performed"] is True
    assert result["fallback_reason"] == "low_classifier_confidence"
    assert result["error"] is None


def test_invalid_input_never_classifies() -> None:
    classifier = SyntheticClassifier()
    result = BilingualInference(classifier, None).infer("... 123")
    assert result["error"]["code"] == "invalid_no_letters"
    assert result["classification_performed"] is False
    assert classifier.inputs == []


def test_synthetic_sheet_is_aggregate_safe_and_pending_human_review(
    tmp_path: Path,
) -> None:
    cases = [
        {
            "case_id": f"{label}_{index}",
            "input_text": "အကူအညီ လိုပါတယ်။",
            "expected_english_intent": "A fictional request for assistance.",
            "expected_department": label,
        }
        for label in LABELS
        for index in range(5)
    ]

    class MatchingClassifier(SyntheticClassifier):
        def __init__(self) -> None:
            super().__init__()
            self.index = 0

        def classify(self, english_text: str) -> dict[str, Any]:
            department = LABELS[self.index // 5]
            self.index += 1
            return {
                "department": department,
                "confidence": 0.9,
                "fallback": False,
                "fallback_reason": None,
            }

    output = tmp_path / "sheet.json"
    evidence = run_synthetic_sheet(
        cases,
        BilingualInference(MatchingClassifier(), SyntheticTranslator()),
        output,
        checkpoint_cache_size_bytes=123,
    )
    assert evidence["checkpoint"] == CHECKPOINT
    assert evidence["revision"] == CHECKPOINT_REVISION
    assert evidence["status"] == "pending_owner_review"
    assert evidence["case_count"] == 30
    assert evidence["classification"]["correct"] == 30
    assert evidence["translation_review"]["pending"] == 30
    assert evidence["translation_review"]["acceptance"] is None
    assert output.is_file()
    with pytest.raises(FileExistsError):
        run_synthetic_sheet(
            cases,
            BilingualInference(MatchingClassifier(), SyntheticTranslator()),
            output,
            checkpoint_cache_size_bytes=123,
        )


@pytest.mark.parametrize("case_count", [0, 29])
def test_synthetic_sheet_rejects_too_few_cases(tmp_path: Path, case_count: int) -> None:
    cases = [
        {
            "case_id": str(index),
            "input_text": "synthetic",
            "expected_english_intent": "synthetic",
            "expected_department": LABELS[index % len(LABELS)],
        }
        for index in range(case_count)
    ]
    with pytest.raises(ValueError, match="at least 30"):
        run_synthetic_sheet(
            cases,
            BilingualInference(SyntheticClassifier(), None),
            tmp_path / "sheet.json",
            checkpoint_cache_size_bytes=0,
        )


def test_owner_review_finalization_preserves_approved_fields(
    tmp_path: Path,
) -> None:
    scores = [0] * 16 + [1] * 9 + [2] * 5
    preliminary = {
        "rubric": {"0": "unusable", "1": "usable", "2": "clear"},
        "cases": [
            {
                "case_id": f"synthetic_{index:02d}",
                "preliminary_score": score,
                "meaning_issue": f"Approved synthetic note {index}.",
                "suggested_translation": f"Approved synthetic correction {index}.",
            }
            for index, score in enumerate(scores)
        ],
    }
    results = {
        "cases": [
            {
                "case_id": f"synthetic_{index:02d}",
                "classification_correct": index < 11,
            }
            for index in range(30)
        ]
    }
    preliminary_path = tmp_path / "preliminary.json"
    results_path = tmp_path / "results.json"
    output_path = tmp_path / "final.json"
    preliminary_path.write_text(json.dumps(preliminary), encoding="utf-8")
    results_path.write_text(json.dumps(results), encoding="utf-8")
    evidence = finalize_review(preliminary_path, results_path, output_path)
    assert evidence["review_status"] == "owner_approved"
    assert evidence["reviewer_role"] == "project_owner"
    assert evidence["aggregate"]["usable_score_1_or_2"] == 14
    assert evidence["aggregate"]["classification_correct"] == 11
    assert evidence["aggregate"]["overall_acceptance"] == "failed"
    assert (
        evidence["cases"][0]["reviewer_note"]
        == preliminary["cases"][0]["meaning_issue"]
    )
    assert (
        evidence["cases"][0]["meaning_loss"] == preliminary["cases"][0]["meaning_issue"]
    )
    assert (
        evidence["cases"][0]["suggested_correction"]
        == preliminary["cases"][0]["suggested_translation"]
    )
    with pytest.raises(FileExistsError):
        finalize_review(preliminary_path, results_path, output_path)
