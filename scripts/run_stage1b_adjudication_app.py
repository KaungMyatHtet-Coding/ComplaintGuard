"""Run the local-only Stage 1B human-adjudication interface."""

from __future__ import annotations

import argparse
import copy
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
DEFAULT_PORT = 8767
ROOT = Path(__file__).resolve().parents[1]
EVALUATION_RELATIVE = Path("evaluation/model_hunting")
SOURCE_FILENAME = "short_english_benchmark_stage1b_disagreement_queue.json"
WORKING_FILENAME = "short_english_benchmark_stage1b_completed_adjudication.json"
SOURCE_PATH = ROOT / EVALUATION_RELATIVE / SOURCE_FILENAME
WORKING_PATH = ROOT / EVALUATION_RELATIVE / WORKING_FILENAME
SOURCE_SHA256 = "decd8bd3fe61b4afdf0925f4d19c4cb58a69574449ab4277f2ce7b48fa44d3c0"
HUMAN_FIELDS = (
    "adjudication_decision",
    "final_department",
    "revised_text",
    "adjudication_note",
)
DECISIONS = (
    "keep_original",
    "use_reviewer",
    "revise_and_relabel",
    "remove_from_benchmark",
    "needs_second_review",
)
DEPARTMENTS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
FINAL_DEPARTMENTS = (*DEPARTMENTS, "unresolved")
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
    "If both labels remain equally defensible, choose needs_second_review.",
    "Do not force a final label when genuine ambiguity remains.",
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
EXPECTED_IDS = {
    "SEB-0088",
    "SEB-0136",
    "SEB-0151",
    "SEB-0158",
    "SEB-0160",
    "SEB-0163",
    "SEB-0167",
    "SEB-0176",
    "SEB-0178",
    "SEB-0179",
}


@dataclass(frozen=True)
class PathPolicy:
    """Canonical source and sole authorized write target for one app instance."""

    authorized_directory: Path
    source_path: Path
    working_path: Path


def _build_path_policy(
    authorized_directory: Path, source_path: Path, working_path: Path
) -> PathPolicy:
    """Build a validated policy; path injection is internal and test-facing only."""
    if authorized_directory.is_symlink():
        raise ValueError("authorized evaluation directory must not be a symlink")
    resolved_directory = authorized_directory.resolve(strict=True)
    if not resolved_directory.is_dir():
        raise ValueError("authorized evaluation directory is not a directory")
    if source_path.name != SOURCE_FILENAME or working_path.name != WORKING_FILENAME:
        raise ValueError("source or working filename differs from the fixed contract")
    if source_path.is_symlink():
        raise ValueError("source disagreement queue must not be a symlink")
    if working_path.is_symlink():
        raise ValueError("completed-adjudication working path must not be a symlink")
    if source_path.parent.resolve(strict=True) != resolved_directory:
        raise ValueError(
            "source disagreement queue is outside the authorized directory"
        )
    if working_path.parent.resolve(strict=True) != resolved_directory:
        raise ValueError(
            "completed-adjudication path is outside the authorized directory"
        )
    resolved_source = source_path.resolve(strict=True)
    resolved_working = working_path.resolve(strict=False)
    expected_source = resolved_directory / SOURCE_FILENAME
    expected_working = resolved_directory / WORKING_FILENAME
    if resolved_source != expected_source:
        raise ValueError("source disagreement queue resolves unexpectedly")
    if resolved_working != expected_working:
        raise ValueError("completed-adjudication path resolves unexpectedly")
    if resolved_working == resolved_source:
        raise ValueError("completed-adjudication path aliases the source queue")
    if working_path.exists() and working_path.samefile(source_path):
        raise ValueError("completed-adjudication path aliases the source queue")
    return PathPolicy(resolved_directory, resolved_source, expected_working)


def production_path_policy() -> PathPolicy:
    """Resolve the fixed repository paths used by production execution."""
    repository_root = ROOT.resolve(strict=True)
    if not (repository_root / ".git").exists():
        raise ValueError("repository root does not contain .git")
    authorized_directory = repository_root / EVALUATION_RELATIVE
    return _build_path_policy(
        authorized_directory,
        authorized_directory / SOURCE_FILENAME,
        authorized_directory / WORKING_FILENAME,
    )


def validate_active_paths(policy: PathPolicy, *, working_required: bool) -> None:
    """Revalidate the sole write target, including immediately before each save."""
    rebuilt = _build_path_policy(
        policy.authorized_directory, policy.source_path, policy.working_path
    )
    if rebuilt != policy:
        raise ValueError("active adjudication paths differ from the authorized policy")
    if working_required and not policy.working_path.is_file():
        raise ValueError("completed-adjudication working copy is missing")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def comparison_text(value: str) -> str:
    normalized = normalize_text(value).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


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


def validate_source(source: dict[str, Any]) -> None:
    entries = source.get("entries")
    if (
        source.get("queue_size") != 10
        or not isinstance(entries, list)
        or len(entries) != 10
    ):
        raise ValueError("source disagreement queue must contain exactly 10 records")
    ids = [entry.get("record_id") for entry in entries]
    if len(set(ids)) != 10 or set(ids) != EXPECTED_IDS:
        raise ValueError("source disagreement queue IDs differ from the approved set")
    orders = [entry.get("adjudication_order") for entry in entries]
    if orders != list(range(1, 11)):
        raise ValueError("source adjudication order must be 1 through 10")
    for entry in entries:
        if entry.get("original_department") not in DEPARTMENTS:
            raise ValueError("source contains an invalid original department")
        if entry.get("reviewer_department") not in DEPARTMENTS:
            raise ValueError("source contains an invalid reviewer department")
        if any(entry.get(field) != "" for field in HUMAN_FIELDS):
            raise ValueError(
                "source disagreement queue adjudication fields are not blank"
            )


def load_source(policy: PathPolicy) -> dict[str, Any]:
    validate_active_paths(policy, working_required=False)
    if sha256_file(policy.source_path) != SOURCE_SHA256:
        raise ValueError("source disagreement queue SHA-256 differs")
    source = read_json(policy.source_path)
    validate_source(source)
    return source


def create_working_copy(policy: PathPolicy) -> bool:
    validate_active_paths(policy, working_required=False)
    source = load_source(policy)
    raw = policy.source_path.read_bytes()
    try:
        with policy.working_path.open("xb") as destination:
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError:
        return False
    validate_active_paths(policy, working_required=True)
    validate_working(source, read_json(policy.working_path))
    return True


def validate_working(source: dict[str, Any], working: dict[str, Any]) -> None:
    source_entries = source["entries"]
    working_entries = working.get("entries")
    if not isinstance(working_entries, list) or len(working_entries) != len(
        source_entries
    ):
        raise ValueError("working copy record count differs from the source queue")
    expected = copy.deepcopy(source)
    for index, (source_entry, working_entry) in enumerate(
        zip(source_entries, working_entries, strict=True)
    ):
        if not isinstance(working_entry, dict):
            raise TypeError(f"working entry {index + 1} is invalid")
        for field in HUMAN_FIELDS:
            value = working_entry.get(field)
            if not isinstance(value, str):
                raise TypeError(f"working field {field} must be text")
            expected["entries"][index][field] = value
        if source_entry["record_id"] != working_entry.get("record_id"):
            raise ValueError("working copy record order or identity changed")
    if working != expected:
        raise ValueError(
            "working copy contains an immutable, added, or removed field change"
        )


def load_working(policy: PathPolicy) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_active_paths(policy, working_required=True)
    source = load_source(policy)
    working = read_json(policy.working_path)
    validate_working(source, working)
    return source, working


def validate_entry(values: dict[str, str], source_entry: dict[str, Any]) -> list[str]:
    decision = values.get("adjudication_decision", "")
    department = values.get("final_department", "")
    revised = normalize_text(values.get("revised_text", ""))
    note = normalize_text(values.get("adjudication_note", ""))
    errors: list[str] = []
    if decision not in DECISIONS:
        errors.append("Choose a valid adjudication decision.")
    if department not in FINAL_DEPARTMENTS:
        errors.append("Choose a valid final department.")
    if not note:
        errors.append("Every completed adjudication requires a note.")
    if contains_sensitive_content(revised) or contains_sensitive_content(note):
        errors.append(
            "Human-entered fields contain prohibited sensitive content or an absolute user path."
        )
    if decision == "keep_original":
        if department != source_entry["original_department"]:
            errors.append("keep_original requires the authored department.")
        if revised:
            errors.append("keep_original requires empty revised text.")
    elif decision == "use_reviewer":
        if department != source_entry["reviewer_department"]:
            errors.append("use_reviewer requires the blind-review department.")
        if revised:
            errors.append("use_reviewer requires empty revised text.")
    elif decision == "revise_and_relabel":
        if department not in DEPARTMENTS:
            errors.append("revise_and_relabel requires one of the six departments.")
        words = revised.split()
        if not revised:
            errors.append("revise_and_relabel requires complete revised text.")
        elif not 3 <= len(words) <= 20:
            errors.append("Revised text must contain 3-20 words.")
        elif not 15 <= len(revised) <= 140:
            errors.append("Revised text must contain 15-140 normalized characters.")
        if revised and comparison_text(revised) == comparison_text(
            source_entry["complaint_text"]
        ):
            errors.append(
                "Revised text must differ meaningfully from the complaint text."
            )
    elif decision in {"remove_from_benchmark", "needs_second_review"}:
        if department != "unresolved":
            errors.append(f"{decision} requires unresolved as the final department.")
        if revised:
            errors.append(f"{decision} requires empty revised text.")
    return errors


def is_complete(entry: dict[str, Any]) -> bool:
    values = {field: entry[field] for field in HUMAN_FIELDS}
    return not validate_entry(values, entry)


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


def save_entry(
    policy: PathPolicy,
    index: int,
    values: dict[str, str],
) -> list[str]:
    validate_active_paths(policy, working_required=True)
    source, working = load_working(policy)
    if not 0 <= index < len(source["entries"]):
        return ["Record index is out of range."]
    errors = validate_entry(values, source["entries"][index])
    if errors:
        return errors
    updated = copy.deepcopy(working)
    for field in HUMAN_FIELDS:
        updated["entries"][index][field] = normalize_text(values.get(field, ""))
    validate_working(source, updated)
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
        f'<label><input type="radio" name="adjudication_decision" value="{value}"'
        f"{' checked' if entry['adjudication_decision'] == value else ''}> "
        f"{value}</label>"
        for value in DECISIONS
    )
    navigation = "".join(
        f'<a class="nav {"complete" if is_complete(item) else "incomplete"} '
        f'{"current" if position == index else ""}" href="/?record={position + 1}">'
        f"{position + 1}</a>"
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
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ComplaintGuard Stage 1B Adjudication</title><style>
body{{font:16px system-ui,sans-serif;margin:0;background:#f4f6f8;color:#17212b}}main{{max-width:1080px;margin:auto;padding:24px}}
.card{{background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:20px;margin:16px 0}}.complaint{{font-size:1.3rem;line-height:1.5}}
.labels,.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.label-box{{border:1px solid #94a3b8;padding:14px;border-radius:8px}}
label{{display:block;margin:8px 0}}select,textarea{{width:100%;box-sizing:border-box;padding:9px}}button,.button{{padding:10px 14px;border:0;border-radius:6px;background:#334155;color:#fff;text-decoration:none;cursor:pointer}}
.nav{{display:inline-block;width:30px;padding:5px;margin:3px;text-align:center;text-decoration:none;border-radius:5px;color:#17212b}}.complete{{border:2px solid #475569}}.incomplete{{border:1px dashed #64748b}}.current{{outline:3px solid #2563eb}}
.errors{{background:#fff1f2;border:1px solid #be123c;padding:12px}}.reminder{{background:#fffbeb}}code{{font-size:.92em}}@media(max-width:720px){{.labels,.form-grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Stage 1B Human Adjudication</h1>
<p><strong>Record {index + 1} of {len(entries)}</strong> · Completed {completed} · Incomplete {len(entries) - completed}</p>
<div class="card"><p><strong>Record ID:</strong> {html.escape(entry["record_id"])}</p>
<p class="complaint">{html.escape(entry["complaint_text"])}</p>
<div class="labels"><div class="label-box"><strong>Original/authored department</strong><br><code>{html.escape(entry["original_department"])}</code></div>
<div class="label-box"><strong>Blind-review department</strong><br><code>{html.escape(entry["reviewer_department"])}</code></div></div>
<p><strong>Original difficulty:</strong> {html.escape(entry["original_difficulty"])}</p>
<p><strong>Neutral review reasons:</strong> {html.escape(", ".join(entry["review_reasons"]) or "none")}</p>
<p><strong>Controlled-variation flags:</strong> {html.escape(", ".join(entry["controlled_variation_flags"]) or "none")}</p></div>{error_html}
<form method="post" action="/save"><input type="hidden" name="index" value="{index}"><div class="card form-grid"><section>
<h2>Adjudication decision</h2>{decisions}<h2>Final department</h2>
<select name="final_department"><option value="">Choose without a default…</option>{_options(FINAL_DEPARTMENTS, entry["final_department"])}</select></section><section>
<label>Revised text (revise_and_relabel only)<textarea name="revised_text" rows="4">{html.escape(entry["revised_text"])}</textarea></label>
<label>Required adjudication note<textarea name="adjudication_note" rows="5">{html.escape(entry["adjudication_note"])}</textarea></label></section></div>
<a class="button" href="/?record={previous}">Previous</a> <button name="action" value="save">Save</button> <button name="action" value="next">Save and Next</button></form>
<div class="card"><h2>Completed/incomplete navigation</h2>{navigation}<p><a href="/summary">Final completion summary</a></p></div>
<div class="card"><h2>Neutral six-department guide</h2><ul>{guide}</ul></div>
<div class="card reminder"><h2>Boundary reminders</h2><ul>{reminders}</ul></div>
</main></body></html>""".encode()


def summary_page(document: dict[str, Any]) -> bytes:
    entries = document["entries"]
    complete = [entry for entry in entries if is_complete(entry)]
    rows = "".join(
        f"<li><code>{html.escape(entry['record_id'])}</code>: "
        f"{'complete' if is_complete(entry) else 'incomplete'}</li>"
        for entry in entries
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Adjudication completion summary</title></head><body><main>
<h1>Final completion summary</h1><p>Completed {len(complete)} of {len(entries)}; incomplete {len(entries) - len(complete)}.</p>
<p>This local working copy does not modify, approve, version, or freeze the benchmark.</p><ul>{rows}</ul><p><a href="/">Return to records</a></p>
</main></body></html>""".encode()


def make_handler(policy: PathPolicy) -> type[BaseHTTPRequestHandler]:
    class AdjudicationHandler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            try:
                _source, working = load_working(policy)
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/summary":
                    self._send(summary_page(working))
                    return
                if parsed.path != "/":
                    self._send(b"Not found", HTTPStatus.NOT_FOUND)
                    return
                query = urllib.parse.parse_qs(parsed.query)
                requested = int(query.get("record", ["1"])[0])
                index = min(max(requested - 1, 0), len(working["entries"]) - 1)
                self._send(page(working, index))
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(
                    f"Local adjudication error: {html.escape(str(exc))}".encode(),
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
                values = {field: form.get(field, [""])[0] for field in HUMAN_FIELDS}
                errors = save_entry(policy, index, values)
                _source, working = load_working(policy)
                if errors:
                    display = min(max(index, 0), len(working["entries"]) - 1)
                    self._send(page(working, display, errors), HTTPStatus.BAD_REQUEST)
                    return
                action = form.get("action", ["save"])[0]
                if action == "next" and index == len(working["entries"]) - 1:
                    self.send_response(HTTPStatus.SEE_OTHER)
                    self.send_header("Location", "/summary")
                else:
                    target = index + 2 if action == "next" else index + 1
                    self.send_response(HTTPStatus.SEE_OTHER)
                    self.send_header("Location", f"/?record={target}")
                self.end_headers()
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(
                    f"Local adjudication error: {html.escape(str(exc))}".encode(),
                    HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

    return AdjudicationHandler


def create_server(policy: PathPolicy, port: int) -> tuple[ThreadingHTTPServer, bool]:
    """Create a loopback server for a prevalidated production or test policy."""
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
        policy = production_path_policy()
        server, created = create_server(policy, args.port)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Adjudication preflight failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        f"Stage 1B adjudication app at http://{HOST}:{args.port}/ "
        f"(working copy {'created' if created else 'resumed'})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping local adjudication app.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
