"""Run the local-only Stage 1B reviewed-candidate spot-check interface."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
DEFAULT_PORT = 8769
ROOT = Path(__file__).resolve().parents[1]
EVALUATION_RELATIVE = Path("evaluation/model_hunting")
CANDIDATE_FILENAME = "short_english_benchmark_reviewed_candidate_v1.jsonl"
SOURCE_FILENAME = "short_english_benchmark_draft_v1.jsonl"
REPORT_FILENAME = "short_english_benchmark_stage1b_application_report.json"
REVIEW_FILENAME = "short_english_benchmark_stage1b_completed_review.csv"
ADJUDICATION_FILENAME = "short_english_benchmark_stage1b_completed_adjudication.json"
WORKING_FILENAME = "short_english_benchmark_stage1b_completed_spot_check.json"
EXPECTED_HASHES = {
    CANDIDATE_FILENAME: "f5fc04393cd8b820df4df70c37719e0d834537cb419aaae43e0abb609c0480ea",
    SOURCE_FILENAME: "f9ae2ab171c51b630a081c770e6db48bc06d0924f3823da4827643c2562553f7",
    REPORT_FILENAME: "e2c38d57863a58738439c7804b7e1a7e61825e19e09c0a7690bd174b5a57ec94",
    REVIEW_FILENAME: "b3975a3604a82ae594e851673a9092054cc74f3294ca70c34ca9195541416cc3",
    ADJUDICATION_FILENAME: "2ebfc8696767aca54c56334cf8d432b5368c40be7faf5d201912ae0967bfd90b",
}
EXPECTED_IDS = (
    "SEB-0176",
    "SEB-0145",
    "SEB-0153",
    "SEB-0148",
    "SEB-0137",
    "SEB-0168",
    "SEB-0085",
    "SEB-0083",
    "SEB-0146",
    "SEB-0022",
    "SEB-0086",
    "SEB-0142",
)
HUMAN_FIELDS = (
    "spot_check_decision",
    "confirmed_department",
    "corrected_rationale",
    "spot_check_note",
)
DECISIONS = (
    "confirm_candidate",
    "correct_rationale_only",
    "reconsider_label",
    "unsuitable_example",
    "needs_followup",
)
DEPARTMENTS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
CONFIRMED_DEPARTMENTS = (*DEPARTMENTS, "unresolved")
DEPARTMENT_GUIDE = {
    "transfer_payment": "transfer or payment delivery, pending or failed payment",
    "account_support": "login, access, verification, profile, account settings",
    "card_atm": "card operation, ATM, withdrawal, retained or activated card",
    "fraud_security": "unauthorized activity, scam, compromised access, suspicious transaction",
    "loan_credit": "loans, repayment, installments, borrowing, credit reporting",
    "general_support": "a clear support problem not fitting the other five",
}
BOUNDARY_REMINDERS = (
    "Account-access inconvenience alone generally indicates account_support.",
    "Evidence of unauthorized access, takeover, suspicious activity, or security compromise generally indicates fraud_security.",
    "Mentioning a card or transfer does not automatically determine the label; use the complaint's primary harm.",
    "general_support should not be used merely because an example is difficult.",
    "Use needs_followup when genuine ambiguity remains; do not force a label.",
    "This spot check records a human judgment but does not modify or approve the candidate.",
)
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){7,}(?!\w)")
LONG_NUMBER_PATTERN = re.compile(r"(?<!\w)\d(?:[\s-]?\d){5,}(?!\w)")
SENSITIVE_TERM_PATTERN = re.compile(
    r"(?i)\b(?:password|passcode|pin|security code|cvv|cvc|api key|access token|"
    r"auth token|private key|account number|card number|loan number|transaction "
    r"identifier|nrc)\b"
)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?i)(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|/(?:home|users)/[^\s]+)"
)


@dataclass(frozen=True)
class PathPolicy:
    """Canonical protected inputs and sole authorized write target."""

    authorized_directory: Path
    candidate_path: Path
    source_path: Path
    report_path: Path
    review_path: Path
    adjudication_path: Path
    working_path: Path
    expected_hashes: dict[str, str]

    @property
    def protected_paths(self) -> tuple[Path, ...]:
        return (
            self.candidate_path,
            self.source_path,
            self.report_path,
            self.review_path,
            self.adjudication_path,
        )


def _build_path_policy(
    authorized_directory: Path,
    *,
    candidate_path: Path,
    source_path: Path,
    report_path: Path,
    review_path: Path,
    adjudication_path: Path,
    working_path: Path,
    expected_hashes: dict[str, str],
) -> PathPolicy:
    """Build an internal/test-facing policy; production has no path overrides."""
    if authorized_directory.is_symlink():
        raise ValueError("authorized evaluation directory must not be a symlink")
    directory = authorized_directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("authorized evaluation directory is not a directory")
    supplied = {
        CANDIDATE_FILENAME: candidate_path,
        SOURCE_FILENAME: source_path,
        REPORT_FILENAME: report_path,
        REVIEW_FILENAME: review_path,
        ADJUDICATION_FILENAME: adjudication_path,
        WORKING_FILENAME: working_path,
    }
    resolved: dict[str, Path] = {}
    for filename, path in supplied.items():
        if path.name != filename:
            raise ValueError(f"{filename} path differs from the fixed contract")
        if path.is_symlink():
            raise ValueError(f"{filename} must not be a symlink")
        if path.parent.resolve(strict=True) != directory:
            raise ValueError(f"{filename} is outside the authorized directory")
        target = path.resolve(strict=filename != WORKING_FILENAME)
        if target != directory / filename:
            raise ValueError(f"{filename} resolves unexpectedly")
        resolved[filename] = target
    working = resolved[WORKING_FILENAME]
    for filename in supplied:
        if filename == WORKING_FILENAME:
            continue
        protected = resolved[filename]
        if working == protected:
            raise ValueError("spot-check working path aliases a protected input")
        if working_path.exists() and working_path.samefile(protected):
            raise ValueError("spot-check working path hardlinks a protected input")
    if set(expected_hashes) != set(EXPECTED_HASHES):
        raise ValueError("expected protected-hash set differs from the contract")
    return PathPolicy(
        directory,
        resolved[CANDIDATE_FILENAME],
        resolved[SOURCE_FILENAME],
        resolved[REPORT_FILENAME],
        resolved[REVIEW_FILENAME],
        resolved[ADJUDICATION_FILENAME],
        working,
        dict(expected_hashes),
    )


def production_path_policy() -> PathPolicy:
    """Resolve repository-controlled production inputs and output."""
    root = ROOT.resolve(strict=True)
    if not (root / ".git").exists():
        raise ValueError("repository root does not contain .git")
    directory = root / EVALUATION_RELATIVE
    return _build_path_policy(
        directory,
        candidate_path=directory / CANDIDATE_FILENAME,
        source_path=directory / SOURCE_FILENAME,
        report_path=directory / REPORT_FILENAME,
        review_path=directory / REVIEW_FILENAME,
        adjudication_path=directory / ADJUDICATION_FILENAME,
        working_path=directory / WORKING_FILENAME,
        expected_hashes=EXPECTED_HASHES,
    )


def validate_active_paths(policy: PathPolicy, *, working_required: bool) -> None:
    """Revalidate fixed paths, including immediately before every save."""
    rebuilt = _build_path_policy(
        policy.authorized_directory,
        candidate_path=policy.candidate_path,
        source_path=policy.source_path,
        report_path=policy.report_path,
        review_path=policy.review_path,
        adjudication_path=policy.adjudication_path,
        working_path=policy.working_path,
        expected_hashes=policy.expected_hashes,
    )
    if rebuilt != policy:
        raise ValueError("active spot-check paths differ from the authorized policy")
    if working_required and not policy.working_path.is_file():
        raise ValueError("completed spot-check working copy is missing")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def contains_sensitive_content(value: str) -> bool:
    return bool(
        EMAIL_PATTERN.search(value)
        or PHONE_PATTERN.search(value)
        or LONG_NUMBER_PATTERN.search(value)
        or SENSITIVE_TERM_PATTERN.search(value)
        or ABSOLUTE_PATH_PATTERN.search(value)
    )


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path.name} must be UTF-8 without BOM")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if not all(isinstance(value, dict) for value in values):
        raise TypeError(f"{path.name} must contain JSON objects")
    return values


def _index(
    records: list[dict[str, Any]], key: str, name: str
) -> dict[str, dict[str, Any]]:
    ids = [record.get(key) for record in records]
    if not all(isinstance(value, str) and value for value in ids):
        raise ValueError(f"{name} contains an invalid record ID")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{name} contains a duplicate record ID")
    return dict(zip(ids, records, strict=True))


def _verify_hashes(policy: PathPolicy) -> None:
    for path in policy.protected_paths:
        if sha256_file(path) != policy.expected_hashes[path.name]:
            raise ValueError(f"{path.name} SHA-256 differs from protected identity")


def build_blank_working(policy: PathPolicy) -> dict[str, Any]:
    """Derive the blank 12-record document from verified committed evidence."""
    validate_active_paths(policy, working_required=False)
    _verify_hashes(policy)
    candidate = read_jsonl(policy.candidate_path)
    source = read_jsonl(policy.source_path)
    report = read_json(policy.report_path)
    adjudication = read_json(policy.adjudication_path)
    candidate_by_id = _index(candidate, "example_id", "candidate")
    source_by_id = _index(source, "example_id", "source draft")
    if len(candidate) != len(source) or set(candidate_by_id) != set(source_by_id):
        raise ValueError("candidate/source membership differs")
    plan = report.get("spot_check_plan")
    if not isinstance(plan, dict) or plan.get("status") != "pending":
        raise ValueError("application report spot-check plan is not pending")
    if plan.get("size") != 12 or tuple(plan.get("record_ids", ())) != EXPECTED_IDS:
        raise ValueError("application report spot-check selection differs")
    differences: list[tuple[str, str, Any, Any]] = []
    for source_record, candidate_record in zip(source, candidate, strict=True):
        if source_record["example_id"] != candidate_record.get("example_id"):
            raise ValueError("candidate/source ordering differs")
        for field in set(source_record) | set(candidate_record):
            if source_record.get(field) != candidate_record.get(field):
                differences.append(
                    (
                        source_record["example_id"],
                        field,
                        source_record.get(field),
                        candidate_record.get(field),
                    )
                )
        if (
            candidate_record.get("approved") is not False
            or candidate_record.get("review_status") != "pending"
            or candidate_record.get("benchmark_version") != ""
        ):
            raise ValueError("candidate review state is not pending and unapproved")
    if differences != [
        ("SEB-0176", "expected_department", "account_support", "fraud_security")
    ]:
        raise ValueError(
            "candidate differs from source outside the authorized label change"
        )
    with policy.review_path.open(encoding="utf-8-sig", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    review_by_id = _index(review_rows, "record_id", "completed review")
    adjudication_entries = adjudication.get("entries")
    if not isinstance(adjudication_entries, list):
        raise TypeError("completed adjudication entries are invalid")
    adjudication_by_id = _index(adjudication_entries, "record_id", "adjudication")
    adjudicated = adjudication_by_id.get("SEB-0176")
    if not adjudicated or any(
        (
            adjudicated.get("original_department") != "account_support",
            adjudicated.get("reviewer_department") != "fraud_security",
            adjudicated.get("adjudication_decision") != "use_reviewer",
            adjudicated.get("final_department") != "fraud_security",
            not normalize_text(adjudicated.get("adjudication_note", "")),
            bool(normalize_text(adjudicated.get("revised_text", ""))),
        )
    ):
        raise ValueError("SEB-0176 adjudication context differs")
    entries: list[dict[str, Any]] = []
    for order, record_id in enumerate(EXPECTED_IDS, 1):
        candidate_record = candidate_by_id[record_id]
        source_record = source_by_id[record_id]
        review = review_by_id.get(record_id)
        if review is None or review.get("complaint_text") != candidate_record["text"]:
            raise ValueError(f"{record_id} completed-review context differs")
        why = (
            "adjudicated_label_change"
            if order == 1
            else "hard_ambiguity_department_representation"
            if order <= 6
            else "controlled_variation_agreement"
        )
        entry = {
            "spot_check_order": order,
            "record_id": record_id,
            "complaint_text": candidate_record["text"],
            "candidate_department": candidate_record["expected_department"],
            "original_department": source_record["expected_department"],
            "blind_review_department": review["reviewer_department"],
            "difficulty": candidate_record["difficulty"],
            "review_reasons": [
                value for value in review.get("review_reasons", "").split("|") if value
            ],
            "variation_flags": list(candidate_record.get("variation_tags", [])),
            "why_selected_for_spot_check": why,
            "preserved_authored_rationale": source_record.get(
                "ground_truth_rationale", ""
            ),
            "preserved_ambiguity_note": source_record.get("ambiguity_notes", ""),
            "adjudication_decision": (
                adjudicated["adjudication_decision"] if order == 1 else ""
            ),
            "adjudication_note": adjudicated["adjudication_note"] if order == 1 else "",
            "spot_check_decision": "",
            "confirmed_department": "",
            "corrected_rationale": "",
            "spot_check_note": "",
        }
        entries.append(entry)
    return {
        "analysis_status": "pending_human_spot_check",
        "selection_status": "pending",
        "selection_method": plan["method"],
        "candidate_path": f"evaluation/model_hunting/{CANDIDATE_FILENAME}",
        "candidate_sha256": policy.expected_hashes[CANDIDATE_FILENAME],
        "application_report_path": f"evaluation/model_hunting/{REPORT_FILENAME}",
        "application_report_sha256": policy.expected_hashes[REPORT_FILENAME],
        "record_count": 12,
        "entries": entries,
        "safeguards": {
            "candidate_is_not_modified_by_this_file": True,
            "spot_check_is_not_benchmark_approval_or_freezing": True,
            "model_predictions_or_confidence_included": False,
        },
    }


def create_working_copy(policy: PathPolicy) -> bool:
    validate_active_paths(policy, working_required=False)
    blank = build_blank_working(policy)
    raw = (json.dumps(blank, ensure_ascii=False, indent=2) + "\n").encode()
    try:
        with policy.working_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return False
    validate_active_paths(policy, working_required=True)
    validate_working(blank, read_json(policy.working_path))
    return True


def validate_working(blank: dict[str, Any], working: dict[str, Any]) -> None:
    expected = copy.deepcopy(blank)
    entries = working.get("entries")
    if not isinstance(entries, list) or len(entries) != 12:
        raise ValueError("spot-check working copy must contain exactly 12 records")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TypeError("spot-check entry must be an object")
        for field in HUMAN_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str):
                raise TypeError(f"{field} must be text")
            expected["entries"][index][field] = value
        if entry.get("record_id") != EXPECTED_IDS[index]:
            raise ValueError("spot-check record order or identity changed")
    if working != expected:
        raise ValueError("working copy contains an immutable, added, or removed change")


def load_working(policy: PathPolicy) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_active_paths(policy, working_required=True)
    blank = build_blank_working(policy)
    working = read_json(policy.working_path)
    validate_working(blank, working)
    return blank, working


def validate_entry(values: dict[str, str], source_entry: dict[str, Any]) -> list[str]:
    decision = values.get("spot_check_decision", "")
    department = values.get("confirmed_department", "")
    rationale = normalize_text(values.get("corrected_rationale", ""))
    note = normalize_text(values.get("spot_check_note", ""))
    errors: list[str] = []
    if decision not in DECISIONS:
        errors.append("Choose a valid spot-check decision.")
    if department not in CONFIRMED_DEPARTMENTS:
        errors.append("Choose a valid confirmed department.")
    if not note:
        errors.append("Every completed spot check requires a note.")
    if contains_sensitive_content(rationale) or contains_sensitive_content(note):
        errors.append(
            "Human-entered fields contain prohibited sensitive content or a user path."
        )
    candidate_department = source_entry["candidate_department"]
    if decision == "confirm_candidate":
        if department != candidate_department:
            errors.append("confirm_candidate requires the candidate department.")
        if rationale:
            errors.append("confirm_candidate requires empty corrected rationale.")
    elif decision == "correct_rationale_only":
        if department != candidate_department:
            errors.append("correct_rationale_only requires the candidate department.")
        if not rationale:
            errors.append("correct_rationale_only requires corrected rationale.")
    elif decision == "reconsider_label":
        if department not in DEPARTMENTS or department == candidate_department:
            errors.append("reconsider_label requires a different real department.")
        if (
            source_entry.get("preserved_authored_rationale")
            or source_entry.get("preserved_ambiguity_note")
        ) and not rationale:
            errors.append(
                "reconsider_label requires corrected rationale when preserved rationale exists."
            )
    elif decision in {"unsuitable_example", "needs_followup"}:
        if department != "unresolved":
            errors.append(f"{decision} requires unresolved.")
        if rationale:
            errors.append(f"{decision} requires empty corrected rationale.")
    return errors


def is_complete(entry: dict[str, Any]) -> bool:
    return not validate_entry({field: entry[field] for field in HUMAN_FIELDS}, entry)


def atomic_write_working(policy: PathPolicy, value: dict[str, Any]) -> None:
    validate_active_paths(policy, working_required=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=policy.authorized_directory,
            prefix=f".{WORKING_FILENAME}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        validate_active_paths(policy, working_required=True)
        os.replace(temporary, policy.working_path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def save_entry(policy: PathPolicy, index: int, values: dict[str, str]) -> list[str]:
    validate_active_paths(policy, working_required=True)
    blank, working = load_working(policy)
    if not 0 <= index < 12:
        return ["Record index is out of range."]
    errors = validate_entry(values, blank["entries"][index])
    if errors:
        return errors
    updated = copy.deepcopy(working)
    for field in HUMAN_FIELDS:
        updated["entries"][index][field] = normalize_text(values.get(field, ""))
    validate_working(blank, updated)
    validate_active_paths(policy, working_required=True)
    atomic_write_working(policy, updated)
    load_working(policy)
    return []


def _options(values: tuple[str, ...], selected: str) -> str:
    return "".join(
        f'<option value="{html.escape(value)}"'
        f"{' selected' if selected == value else ''}>{html.escape(value)}</option>"
        for value in values
    )


def page(
    document: dict[str, Any], index: int, errors: list[str] | None = None
) -> bytes:
    entries = document["entries"]
    entry = entries[index]
    completed = sum(is_complete(item) for item in entries)
    decisions = "".join(
        f'<label><input type="radio" name="spot_check_decision" value="{value}"'
        f"{' checked' if entry['spot_check_decision'] == value else ''}> {value}</label>"
        for value in DECISIONS
    )
    navigation = "".join(
        f'<a class="nav {"complete" if is_complete(item) else "incomplete"} '
        f'{"current" if position == index else ""}" href="/?record={position + 1}">{position + 1}</a>'
        for position, item in enumerate(entries)
    )
    guide = "".join(
        f"<li><code>{key}</code>: {html.escape(value)}</li>"
        for key, value in DEPARTMENT_GUIDE.items()
    )
    reminders = "".join(
        f"<li>{html.escape(value)}</li>" for value in BOUNDARY_REMINDERS
    )
    error_html = (
        ""
        if not errors
        else '<div class="errors">' + "<br>".join(map(html.escape, errors)) + "</div>"
    )
    previous = max(1, index)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ComplaintGuard Stage 1B Spot Check</title><style>
body{{font:16px system-ui,sans-serif;margin:0;background:#f4f6f8;color:#17212b}}main{{max-width:1080px;margin:auto;padding:24px}}
.card{{background:#fff;border:1px solid #94a3b8;border-radius:10px;padding:20px;margin:16px 0}}.complaint{{font-size:1.3rem;line-height:1.5}}
.labels,.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.label-box{{border:1px solid #64748b;padding:14px;border-radius:8px}}
label{{display:block;margin:8px 0}}select,textarea{{width:100%;box-sizing:border-box;padding:9px}}button,.button{{padding:10px 14px;border:0;border-radius:6px;background:#334155;color:#fff;text-decoration:none;cursor:pointer}}
.nav{{display:inline-block;width:30px;padding:5px;margin:3px;text-align:center;text-decoration:none;border-radius:5px;color:#17212b}}.complete{{border:2px solid #475569}}.incomplete{{border:1px dashed #64748b}}.current{{outline:3px solid #2563eb}}.errors{{background:#fff1f2;border:1px solid #be123c;padding:12px}}code{{font-size:.92em}}@media(max-width:720px){{.labels,.form-grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Stage 1B Candidate Spot Check</h1><p><strong>Record {index + 1} of 12</strong> · Completed {completed} · Incomplete {12 - completed}</p>
<div class="card"><p><strong>Record ID:</strong> {html.escape(entry["record_id"])}</p><p class="complaint">{html.escape(entry["complaint_text"])}</p>
<div class="labels"><div class="label-box"><strong>Source/original department</strong><br><code>{html.escape(entry["original_department"])}</code></div><div class="label-box"><strong>Blind-review department</strong><br><code>{html.escape(entry["blind_review_department"])}</code></div><div class="label-box"><strong>Adjudicated final/candidate department</strong><br><code>{html.escape(entry["candidate_department"])}</code></div><div class="label-box"><strong>Difficulty</strong><br>{html.escape(entry["difficulty"])}</div></div>
<p><strong>Neutral review reasons:</strong> {html.escape(", ".join(entry["review_reasons"]) or "none")}</p><p><strong>Variation flags:</strong> {html.escape(", ".join(entry["variation_flags"]) or "none")}</p><p><strong>Why selected:</strong> {html.escape(entry["why_selected_for_spot_check"])}</p><p><strong>Preserved authored rationale:</strong> {html.escape(entry["preserved_authored_rationale"] or "none")}</p><p><strong>Preserved ambiguity note:</strong> {html.escape(entry["preserved_ambiguity_note"] or "none")}</p><p><strong>Adjudication decision:</strong> {html.escape(entry["adjudication_decision"] or "not applicable")}</p><p><strong>Adjudication note:</strong> {html.escape(entry["adjudication_note"] or "not applicable")}</p></div>{error_html}
<form method="post" action="/save"><input type="hidden" name="index" value="{index}"><div class="card form-grid"><section><h2>Spot-check decision</h2>{decisions}<h2>Confirmed department</h2><select name="confirmed_department"><option value="">Choose without a default…</option>{_options(CONFIRMED_DEPARTMENTS, entry["confirmed_department"])}</select></section><section><label>Corrected rationale (only when required)<textarea name="corrected_rationale" rows="5">{html.escape(entry["corrected_rationale"])}</textarea></label><label>Required spot-check note<textarea name="spot_check_note" rows="5">{html.escape(entry["spot_check_note"])}</textarea></label></section></div>
<a class="button" href="/?record={previous}">Previous</a> <button name="action" value="save">Save</button> <button name="action" value="next">Save and Next</button></form><div class="card"><h2>Completed/incomplete navigation</h2>{navigation}<p><a href="/summary">Final completion summary</a></p></div><div class="card"><h2>Neutral six-department guide</h2><ul>{guide}</ul><h2>Boundary reminders</h2><ul>{reminders}</ul></div></main></body></html>""".encode()


def summary_page(document: dict[str, Any]) -> bytes:
    complete = sum(is_complete(entry) for entry in document["entries"])
    rows = "".join(
        f"<li><code>{html.escape(entry['record_id'])}</code>: {'complete' if is_complete(entry) else 'incomplete'}</li>"
        for entry in document["entries"]
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Spot-check completion summary</title></head><body><main><h1>Final completion summary</h1><p>Completed {complete} of 12; incomplete {12 - complete}.</p><p>This local working copy does not modify, approve, version, or freeze the candidate.</p><ul>{rows}</ul><p><a href="/">Return to records</a></p></main></body></html>""".encode()


def make_handler(policy: PathPolicy) -> type[BaseHTTPRequestHandler]:
    class SpotCheckHandler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            try:
                _blank, working = load_working(policy)
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/summary":
                    self._send(summary_page(working))
                    return
                if parsed.path != "/":
                    self._send(b"Not found", HTTPStatus.NOT_FOUND)
                    return
                requested = int(
                    urllib.parse.parse_qs(parsed.query).get("record", ["1"])[0]
                )
                self._send(page(working, min(max(requested - 1, 0), 11)))
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(
                    f"Local spot-check error: {html.escape(str(exc))}".encode(),
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:
            if urllib.parse.urlparse(self.path).path != "/save":
                self._send(b"Not found", HTTPStatus.NOT_FOUND)
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 32_768)
                form = urllib.parse.parse_qs(
                    self.rfile.read(length).decode("utf-8"), keep_blank_values=True
                )
                index = int(form.get("index", ["-1"])[0])
                errors = save_entry(
                    policy,
                    index,
                    {field: form.get(field, [""])[0] for field in HUMAN_FIELDS},
                )
                _blank, working = load_working(policy)
                if errors:
                    self._send(
                        page(working, min(max(index, 0), 11), errors),
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                action = form.get("action", ["save"])[0]
                target = (
                    "/summary"
                    if action == "next" and index == 11
                    else f"/?record={index + 2 if action == 'next' else index + 1}"
                )
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", target)
                self.end_headers()
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(
                    f"Local spot-check error: {html.escape(str(exc))}".encode(),
                    HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

    return SpotCheckHandler


def create_server(policy: PathPolicy, port: int) -> tuple[ThreadingHTTPServer, bool]:
    validate_active_paths(policy, working_required=False)
    created = create_working_copy(policy)
    load_working(policy)
    return ThreadingHTTPServer((HOST, port), make_handler(policy)), created


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.")
        return 2
    try:
        server, created = create_server(production_path_policy(), args.port)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Spot-check preflight failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        f"Stage 1B spot-check app at http://{HOST}:{args.port}/ (working copy {'created' if created else 'resumed'})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping local spot-check app.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
