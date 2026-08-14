"""Validate and analyze Stage 1B authored-label/human-review agreement."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
EXPECTED_HASHES = {
    "completed_review": "b3975a3604a82ae594e851673a9092054cc74f3294ca70c34ca9195541416cc3",
    "pristine_worksheet": "1c1771b3ab77daa7bb0d30807faadf23ad76b1ed298c1d38d891f71094ce34b1",
    "draft_benchmark": "f9ae2ab171c51b630a081c770e6db48bc06d0924f3823da4827643c2562553f7",
}
IMMUTABLE_COLUMNS = (
    "review_order",
    "record_id",
    "complaint_text",
    "review_reasons",
    "word_count",
)
REFERENCE_FIELDS = {
    "review_order",
    "record_id",
    "original_department",
    "original_difficulty",
    "original_review_reasons",
    "source_queue_position",
}
REFERENCE_TOP_FIELDS = {
    "status",
    "do_not_consult_during_blind_review",
    "not_human_review_results",
    "not_approval_evidence",
    "contains_predictions",
    "contains_confidence",
    "deterministic_shuffle",
    "source_draft_sha256",
    "record_count",
    "records",
}
ORDERING_SEED = "stage1b-disagreement-queue-v1"


class AnalysisError(ValueError):
    """Raised when protected evidence or its contract is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AnalysisError(f"{path} must be UTF-8 without BOM")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalysisError(f"{path} is not valid UTF-8") from exc
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"invalid JSON in {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                records.append(json.loads(line))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"invalid JSONL in {path} at line {line_number}") from exc
    return records


def _find_forbidden_fields(value: Any, path: str = "$") -> list[str]:
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.casefold()
            if (
                "prediction" in lowered
                or "predicted" in lowered
                or "confidence" in lowered
            ) and key not in {
                "contains_predictions",
                "contains_confidence",
            }:
                findings.append(f"{path}.{key}")
            findings.extend(_find_forbidden_fields(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_forbidden_fields(child, f"{path}[{index}]"))
    return findings


def validate_reference(reference: Any, draft_hash: str) -> list[dict[str, Any]]:
    if not isinstance(reference, dict) or set(reference) != REFERENCE_TOP_FIELDS:
        raise AnalysisError("sealed reference top-level schema is invalid")
    markers = {
        "status": "internal_reference_only",
        "do_not_consult_during_blind_review": True,
        "not_human_review_results": True,
        "not_approval_evidence": True,
        "contains_predictions": False,
        "contains_confidence": False,
    }
    for key, expected in markers.items():
        if reference.get(key) != expected:
            raise AnalysisError(f"sealed reference marker {key!r} is invalid")
    shuffle = reference.get("deterministic_shuffle")
    if not isinstance(shuffle, dict) or shuffle.get("seed") != 20260814:
        raise AnalysisError("sealed reference shuffle seed is invalid")
    if reference.get("source_draft_sha256", "").casefold() != draft_hash.casefold():
        raise AnalysisError("sealed reference source draft SHA-256 is invalid")
    records = reference.get("records")
    if (
        not isinstance(records, list)
        or reference.get("record_count") != 73
        or len(records) != 73
    ):
        raise AnalysisError("sealed reference must contain exactly 73 records")
    if any(
        not isinstance(record, dict) or set(record) != REFERENCE_FIELDS
        for record in records
    ):
        raise AnalysisError("sealed reference record schema is invalid")
    ids = [record["record_id"] for record in records]
    if len(set(ids)) != 73:
        raise AnalysisError("sealed reference record IDs are not unique")
    if _find_forbidden_fields(reference):
        raise AnalysisError("sealed reference contains prediction or confidence fields")
    return records


def _unique_by_id(
    records: list[dict[str, Any]], id_field: str, source: str
) -> dict[str, dict[str, Any]]:
    result = {}
    for record in records:
        record_id = record.get(id_field)
        if not isinstance(record_id, str) or not record_id:
            raise AnalysisError(f"{source} contains a missing record ID")
        if record_id in result:
            raise AnalysisError(f"{source} contains duplicate record ID {record_id}")
        result[record_id] = record
    return result


def validate_inputs(
    completed_rows: list[dict[str, str]],
    pristine_rows: list[dict[str, str]],
    reference_records: list[dict[str, Any]],
    draft_records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if len(completed_rows) != 73 or len(pristine_rows) != 73:
        raise AnalysisError(
            "completed review and pristine worksheet must each contain 73 rows"
        )
    completed = _unique_by_id(completed_rows, "record_id", "completed review")
    pristine = _unique_by_id(pristine_rows, "record_id", "pristine worksheet")
    reference = _unique_by_id(reference_records, "record_id", "sealed reference")
    draft = _unique_by_id(draft_records, "example_id", "draft benchmark")
    if set(completed) != set(pristine):
        raise AnalysisError(
            "completed review membership differs from pristine worksheet"
        )
    if set(completed) != set(reference):
        missing = sorted(set(completed) - set(reference))
        extra = sorted(set(reference) - set(completed))
        raise AnalysisError(
            f"sealed reference membership differs: missing={missing} extra={extra}"
        )
    if not set(completed) <= set(draft):
        raise AnalysisError(
            "completed review contains a record missing from draft benchmark"
        )
    for record_id, row in completed.items():
        pristine_row = pristine[record_id]
        if any(
            row.get(column) != pristine_row.get(column) for column in IMMUTABLE_COLUMNS
        ):
            raise AnalysisError(f"immutable worksheet fields differ for {record_id}")
        if row.get("reviewer_decision") != "approve":
            raise AnalysisError(f"review decision is not approve for {record_id}")
        if row.get("reviewer_department") not in LABELS:
            raise AnalysisError(f"invalid reviewer label for {record_id}")
        if reference[record_id].get("original_department") not in LABELS:
            raise AnalysisError(f"invalid original label for {record_id}")
        if draft[record_id].get("expected_department") != reference[record_id].get(
            "original_department"
        ):
            raise AnalysisError(
                f"draft/reference original label mismatch for {record_id}"
            )
        if row.get("complaint_text") != draft[record_id].get("text"):
            raise AnalysisError(
                f"worksheet/draft complaint text mismatch for {record_id}"
            )
    return reference, draft


def cohen_kappa(matrix: dict[str, dict[str, int]], total: int) -> float:
    observed = sum(matrix[label][label] for label in LABELS) / total
    row_totals = {label: sum(matrix[label].values()) for label in LABELS}
    column_totals = {
        label: sum(matrix[row][label] for row in LABELS) for label in LABELS
    }
    expected = (
        sum(row_totals[label] * column_totals[label] for label in LABELS) / total**2
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _group_summary(items: list[tuple[str, bool]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[bool]] = {}
    for name, agrees in items:
        grouped.setdefault(name, []).append(agrees)
    return {
        name: {
            "reviewed_count": len(values),
            "agreement_count": sum(values),
            "agreement_rate": sum(values) / len(values),
        }
        for name, values in sorted(grouped.items())
    }


def analyze_records(
    completed_rows: list[dict[str, str]],
    reference: dict[str, dict[str, Any]],
    draft: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    matrix = {row: {column: 0 for column in LABELS} for row in LABELS}
    difficulty_items: list[tuple[str, bool]] = []
    reason_items: list[tuple[str, bool]] = []
    variation_items: list[tuple[str, bool]] = []
    controlled_items: list[tuple[str, bool]] = []
    disagreements = []
    original_distribution: Counter[str] = Counter()
    reviewer_distribution: Counter[str] = Counter()
    pairwise: Counter[str] = Counter()
    for row in completed_rows:
        record_id = row["record_id"]
        source = reference[record_id]
        draft_record = draft[record_id]
        original = source["original_department"]
        reviewer = row["reviewer_department"]
        agrees = original == reviewer
        matrix[original][reviewer] += 1
        original_distribution[original] += 1
        reviewer_distribution[reviewer] += 1
        difficulty_items.append((source["original_difficulty"], agrees))
        reasons = sorted(filter(None, row["review_reasons"].split("|")))
        variations = sorted(set(draft_record.get("variation_tags", [])))
        source_reasons = source["original_review_reasons"]
        if not isinstance(source_reasons, list):
            raise AnalysisError(f"invalid sealed review reasons for {record_id}")
        for reason in reasons:
            reason_items.append((reason, agrees))
        for variation in variations:
            variation_items.append((variation, agrees))
        controlled_items.append(
            (
                "present" if "controlled_variation" in source_reasons else "absent",
                agrees,
            )
        )
        if not agrees:
            pairwise[f"{original}->{reviewer}"] += 1
            disagreements.append(
                {
                    "record_id": record_id,
                    "complaint_text": row["complaint_text"],
                    "original_department": original,
                    "reviewer_department": reviewer,
                    "original_difficulty": source["original_difficulty"],
                    "review_reasons": reasons,
                    "controlled_variation_flags": variations,
                }
            )
    total = len(completed_rows)
    agreement_count = sum(matrix[label][label] for label in LABELS)
    per_label = {}
    for label in LABELS:
        reviewed_count = sum(matrix[label].values())
        per_label[label] = {
            "reviewed_count": reviewed_count,
            "agreement_count": matrix[label][label],
            "agreement_rate": (
                matrix[label][label] / reviewed_count if reviewed_count else None
            ),
        }
    metrics = {
        "record_count": total,
        "agreement_count": agreement_count,
        "disagreement_count": total - agreement_count,
        "exact_agreement_percentage": agreement_count / total * 100,
        "cohens_kappa": cohen_kappa(matrix, total),
        "original_department_distribution": {
            label: original_distribution[label] for label in LABELS
        },
        "reviewer_department_distribution": {
            label: reviewer_distribution[label] for label in LABELS
        },
        "confusion_matrix": {
            "orientation": "rows=original_department; columns=reviewer_department",
            "label_order": list(LABELS),
            "values": [[matrix[row][column] for column in LABELS] for row in LABELS],
        },
        "per_original_department_agreement": per_label,
        "difficulty_agreement": _group_summary(difficulty_items),
        "review_reason_agreement": _group_summary(reason_items),
        "controlled_variation_status_agreement": _group_summary(controlled_items),
        "controlled_variation_type_agreement": _group_summary(variation_items),
        "pairwise_disagreement_counts": dict(sorted(pairwise.items())),
        "disagreement_record_ids": sorted(item["record_id"] for item in disagreements),
    }
    return metrics, disagreements


def deterministic_queue(disagreements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        disagreements,
        key=lambda item: hashlib.sha256(
            f"{ORDERING_SEED}:{item['record_id']}".encode()
        ).hexdigest(),
    )
    return [
        {
            "adjudication_order": index,
            **item,
            "adjudication_decision": "",
            "final_department": "",
            "revised_text": "",
            "adjudication_note": "",
        }
        for index, item in enumerate(ordered, start=1)
    ]


def build_outputs(
    *,
    completed_path: Path,
    pristine_path: Path,
    reference_path: Path,
    draft_path: Path,
    expected_hashes: dict[str, str],
    git_commit: str,
    unsealed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {
        "completed_review": completed_path,
        "pristine_worksheet": pristine_path,
        "sealed_reference": reference_path,
        "draft_benchmark": draft_path,
    }
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    for name, expected in expected_hashes.items():
        if hashes[name].casefold() != expected.casefold():
            raise AnalysisError(f"protected input hash differs for {name}")
    _completed_columns, completed_rows = load_csv(completed_path)
    _pristine_columns, pristine_rows = load_csv(pristine_path)
    reference_data = load_json(reference_path)
    reference_records = validate_reference(reference_data, hashes["draft_benchmark"])
    draft_records = load_jsonl(draft_path)
    reference, draft = validate_inputs(
        completed_rows, pristine_rows, reference_records, draft_records
    )
    metrics, disagreements = analyze_records(completed_rows, reference, draft)
    queue_entries = deterministic_queue(disagreements)
    per_label_rates = {
        label: values["agreement_rate"]
        for label, values in metrics["per_original_department_agreement"].items()
        if values["agreement_rate"] is not None
    }
    sorted_rates = sorted(per_label_rates.values())
    median_rate = (
        sorted_rates[len(sorted_rates) // 2 - 1] + sorted_rates[len(sorted_rates) // 2]
    ) / 2
    materially_lower_labels = [
        {
            "original_department": label,
            "agreement_rate": rate,
            "comparison_median_rate": median_rate,
            "gap_below_median": median_rate - rate,
        }
        for label, rate in per_label_rates.items()
        if median_rate - rate >= 0.10
    ]
    disagreement_pair_flags = [
        {
            "original_to_reviewer": pair,
            "disagreement_count": count,
            "human_adjudication_required": True,
        }
        for pair, count in sorted(
            metrics["pairwise_disagreement_counts"].items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    inputs = {
        name: {"path": path.as_posix(), "sha256": hashes[name]}
        for name, path in paths.items()
    }
    analysis = {
        "analysis_status": "descriptive_agreement_analysis_complete_no_adjudication",
        "git_commit_analyzed": git_commit,
        "controlled_unsealing_timestamp": unsealed_at,
        "inputs": inputs,
        "record_counts": {
            "completed_review": len(completed_rows),
            "unique_completed_record_ids": len(
                {row["record_id"] for row in completed_rows}
            ),
            "sealed_reference_mappings": len(reference_records),
            "disagreement_queue": len(queue_entries),
        },
        "metrics": metrics,
        "quality_flags": {
            "materially_lower_department_definition": "at least 0.10 below the median per-original-department agreement rate",
            "materially_lower_original_departments": materially_lower_labels,
            "disagreement_department_pairs": disagreement_pair_flags,
        },
        "interpretation": {
            "metric_boundary": "Agreement is not model accuracy; no model was evaluated.",
            "kappa_scope": "Cohen's kappa describes agreement between authored label proposals and one delayed blind human review.",
            "single_reviewer_limitation": "One delayed blind reviewer cannot establish inter-annotator reliability.",
            "decision_coverage_limitation": "All 73 reviewer decisions were approve, so rejection and revision quality was not exercised.",
            "high_agreement_limitation": "High or perfect agreement does not prove benchmark validity; a post-unsealing spot check of hard and ambiguous examples is recommended.",
            "worksheet_blinding_check": "The pristine worksheet contains complaint text, neutral review reasons, word count, and empty human-entry fields; it contains no original/proposed label, difficulty, rationale, prediction, or confidence column.",
            "spot_check_recommendation": "Spot-check hard and ambiguity-review records because all 73 decisions were approve, even if no disagreements enter the queue.",
        },
        "safeguards": {
            "no_disagreement_adjudicated": True,
            "no_benchmark_record_modified": True,
            "original_labels_are_proposals_not_automatic_ground_truth": True,
            "reviewer_labels_are_human_judgments_not_automatic_replacements": True,
            "benchmark_status": "draft_unfrozen",
        },
    }
    queue = {
        "status": "unadjudicated_disagreement_queue",
        "git_commit_analyzed": git_commit,
        "controlled_unsealing_timestamp": unsealed_at,
        "ordering": {
            "method": "ascending SHA-256 of fixed seed, colon, and record_id",
            "fixed_seed": ORDERING_SEED,
            "independent_of_original_and_reviewer_labels": True,
        },
        "queue_size": len(queue_entries),
        "entries": queue_entries,
        "safeguards": {
            "no_agreement_records_included": True,
            "no_final_department_preselected_or_recommended": True,
            "no_adjudication_occurred": True,
            "empty_queue_does_not_mean_benchmark_approval": not queue_entries,
            "spot_check_still_recommended_because_all_decisions_were_approve": True,
        },
    }
    return analysis, queue


def write_json_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("evaluation/model_hunting")
    parser.add_argument(
        "--completed",
        type=Path,
        default=root / "short_english_benchmark_stage1b_completed_review.csv",
    )
    parser.add_argument(
        "--pristine",
        type=Path,
        default=root / "short_english_benchmark_stage1b_review_worksheet.csv",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=root / "short_english_benchmark_stage1b_reference.json",
    )
    parser.add_argument(
        "--draft", type=Path, default=root / "short_english_benchmark_draft_v1.jsonl"
    )
    parser.add_argument(
        "--analysis-output",
        type=Path,
        default=root / "short_english_benchmark_stage1b_agreement_analysis.json",
    )
    parser.add_argument(
        "--queue-output",
        type=Path,
        default=root / "short_english_benchmark_stage1b_disagreement_queue.json",
    )
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--unsealed-at", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        datetime.fromisoformat(args.unsealed_at)
        analysis, queue = build_outputs(
            completed_path=args.completed,
            pristine_path=args.pristine,
            reference_path=args.reference,
            draft_path=args.draft,
            expected_hashes=EXPECTED_HASHES,
            git_commit=args.git_commit,
            unsealed_at=args.unsealed_at,
        )
        write_json_new(args.analysis_output, analysis)
        write_json_new(args.queue_output, queue)
    except (AnalysisError, OSError, ValueError) as exc:
        print(f"Stage 1B agreement analysis failed: {type(exc).__name__}: {exc}")
        return 1
    metrics = analysis["metrics"]
    print(
        "Stage 1B agreement analysis passed: "
        f"records={metrics['record_count']} "
        f"agreements={metrics['agreement_count']} "
        f"disagreements={metrics['disagreement_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
