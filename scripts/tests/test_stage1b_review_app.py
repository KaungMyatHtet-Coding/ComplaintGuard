"""Tests for the local-only Stage 1B review application."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.run_stage1b_review_app as app


def pristine_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "pristine.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=app.FIELDS, lineterminator="\n")
        writer.writeheader()
        for index in range(1, 74):
            writer.writerow(
                {
                    "review_order": index,
                    "record_id": f"SEB-{index:04d}",
                    "complaint_text": f"Synthetic complaint number {index}",
                    "review_reasons": "hard_label_confirmation",
                    "word_count": 4,
                    **{field: "" for field in app.HUMAN_FIELDS},
                }
            )
    return path


def create_fixture_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    pristine = pristine_fixture(tmp_path)
    working = tmp_path / "working.csv"
    digest = hashlib.sha256(pristine.read_bytes()).hexdigest()
    monkeypatch.setattr(app, "PRISTINE_SHA256", digest)
    assert app.create_working_copy(pristine, working)
    return pristine, working


def valid_entry(decision: str = "approve") -> dict[str, str]:
    return {
        "reviewer_decision": decision,
        "reviewer_department": "general_support",
        "revised_text": "",
        "reviewer_note": "",
    }


def test_working_copy_preserves_pristine_and_all_73_blank_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    before = pristine.read_bytes()
    assert working.read_bytes() == before
    rows = app.read_rows(working)
    assert len(rows) == 73
    assert len({row["record_id"] for row in rows}) == 73
    assert all(not row[field] for row in rows for field in app.HUMAN_FIELDS)
    assert pristine.read_bytes() == before


def test_existing_working_copy_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    working.write_text("saved progress", encoding="utf-8")
    assert not app.create_working_copy(pristine, working)
    assert working.read_text(encoding="utf-8") == "saved progress"


def test_valid_approve_and_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    assert app.save_entry(working, 0, valid_entry()) == []
    assert app.read_rows(working)[0]["reviewer_decision"] == "approve"


def test_valid_revise_saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    values = valid_entry("revise") | {
        "revised_text": "Support never explained the complaint outcome",
        "reviewer_note": "Clarified the complete complaint wording.",
    }
    assert app.save_entry(working, 1, values) == []
    assert app.read_rows(working)[1]["revised_text"] == values["revised_text"]


@pytest.mark.parametrize("decision", ["reject", "unsure"])
def test_reject_and_unsure_require_notes(decision: str) -> None:
    assert app.validate_entry(valid_entry(decision)) == [
        f"{decision.capitalize()} requires a reviewer note."
    ]


def test_revise_requires_valid_text_and_note() -> None:
    errors = app.validate_entry(valid_entry("revise"))
    assert "Revision requires complete replacement wording." in errors
    assert "Revision requires a reviewer note." in errors
    too_short = valid_entry("revise") | {
        "revised_text": "Too short",
        "reviewer_note": "Reason",
    }
    assert "Revised text must contain 3–20 words." in app.validate_entry(too_short)


@pytest.mark.parametrize(
    ("field", "value"),
    [("reviewer_decision", "automatic"), ("reviewer_department", "hidden_label")],
)
def test_invalid_values_are_rejected(field: str, value: str) -> None:
    entry = valid_entry()
    entry[field] = value
    assert app.validate_entry(entry)


def test_immutable_fields_and_pristine_hash_survive_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    before_hash = hashlib.sha256(pristine.read_bytes()).hexdigest()
    before = app.immutable_snapshot(app.read_rows(working))
    app.save_entry(working, 2, valid_entry())
    assert app.immutable_snapshot(app.read_rows(working)) == before
    assert hashlib.sha256(pristine.read_bytes()).hexdigest() == before_hash


def test_page_is_blind_and_has_no_default_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    rendered = app.page(app.read_rows(working), 0).decode()
    assert "original_department" not in rendered
    assert "predicted_department" not in rendered
    assert "confidence_score" not in rendered
    assert (
        'type="radio" name="reviewer_decision" value="approve" checked' not in rendered
    )
    assert '<option value="general_support" selected>' not in rendered


def test_server_is_loopback_only_and_reference_is_not_in_runtime_source() -> None:
    assert app.HOST == "127.0.0.1"
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "stage1b_reference" not in source
    assert "expected_department" not in source


def test_atomic_write_uses_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pristine, working = create_fixture_copy(tmp_path, monkeypatch)
    rows = app.read_rows(working)
    real_replace = app.os.replace
    calls: list[tuple[str, Path]] = []

    def observed_replace(source: str, destination: Path) -> None:
        calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(app.os, "replace", observed_replace)
    app.atomic_write_rows(working, rows)
    assert len(calls) == 1
    assert Path(calls[0][0]).parent == working.parent
    assert calls[0][1] == working


def test_handler_has_no_file_serving_route() -> None:
    handler = app.ReviewHandler.__new__(app.ReviewHandler)
    handler.path = "/sealed-reference.json"
    handler.requestline = "GET /sealed-reference.json HTTP/1.1"
    handler.command = "GET"
    handler.request_version = "HTTP/1.1"
    handler.wfile = io.BytesIO()
    with patch.object(handler, "send_error") as send_error:
        handler.do_GET()
    send_error.assert_called_once_with(404)
