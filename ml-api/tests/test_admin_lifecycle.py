from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.admin_lifecycle import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    LIFECYCLE_ACTION_DOMAIN,
    LIFECYCLE_POLICY_VERSION,
    InMemoryLifecycleRepository,
    LifecycleActionService,
    LifecycleAuditEvent,
    LifecycleIdempotencyConflict,
    LifecycleStateConflict,
    LifecycleValidationError,
    lifecycle_action_reference,
    lifecycle_audit_event_reference,
    lifecycle_request_fingerprint,
    validate_action_document,
    validate_audit_document,
)

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)


def service(repo: InMemoryLifecycleRepository) -> LifecycleActionService:
    return LifecycleActionService(repo, clock=lambda: NOW)


def test_action_reference_has_stable_domain_separated_vector() -> None:
    reference = lifecycle_action_reference(
        actor_uid="admin-actor",
        target_uid="customer-1",
        idempotency_key="action_001",
        operation="disable",
    )
    assert reference == "f2c75c91bf3b096c33d77c874b6fce88af2ffc06da79405d419c344aeb75e15c"
    assert len(reference) == 64 and reference == reference.lower()
    assert LIFECYCLE_ACTION_DOMAIN == "complaintguard:admin-lifecycle:v1"
    assert LIFECYCLE_POLICY_VERSION == "r2c2a-v1"


def test_action_reference_isolated_and_normalized_without_raw_values() -> None:
    base = lifecycle_action_reference(
        actor_uid="admin-actor",
        target_uid="target-1",
        idempotency_key="  action_001  ",
        operation="disable",
    )
    assert base == lifecycle_action_reference(
        actor_uid="admin-actor",
        target_uid="target-1",
        idempotency_key="action_001",
        operation="disable",
    )
    assert base != lifecycle_action_reference(
        actor_uid="admin-actor", target_uid="target-2", idempotency_key="action_001", operation="disable"
    )
    assert base != lifecycle_action_reference(
        actor_uid="admin-actor", target_uid="target-1", idempotency_key="action_001", operation="reactivate"
    )
    assert "admin-actor" not in base and "target-1" not in base and "action_001" not in base


def test_request_fingerprint_binds_operation_target_department_and_policy() -> None:
    first = lifecycle_request_fingerprint(
        target_uid="staff-1", operation="reassign_department", requested_department="transfer_payment"
    )
    assert first == "2610609d66fa90f662026d110043932307aec153b1bc11e64489ab559fa38682"
    assert len(first) == 64
    assert first != lifecycle_request_fingerprint(
        target_uid="staff-1", operation="reassign_department", requested_department="account_support"
    )
    assert first != lifecycle_request_fingerprint(
        target_uid="staff-1", operation="disable"
    )
    assert first != lifecycle_request_fingerprint(
        target_uid="staff-2", operation="reassign_department", requested_department="transfer_payment"
    )


def test_invalid_operation_department_and_private_input_fail_closed() -> None:
    with pytest.raises(LifecycleValidationError):
        lifecycle_action_reference(
            actor_uid="admin-actor", target_uid="target-1", idempotency_key="short", operation="delete"
        )
    with pytest.raises(LifecycleValidationError):
        lifecycle_request_fingerprint(
            target_uid="staff-1", operation="reassign_department", requested_department="unknown"
        )
    with pytest.raises(LifecycleValidationError):
        lifecycle_request_fingerprint(
            target_uid="target-1", operation="disable", requested_department="transfer_payment"
        )
    with pytest.raises(LifecycleValidationError):
        service(InMemoryLifecycleRepository()).reserve(
            actor_uid="same-user",
            target_uid="same-user",
            target_role="admin",
            operation="disable",
            idempotency_key="action_001",
        )


def test_reservation_same_retry_replays_and_changed_request_conflicts() -> None:
    repo = InMemoryLifecycleRepository()
    action = service(repo).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="customer",
        operation="disable",
        idempotency_key="action_001",
    )
    replay = service(repo).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="customer",
        operation="disable",
        idempotency_key="action_001",
    )
    assert replay == action
    with pytest.raises(LifecycleIdempotencyConflict):
        service(repo).reserve(
            actor_uid="admin-actor",
            target_uid="target-1",
            target_role="customer",
            operation="reactivate",
            idempotency_key="action_001",
        )


def test_same_target_concurrent_incompatible_action_conflicts() -> None:
    repo = InMemoryLifecycleRepository()
    service(repo).reserve(
        actor_uid="admin-1", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    with pytest.raises(LifecycleStateConflict):
        service(repo).reserve(
            actor_uid="admin-2", target_uid="target-1", target_role="customer", operation="reactivate", idempotency_key="action_002"
        )


def test_transition_matrix_versioning_and_completed_replay() -> None:
    repo = InMemoryLifecycleRepository()
    action_service = service(repo)
    action = action_service.reserve(
        actor_uid="admin-actor", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    assert "profile_inactivated" in ALLOWED_LIFECYCLE_TRANSITIONS["reserved"]
    with pytest.raises(LifecycleStateConflict):
        action_service.transition(action.action_ref, expected_version=1, to_state="completed")
    progressed = action_service.transition(action.action_ref, expected_version=1, to_state="profile_inactivated")
    completed = action_service.transition(progressed.action_ref, expected_version=2, to_state="auth_disable_pending")
    completed = action_service.transition(completed.action_ref, expected_version=3, to_state="completed")
    replay = action_service.transition(completed.action_ref, expected_version=4, to_state="completed")
    assert replay.state == "completed" and replay.completed_at is not None
    assert replay.version == completed.version
    with pytest.raises(LifecycleStateConflict):
        action_service.transition(action.action_ref, expected_version=1, to_state="reserved")


def test_failed_and_conflict_are_terminal_but_completed_replays() -> None:
    repo = InMemoryLifecycleRepository()
    action_service = service(repo)
    failed = action_service.reserve(
        actor_uid="admin-actor", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    failed = action_service.transition(failed.action_ref, expected_version=1, to_state="failed")
    with pytest.raises(LifecycleStateConflict):
        action_service.transition(failed.action_ref, expected_version=failed.version, to_state="failed")
    conflict = action_service.reserve(
        actor_uid="admin-actor", target_uid="target-2", target_role="customer", operation="disable", idempotency_key="action_002"
    )
    conflict = action_service.transition(conflict.action_ref, expected_version=1, to_state="conflict")
    with pytest.raises(LifecycleStateConflict):
        action_service.transition(conflict.action_ref, expected_version=conflict.version, to_state="conflict")


def test_reactivation_recovery_path_is_operation_specific() -> None:
    repo = InMemoryLifecycleRepository()
    action_service = service(repo)
    action = action_service.reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="customer",
        operation="reactivate",
        idempotency_key="action_001",
    )
    with pytest.raises(LifecycleStateConflict):
        action_service.transition(action.action_ref, expected_version=1, to_state="profile_activation_pending")
    auth_pending = action_service.transition(
        action.action_ref, expected_version=1, to_state="auth_enable_pending"
    )
    profile_pending = action_service.transition(
        action.action_ref, expected_version=auth_pending.version, to_state="profile_activation_pending"
    )
    final = action_service.transition(
        action.action_ref, expected_version=profile_pending.version, to_state="completed"
    )
    assert final.state == "completed"
    disable_repo = InMemoryLifecycleRepository()
    disable = service(disable_repo).reserve(
        actor_uid="admin-actor",
        target_uid="target-2",
        target_role="customer",
        operation="disable",
        idempotency_key="action_002",
    )
    with pytest.raises(LifecycleStateConflict):
        service(disable_repo).transition(
            disable.action_ref, expected_version=1, to_state="auth_enable_pending"
        )


def test_stale_version_and_invalid_transition_fail_without_change() -> None:
    repo = InMemoryLifecycleRepository()
    action = service(repo).reserve(
        actor_uid="admin-actor", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    with pytest.raises(LifecycleStateConflict):
        service(repo).transition(action.action_ref, expected_version=2, to_state="profile_inactivated")
    assert repo.records[action.action_ref].version == 1
    progressed = service(repo).transition(
        action.action_ref, expected_version=1, to_state="profile_inactivated"
    )
    with pytest.raises(LifecycleStateConflict):
        service(repo).transition(
            progressed.action_ref,
            expected_version=progressed.version,
            to_state="profile_activation_pending",
        )
    assert repo.records[action.action_ref].state == "profile_inactivated"


def test_reassignment_requires_staff_and_safe_department() -> None:
    repo = InMemoryLifecycleRepository()
    action = service(repo).reserve(
        actor_uid="admin-actor",
        target_uid="staff-1",
        target_role="staff",
        operation="reassign_department",
        idempotency_key="action_001",
        requested_department="transfer_payment",
    )
    document = action.to_document()
    assert document["requestedDepartment"] == "transfer_payment"
    assert "email" not in document and "displayName" not in document
    with pytest.raises(LifecycleValidationError):
        service(InMemoryLifecycleRepository()).reserve(
            actor_uid="admin-actor", target_uid="manager-1", target_role="manager", operation="reassign_department", idempotency_key="action_002", requested_department="transfer_payment"
        )


def test_strict_backend_record_fields_and_private_values_are_rejected() -> None:
    repo = InMemoryLifecycleRepository()
    action = service(repo).reserve(
        actor_uid="admin-actor", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    document = action.to_document()
    assert set(document) <= {
        "operation", "actorUid", "targetUid", "actionRef", "idempotencyKeyHash", "requestFingerprint", "state", "resultCode", "targetRole", "version", "createdAt", "updatedAt", "accountRef", "requestedDepartment", "completedAt"
    }
    assert all(value not in str(document) for value in ("action_001", "password", "token", "complaintText"))
    assert validate_action_document(document) == action
    with pytest.raises(LifecycleValidationError):
        validate_action_document({**document, "privateField": "no"})
    with pytest.raises(LifecycleValidationError):
        validate_action_document({**document, "updatedAt": NOW.replace(year=2025)})


def test_immutable_audit_event_is_deduplicated_but_conflicts_are_rejected() -> None:
    repo = InMemoryLifecycleRepository()
    action = service(repo).reserve(
        actor_uid="admin-actor", target_uid="target-1", target_role="customer", operation="disable", idempotency_key="action_001"
    )
    progressed = service(repo).transition(action.action_ref, expected_version=1, to_state="profile_inactivated")
    audit_service = service(repo)
    event = audit_service.append_transition_audit(progressed, from_state="reserved")
    assert repo.append_audit(event) == event
    assert len(repo.audit_events) == 1
    assert validate_audit_document(event.to_document()) == event
    with pytest.raises(LifecycleValidationError):
        validate_audit_document({**event.to_document(), "privateField": "no"})
    with pytest.raises(LifecycleValidationError):
        LifecycleAuditEvent(
            event_ref=event.event_ref,
            action_ref=event.action_ref,
            operation=event.operation,
            actor_uid=event.actor_uid,
            target_uid=event.target_uid,
            from_state=event.from_state,
            to_state=event.to_state,
            result_code="unsafe reason",
            version=event.version,
            created_at=NOW,
        )


def test_pending_setup_is_not_reinterpreted_by_this_foundation() -> None:
    # No profile mutation or lifecycle-state inference belongs to R2C2A.
    assert "pending_setup" not in ALLOWED_LIFECYCLE_TRANSITIONS
    assert "active" not in ALLOWED_LIFECYCLE_TRANSITIONS


def test_existing_account_ref_contract_remains_strict() -> None:
    from app.admin_directory import ACCOUNT_REFERENCE_PATTERN

    assert ACCOUNT_REFERENCE_PATTERN.fullmatch("acct_v1_" + "a" * 64)


def test_no_public_lifecycle_route_or_firebase_write_is_added() -> None:
    main_source = Path(__file__).parents[1].joinpath("app", "main.py").read_text(encoding="utf-8")
    assert "/admin/accounts/" not in main_source
    module_source = Path(__file__).parents[1].joinpath("app", "admin_lifecycle.py").read_text(encoding="utf-8")
    assert "firebase_admin" not in module_source


def test_audit_event_reference_is_opaque_and_deterministic() -> None:
    action_ref = lifecycle_action_reference(
        actor_uid="admin-actor", target_uid="target-1", idempotency_key="action_001", operation="disable"
    )
    first = lifecycle_audit_event_reference(action_ref=action_ref, to_state="completed", version=4)
    assert first == lifecycle_audit_event_reference(action_ref=action_ref, to_state="completed", version=4)
    assert len(first) == 64 and action_ref not in first
