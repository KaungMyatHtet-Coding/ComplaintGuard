"""Version 2 department and Staff foundation.

All writes in this module are trusted-admin operations.  It is intentionally
separate from the V1 account and ticket workflows: no existing V1 document is
rewritten and no routing or assignment decision is made here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.admin_auth import AdminAuthBackend, AdminPrincipal, FirebaseAdminAuthBackend
from app.ticketing import PersistenceError, run_firestore_transaction
from app.v2_contracts import (
    V2_CATEGORY_IDS,
    V2_TAXONOMY_VERSION,
    StaffAvailabilityState,
    StaffEmploymentState,
    V2CategoryId,
)

MAX_PAGE_SIZE = 50
MAX_SCAN = 200
FOUNDATION_ACTION_DOMAIN = "complaintguard:v2-foundation:v1"
DEPARTMENT_STATE = ("active", "archived")
_EMPLOYEE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class FoundationValidationError(ValueError):
    """A request or stored foundation record is invalid."""


class FoundationNotFound(LookupError):
    """A requested department or Staff profile does not exist."""


class FoundationConflict(RuntimeError):
    """A safe mutation conflict, including duplicate IDs or employee codes."""


class FoundationIdempotencyConflict(FoundationConflict):
    """An idempotency key was reused with different request data."""


class FoundationPermissionError(PermissionError):
    """A mutation was attempted without an Admin principal."""


class AssignmentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    strategy: Literal["priority_then_workload"] = "priority_then_workload"
    language_preference: StrictBool = Field(default=True, alias="languagePreference")
    allow_manual_claim: StrictBool = Field(default=False, alias="allowManualClaim")


class DepartmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    department_id: V2CategoryId = Field(alias="departmentId")
    name_en: StrictStr = Field(alias="nameEn", min_length=1, max_length=120)
    name_my: StrictStr = Field(alias="nameMy", min_length=1, max_length=120)
    description: StrictStr = Field(min_length=1, max_length=500)
    is_customer_complaint_unit: StrictBool = Field(alias="isCustomerComplaintUnit")
    routing_enabled: StrictBool = Field(alias="routingEnabled")
    assignment_policy: AssignmentPolicy = Field(alias="assignmentPolicy")
    default_staff_capacity: StrictInt = Field(alias="defaultStaffCapacity", ge=1, le=100)
    idempotency_key: StrictStr = Field(alias="idempotencyKey", min_length=8, max_length=64)

    @field_validator("name_en", "name_my", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("idempotency_key")
    @classmethod
    def safe_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("idempotency key is invalid")
        return value

    @model_validator(mode="after")
    def validate_fallback(self) -> DepartmentCreateRequest:
        if self.is_customer_complaint_unit != (self.department_id == "general_complaints"):
            raise ValueError("only general_complaints is the Customer Complaint Unit")
        if not self.routing_enabled and self.department_id == "general_complaints":
            raise ValueError("Customer Complaint Unit routing must remain enabled")
        return self


class DepartmentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    name_en: StrictStr = Field(alias="nameEn", min_length=1, max_length=120)
    name_my: StrictStr = Field(alias="nameMy", min_length=1, max_length=120)
    description: StrictStr = Field(min_length=1, max_length=500)
    routing_enabled: StrictBool = Field(alias="routingEnabled")
    assignment_policy: AssignmentPolicy = Field(alias="assignmentPolicy")
    default_staff_capacity: StrictInt = Field(alias="defaultStaffCapacity", ge=1, le=100)
    idempotency_key: StrictStr = Field(alias="idempotencyKey", min_length=8, max_length=64)

    @field_validator("name_en", "name_my", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("idempotency_key")
    @classmethod
    def safe_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("idempotency key is invalid")
        return value


class StaffCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    employee_code: StrictStr = Field(alias="employeeCode", min_length=2, max_length=32)
    display_name: StrictStr = Field(alias="displayName", min_length=1, max_length=120)
    work_email: StrictStr = Field(alias="workEmail", min_length=3, max_length=254)
    department_ids: list[V2CategoryId] = Field(alias="departmentIds", min_length=1, max_length=8)
    primary_department_id: V2CategoryId = Field(alias="primaryDepartmentId")
    position: StrictStr = Field(min_length=1, max_length=120)
    employment_state: StaffEmploymentState = Field(alias="employmentState", default="invited")
    availability_state: StaffAvailabilityState = Field(alias="availabilityState", default="offline")
    capacity: StrictInt = Field(ge=1, le=100)
    language_skills: list[Literal["en", "my"]] = Field(alias="languageSkills", min_length=1, max_length=2)
    shift: StrictStr = Field(min_length=1, max_length=120)
    idempotency_key: StrictStr = Field(alias="idempotencyKey", min_length=8, max_length=64)

    @field_validator("employee_code")
    @classmethod
    def employee_code_format(cls, value: str) -> str:
        value = value.strip().upper()
        if not _EMPLOYEE_CODE.fullmatch(value):
            raise ValueError("employee code is invalid")
        return value

    @field_validator("display_name", "position", "shift", mode="before")
    @classmethod
    def trim_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("work_email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("language_skills")
    @classmethod
    def unique_languages(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("language skills must be unique")
        return value

    @model_validator(mode="after")
    def validate_membership(self) -> StaffCreateRequest:
        if self.primary_department_id not in self.department_ids:
            raise ValueError("primary department must be a member department")
        if self.employment_state != "active" and self.availability_state == "available":
            raise ValueError("non-active Staff cannot be available")
        return self


class StaffUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    display_name: StrictStr = Field(alias="displayName", min_length=1, max_length=120)
    work_email: StrictStr = Field(alias="workEmail", min_length=3, max_length=254)
    department_ids: list[V2CategoryId] = Field(alias="departmentIds", min_length=1, max_length=8)
    primary_department_id: V2CategoryId = Field(alias="primaryDepartmentId")
    position: StrictStr = Field(min_length=1, max_length=120)
    employment_state: StaffEmploymentState = Field(alias="employmentState")
    availability_state: StaffAvailabilityState = Field(alias="availabilityState")
    capacity: StrictInt = Field(ge=1, le=100)
    active_workload: StrictInt = Field(alias="activeWorkload", ge=0)
    language_skills: list[Literal["en", "my"]] = Field(alias="languageSkills", min_length=1, max_length=2)
    shift: StrictStr = Field(min_length=1, max_length=120)
    login_enabled: StrictBool = Field(alias="loginEnabled")
    idempotency_key: StrictStr = Field(alias="idempotencyKey", min_length=8, max_length=64)

    @field_validator("display_name", "position", "shift", mode="before")
    @classmethod
    def trim_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("work_email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("language_skills")
    @classmethod
    def unique_languages(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("language skills must be unique")
        return value

    @model_validator(mode="after")
    def validate_membership(self) -> StaffUpdateRequest:
        if self.primary_department_id not in self.department_ids:
            raise ValueError("primary department must be a member department")
        if self.active_workload > self.capacity:
            raise ValueError("active workload cannot exceed capacity")
        if self.employment_state != "active" and self.availability_state == "available":
            raise ValueError("non-active Staff cannot be available")
        return self


class FoundationPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    page_size: int = Field(default=25, alias="pageSize", ge=1, le=MAX_PAGE_SIZE)
    cursor: str | None = Field(default=None, max_length=512)
    state: str | None = Field(default=None, pattern=r"^(active|archived)$")
    employment_state: str | None = Field(default=None, alias="employmentState", pattern=r"^(invited|active|on_leave|suspended|departed|archived)$")
    department_id: str | None = Field(default=None, alias="departmentId")


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    department_id: V2CategoryId = Field(alias="departmentId")
    taxonomy_version: str = Field(alias="taxonomyVersion")
    name_en: str = Field(alias="nameEn")
    name_my: str = Field(alias="nameMy")
    description: str
    state: Literal["active", "archived"]
    is_customer_complaint_unit: bool = Field(alias="isCustomerComplaintUnit")
    routing_enabled: bool = Field(alias="routingEnabled")
    assignment_policy: AssignmentPolicy = Field(alias="assignmentPolicy")
    default_staff_capacity: int = Field(alias="defaultStaffCapacity")
    service_identity_id: str = Field(alias="serviceIdentityId")
    created_at: Any = Field(alias="createdAt")
    created_by: str = Field(alias="createdBy")
    updated_at: Any = Field(alias="updatedAt")
    updated_by: str = Field(alias="updatedBy")


class StaffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    staff_id: str = Field(alias="staffId")
    uid: str
    employee_code: str = Field(alias="employeeCode")
    display_name: str = Field(alias="displayName")
    work_email: str = Field(alias="workEmail")
    department_ids: list[V2CategoryId] = Field(alias="departmentIds")
    primary_department_id: V2CategoryId = Field(alias="primaryDepartmentId")
    position: str
    employment_state: StaffEmploymentState = Field(alias="employmentState")
    availability_state: StaffAvailabilityState = Field(alias="availabilityState")
    capacity: int
    active_workload: int = Field(alias="activeWorkload")
    language_skills: list[str] = Field(alias="languageSkills")
    shift: str
    login_enabled: bool = Field(alias="loginEnabled")
    joined_at: Any = Field(alias="joinedAt")
    departed_at: Any = Field(alias="departedAt")
    created_at: Any = Field(alias="createdAt")
    created_by: str = Field(alias="createdBy")
    updated_at: Any = Field(alias="updatedAt")
    updated_by: str = Field(alias="updatedBy")
    profile_version: int = Field(alias="profileVersion")
    historical_identity_id: str = Field(alias="historicalIdentityId")


class HistoricalIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    historical_identity_id: str = Field(alias="historicalIdentityId")
    uid: str
    employee_code: str = Field(alias="employeeCode")
    display_name: str = Field(alias="displayName")
    department_ids: list[V2CategoryId] = Field(alias="departmentIds")
    primary_department_id: V2CategoryId = Field(alias="primaryDepartmentId")
    position: str
    profile_version: int = Field(alias="profileVersion")
    joined_at: Any = Field(alias="joinedAt")
    departed_at: Any = Field(alias="departedAt")
    created_at: Any = Field(alias="createdAt")


class DepartmentPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    departments: list[DepartmentResponse]
    next_cursor: str | None = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")


class StaffPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    staff: list[StaffResponse]
    next_cursor: str | None = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _action_id(actor_uid: str, operation: str, target: str, key: str) -> str:
    return hashlib.sha256(json.dumps([FOUNDATION_ACTION_DOMAIN, actor_uid, operation, target, key], separators=(",", ":")).encode()).hexdigest()


def _cursor(offset: int, fingerprint: str) -> str:
    payload = json.dumps({"v": 1, "offset": offset, "filter": fingerprint}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None, fingerprint: str) -> int:
    if value is None:
        return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FoundationValidationError("cursor is invalid") from exc
    if payload.get("v") != 1 or payload.get("filter") != fingerprint or not isinstance(payload.get("offset"), int) or not 0 <= payload["offset"] <= MAX_SCAN:
        raise FoundationValidationError("cursor is invalid")
    return payload["offset"]


def _validate_department_id(value: str) -> V2CategoryId:
    if value not in V2_CATEGORY_IDS:
        raise FoundationValidationError("unknown V2 department")
    return value  # type: ignore[return-value]


def _validate_email(value: str) -> str:
    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        raise FoundationValidationError("work email is invalid")
    return value


def _department_doc(request: DepartmentCreateRequest, actor: AdminPrincipal, timestamp: Any) -> dict[str, Any]:
    return {
        "departmentId": request.department_id,
        "taxonomyVersion": V2_TAXONOMY_VERSION,
        "nameEn": request.name_en,
        "nameMy": request.name_my,
        "description": request.description,
        "state": "active",
        "isCustomerComplaintUnit": request.is_customer_complaint_unit,
        "routingEnabled": request.routing_enabled,
        "assignmentPolicy": request.assignment_policy.model_dump(by_alias=True),
        "defaultStaffCapacity": request.default_staff_capacity,
        "serviceIdentityId": f"department_service_{request.department_id}",
        "createdAt": timestamp,
        "createdBy": actor.uid,
        "updatedAt": timestamp,
        "updatedBy": actor.uid,
    }


def _queue_doc(department_id: str, timestamp: Any) -> dict[str, Any]:
    return {
        "departmentId": department_id,
        "queuedCount": 0,
        "assignedCount": 0,
        "assignmentSequence": 0,
        "version": 1,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def staff_is_eligible_for_assignment(profile: dict[str, Any]) -> bool:
    """Pure eligibility contract for future assignment; this phase never calls it to assign."""
    return (
        profile.get("employmentState") == "active"
        and profile.get("availabilityState") == "available"
        and profile.get("loginEnabled") is True
        and isinstance(profile.get("activeWorkload"), int)
        and isinstance(profile.get("capacity"), int)
        and profile["activeWorkload"] < profile["capacity"]
    )


def _audit_doc(actor: AdminPrincipal, action: str, target_type: str, target_id: str, before: Any, after: Any, timestamp: Any, action_id: str) -> dict[str, Any]:
    return {
        "actorUid": actor.uid,
        "actorRole": actor.role,
        "actorDisplayName": actor.display_name,
        "action": action,
        "targetType": target_type,
        "targetId": target_id,
        "before": before,
        "after": after,
        "actionId": action_id,
        "createdAt": timestamp,
    }


class FoundationBackend(AdminAuthBackend, Protocol):
    server_timestamp: Any

    def create_department(self, actor: AdminPrincipal, request: DepartmentCreateRequest) -> dict[str, Any]: ...
    def update_department(self, actor: AdminPrincipal, department_id: str, request: DepartmentUpdateRequest) -> dict[str, Any]: ...
    def set_department_state(self, actor: AdminPrincipal, department_id: str, state: str, idempotency_key: str) -> dict[str, Any]: ...
    def get_department(self, department_id: str) -> dict[str, Any]: ...
    def list_departments(self, request: FoundationPageRequest) -> DepartmentPageResponse: ...
    def create_staff(self, actor: AdminPrincipal, request: StaffCreateRequest) -> dict[str, Any]: ...
    def update_staff(self, actor: AdminPrincipal, staff_id: str, request: StaffUpdateRequest) -> dict[str, Any]: ...
    def get_staff(self, staff_id: str) -> dict[str, Any]: ...
    def list_staff(self, request: FoundationPageRequest) -> StaffPageResponse: ...


@dataclass
class InMemoryFoundationBackend:
    """Deterministic backend for pure/API tests; mirrors durable document shapes."""

    profiles: dict[str, dict[str, Any]]
    departments: dict[str, dict[str, Any]]

    def __init__(self) -> None:
        self.profiles = {}
        self.departments = {}
        self.identities: dict[str, dict[str, Any]] = {}
        self.actions: dict[str, dict[str, Any]] = {}
        self.audits: list[dict[str, Any]] = []
        self.memberships: dict[tuple[str, str], dict[str, Any]] = {}
        self.auth: dict[str, dict[str, Any]] = {}
        self.server_timestamp = datetime.now(timezone.utc)
        self._counter = 0

    def verify_id_token(self, token: str) -> dict[str, Any]:
        if token != "admin-token":
            from app.ticketing import AuthenticationError
            raise AuthenticationError("invalid token")
        return {"uid": "admin-uid", "email": "admin@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        if uid == "admin-uid":
            return {"uid": uid, "email": "admin@example.test", "displayName": "Synthetic Admin", "locale": "en", "role": "admin", "departmentId": None, "active": True, "accountState": "active", "createdAt": self.server_timestamp, "updatedAt": self.server_timestamp}
        return self.profiles.get(uid)

    def _timestamp(self) -> datetime:
        return datetime.now(timezone.utc)

    def _audit(self, actor: AdminPrincipal, action: str, target_type: str, target_id: str, before: Any, after: Any, action_id: str) -> None:
        self.audits.append(_audit_doc(actor, action, target_type, target_id, deepcopy(before), deepcopy(after), self._timestamp(), action_id))

    def _idempotency(self, actor: AdminPrincipal, operation: str, target: str, key: str, request: Any) -> tuple[str, dict[str, Any] | None]:
        action_id = _action_id(actor.uid, operation, target, key)
        fingerprint = _fingerprint(request)
        existing = self.actions.get(action_id)
        if existing and existing["requestFingerprint"] != fingerprint:
            raise FoundationIdempotencyConflict("idempotency key reused")
        return action_id, existing

    def create_department(self, actor: AdminPrincipal, request: DepartmentCreateRequest) -> dict[str, Any]:
        action_id, existing = self._idempotency(actor, "create_department", request.department_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing:
            return deepcopy(self.departments[request.department_id])
        if request.department_id in self.departments:
            raise FoundationConflict("department already exists")
        timestamp = self._timestamp()
        document = _department_doc(request, actor, timestamp)
        self.departments[request.department_id] = document
        self.actions[action_id] = {"requestFingerprint": _fingerprint(request.model_dump(mode="json", by_alias=True)), "status": "completed", "targetId": request.department_id}
        self._audit(actor, "department_created", "department", request.department_id, None, document, action_id)
        return deepcopy(document)

    def update_department(self, actor: AdminPrincipal, department_id: str, request: DepartmentUpdateRequest) -> dict[str, Any]:
        _validate_department_id(department_id)
        action_id, existing = self._idempotency(actor, "update_department", department_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing:
            return deepcopy(self.departments[department_id])
        current = self.departments.get(department_id)
        if current is None:
            raise FoundationNotFound("department not found")
        if department_id == "general_complaints" and not request.routing_enabled:
            raise FoundationValidationError("Customer Complaint Unit routing must remain enabled")
        before = deepcopy(current)
        current.update({"nameEn": request.name_en, "nameMy": request.name_my, "description": request.description, "routingEnabled": request.routing_enabled, "assignmentPolicy": request.assignment_policy.model_dump(by_alias=True), "defaultStaffCapacity": request.default_staff_capacity, "updatedAt": self._timestamp(), "updatedBy": actor.uid})
        self.actions[action_id] = {"requestFingerprint": _fingerprint(request.model_dump(mode="json", by_alias=True)), "status": "completed", "targetId": department_id}
        self._audit(actor, "department_updated", "department", department_id, before, current, action_id)
        return deepcopy(current)

    def set_department_state(self, actor: AdminPrincipal, department_id: str, state: str, idempotency_key: str) -> dict[str, Any]:
        _validate_department_id(department_id)
        if state not in DEPARTMENT_STATE:
            raise FoundationValidationError("department state is invalid")
        action_id, existing = self._idempotency(actor, f"department_{state}", department_id, idempotency_key, {"state": state})
        current = self.departments.get(department_id)
        if current is None:
            raise FoundationNotFound("department not found")
        if existing:
            return deepcopy(current)
        before = deepcopy(current)
        current["state"] = state
        if state == "archived":
            current["routingEnabledBeforeArchive"] = current["routingEnabled"]
            current["routingEnabled"] = False
        elif state == "active" and "routingEnabledBeforeArchive" in current:
            current["routingEnabled"] = current.pop("routingEnabledBeforeArchive")
        current["updatedAt"] = self._timestamp()
        current["updatedBy"] = actor.uid
        self.actions[action_id] = {"requestFingerprint": _fingerprint({"state": state}), "status": "completed", "targetId": department_id}
        self._audit(actor, f"department_{state}", "department", department_id, before, current, action_id)
        return deepcopy(current)

    def get_department(self, department_id: str) -> dict[str, Any]:
        _validate_department_id(department_id)
        if department_id not in self.departments:
            raise FoundationNotFound("department not found")
        return deepcopy(self.departments[department_id])

    def list_departments(self, request: FoundationPageRequest) -> DepartmentPageResponse:
        fingerprint = _fingerprint(request.model_dump(mode="json", by_alias=True))
        offset = _decode_cursor(request.cursor, fingerprint)
        rows = list(self.departments.values())
        if request.state:
            rows = [row for row in rows if row["state"] == request.state]
        rows.sort(key=lambda row: row["departmentId"])
        selected = rows[offset : offset + request.page_size]
        next_offset = offset + len(selected)
        next_cursor = _cursor(next_offset, fingerprint) if next_offset < len(rows) else None
        return DepartmentPageResponse(departments=[DepartmentResponse.model_validate(row) for row in selected], nextCursor=next_cursor, hasMore=next_cursor is not None)

    def _validate_staff_departments(self, request: StaffCreateRequest | StaffUpdateRequest) -> None:
        if len(set(request.department_ids)) != len(request.department_ids):
            raise FoundationValidationError("department memberships must be unique")
        for department_id in request.department_ids:
            department = self.departments.get(department_id)
            if department is None or department["state"] != "active":
                raise FoundationValidationError("department reference is invalid")

    def _staff_document(self, actor: AdminPrincipal, request: StaffCreateRequest, staff_id: str, uid: str, identity_id: str, timestamp: Any) -> dict[str, Any]:
        joined = timestamp if request.employment_state in {"active", "on_leave", "suspended"} else None
        return {"staffId": staff_id, "uid": uid, "employeeCode": request.employee_code, "displayName": request.display_name, "workEmail": _validate_email(request.work_email), "departmentIds": request.department_ids, "primaryDepartmentId": request.primary_department_id, "position": request.position, "employmentState": request.employment_state, "availabilityState": request.availability_state, "capacity": request.capacity, "activeWorkload": 0, "languageSkills": request.language_skills, "shift": request.shift, "loginEnabled": False, "joinedAt": joined, "departedAt": None, "createdAt": timestamp, "createdBy": actor.uid, "updatedAt": timestamp, "updatedBy": actor.uid, "profileVersion": 1, "historicalIdentityId": identity_id}

    def create_staff(self, actor: AdminPrincipal, request: StaffCreateRequest) -> dict[str, Any]:
        self._validate_staff_departments(request)
        action_id, existing = self._idempotency(actor, "create_staff", request.employee_code, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing:
            return deepcopy(self.profiles[existing["staffId"]])
        if any(profile["employeeCode"] == request.employee_code for profile in self.profiles.values()):
            raise FoundationConflict("employee code already exists")
        self._counter += 1
        staff_id = f"staff_v2_{self._counter:06d}"
        uid = f"staff-v2-{self._counter:06d}"
        identity_id = f"staff_identity_v2_{self._counter:06d}"
        timestamp = self._timestamp()
        profile = self._staff_document(actor, request, staff_id, uid, identity_id, timestamp)
        self.profiles[staff_id] = profile
        self.auth[uid] = {"uid": uid, "email": request.work_email, "disabled": True}
        self.identities[identity_id] = self._identity_snapshot(profile)
        for department_id in request.department_ids:
            self.memberships[(department_id, staff_id)] = {"departmentId": department_id, "staffId": staff_id, "uid": uid, "membershipState": "active", "createdAt": timestamp, "updatedAt": timestamp}
        self.actions[action_id] = {"requestFingerprint": _fingerprint(request.model_dump(mode="json", by_alias=True)), "status": "completed", "staffId": staff_id}
        self._audit(actor, "staff_created", "staffProfile", staff_id, None, profile, action_id)
        return deepcopy(profile)

    @staticmethod
    def _identity_snapshot(profile: dict[str, Any]) -> dict[str, Any]:
        return {key: profile[key] for key in ("historicalIdentityId", "uid", "employeeCode", "displayName", "departmentIds", "primaryDepartmentId", "position", "profileVersion", "joinedAt", "departedAt", "createdAt")}

    def update_staff(self, actor: AdminPrincipal, staff_id: str, request: StaffUpdateRequest) -> dict[str, Any]:
        profile = self.profiles.get(staff_id)
        if profile is None:
            raise FoundationNotFound("Staff profile not found")
        self._validate_staff_departments(request)
        action_id, existing = self._idempotency(actor, "update_staff", staff_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing:
            return deepcopy(profile)
        if any(other["employeeCode"] == profile["employeeCode"] and other["staffId"] != staff_id for other in self.profiles.values()):
            raise FoundationConflict("employee code already exists")
        if request.work_email != profile["workEmail"] and any(other["workEmail"] == request.work_email and other["staffId"] != staff_id for other in self.profiles.values()):
            raise FoundationConflict("work email already exists")
        before = deepcopy(profile)
        old_departments = set(profile["departmentIds"])
        profile.update({"displayName": request.display_name, "workEmail": _validate_email(request.work_email), "departmentIds": request.department_ids, "primaryDepartmentId": request.primary_department_id, "position": request.position, "employmentState": request.employment_state, "availabilityState": request.availability_state, "capacity": request.capacity, "activeWorkload": request.active_workload, "languageSkills": request.language_skills, "shift": request.shift, "loginEnabled": request.login_enabled, "profileVersion": profile["profileVersion"] + 1, "departedAt": self._timestamp() if request.employment_state in {"departed", "archived"} else None, "updatedAt": self._timestamp(), "updatedBy": actor.uid})
        self.auth[profile["uid"]]["email"] = profile["workEmail"]
        self.auth[profile["uid"]]["disabled"] = not request.login_enabled
        for department_id in old_departments - set(request.department_ids):
            self.memberships.pop((department_id, staff_id), None)
        for department_id in set(request.department_ids) - old_departments:
            self.memberships[(department_id, staff_id)] = {"departmentId": department_id, "staffId": staff_id, "uid": profile["uid"], "membershipState": "active", "createdAt": profile["createdAt"], "updatedAt": profile["updatedAt"]}
        self.identities[f"{profile['historicalIdentityId']}_v{profile['profileVersion']}"] = self._identity_snapshot(profile)
        self.actions[action_id] = {"requestFingerprint": _fingerprint(request.model_dump(mode="json", by_alias=True)), "status": "completed", "staffId": staff_id}
        self._audit(actor, "staff_updated", "staffProfile", staff_id, before, profile, action_id)
        return deepcopy(profile)

    def get_staff(self, staff_id: str) -> dict[str, Any]:
        if staff_id not in self.profiles:
            raise FoundationNotFound("Staff profile not found")
        return deepcopy(self.profiles[staff_id])

    def list_staff(self, request: FoundationPageRequest) -> StaffPageResponse:
        fingerprint = _fingerprint(request.model_dump(mode="json", by_alias=True))
        offset = _decode_cursor(request.cursor, fingerprint)
        rows = list(self.profiles.values())
        if request.employment_state:
            rows = [row for row in rows if row["employmentState"] == request.employment_state]
        if request.department_id:
            _validate_department_id(request.department_id)
            rows = [row for row in rows if request.department_id in row["departmentIds"]]
        rows.sort(key=lambda row: row["employeeCode"])
        selected = rows[offset : offset + request.page_size]
        next_offset = offset + len(selected)
        next_cursor = _cursor(next_offset, fingerprint) if next_offset < len(rows) else None
        return StaffPageResponse(staff=[StaffResponse.model_validate(row) for row in selected], nextCursor=next_cursor, hasMore=next_cursor is not None)


class FirebaseAdminFoundationBackend(FirebaseAdminAuthBackend):
    """Firestore/Auth adapter; all privileged writes use Admin SDK transactions."""

    server_timestamp: Any

    def __init__(self, clients: tuple[Any, Any, object] | None = None) -> None:
        super().__init__(clients)
        self.server_timestamp = self._server_timestamp

    def _action_ref(self, action_id: str) -> Any:
        return self._db.collection("v2FoundationActions").document(action_id)

    def _audit_ref(self, action_id: str) -> Any:
        return self._db.collection("auditLogs").document(f"v2_{action_id}")

    def _reserve(self, actor: AdminPrincipal, operation: str, target: str, key: str, request: Any) -> tuple[str, dict[str, Any] | None]:
        action_id = _action_id(actor.uid, operation, target, key)
        fingerprint = _fingerprint(request)
        reference = self._action_ref(action_id)
        document = {"actionId": action_id, "operation": operation, "targetId": target, "actorUid": actor.uid, "requestFingerprint": fingerprint, "status": "started", "createdAt": self.server_timestamp, "updatedAt": self.server_timestamp}
        def operation_fn(transaction: Any) -> dict[str, Any] | None:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                return snapshot.to_dict()
            transaction.create(reference, document)
            return None
        try:
            return action_id, run_firestore_transaction(self._db, operation_fn)
        except Exception as exc:
            raise PersistenceError("foundation action reservation failed") from exc

    def _finish(self, transaction: Any, action_id: str, actor: AdminPrincipal, action: str, target_type: str, target_id: str, before: Any, after: Any) -> None:
        transaction.update(self._action_ref(action_id), {"status": "completed", "updatedAt": self.server_timestamp})
        transaction.create(self._audit_ref(action_id), _audit_doc(actor, action, target_type, target_id, before, after, self.server_timestamp, action_id))

    def create_department(self, actor: AdminPrincipal, request: DepartmentCreateRequest) -> dict[str, Any]:
        action_id, existing = self._reserve(actor, "create_department", request.department_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing:
            return self.get_department(request.department_id)
        reference = self._db.collection("departments").document(request.department_id)
        queue_reference = reference.collection("queueState").document("current")
        document = _department_doc(request, actor, self.server_timestamp)
        def operation(transaction: Any) -> dict[str, Any]:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                raise FoundationConflict("department already exists")
            transaction.create(reference, document)
            transaction.create(queue_reference, _queue_doc(request.department_id, self.server_timestamp))
            self._finish(transaction, action_id, actor, "department_created", "department", request.department_id, None, document)
            return document
        try:
            return run_firestore_transaction(self._db, operation)
        except (FoundationConflict, FoundationValidationError):
            raise
        except Exception as exc:
            raise PersistenceError("department creation failed") from exc

    def update_department(self, actor: AdminPrincipal, department_id: str, request: DepartmentUpdateRequest) -> dict[str, Any]:
        _validate_department_id(department_id)
        action_id, existing = self._reserve(actor, "update_department", department_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        reference = self._db.collection("departments").document(department_id)
        if existing:
            return self.get_department(department_id)
        def operation(transaction: Any) -> dict[str, Any]:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise FoundationNotFound("department not found")
            before = snapshot.to_dict() or {}
            if department_id == "general_complaints" and not request.routing_enabled:
                raise FoundationValidationError("Customer Complaint Unit routing must remain enabled")
            after = {**before, "nameEn": request.name_en, "nameMy": request.name_my, "description": request.description, "routingEnabled": request.routing_enabled, "assignmentPolicy": request.assignment_policy.model_dump(by_alias=True), "defaultStaffCapacity": request.default_staff_capacity, "updatedAt": self.server_timestamp, "updatedBy": actor.uid}
            transaction.update(reference, after)
            self._finish(transaction, action_id, actor, "department_updated", "department", department_id, before, after)
            return after
        try:
            return run_firestore_transaction(self._db, operation)
        except (FoundationConflict, FoundationValidationError, FoundationNotFound):
            raise
        except Exception as exc:
            raise PersistenceError("department update failed") from exc

    def set_department_state(self, actor: AdminPrincipal, department_id: str, state: str, idempotency_key: str) -> dict[str, Any]:
        _validate_department_id(department_id)
        if state not in DEPARTMENT_STATE:
            raise FoundationValidationError("department state is invalid")
        action_id, existing = self._reserve(actor, f"department_{state}", department_id, idempotency_key, {"state": state})
        reference = self._db.collection("departments").document(department_id)
        def operation(transaction: Any) -> dict[str, Any]:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise FoundationNotFound("department not found")
            before = snapshot.to_dict() or {}
            if existing:
                return before
            after = {**before, "state": state, "updatedAt": self.server_timestamp, "updatedBy": actor.uid}
            if state == "archived":
                after["routingEnabledBeforeArchive"] = before.get("routingEnabled", True)
                after["routingEnabled"] = False
            elif "routingEnabledBeforeArchive" in before:
                after["routingEnabled"] = before["routingEnabledBeforeArchive"]
                after.pop("routingEnabledBeforeArchive", None)
            transaction.update(reference, after)
            self._finish(transaction, action_id, actor, f"department_{state}", "department", department_id, before, after)
            return after
        try:
            return run_firestore_transaction(self._db, operation)
        except (FoundationConflict, FoundationValidationError, FoundationNotFound):
            raise
        except Exception as exc:
            raise PersistenceError("department state change failed") from exc

    def get_department(self, department_id: str) -> dict[str, Any]:
        _validate_department_id(department_id)
        try:
            snapshot = self._db.collection("departments").document(department_id).get()
        except Exception as exc:
            raise PersistenceError("department lookup failed") from exc
        if not snapshot.exists:
            raise FoundationNotFound("department not found")
        return snapshot.to_dict() or {}

    def list_departments(self, request: FoundationPageRequest) -> DepartmentPageResponse:
        fingerprint = _fingerprint(request.model_dump(mode="json", by_alias=True))
        offset = _decode_cursor(request.cursor, fingerprint)
        try:
            snapshots = self._db.collection("departments").limit(MAX_SCAN + 1).stream()
            rows = [snapshot.to_dict() or {} for snapshot in snapshots]
        except Exception as exc:
            raise PersistenceError("department list failed") from exc
        if len(rows) > MAX_SCAN:
            raise PersistenceError("department list scan is incomplete")
        if request.state:
            rows = [row for row in rows if row.get("state") == request.state]
        rows.sort(key=lambda row: row.get("departmentId", ""))
        selected = rows[offset : offset + request.page_size]
        next_offset = offset + len(selected)
        next_cursor = _cursor(next_offset, fingerprint) if next_offset < len(rows) else None
        return DepartmentPageResponse(departments=[DepartmentResponse.model_validate(row) for row in selected], nextCursor=next_cursor, hasMore=next_cursor is not None)

    def _validate_departments(self, department_ids: list[str]) -> None:
        if len(set(department_ids)) != len(department_ids):
            raise FoundationValidationError("department memberships must be unique")
        for department_id in department_ids:
            _validate_department_id(department_id)
            snapshot = self._db.collection("departments").document(department_id).get()
            if not snapshot.exists or (snapshot.to_dict() or {}).get("state") != "active":
                raise FoundationValidationError("department reference is invalid")

    def create_staff(self, actor: AdminPrincipal, request: StaffCreateRequest) -> dict[str, Any]:
        self._validate_departments(request.department_ids)
        _validate_email(request.work_email)
        action_id, existing = self._reserve(actor, "create_staff", request.employee_code, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        if existing and existing.get("staffId"):
            return self.get_staff(existing["staffId"])
        try:
            existing_codes = list(self._db.collection("staffProfiles").where("employeeCode", "==", request.employee_code).limit(1).stream())
            if existing_codes:
                raise FoundationConflict("employee code already exists")
            auth_record = self._auth.create_user(email=request.work_email, display_name=request.display_name, disabled=True)
            uid = getattr(auth_record, "uid", None)
            if not isinstance(uid, str):
                raise PersistenceError("Staff Auth identity was not created safely")
        except FoundationConflict:
            raise
        except Exception as exc:
            raise PersistenceError("Staff Auth identity creation failed") from exc
        staff_id = f"staff_v2_{uuid.uuid4().hex}"
        identity_id = f"staff_identity_v2_{uuid.uuid4().hex}"
        timestamp = self.server_timestamp
        profile = {"staffId": staff_id, "uid": uid, "employeeCode": request.employee_code, "displayName": request.display_name, "workEmail": request.work_email, "departmentIds": request.department_ids, "primaryDepartmentId": request.primary_department_id, "position": request.position, "employmentState": request.employment_state, "availabilityState": request.availability_state, "capacity": request.capacity, "activeWorkload": 0, "languageSkills": request.language_skills, "shift": request.shift, "loginEnabled": False, "joinedAt": timestamp if request.employment_state in {"active", "on_leave", "suspended"} else None, "departedAt": None, "createdAt": timestamp, "createdBy": actor.uid, "updatedAt": timestamp, "updatedBy": actor.uid, "profileVersion": 1, "historicalIdentityId": identity_id}
        identity = {key: profile[key] for key in ("historicalIdentityId", "uid", "employeeCode", "displayName", "departmentIds", "primaryDepartmentId", "position", "profileVersion", "joinedAt", "departedAt", "createdAt")}
        profile_reference = self._db.collection("staffProfiles").document(staff_id)
        identity_reference = self._db.collection("staffIdentities").document(identity_id)
        action_reference = self._action_ref(action_id)
        def operation(transaction: Any) -> dict[str, Any]:
            if next(transaction.get(profile_reference)).exists:
                raise FoundationConflict("Staff profile already exists")
            transaction.create(profile_reference, profile)
            transaction.create(identity_reference, identity)
            for department_id in request.department_ids:
                transaction.create(self._db.collection("departments").document(department_id).collection("members").document(staff_id), {"departmentId": department_id, "staffId": staff_id, "uid": uid, "membershipState": "active", "createdAt": timestamp, "updatedAt": timestamp})
            transaction.update(action_reference, {"staffId": staff_id, "uid": uid, "status": "completed", "updatedAt": timestamp})
            transaction.create(self._audit_ref(action_id), _audit_doc(actor, "staff_created", "staffProfile", staff_id, None, profile, timestamp, action_id))
            return profile
        try:
            return run_firestore_transaction(self._db, operation)
        except (FoundationConflict, FoundationValidationError):
            raise
        except Exception as exc:
            raise PersistenceError("Staff profile creation failed") from exc

    def update_staff(self, actor: AdminPrincipal, staff_id: str, request: StaffUpdateRequest) -> dict[str, Any]:
        self._validate_departments(request.department_ids)
        _validate_email(request.work_email)
        action_id, existing = self._reserve(actor, "update_staff", staff_id, request.idempotency_key, request.model_dump(mode="json", by_alias=True))
        reference = self._db.collection("staffProfiles").document(staff_id)
        def operation(transaction: Any) -> dict[str, Any]:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise FoundationNotFound("Staff profile not found")
            before = snapshot.to_dict() or {}
            if existing:
                return before
            after = {**before, "displayName": request.display_name, "workEmail": request.work_email, "departmentIds": request.department_ids, "primaryDepartmentId": request.primary_department_id, "position": request.position, "employmentState": request.employment_state, "availabilityState": request.availability_state, "capacity": request.capacity, "activeWorkload": request.active_workload, "languageSkills": request.language_skills, "shift": request.shift, "loginEnabled": request.login_enabled, "profileVersion": before.get("profileVersion", 1) + 1, "departedAt": self.server_timestamp if request.employment_state in {"departed", "archived"} else None, "updatedAt": self.server_timestamp, "updatedBy": actor.uid}
            old_departments = set(before.get("departmentIds", []))
            new_departments = set(request.department_ids)
            membership_time = self.server_timestamp
            for department_id in old_departments - new_departments:
                membership_ref = self._db.collection("departments").document(department_id).collection("members").document(staff_id)
                transaction.set(membership_ref, {"membershipState": "inactive", "updatedAt": membership_time, "updatedBy": actor.uid}, merge=True)
            for department_id in new_departments - old_departments:
                membership_ref = self._db.collection("departments").document(department_id).collection("members").document(staff_id)
                transaction.set(membership_ref, {"departmentId": department_id, "staffId": staff_id, "uid": before["uid"], "membershipState": "active", "createdAt": membership_time, "updatedAt": membership_time, "updatedBy": actor.uid})
            transaction.update(reference, after)
            identity_id = f"{after['historicalIdentityId']}_v{after['profileVersion']}"
            transaction.create(self._db.collection("staffIdentities").document(identity_id), {key: after[key] for key in ("historicalIdentityId", "uid", "employeeCode", "displayName", "departmentIds", "primaryDepartmentId", "position", "profileVersion", "joinedAt", "departedAt", "createdAt")})
            self._finish(transaction, action_id, actor, "staff_updated", "staffProfile", staff_id, before, after)
            return after
        try:
            result = run_firestore_transaction(self._db, operation)
            try:
                self._auth.update_user(result["uid"], disabled=not request.login_enabled)
            except Exception as exc:
                raise PersistenceError("Staff login state update failed") from exc
            return result
        except (FoundationConflict, FoundationValidationError, FoundationNotFound, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("Staff profile update failed") from exc

    def get_staff(self, staff_id: str) -> dict[str, Any]:
        try:
            snapshot = self._db.collection("staffProfiles").document(staff_id).get()
        except Exception as exc:
            raise PersistenceError("Staff profile lookup failed") from exc
        if not snapshot.exists:
            raise FoundationNotFound("Staff profile not found")
        return snapshot.to_dict() or {}

    def list_staff(self, request: FoundationPageRequest) -> StaffPageResponse:
        if request.department_id:
            _validate_department_id(request.department_id)
        fingerprint = _fingerprint(request.model_dump(mode="json", by_alias=True))
        offset = _decode_cursor(request.cursor, fingerprint)
        try:
            snapshots = self._db.collection("staffProfiles").limit(MAX_SCAN + 1).stream()
            rows = [snapshot.to_dict() or {} for snapshot in snapshots]
        except Exception as exc:
            raise PersistenceError("Staff list failed") from exc
        if len(rows) > MAX_SCAN:
            raise PersistenceError("Staff list scan is incomplete")
        if request.employment_state:
            rows = [row for row in rows if row.get("employmentState") == request.employment_state]
        if request.department_id:
            rows = [row for row in rows if request.department_id in row.get("departmentIds", [])]
        rows.sort(key=lambda row: row.get("employeeCode", ""))
        selected = rows[offset : offset + request.page_size]
        next_offset = offset + len(selected)
        next_cursor = _cursor(next_offset, fingerprint) if next_offset < len(rows) else None
        return StaffPageResponse(staff=[StaffResponse.model_validate(row) for row in selected], nextCursor=next_cursor, hasMore=next_cursor is not None)


def require_admin(actor: AdminPrincipal) -> None:
    if actor.role != "admin":
        raise FoundationPermissionError("active Admin required")
