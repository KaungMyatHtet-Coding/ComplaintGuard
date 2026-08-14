from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import run_stage1b_spot_check_app as app


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_record(record_id: str, department: str) -> dict[str, object]:
    text = f"Synthetic complaint for {record_id}"
    return {
        "ambiguity_notes": "Review the boundary neutrally.",
        "approved": False,
        "author": "project_owner",
        "benchmark_version": "",
        "character_count": len(text),
        "difficulty": "hard",
        "duplicate_group": "",
        "example_id": record_id,
        "expected_department": department,
        "ground_truth_rationale": "The authored rationale is preserved for review.",
        "review_status": "pending",
        "reviewer": "pending_delayed_blind_self_review",
        "source_type": "synthetic_authored",
        "split": "final",
        "text": text,
        "variation_tags": ["informal_language"],
        "word_count": len(text.split()),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> app.PathPolicy:
    departments = list(app.DEPARTMENTS) * 2
    source = [
        _candidate_record(record_id, departments[index])
        for index, record_id in enumerate(app.EXPECTED_IDS)
    ]
    source[0]["expected_department"] = "account_support"
    candidate = json.loads(json.dumps(source))
    candidate[0]["expected_department"] = "fraud_security"
    paths = {
        app.SOURCE_FILENAME: tmp_path / app.SOURCE_FILENAME,
        app.CANDIDATE_FILENAME: tmp_path / app.CANDIDATE_FILENAME,
        app.REPORT_FILENAME: tmp_path / app.REPORT_FILENAME,
        app.REVIEW_FILENAME: tmp_path / app.REVIEW_FILENAME,
        app.ADJUDICATION_FILENAME: tmp_path / app.ADJUDICATION_FILENAME,
        app.WORKING_FILENAME: tmp_path / app.WORKING_FILENAME,
    }
    paths[app.SOURCE_FILENAME].write_text(
        "".join(
            json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"
            for value in source
        ),
        encoding="utf-8",
    )
    paths[app.CANDIDATE_FILENAME].write_text(
        "".join(
            json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"
            for value in candidate
        ),
        encoding="utf-8",
    )
    _write_json(
        paths[app.REPORT_FILENAME],
        {
            "spot_check_plan": {
                "method": "Deterministic synthetic selection.",
                "record_ids": list(app.EXPECTED_IDS),
                "size": 12,
                "status": "pending",
            }
        },
    )
    with paths[app.REVIEW_FILENAME].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "complaint_text",
                "reviewer_department",
                "review_reasons",
            ],
        )
        writer.writeheader()
        for record in candidate:
            writer.writerow(
                {
                    "record_id": record["example_id"],
                    "complaint_text": record["text"],
                    "reviewer_department": record["expected_department"],
                    "review_reasons": "ambiguity_review|controlled_variation",
                }
            )
    _write_json(
        paths[app.ADJUDICATION_FILENAME],
        {
            "entries": [
                {
                    "record_id": "SEB-0176",
                    "original_department": "account_support",
                    "reviewer_department": "fraud_security",
                    "adjudication_decision": "use_reviewer",
                    "final_department": "fraud_security",
                    "adjudication_note": "Human review selected the security boundary.",
                    "revised_text": "",
                }
            ]
        },
    )
    hashes = {
        filename: _hash(path)
        for filename, path in paths.items()
        if filename != app.WORKING_FILENAME
    }
    return app._build_path_policy(
        tmp_path,
        candidate_path=paths[app.CANDIDATE_FILENAME],
        source_path=paths[app.SOURCE_FILENAME],
        report_path=paths[app.REPORT_FILENAME],
        review_path=paths[app.REVIEW_FILENAME],
        adjudication_path=paths[app.ADJUDICATION_FILENAME],
        working_path=paths[app.WORKING_FILENAME],
        expected_hashes=hashes,
    )


def _values(decision: str, department: str, rationale: str = "") -> dict[str, str]:
    return {
        "spot_check_decision": decision,
        "confirmed_department": department,
        "corrected_rationale": rationale,
        "spot_check_note": "A neutral human note explains this choice.",
    }


def test_deterministic_selection_exact_order_and_blank_fields(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    first = app.build_blank_working(policy)
    second = app.build_blank_working(policy)
    assert first == second
    assert [entry["record_id"] for entry in first["entries"]] == list(app.EXPECTED_IDS)
    assert all(
        not entry[field] for entry in first["entries"] for field in app.HUMAN_FIELDS
    )
    rendered = app.page(first, 0).decode()
    assert 'name="spot_check_decision"' in rendered
    assert " checked>" not in rendered and " selected>" not in rendered


def test_candidate_source_membership_is_verified(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    rows = app.read_jsonl(policy.candidate_path)
    rows.pop()
    policy.candidate_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    policy.expected_hashes[app.CANDIDATE_FILENAME] = _hash(policy.candidate_path)
    with pytest.raises(ValueError, match="membership"):
        app.build_blank_working(policy)


def test_seb_0176_context_is_neutral_and_complete(tmp_path: Path) -> None:
    entry = app.build_blank_working(_fixture(tmp_path))["entries"][0]
    assert entry["original_department"] == "account_support"
    assert entry["blind_review_department"] == "fraud_security"
    assert entry["candidate_department"] == "fraud_security"
    assert entry["adjudication_decision"] == "use_reviewer"
    assert entry["adjudication_note"]
    assert entry["preserved_authored_rationale"]


@pytest.mark.parametrize(
    ("decision", "department", "rationale"),
    [
        ("confirm_candidate", "fraud_security", ""),
        ("correct_rationale_only", "fraud_security", "Corrected neutral rationale."),
        ("reconsider_label", "account_support", "Revised neutral rationale."),
        ("unsuitable_example", "unresolved", ""),
        ("needs_followup", "unresolved", ""),
    ],
)
def test_valid_decision_contracts(
    tmp_path: Path, decision: str, department: str, rationale: str
) -> None:
    entry = app.build_blank_working(_fixture(tmp_path))["entries"][0]
    assert app.validate_entry(_values(decision, department, rationale), entry) == []


@pytest.mark.parametrize(
    "values",
    [
        _values("invalid", "fraud_security"),
        _values("confirm_candidate", "account_support"),
        _values("correct_rationale_only", "fraud_security"),
        _values("reconsider_label", "fraud_security", "Changed rationale."),
        _values("unsuitable_example", "fraud_security"),
        _values("needs_followup", "unresolved") | {"spot_check_note": ""},
    ],
)
def test_invalid_decision_contracts(tmp_path: Path, values: dict[str, str]) -> None:
    entry = app.build_blank_working(_fixture(tmp_path))["entries"][0]
    assert app.validate_entry(values, entry)


def test_sensitive_human_content_is_rejected(tmp_path: Path) -> None:
    entry = app.build_blank_working(_fixture(tmp_path))["entries"][0]
    values = _values("confirm_candidate", "fraud_security")
    values["spot_check_note"] = "Contact person@example.com with account number 123456."
    assert any("sensitive" in error for error in app.validate_entry(values, entry))


def test_immutable_add_delete_and_reorder_changes_are_rejected(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    blank = app.build_blank_working(policy)
    for mutation in ("immutable", "addition", "deletion", "reorder"):
        changed = json.loads(json.dumps(blank))
        if mutation == "immutable":
            changed["entries"][0]["complaint_text"] = "changed"
        elif mutation == "addition":
            changed["entries"][0]["extra"] = "changed"
        elif mutation == "deletion":
            changed["entries"].pop()
        else:
            changed["entries"][0], changed["entries"][1] = (
                changed["entries"][1],
                changed["entries"][0],
            )
        with pytest.raises(ValueError):
            app.validate_working(blank, changed)


def test_save_is_atomic_and_progress_survives_reload(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    assert app.create_working_copy(policy)
    before_candidate = _hash(policy.candidate_path)
    with patch.object(app.os, "replace", wraps=os.replace) as replace:
        assert (
            app.save_entry(policy, 0, _values("confirm_candidate", "fraud_security"))
            == []
        )
        assert replace.call_count == 1
    _blank, working = app.load_working(policy)
    assert working["entries"][0]["spot_check_decision"] == "confirm_candidate"
    assert _hash(policy.candidate_path) == before_candidate


def test_per_save_path_revalidation_occurs(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    app.create_working_copy(policy)
    original = app.validate_active_paths
    with patch.object(app, "validate_active_paths", wraps=original) as validate:
        app.save_entry(policy, 0, _values("confirm_candidate", "fraud_security"))
        assert validate.call_count >= 4


def test_working_hardlink_to_candidate_is_rejected(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    os.link(policy.candidate_path, policy.working_path)
    with pytest.raises(ValueError, match="hardlinks"):
        app.validate_active_paths(policy, working_required=True)


def test_working_path_equal_to_protected_path_is_rejected(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    with pytest.raises(ValueError, match="fixed contract"):
        app._build_path_policy(
            tmp_path,
            candidate_path=policy.candidate_path,
            source_path=policy.source_path,
            report_path=policy.report_path,
            review_path=policy.review_path,
            adjudication_path=policy.adjudication_path,
            working_path=policy.candidate_path,
            expected_hashes=policy.expected_hashes,
        )


def test_normal_save_preserves_every_protected_input(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    app.create_working_copy(policy)
    before = {path.name: _hash(path) for path in policy.protected_paths}
    assert (
        app.save_entry(policy, 0, _values("confirm_candidate", "fraud_security")) == []
    )
    assert {path.name: _hash(path) for path in policy.protected_paths} == before


def test_working_symlink_to_protected_input_is_rejected(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    try:
        policy.working_path.symlink_to(policy.report_path)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        app.validate_active_paths(policy, working_required=True)


def test_outside_directory_target_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "inside"
    directory.mkdir()
    policy = _fixture(directory)
    outside = tmp_path / app.WORKING_FILENAME
    with pytest.raises(ValueError, match="outside"):
        app._build_path_policy(
            directory,
            candidate_path=policy.candidate_path,
            source_path=policy.source_path,
            report_path=policy.report_path,
            review_path=policy.review_path,
            adjudication_path=policy.adjudication_path,
            working_path=outside,
            expected_hashes=policy.expected_hashes,
        )


def test_fixed_production_paths_and_cli_surface() -> None:
    policy = app.production_path_policy()
    assert policy.working_path == (policy.authorized_directory / app.WORKING_FILENAME)
    assert (
        policy.protected_paths[0]
        == policy.authorized_directory / app.CANDIDATE_FILENAME
    )
    assert vars(app.parse_args([])) == {"port": 8769}
    assert vars(app.parse_args(["--port", "8770"])) == {"port": 8770}


@pytest.mark.parametrize("option", ["--source", "--working", "--candidate", "--output"])
def test_unsafe_cli_path_options_are_rejected(option: str) -> None:
    result = subprocess.run(
        [sys.executable, str(Path(app.__file__)), option, "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_server_binding_is_loopback_only(tmp_path: Path) -> None:
    policy = _fixture(tmp_path)
    with patch.object(app, "ThreadingHTTPServer") as server:
        app.create_server(policy, 0)
        assert server.call_args.args[0] == ("127.0.0.1", 0)


def test_no_external_assets_environment_overrides_or_model_logic() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "<script src=" not in source and "<link href=" not in source
    assert "urlopen" not in source and "requests." not in source
    assert "os.environ" not in source and "getenv" not in source
    assert "sklearn" not in source and "joblib" not in source
    assert 'model_predictions_or_confidence_included": False' in source


def test_real_protected_hashes_and_blank_derivation() -> None:
    policy = app.production_path_policy()
    app._verify_hashes(policy)
    blank = app.build_blank_working(policy)
    assert blank["record_count"] == 12
    assert all(
        not entry[field] for entry in blank["entries"] for field in app.HUMAN_FIELDS
    )
