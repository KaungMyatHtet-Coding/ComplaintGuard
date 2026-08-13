"""Run the local-only Stage 1B blind human-review application."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
import shutil
import tempfile
import unicodedata
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ROOT = Path(__file__).resolve().parents[1]
PRISTINE_PATH = (
    ROOT
    / "evaluation/model_hunting/short_english_benchmark_stage1b_review_worksheet.csv"
)
WORKING_PATH = (
    ROOT
    / "evaluation/model_hunting/short_english_benchmark_stage1b_completed_review.csv"
)
PRISTINE_SHA256 = "1c1771b3ab77daa7bb0d30807faadf23ad76b1ed298c1d38d891f71094ce34b1"
FIELDS = (
    "review_order",
    "record_id",
    "complaint_text",
    "review_reasons",
    "word_count",
    "reviewer_decision",
    "reviewer_department",
    "revised_text",
    "reviewer_note",
)
HUMAN_FIELDS = FIELDS[5:]
DECISIONS = ("approve", "revise", "reject", "unsure")
DEPARTMENTS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
    "unsure",
)
DEPARTMENT_HELP = {
    "transfer_payment": "transfers, payments, pending/failed delivery to recipient",
    "account_support": "login, access, verification, profile, account settings",
    "card_atm": "cards, ATM use, withdrawals, retained/activated cards",
    "fraud_security": "unauthorized activity, scams, compromised access, suspicious transactions",
    "loan_credit": "loans, repayments, installments, borrowing, credit reporting",
    "general_support": "a clear support issue that fits none of the other departments",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_working_copy(pristine: Path, working: Path) -> bool:
    """Create the working copy once, without ever overwriting saved progress."""
    if sha256_file(pristine) != PRISTINE_SHA256:
        raise ValueError("pristine worksheet SHA-256 does not match Stage 1B")
    try:
        with working.open("xb") as destination, pristine.open("rb") as source:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError:
        return False
    return True


def read_rows(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError(
            "review CSV must be UTF-8 without BOM and use canonical LF endings"
        )
    text = raw.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("review CSV columns differ from the canonical worksheet")
    rows = list(reader)
    if len(rows) != 73 or len({row["record_id"] for row in rows}) != 73:
        raise ValueError("review CSV must preserve exactly 73 unique records")
    return rows


def immutable_snapshot(rows: list[dict[str, str]]) -> list[tuple[str, ...]]:
    return [tuple(row[field] for field in FIELDS[:5]) for row in rows]


def normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def validate_entry(values: dict[str, str]) -> list[str]:
    decision = values.get("reviewer_decision", "")
    department = values.get("reviewer_department", "")
    revised = normalized_text(values.get("revised_text", ""))
    note = values.get("reviewer_note", "").strip()
    errors: list[str] = []
    if decision not in DECISIONS:
        errors.append("Choose a valid reviewer decision.")
    if department not in DEPARTMENTS:
        errors.append("Choose a valid reviewer department.")
    if decision == "revise":
        words = revised.split()
        if not revised:
            errors.append("Revision requires complete replacement wording.")
        elif not 3 <= len(words) <= 20:
            errors.append("Revised text must contain 3–20 words.")
        elif not 15 <= len(revised) <= 140:
            errors.append("Revised text must contain 15–140 normalized characters.")
        if not note:
            errors.append("Revision requires a reviewer note.")
    if decision in {"reject", "unsure"} and not note:
        errors.append(f"{decision.capitalize()} requires a reviewer note.")
    if decision == "approve" and revised:
        errors.append("Approve must leave revised text empty.")
    return errors


def is_complete(row: dict[str, str]) -> bool:
    return not validate_entry({field: row[field] for field in HUMAN_FIELDS})


def atomic_write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def save_entry(path: Path, index: int, values: dict[str, str]) -> list[str]:
    rows = read_rows(path)
    if not 0 <= index < len(rows):
        return ["Record index is out of range."]
    errors = validate_entry(values)
    if errors:
        return errors
    before = immutable_snapshot(rows)
    for field in HUMAN_FIELDS:
        rows[index][field] = values.get(field, "").strip()
    if immutable_snapshot(rows) != before:
        raise ValueError("immutable worksheet fields changed")
    atomic_write_rows(path, rows)
    return []


def validate_blank_working_copy(pristine: Path, working: Path) -> list[str]:
    errors: list[str] = []
    pristine_rows = read_rows(pristine)
    working_rows = read_rows(working)
    if immutable_snapshot(pristine_rows) != immutable_snapshot(working_rows):
        errors.append("working copy immutable fields differ from pristine worksheet")
    if any(row[field] for row in working_rows for field in HUMAN_FIELDS):
        errors.append("working copy human-entry fields are not all empty")
    return errors


def page(
    rows: list[dict[str, str]], index: int, errors: list[str] | None = None
) -> bytes:
    row = rows[index]
    completed = sum(is_complete(item) for item in rows)
    options = "".join(
        f'<option value="{html.escape(value)}"'
        f"{' selected' if row['reviewer_department'] == value else ''}>{html.escape(value)}</option>"
        for value in DEPARTMENTS
    )
    decisions = "".join(
        f'<label><input type="radio" name="reviewer_decision" value="{value}"'
        f"{' checked' if row['reviewer_decision'] == value else ''}> {value}</label>"
        for value in DECISIONS
    )
    navigation = "".join(
        f'<a class="nav {"done" if is_complete(item) else "todo"} {"current" if position == index else ""}" '
        f'href="/?record={position + 1}">{position + 1}</a>'
        for position, item in enumerate(rows)
    )
    error_html = (
        ""
        if not errors
        else '<div class="errors">' + "<br>".join(map(html.escape, errors)) + "</div>"
    )
    help_items = "".join(
        f"<li><code>{key}</code>: {html.escape(value)}</li>"
        for key, value in DEPARTMENT_HELP.items()
    )
    previous = max(1, index)
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ComplaintGuard Blind Review</title>
<style>
body{{font:16px system-ui,sans-serif;margin:0;background:#f4f6f8;color:#17212b}}main{{max-width:1050px;margin:auto;padding:24px}}
.card{{background:white;border:1px solid #ccd5df;border-radius:12px;padding:22px;margin-bottom:18px}}.complaint{{font-size:1.35rem;line-height:1.5}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}label{{display:block;margin:8px 0}}select,textarea{{width:100%;box-sizing:border-box;padding:9px}}
button,.button{{display:inline-block;padding:10px 15px;border:0;border-radius:7px;background:#175cd3;color:white;text-decoration:none;cursor:pointer}}
.secondary{{background:#52606d}}.nav{{display:inline-block;width:30px;padding:5px;margin:3px;text-align:center;text-decoration:none;border-radius:5px}}
.done{{background:#d1fadf;color:#075e36}}.todo{{background:#e7ebef;color:#394452}}.current{{outline:3px solid #175cd3}}.errors{{background:#fee4e2;color:#912018;padding:12px;margin:12px 0}}
.reminder{{background:#fff7d6}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Stage 1B Blind Human Review</h1>
<p><strong>Record {index + 1} of {len(rows)}</strong> · Completed {completed} · Incomplete {len(rows) - completed}</p>
<div class="card"><p><strong>Record ID:</strong> {html.escape(row["record_id"])}</p>
<p class="complaint">{html.escape(row["complaint_text"])}</p><p><strong>Neutral reasons:</strong> {html.escape(row["review_reasons"])}</p>
<p><strong>Word count:</strong> {html.escape(row["word_count"])}</p></div>{error_html}
<form method="post" action="/save"><input type="hidden" name="index" value="{index}"><div class="card grid"><section>
<h2>Department</h2><select name="reviewer_department"><option value="">Choose…</option>{options}</select>
<h2>Decision</h2>{decisions}</section><section><label>Complete revised text (revise only)<textarea name="revised_text" rows="4">{html.escape(row["revised_text"])}</textarea></label>
<label>Reviewer note<textarea name="reviewer_note" rows="4">{html.escape(row["reviewer_note"])}</textarea></label></section></div>
<a class="button secondary" href="/?record={previous}">Previous</a> <button name="action" value="save">Save</button> <button name="action" value="next">Save and Next</button></form>
<div class="card"><h2>Navigation</h2>{navigation}</div><div class="card reminder"><h2>Review reminders</h2><ul>
<li>Typos and informal wording are not automatically wrong.</li><li>Hard examples are not automatically rejected.</li>
<li>Reject when two departments are equally defensible.</li><li>Do not consult the sealed reference or any model prediction.</li>
<li>Select based on the primary complaint problem.</li></ul><h3>Neutral department guide</h3><ul>{help_items}</ul></div>
<div class="card"><h2>Completion summary</h2><p>{completed} of {len(rows)} records satisfy the entry rules. No result is automatically approved or submitted.</p></div>
</main></body></html>"""
    return body.encode("utf-8")


class ReviewHandler(BaseHTTPRequestHandler):
    working_path = WORKING_PATH

    def send_page(self, index: int, errors: list[str] | None = None) -> None:
        rows = read_rows(self.working_path)
        index = min(max(index, 0), len(rows) - 1)
        content = page(rows, index, errors)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        query = urllib.parse.parse_qs(parsed.query)
        try:
            index = int(query.get("record", ["1"])[0]) - 1
        except ValueError:
            index = 0
        self.send_page(index)

    def do_POST(self) -> None:
        if self.path != "/save":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20_000:
                raise ValueError("request is too large")
            form = urllib.parse.parse_qs(
                self.rfile.read(length).decode("utf-8"), keep_blank_values=True
            )
            index = int(form.get("index", ["-1"])[0])
            values = {field: form.get(field, [""])[0] for field in HUMAN_FIELDS}
            errors = save_entry(self.working_path, index, values)
        except (UnicodeDecodeError, ValueError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if errors:
            self.send_page(index, errors)
            return
        destination = index + 1 if form.get("action", ["save"])[0] == "next" else index
        destination = min(destination, 72)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?record={destination + 1}")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--validate-blank-copy", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    create_working_copy(PRISTINE_PATH, WORKING_PATH)
    if args.validate_blank_copy:
        errors = validate_blank_working_copy(PRISTINE_PATH, WORKING_PATH)
        if errors:
            print("\n".join(f"ERROR: {error}" for error in errors))
            return 1
        print("Blank completed-review copy validation passed: rows=73")
        return 0
    server = ThreadingHTTPServer((HOST, args.port), ReviewHandler)
    url = f"http://{HOST}:{server.server_port}/"
    print(f"ComplaintGuard blind review is available only at {url}")
    print("Press Ctrl+C to stop. Progress is saved after each successful Save action.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
