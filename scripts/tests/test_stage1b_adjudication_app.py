"""Synthetic tests for the local Stage 1B adjudication interface."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
from pathlib import Path

import pytest

import scripts.run_stage1b_adjudication_app as app


def fixture_source() -> dict:
    ids = sorted(app.EXPECTED_IDS)
    entries = []
    for index, record_id in enumerate(ids, start=1):
        entries.append(
            {
                "adjudication_order": index,
                "record_id": record_id,
                "complaint_text": f"Synthetic complaint wording {index}",
                "original_department": "account_support",
                "reviewer_department": "fraud_security",
                "original_difficulty": "hard",
                "review_reasons": ["ambiguity_review"],
                "controlled_variation_flags": [],
                "adjudication_decision": "",
                "final_department": "",
                "revised_text": "",
                "adjudication_note": "",
            }
        )
    return {
        "status": "unadjudicated_disagreement_queue",
        "queue_size": 10,
        "entries": entries,
        "safeguards": {"no_adjudication_occurred": True},
    }


def write_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> app.PathPolicy:
    source = tmp_path / app.SOURCE_FILENAME
    source.write_text(
        json.dumps(fixture_source(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(
        app, "SOURCE_SHA256", hashlib.sha256(source.read_bytes()).hexdigest()
    )
    working = tmp_path / app.WORKING_FILENAME
    return app._build_path_policy(tmp_path, source, working)


def valid_values(decision: str) -> dict[str, str]:
    values = {
        "adjudication_decision": decision,
        "final_department": "",
        "revised_text": "",
        "adjudication_note": "Synthetic human explanation for this decision.",
    }
    if decision == "keep_original":
        values["final_department"] = "account_support"
    elif decision == "use_reviewer":
        values["final_department"] = "fraud_security"
    elif decision == "revise_and_relabel":
        values["final_department"] = "loan_credit"
        values["revised_text"] = "My loan payment was recorded late"
    else:
        values["final_department"] = "unresolved"
    return values


def test_working_copy_creation_is_exact_blank_and_preserves_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    before = policy.source_path.read_bytes()
    assert app.create_working_copy(policy) is True
    assert policy.working_path.read_bytes() == before
    assert policy.source_path.read_bytes() == before
    _, document = app.load_working(policy)
    assert len(document["entries"]) == 10
    assert all(
        not entry[field] for entry in document["entries"] for field in app.HUMAN_FIELDS
    )
    assert app.create_working_copy(policy) is False


def test_initial_page_has_no_default_selection() -> None:
    document = fixture_source()
    rendered = app.page(document, 0).decode()
    assert 'name="adjudication_decision"' in rendered
    assert " checked" not in rendered
    assert " selected" not in rendered
    assert "Record 1 of 10" in rendered
    assert "Original/authored department" in rendered
    assert "Blind-review department" in rendered
    assert "Final completion summary" in rendered


@pytest.mark.parametrize(
    "decision",
    [
        "keep_original",
        "use_reviewer",
        "revise_and_relabel",
        "remove_from_benchmark",
        "needs_second_review",
    ],
)
def test_each_valid_decision_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    assert app.save_entry(policy, 0, valid_values(decision)) == []
    _, saved = app.load_working(policy)
    assert saved["entries"][0]["adjudication_decision"] == decision
    assert app.is_complete(saved["entries"][0])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("adjudication_decision", "automatic_choice", "valid adjudication decision"),
        ("final_department", "other", "valid final department"),
        ("adjudication_note", "", "requires a note"),
    ],
)
def test_invalid_choice_or_missing_note_is_rejected(
    field: str, value: str, message: str
) -> None:
    entry = fixture_source()["entries"][0]
    values = valid_values("keep_original")
    values[field] = value
    assert any(message in error for error in app.validate_entry(values, entry))


@pytest.mark.parametrize(
    ("decision", "department"),
    [
        ("keep_original", "fraud_security"),
        ("use_reviewer", "account_support"),
        ("remove_from_benchmark", "general_support"),
        ("needs_second_review", "general_support"),
        ("revise_and_relabel", "unresolved"),
    ],
)
def test_decision_department_mismatch_is_rejected(
    decision: str, department: str
) -> None:
    entry = fixture_source()["entries"][0]
    values = valid_values(decision)
    values["final_department"] = department
    assert app.validate_entry(values, entry)


@pytest.mark.parametrize(
    "revised",
    [
        "",
        "Two words",
        "word " * 21,
        "x" * 141,
        "Synthetic complaint wording 1!",
    ],
)
def test_revised_text_rules_are_enforced(revised: str) -> None:
    entry = fixture_source()["entries"][0]
    values = valid_values("revise_and_relabel")
    values["revised_text"] = revised
    assert app.validate_entry(values, entry)


@pytest.mark.parametrize(
    "decision",
    ["keep_original", "use_reviewer", "remove_from_benchmark", "needs_second_review"],
)
def test_non_revision_decisions_reject_revised_text(decision: str) -> None:
    entry = fixture_source()["entries"][0]
    values = valid_values(decision)
    values["revised_text"] = "This text should not be present"
    assert app.validate_entry(values, entry)


@pytest.mark.parametrize(
    "value",
    [
        "Contact me at person@example.com",
        "Call +1 555 123 4567",
        "My account number is listed here",
        r"Saved under C:\Users\Someone\file.txt",
    ],
)
def test_sensitive_human_text_is_rejected(value: str) -> None:
    entry = fixture_source()["entries"][0]
    values = valid_values("keep_original")
    values["adjudication_note"] = value
    assert any("sensitive" in error for error in app.validate_entry(values, entry))


@pytest.mark.parametrize("mutation", ["edit", "add", "delete", "reorder"])
def test_immutable_change_addition_deletion_or_reordering_is_rejected(
    mutation: str,
) -> None:
    source = fixture_source()
    working = copy.deepcopy(source)
    if mutation == "edit":
        working["entries"][0]["complaint_text"] = "Changed"
    elif mutation == "add":
        working["entries"].append(copy.deepcopy(working["entries"][0]))
    elif mutation == "delete":
        working["entries"].pop()
    else:
        working["entries"][0], working["entries"][1] = (
            working["entries"][1],
            working["entries"][0],
        )
    with pytest.raises(ValueError):
        app.validate_working(source, working)


def test_saved_progress_survives_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    app.save_entry(policy, 3, valid_values("needs_second_review"))
    _, reloaded = app.load_working(policy)
    assert reloaded["entries"][3]["adjudication_decision"] == "needs_second_review"
    assert app.create_working_copy(policy) is False
    _, resumed = app.load_working(policy)
    assert resumed == reloaded


def test_atomic_write_replaces_from_same_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    original_replace = os.replace
    observed: list[tuple[Path, Path]] = []

    def recording_replace(source: str, destination: Path) -> None:
        observed.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(app.os, "replace", recording_replace)
    value = json.loads(policy.working_path.read_text(encoding="utf-8"))
    app.atomic_write_working(policy, value)
    assert len(observed) == 1
    assert observed[0][0].parent == policy.authorized_directory
    assert observed[0][1] == policy.working_path
    assert json.loads(policy.working_path.read_text(encoding="utf-8")) == value


def test_loopback_only_no_external_assets_and_no_model_logic() -> None:
    source = inspect.getsource(app)
    rendered = app.page(fixture_source(), 0).decode()
    assert app.HOST == "127.0.0.1"
    assert app.DEFAULT_PORT == 8767
    assert "http://" not in rendered and "https://" not in rendered
    assert "<script" not in rendered and "<link" not in rendered
    assert "sklearn" not in source
    assert "joblib" not in source
    assert ".predict(" not in source
    assert "confidence score" not in rendered.casefold()
    assert "preferred" not in rendered.casefold()


def test_cli_help_exposes_only_port(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        app.parse_args(["--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--port" in help_text
    assert "--source" not in help_text
    assert "--working" not in help_text


@pytest.mark.parametrize("option", ["--source", "--working"])
def test_cli_rejects_path_override(
    option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        app.parse_args([option, "redirect.json"])
    assert exit_info.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_production_policy_uses_only_fixed_repository_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    evaluation = repository / app.EVALUATION_RELATIVE
    evaluation.mkdir(parents=True)
    source = evaluation / app.SOURCE_FILENAME
    source.write_text(json.dumps(fixture_source(), indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(app, "ROOT", repository)
    policy = app.production_path_policy()
    assert policy.source_path == source.resolve()
    assert policy.working_path == evaluation.resolve() / app.WORKING_FILENAME


def test_working_path_equal_to_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        app._build_path_policy(
            policy.authorized_directory, policy.source_path, policy.source_path
        )


def test_hardlink_alias_to_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    try:
        os.link(policy.source_path, policy.working_path)
    except OSError as exc:
        pytest.skip(f"hardlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="aliases"):
        app._build_path_policy(
            policy.authorized_directory, policy.source_path, policy.working_path
        )


def test_symlink_alias_to_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    try:
        policy.working_path.symlink_to(policy.source_path)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        app._build_path_policy(
            policy.authorized_directory, policy.source_path, policy.working_path
        )


def test_working_path_outside_authorized_directory_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="outside"):
        app._build_path_policy(
            policy.authorized_directory,
            policy.source_path,
            outside / app.WORKING_FILENAME,
        )


def test_save_rechecks_policy_immediately_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    original_validate = app.validate_active_paths
    original_replace = os.replace
    validations: list[bool] = []
    replace_checks: list[bool] = []

    def recording_validate(
        active_policy: app.PathPolicy, *, working_required: bool
    ) -> None:
        validations.append(working_required)
        original_validate(active_policy, working_required=working_required)

    def recording_replace(source: str, destination: Path) -> None:
        replace_checks.append(validations[-1])
        original_replace(source, destination)

    monkeypatch.setattr(app, "validate_active_paths", recording_validate)
    monkeypatch.setattr(app.os, "replace", recording_replace)
    app.save_entry(policy, 0, valid_values("keep_original"))
    assert replace_checks == [True]
    assert sum(validations) >= 4


def test_attempted_redirection_cannot_modify_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    source_before = policy.source_path.read_bytes()
    policy.working_path.unlink()
    try:
        policy.working_path.symlink_to(policy.source_path)
    except (NotImplementedError, OSError):
        os.link(policy.source_path, policy.working_path)
    with pytest.raises(ValueError):
        app.save_entry(policy, 0, valid_values("keep_original"))
    assert policy.source_path.read_bytes() == source_before


def test_normal_save_changes_only_test_working_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    source_before = policy.source_path.read_bytes()
    working_before = policy.working_path.read_bytes()
    assert app.save_entry(policy, 0, valid_values("use_reviewer")) == []
    assert policy.source_path.read_bytes() == source_before
    assert policy.working_path.read_bytes() != working_before


def test_server_binds_to_loopback_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    server, _created = app.create_server(policy, 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
    finally:
        server.server_close()


def test_source_hash_is_checked_before_working_copy_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path, monkeypatch)
    app.create_working_copy(policy)
    before = policy.working_path.read_bytes()
    policy.source_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        app.load_working(policy)
    assert policy.working_path.read_bytes() == before
