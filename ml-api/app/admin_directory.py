"""Read-only, bounded Admin directory workflow for all application profiles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.admin_auth import AdminAuthBackend
from app.language import normalize_input
from app.schemas import (
    AdminDirectoryRequest,
    AdminDirectoryResponse,
    AdminDirectoryRow,
    AdminLifecycleEligibilityResponse,
    LifecycleEligibilityOperation,
    LifecycleEligibilityOperations,
)
from app.ticketing import PersistenceError

MAX_DIRECTORY_SCAN = 200
MAX_TICKET_ELIGIBILITY_SCAN = 200
ACCOUNT_REFERENCE_DOMAIN = "complaintguard:admin-account-ref:v1"
ACCOUNT_REFERENCE_PROJECT = "local-emulator:demo-complaintguard"
ACCOUNT_REFERENCE_PATTERN = re.compile(r"^acct_v1_[0-9a-f]{64}$")
UNRESOLVED_TICKET_STATUSES = {"submitted", "triaged", "in_progress", "awaiting_customer"}
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
    """A stored profile is malformed and is not exposed."""


class AdminDirectoryBackend(AdminAuthBackend, Protocol):
    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]: ...

    def list_tickets(self, *, limit: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class DirectoryCursor:
    offset: int
    filter_fingerprint: str


def _filter_fingerprint(request: AdminDirectoryRequest) -> str:
    canonical = json.dumps(
        {
            "role": request.role,
            "departmentId": request.department_id,
            "active": request.active,
            "search": request.search,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def canonical_account_reference_input(uid: str, *, project_domain: str = ACCOUNT_REFERENCE_PROJECT) -> str:
    if not isinstance(uid, str) or not 1 <= len(uid) <= 128 or uid != uid.strip() or any(character.isspace() for character in uid):
        raise ValueError("account reference input is invalid")
    if not isinstance(project_domain, str) or not 1 <= len(project_domain) <= 128:
        raise ValueError("account reference project is invalid")
    return json.dumps(
        {"domain": ACCOUNT_REFERENCE_DOMAIN, "project": project_domain, "uid": uid},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def account_reference(uid: str, *, project_domain: str = ACCOUNT_REFERENCE_PROJECT) -> str:
    canonical = canonical_account_reference_input(uid, project_domain=project_domain)
    return "acct_v1_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_account_reference(value: str) -> str:
    if not isinstance(value, str) or not ACCOUNT_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError("account reference is invalid")
    return value


def encode_directory_cursor(offset: int, filter_fingerprint: str) -> str:
    if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= MAX_DIRECTORY_SCAN:
        raise ValueError("cursor offset is invalid")
    if filter_fingerprint and not re.fullmatch(r"[0-9a-f]{64}", filter_fingerprint):
        raise ValueError("cursor filter binding is invalid")
    payload = {"v": 2, "offset": offset, "f": filter_fingerprint}
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_directory_cursor(value: str | None, *, expected_filter_fingerprint: str | None = None) -> DirectoryCursor:
    if value is None:
        return DirectoryCursor(0, expected_filter_fingerprint or "")
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("cursor is invalid")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("cursor is invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 2
        or not isinstance(payload.get("offset"), int)
        or isinstance(payload["offset"], bool)
        or not 0 <= payload["offset"] <= MAX_DIRECTORY_SCAN
        or set(payload) != {"v", "offset", "f"}
        or not isinstance(payload.get("f"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["f"])
    ):
        raise ValueError("cursor is invalid")
    if expected_filter_fingerprint is not None and payload["f"] != expected_filter_fingerprint:
        raise ValueError("cursor filter binding is invalid")
    return DirectoryCursor(payload["offset"], payload["f"])


def _valid_timestamp(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _parse_profile(uid: str, value: Any) -> AdminDirectoryRow | None:
    if not isinstance(uid, str) or not 1 <= len(uid) <= 128 or not isinstance(value, dict):
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
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    normalized_display_name = normalize_input(display_name) if isinstance(display_name, str) else ""
    if (
        not isinstance(email, str)
        or not _EMAIL_PATTERN.fullmatch(email)
        or email != normalized_email
        or not isinstance(display_name, str)
        or display_name != normalized_display_name
        or not normalized_display_name
        or value["locale"] not in {"en", "my"}
        or role not in {"customer", "staff", "manager", "admin"}
        or type(active) is not bool
        or not _valid_timestamp(value["createdAt"])
        or not _valid_timestamp(value["updatedAt"])
        or (role == "staff" and department not in _DEPARTMENTS)
        or (role != "staff" and department is not None)
    ):
        raise DirectoryDataIntegrityError("directory profile is malformed")
    return AdminDirectoryRow(
        email=email,
        displayName=normalized_display_name,
        locale=value["locale"],
        role=role,
        departmentId=department,
        active=active,
        setupStatus="active" if active else "pending_setup",
        accountRef=account_reference(uid),
    )


class AdminDirectoryService:
    def __init__(self, backend: AdminDirectoryBackend) -> None:
        self._backend = backend

    def list_users(self, request: AdminDirectoryRequest) -> AdminDirectoryResponse:
        if request.department_id is not None and request.role not in {None, "staff"}:
            raise ValueError("department filtering is limited to Staff profiles")
        fingerprint = _filter_fingerprint(request)
        cursor = decode_directory_cursor(request.cursor, expected_filter_fingerprint=fingerprint)
        try:
            profiles = self._backend.list_user_profiles(limit=MAX_DIRECTORY_SCAN)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc
        rows: list[tuple[tuple[str, str, str, str], AdminDirectoryRow]] = []
        seen_emails: set[str] = set()
        for uid, value in profiles:
            row = _parse_profile(uid, value)
            if row is None:
                continue
            normalized_email = row.email.casefold()
            if normalized_email in seen_emails:
                raise DirectoryDataIntegrityError("directory email identity is inconsistent")
            seen_emails.add(normalized_email)
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
        next_cursor = encode_directory_cursor(next_offset, fingerprint) if next_offset < len(rows) else None
        return AdminDirectoryResponse(
            rows=[row for _, row in selected],
            nextCursor=next_cursor,
            hasMore=next_cursor is not None,
        )

    def lifecycle_eligibility(
        self,
        actor_uid: str,
        account_ref: str,
    ) -> AdminLifecycleEligibilityResponse:
        validate_account_reference(account_ref)
        try:
            profiles = self._backend.list_user_profiles(limit=MAX_DIRECTORY_SCAN + 1)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc
        if len(profiles) > MAX_DIRECTORY_SCAN:
            raise PersistenceError("lifecycle profile scan is incomplete")

        target: tuple[str, AdminDirectoryRow] | None = None
        valid_active_admins = 0
        seen_references: set[str] = set()
        for uid, value in profiles:
            row = _parse_profile(uid, value)
            reference = row.account_ref
            if reference in seen_references:
                raise DirectoryDataIntegrityError("directory account reference is inconsistent")
            seen_references.add(reference)
            if row.role == "admin" and row.active:
                valid_active_admins += 1
            if reference == account_ref:
                target = (uid, row)
        if target is None:
            raise LookupError("account reference not found")

        target_uid, row = target
        same_actor = target_uid == actor_uid
        if row.active:
            disable_reason = "self_target_forbidden" if same_actor else None
            if disable_reason is None and row.role == "admin" and valid_active_admins <= 1:
                disable_reason = "last_active_admin"
            disable = LifecycleEligibilityOperation(
                eligible=disable_reason is None,
                reason=disable_reason,
            )
            reactivate = LifecycleEligibilityOperation(
                eligible=False,
                reason="self_target_forbidden" if same_actor else "already_active",
            )
        else:
            disable = LifecycleEligibilityOperation(
                eligible=False,
                reason="already_inactive",
            )
            reactivate_reason = "self_target_forbidden" if same_actor else "pending_setup_activation_forbidden"
            reactivate = LifecycleEligibilityOperation(
                eligible=False,
                reason=reactivate_reason,
            )

        reassignment_reason: str | None = None
        reassignment_eligible = row.role == "staff"
        if row.role != "staff":
            reassignment_reason = "role_not_reassignable"
            reassignment_eligible = False
        else:
            try:
                tickets = self._backend.list_tickets(limit=MAX_TICKET_ELIGIBILITY_SCAN + 1)
            except PersistenceError:
                raise
            except Exception as exc:
                raise PersistenceError("ticket eligibility lookup failed") from exc
            if len(tickets) > MAX_TICKET_ELIGIBILITY_SCAN:
                raise PersistenceError("ticket eligibility scan is incomplete")
            for ticket in tickets:
                if not isinstance(ticket, dict):
                    raise DirectoryDataIntegrityError("ticket eligibility data is malformed")
                status = ticket.get("status")
                assigned_staff_id = ticket.get("assignedStaffId")
                if not isinstance(status, str) or (
                    assigned_staff_id is not None and not isinstance(assigned_staff_id, str)
                ):
                    raise DirectoryDataIntegrityError("ticket eligibility data is malformed")
                if status in UNRESOLVED_TICKET_STATUSES and assigned_staff_id == target_uid:
                    reassignment_reason = "assigned_unresolved_work"
                    reassignment_eligible = False
                    break
        operations = LifecycleEligibilityOperations(
            disable=disable,
            reactivate=reactivate,
            reassignDepartment=LifecycleEligibilityOperation(
                eligible=reassignment_eligible,
                reason=reassignment_reason,
            ),
        )
        return AdminLifecycleEligibilityResponse(
            accountRef=account_ref,
            profileState="active" if row.active else "inactive",
            operations=operations,
        )

    def resolve_account_reference(
        self, account_ref: str
    ) -> tuple[str, AdminDirectoryRow]:
        """Resolve an opaque account reference after trusted authorization."""

        validate_account_reference(account_ref)
        try:
            profiles = self._backend.list_user_profiles(limit=MAX_DIRECTORY_SCAN + 1)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc
        if len(profiles) > MAX_DIRECTORY_SCAN:
            raise PersistenceError("lifecycle profile scan is incomplete")
        found: tuple[str, AdminDirectoryRow] | None = None
        seen_references: set[str] = set()
        for uid, value in profiles:
            row = _parse_profile(uid, value)
            if row.account_ref in seen_references:
                raise DirectoryDataIntegrityError("directory account reference is inconsistent")
            seen_references.add(row.account_ref)
            if row.account_ref == account_ref:
                found = (uid, row)
        if found is None:
            raise LookupError("account reference not found")
        return found
