"""Normalize owner-approved Day 10 preliminary review evidence."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from scripts.bilingual_inference import file_sha256
else:
    from bilingual_inference import file_sha256

EXPECTED_SCORE_COUNTS = {0: 16, 1: 9, 2: 5}
EXPECTED_CLASSIFICATION_CORRECT = 11
EXPECTED_CASE_COUNT = 30


def finalize_review(
    preliminary_path: Path, results_path: Path, output_path: Path
) -> dict[str, Any]:
    """Validate and atomically normalize an approved preliminary review."""
    if output_path.exists():
        raise FileExistsError("refusing to overwrite final owner review evidence")
    preliminary = json.loads(preliminary_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    cases = preliminary.get("cases")
    result_cases = results.get("cases")
    if not isinstance(cases, list) or not isinstance(result_cases, list):
        raise TypeError("review and inference cases must be arrays")
    case_ids = [case.get("case_id") for case in cases]
    if len(case_ids) != EXPECTED_CASE_COUNT or len(set(case_ids)) != len(case_ids):
        raise ValueError("review must contain exactly 30 unique case IDs")
    result_by_id = {case.get("case_id"): case for case in result_cases}
    if set(case_ids) != set(result_by_id):
        raise ValueError("review and inference case IDs do not reconcile")
    required = {"preliminary_score", "meaning_issue", "suggested_translation"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("a review case is missing an owner-approved field")
    score_counts = Counter(case["preliminary_score"] for case in cases)
    if dict(score_counts) != EXPECTED_SCORE_COUNTS:
        raise ValueError("owner-review score distribution is inconsistent")
    classification_correct = sum(
        bool(result_by_id[case_id].get("classification_correct"))
        for case_id in case_ids
    )
    if classification_correct != EXPECTED_CLASSIFICATION_CORRECT:
        raise ValueError("classification correctness is inconsistent")
    usable = score_counts[1] + score_counts[2]
    final_cases = []
    for case in cases:
        result = result_by_id[case["case_id"]]
        final_cases.append(
            {
                "case_id": case["case_id"],
                "score": case["preliminary_score"],
                "reviewer_note": case["meaning_issue"],
                "meaning_loss": case["meaning_issue"],
                "suggested_correction": case["suggested_translation"],
                "classification_correct": bool(result["classification_correct"]),
            }
        )
    evidence = {
        "schema_version": 1,
        "review_status": "owner_approved",
        "reviewer_role": "project_owner",
        "source_preliminary_review": preliminary_path.name,
        "source_preliminary_review_sha256": file_sha256(preliminary_path),
        "source_inference_results": results_path.name,
        "source_inference_results_sha256": file_sha256(results_path),
        "scoring_rubric": preliminary["rubric"],
        "aggregate": {
            "total": EXPECTED_CASE_COUNT,
            "score_2": score_counts[2],
            "score_1": score_counts[1],
            "score_0": score_counts[0],
            "usable_score_1_or_2": usable,
            "usable_rate": usable / EXPECTED_CASE_COUNT,
            "required_usable": 24,
            "translation_acceptance": "failed",
            "classification_correct": classification_correct,
            "classification_total": EXPECTED_CASE_COUNT,
            "classification_rate": (classification_correct / EXPECTED_CASE_COUNT),
            "required_classification_correct": 24,
            "classification_acceptance": "failed",
            "overall_acceptance": "failed",
        },
        "cases": final_cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preliminary", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = finalize_review(args.preliminary, args.results, args.output)
    print(
        "Owner review finalized: "
        f"cases={evidence['aggregate']['total']} "
        f"usable={evidence['aggregate']['usable_score_1_or_2']} "
        f"classification_correct={evidence['aggregate']['classification_correct']} "
        "acceptance=failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
