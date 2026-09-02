"""Additive Version 2 domain contracts.

This module is deliberately separate from the active V1 schemas.  Importing it
must not change V1 routing, persistence, authorization, or model behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

V1_SCHEMA_VERSION = "v1"
V1_WORKFLOW_VERSION = "v1"
V1_TAXONOMY_VERSION = "v1"
V2_SCHEMA_VERSION = "v2"
V2_WORKFLOW_VERSION = "v2"
V2_TAXONOMY_VERSION = "v2"

V2_CATEGORY_IDS = (
    "account_branch_services",
    "cards_atm_pos",
    "mobile_internet_banking",
    "transfers_payments_remittance",
    "loans_credit",
    "fraud_scam_unauthorized",
    "kyc_verification_restrictions",
    "general_complaints",
)
V2_LIFECYCLE_STATUSES = (
    "received",
    "queued",
    "assigned",
    "under_investigation",
    "additional_information_required",
    "action_in_progress",
    "resolved",
    "closed",
    "reopened",
)
STAFF_EMPLOYMENT_STATES = (
    "invited",
    "active",
    "on_leave",
    "suspended",
    "departed",
    "archived",
)
STAFF_AVAILABILITY_STATES = ("available", "busy", "offline", "unavailable")

V2CategoryId = Literal[
    "account_branch_services",
    "cards_atm_pos",
    "mobile_internet_banking",
    "transfers_payments_remittance",
    "loans_credit",
    "fraud_scam_unauthorized",
    "kyc_verification_restrictions",
    "general_complaints",
]
V2LifecycleStatus = Literal[
    "received",
    "queued",
    "assigned",
    "under_investigation",
    "additional_information_required",
    "action_in_progress",
    "resolved",
    "closed",
    "reopened",
]
StaffEmploymentState = Literal[
    "invited", "active", "on_leave", "suspended", "departed", "archived"
]
StaffAvailabilityState = Literal["available", "busy", "offline", "unavailable"]

V1_TICKET_STATUSES = frozenset(
    {"submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"}
)
V1_CATEGORY_IDS = frozenset(
    {
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    }
)


class V2ContractError(ValueError):
    """Raised when a V2 contract is unknown, malformed, or unsafe to read."""


class V2TicketContract(BaseModel):
    """Strict, additive V2 ticket contract used before future persistence."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=False, str_strip_whitespace=False
    )

    schema_version: Literal["v2"] = Field(alias="schemaVersion")
    workflow_version: Literal["v2"] = Field(alias="workflowVersion")
    taxonomy_version: Literal["v2"] = Field(alias="taxonomyVersion")
    category_id: V2CategoryId = Field(alias="categoryId")
    status: V2LifecycleStatus


class V2StaffProfileContract(BaseModel):
    """Strict V2 Staff lifecycle fields; no authentication behavior is changed."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    schema_version: Literal["v2"] = Field(alias="schemaVersion")
    employment_state: StaffEmploymentState = Field(alias="employmentState")
    availability: StaffAvailabilityState


class TicketVersionInfo(BaseModel):
    """Safe reader result; it never converts V1 values into V2 values."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1", "v2"] = Field(alias="schemaVersion")
    workflow_version: Literal["v1", "v2"] = Field(alias="workflowVersion")
    taxonomy_version: Literal["v1", "v2"] = Field(alias="taxonomyVersion")


def _raw_key_present(document: Mapping[str, Any]) -> bool:
    """Reject snake_case aliases at the V2 boundary."""

    return any("_" in key for key in document if isinstance(key, str))


def read_ticket_version(document: Mapping[str, Any]) -> TicketVersionInfo:
    """Read version metadata without rewriting or reinterpreting a ticket.

    A document without version metadata is treated as V1 only when its
    historical status and department fields are recognizable. Partial or
    unknown metadata fails closed.
    """

    if not isinstance(document, Mapping) or _raw_key_present(document):
        raise V2ContractError("ticket version metadata is not safely readable")
    version_keys = ("schemaVersion", "workflowVersion", "taxonomyVersion")
    present = [key in document for key in version_keys]
    if not any(present):
        status = document.get("status")
        department = document.get("departmentId")
        if status not in V1_TICKET_STATUSES or (
            department is not None and department not in V1_CATEGORY_IDS
        ):
            raise V2ContractError("missing version metadata is not proven V1")
        return TicketVersionInfo(
            schemaVersion=V1_SCHEMA_VERSION,
            workflowVersion=V1_WORKFLOW_VERSION,
            taxonomyVersion=V1_TAXONOMY_VERSION,
        )
    if not all(present):
        raise V2ContractError("version metadata is incomplete")
    values = tuple(document.get(key) for key in version_keys)
    if values == (V1_SCHEMA_VERSION, V1_WORKFLOW_VERSION, V1_TAXONOMY_VERSION):
        return TicketVersionInfo(
            schemaVersion=V1_SCHEMA_VERSION,
            workflowVersion=V1_WORKFLOW_VERSION,
            taxonomyVersion=V1_TAXONOMY_VERSION,
        )
    if values == (V2_SCHEMA_VERSION, V2_WORKFLOW_VERSION, V2_TAXONOMY_VERSION):
        return TicketVersionInfo(
            schemaVersion=V2_SCHEMA_VERSION,
            workflowVersion=V2_WORKFLOW_VERSION,
            taxonomyVersion=V2_TAXONOMY_VERSION,
        )
    raise V2ContractError("ticket version is unknown or inconsistent")


def validate_v2_category(category_id: Any) -> V2CategoryId:
    if category_id not in V2_CATEGORY_IDS:
        raise V2ContractError("unknown V2 category")
    return category_id  # type: ignore[return-value]


def validate_v2_lifecycle_status(status: Any) -> V2LifecycleStatus:
    if status not in V2_LIFECYCLE_STATUSES:
        raise V2ContractError("unknown V2 lifecycle status")
    return status  # type: ignore[return-value]


def validate_staff_profile_states(
    *, employment_state: Any, availability: Any
) -> tuple[StaffEmploymentState, StaffAvailabilityState]:
    if employment_state not in STAFF_EMPLOYMENT_STATES:
        raise V2ContractError("unknown Staff employment state")
    if availability not in STAFF_AVAILABILITY_STATES:
        raise V2ContractError("unknown Staff availability state")
    return employment_state, availability  # type: ignore[return-value]
