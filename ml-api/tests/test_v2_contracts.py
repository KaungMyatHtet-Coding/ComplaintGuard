import pytest
from pydantic import ValidationError

from app.v2_contracts import (
    STAFF_AVAILABILITY_STATES,
    STAFF_EMPLOYMENT_STATES,
    V2_CATEGORY_IDS,
    V2_LIFECYCLE_STATUSES,
    V2ContractError,
    V2StaffProfileContract,
    V2TicketContract,
    read_ticket_version,
    validate_staff_profile_states,
    validate_v2_category,
    validate_v2_lifecycle_status,
)


def v2_ticket(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "v2",
        "workflowVersion": "v2",
        "taxonomyVersion": "v2",
        "categoryId": "general_complaints",
        "status": "received",
    }
    value.update(overrides)
    return value


def test_v1_ticket_without_versions_defaults_only_when_proven() -> None:
    result = read_ticket_version({"status": "triaged", "departmentId": "card_atm"})
    assert result.model_dump(by_alias=True) == {
        "schemaVersion": "v1",
        "workflowVersion": "v1",
        "taxonomyVersion": "v1",
    }


def test_explicit_v1_ticket_remains_v1() -> None:
    result = read_ticket_version(
        {
            "schemaVersion": "v1",
            "workflowVersion": "v1",
            "taxonomyVersion": "v1",
            "status": "closed",
            "departmentId": "general_support",
        }
    )
    assert result.schema_version == "v1"


def test_v2_ticket_schema_accepts_all_contract_values() -> None:
    for category in V2_CATEGORY_IDS:
        for status in V2_LIFECYCLE_STATUSES:
            ticket = V2TicketContract.model_validate(v2_ticket(categoryId=category, status=status))
            assert ticket.category_id == category
            assert ticket.status == status


def test_v2_staff_states_accept_all_contract_values() -> None:
    for employment_state in STAFF_EMPLOYMENT_STATES:
        for availability in STAFF_AVAILABILITY_STATES:
            profile = V2StaffProfileContract.model_validate(
                {
                    "schemaVersion": "v2",
                    "employmentState": employment_state,
                    "availability": availability,
                }
            )
            assert profile.employment_state == employment_state
            assert profile.availability == availability


@pytest.mark.parametrize(
    "document",
    [
        {"schemaVersion": "v3", "workflowVersion": "v3", "taxonomyVersion": "v3"},
        {"schemaVersion": "v2", "workflowVersion": "v1", "taxonomyVersion": "v2"},
        {"schemaVersion": "v2"},
        {"status": "unknown", "departmentId": "card_atm"},
        {"status": "triaged", "departmentId": "unknown"},
        {"schema_version": "v1", "workflow_version": "v1", "taxonomy_version": "v1"},
    ],
)
def test_unknown_or_unsafe_versions_fail_closed(document: dict[str, object]) -> None:
    with pytest.raises(V2ContractError):
        read_ticket_version(document)


def test_v2_schema_rejects_unknown_category_status_and_raw_keys() -> None:
    with pytest.raises(ValidationError):
        V2TicketContract.model_validate(v2_ticket(categoryId="account_support"))
    with pytest.raises(ValidationError):
        V2TicketContract.model_validate(v2_ticket(status="triaged"))
    with pytest.raises(ValidationError):
        V2TicketContract.model_validate({**v2_ticket(), "category_id": "general_complaints"})


def test_direct_validators_reject_unknown_values() -> None:
    assert validate_v2_category("general_complaints") == "general_complaints"
    assert validate_v2_lifecycle_status("reopened") == "reopened"
    assert validate_staff_profile_states(
        employment_state="active", availability="available"
    ) == ("active", "available")
    with pytest.raises(V2ContractError):
        validate_v2_category("general_support")
    with pytest.raises(V2ContractError):
        validate_v2_lifecycle_status("in_progress")
    with pytest.raises(V2ContractError):
        validate_staff_profile_states(employment_state="disabled", availability="offline")

