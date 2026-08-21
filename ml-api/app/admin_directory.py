"""Read-only, bounded Admin directory workflow for Staff and Manager profiles."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.admin_auth import AdminAuthBackend
from app.schemas import AdminDirectoryRequest, AdminDirectoryResponse, AdminDirectoryRow
from app.ticketing import PersistenceError

MAX_DIRECTORY_SCAN = 200
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DEPARTMENTS = {
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
}


class DirectoryDataIntegrityError(PersistenceError):
    """A stored Staff/Manager profile is malformed and is not exposed."""


class AdminDirectoryBackend(AdminAuthBackend, Protocol):
    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]: ...


@dataclass(frozen=True)
class DirectoryCursor:
    offset: int


def encode_directory_cursor(offset: int) -> str:
    if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= MAX_DIRECTORY_SCAN:
        raise ValueError("cursor offset is invalid")
    payload = json.dumps({"v": 1, "offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_directory_cursor(value: str | None) -> DirectoryCursor:
    if value is None:
        return DirectoryCursor(0)
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("cursor is invalid")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("cursor is invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 1
        or not isinstance(payload.get("offset"), int)
        or isinstance(payload["offset"], bool)
        or not 0 <= payload["offset"] <= MAX_DIRECTORY_SCAN
    ):
        raise ValueError("cursor is invalid")
    return DirectoryCursor(payload["offset"])


def _parse_profile(uid: str, value: Any) -> AdminDirectoryRow | None:
    if not isinstance(uid, str) or not uid or not isinstance(value, dict):
        raise DirectoryDataIntegrityError("directory profile is malformed")
    expected = {
        "email",
        "displayName",
        "locale",
        "role",
        "departmentId",
        "active",
        "createdAt",
        "updatedAt",
    }
    if set(value) != expected:
        raise DirectoryDataIntegrityError("directory profile is malformed")
    email = value["email"]
    display_name = value["displayName"]
    role = value["role"]
    department = value["departmentId"]
    active = value["active"]
    if (
        not isinstance(email, str)
        or not _EMAIL_PATTERN.fullmatch(email)
        or not isinstance(display_name, str)
        or not display_name.strip()
        or value["locale"] not in {"en", "my"}
        or role not in {"customer", "staff", "manager", "admin"}
        or type(active) is not bool
        or value["createdAt"] is None
        or value["updatedAt"] is None
        or (role == "staff" and department not in _DEPARTMENTS)
        or (role != "staff" and department is not None)
    ):
        raise DirectoryDataIntegrityError("directory profile is malformed")
    if role in {"customer", "admin"}:
        return None
    return AdminDirectoryRow(
        email=email,
        displayName=display_name.strip(),
        locale=value["locale"],
        role=role,
        departmentId=department,
        active=active,
        setupStatus="active" if active else "pending_setup",
    )


class AdminDirectoryService:
    def __init__(self, backend: AdminDirectoryBackend) -> None:
        self._backend = backend

    def list_users(self, request: AdminDirectoryRequest) -> AdminDirectoryResponse:
        cursor = decode_directory_cursor(request.cursor)
        try:
            profiles = self._backend.list_user_profiles(limit=MAX_DIRECTORY_SCAN)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc
        rows: list[tuple[tuple[str, str, str, str], AdminDirectoryRow]] = []
        for uid, value in profiles:
            row = _parse_profile(uid, value)
            if row is None:
                continue
            if request.role is not None and row.role != request.role:
                continue
            if request.department_id is not None and row.department_id != request.department_id:
                continue
            if request.active is not None and row.active is not request.active:
                continue
            if request.search is not None:
                needle = request.search.casefold()
                if needle not in row.email.casefold() and needle not in row.display_name.casefold():
                    continue
            rows.append(((row.email.casefold(), row.display_name.casefold(), row.role, uid), row))
        rows.sort(key=lambda item: item[0])
        selected = rows[cursor.offset : cursor.offset + request.page_size]
        next_offset = cursor.offset + len(selected)
        next_cursor = encode_directory_cursor(next_offset) if next_offset < len(rows) else None
        return AdminDirectoryResponse(
            rows=[row for _, row in selected],
            nextCursor=next_cursor,
            hasMore=next_cursor is not None,
        )
