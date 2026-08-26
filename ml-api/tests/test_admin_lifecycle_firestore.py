"""Pure fake-backed tests for the trusted lifecycle Firestore adapter."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, tzinfo
from typing import Any

import pytest

from app.admin_lifecycle import (
    LIFECYCLE_ACTIONS_COLLECTION,
    LIFECYCLE_AUDIT_EVENTS_COLLECTION,
    LIFECYCLE_TARGET_GUARDS_COLLECTION,
    FirestoreLifecycleRepository,
    InMemoryLifecycleRepository,
    LifecycleActionService,
    LifecycleConflictError,
    LifecycleIdempotencyConflict,
    LifecycleReactivationNotEligible,
    LifecycleStateConflict,
    LifecycleValidationError,
    lifecycle_audit_event_reference,
    lifecycle_target_guard_reference,
)
from app.ticketing import PersistenceError

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)


class Snapshot:
    def __init__(self, key: tuple[str, str], value: dict[str, Any] | None) -> None:
        self.id = key[1]
        self.exists = value is not None
        self._value = deepcopy(value)

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._value)


class Reference:
    def __init__(self, db: "FakeDb", key: tuple[str, str]) -> None:
        self.db = db
        self.key = key


class Query:
    def __init__(self, db: "FakeDb", collection: str, limit: int) -> None:
        self.db = db
        self.collection = collection
        self.limit_count = limit


class Collection:
    def __init__(self, db: "FakeDb", name: str) -> None:
        self.db = db
        self.name = name

    def document(self, document_id: str) -> Reference:
        return Reference(self.db, (self.name, document_id))

    def limit(self, count: int) -> Query:
        return Query(self.db, self.name, count)


class FakeTransaction:
    def __init__(self, db: "FakeDb", values: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.db = db
        self.values = values

    def get(self, reference: Reference | Query):
        if isinstance(reference, Query):
            self.db.operations.append(("read", (reference.collection, "*")))
            matches = [
                (key, value)
                for key, value in self.values.items()
                if key[0] == reference.collection
            ][: reference.limit_count]
            for key, value in matches:
                yield Snapshot(key, value)
            return
        self.db.operations.append(("read", reference.key))
        yield Snapshot(reference.key, self.values.get(reference.key))

    def create(self, reference: Reference, value: dict[str, Any]) -> None:
        self.db.operations.append(("write", reference.key))
        if reference.key in self.values:
            raise RuntimeError("already exists")
        self.values[reference.key] = deepcopy(value)

    def update(self, reference: Reference, value: dict[str, Any]) -> None:
        self.db.operations.append(("write", reference.key))
        if reference.key not in self.values:
            raise RuntimeError("missing")
        updated = deepcopy(self.values[reference.key])
        updated.update(deepcopy(value))
        self.values[reference.key] = updated


class FakeDb:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], dict[str, Any]] = {}
        self.operations: list[tuple[str, tuple[str, str]]] = []

    def collection(self, name: str) -> Collection:
        return Collection(self, name)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self, deepcopy(self.values))


def run_transaction(db: FakeDb, operation: Any) -> Any:
    transaction = db.transaction()
    result = operation(transaction)
    db.values = transaction.values
    return result


def make_record(operation: str = "disable", target: str = "target-1", key: str = "action_001"):
    return LifecycleActionService(InMemoryLifecycleRepository(), clock=lambda: NOW).reserve(
        actor_uid="admin-actor",
        target_uid=target,
        target_role="customer",
        operation=operation,
        idempotency_key=key,
    )


def repository(db: FakeDb) -> FirestoreLifecycleRepository:
    return FirestoreLifecycleRepository(
        (None, db, None),
        project_id="demo-complaintguard",
        environment="local-emulator",
        transaction_runner=run_transaction,
    )


def test_exact_collection_names_and_guard_vector() -> None:
    assert LIFECYCLE_ACTIONS_COLLECTION == "adminAccountLifecycleActions"
    assert LIFECYCLE_TARGET_GUARDS_COLLECTION == "adminAccountLifecycleTargetGuards"
    assert LIFECYCLE_AUDIT_EVENTS_COLLECTION == "adminAccountLifecycleAuditEvents"
    assert lifecycle_target_guard_reference(
        target_uid="target-1", project_id="demo-complaintguard", environment="local-emulator"
    ) == "8ce5ee3703e30ceea3a1f102d4dc1d5c82fd3c0f862bc4429127b9cbb8cbcef8"
    reference = lifecycle_target_guard_reference(
        target_uid="target-1", project_id="demo-complaintguard", environment="local-emulator"
    )
    assert len(reference) == 64 and reference == reference.lower()
    assert "target-1" not in reference
    assert reference != lifecycle_target_guard_reference(
        target_uid="target-2", project_id="demo-complaintguard", environment="local-emulator"
    )
    assert reference != lifecycle_target_guard_reference(
        target_uid="target-1", project_id="other-project", environment="local-emulator"
    )
    assert reference != lifecycle_target_guard_reference(
        target_uid="target-1", project_id="demo-complaintguard", environment="other-environment"
    )


def test_cloud_adapter_construction_is_not_mapped_to_local() -> None:
    with pytest.raises(PersistenceError, match="cloud_staging_not_adopted"):
        FirestoreLifecycleRepository(
            (None, FakeDb(), None), project_id="complaintguard", environment="cloud-staging"
        )


def test_atomic_reservation_replay_conflict_and_isolation() -> None:
    db = FakeDb()
    repo = repository(db)
    record = make_record()
    assert repo.reserve(record) == record
    with pytest.raises(LifecycleIdempotencyConflict):
        repo.reserve(replace(record, request_fingerprint="a" * 64))
    assert {collection for collection, _ in db.values} == {
        LIFECYCLE_ACTIONS_COLLECTION,
        LIFECYCLE_TARGET_GUARDS_COLLECTION,
    }
    assert repo.reserve(record) == record
    with pytest.raises(LifecycleStateConflict):
        repo.reserve(make_record(operation="reactivate", key="action_002"))
    guard_key = next(key for key in db.values if key[0] == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert db.values[guard_key]["actionRef"] == record.action_ref
    assert db.values[guard_key]["state"] == "active"
    other = make_record(target="target-2", key="action_003")
    assert repo.reserve(other) == other


def test_reservation_failure_rolls_back_without_partial_state() -> None:
    db = FakeDb()
    record = make_record()
    original = db.values.copy()

    def failing_runner(db: FakeDb, operation: Any) -> Any:
        transaction = db.transaction()
        operation(transaction)
        raise RuntimeError("synthetic transaction abort")

    failing = FirestoreLifecycleRepository((None, db, None), transaction_runner=failing_runner)
    with pytest.raises(PersistenceError):
        failing.reserve(record)
    assert db.values == original


def test_transition_audit_once_same_state_and_atomic_completion_release() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    progressed = repo.transition(
        record.action_ref,
        expected_version=1,
        to_state="profile_inactivated",
        result_code="profile_inactivated",
        now=NOW,
    )
    assert progressed.version == 2
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "active" and guard["version"] == 2
    assert len([key for key in db.values if key[0] == LIFECYCLE_AUDIT_EVENTS_COLLECTION]) == 1
    assert repo.transition(
        record.action_ref,
        expected_version=2,
        to_state="profile_inactivated",
        result_code="profile_inactivated",
        now=NOW,
    ) == progressed
    completed = repo.transition(
        record.action_ref,
        expected_version=2,
        to_state="auth_disable_pending",
        result_code="auth_disable_pending",
        now=NOW,
    )
    completed = repo.transition(
        record.action_ref,
        expected_version=3,
        to_state="completed",
        result_code="completed",
        now=NOW,
    )
    assert completed.version == 4
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "inactive" and guard["version"] == 4
    assert repo.transition(
        record.action_ref,
        expected_version=4,
        to_state="completed",
        result_code="completed",
        now=NOW,
    ) == completed


def test_atomic_profile_inactivation_preserves_profile_fields_and_keeps_guard_active() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    db.values[("users", "target-1")] = {
        "email": "target-1@example.test",
        "displayName": "Synthetic target-1",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": True,
        "accountState": "active",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    result = repo.inactivate_profile(record.action_ref, now=NOW)
    assert result.state == "profile_inactivated"
    assert db.values[("users", "target-1")] == {
        "email": "target-1@example.test",
        "displayName": "Synthetic target-1",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": False,
        "accountState": "disabled",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "active"
    assert len([key for key in db.values if key[0] == LIFECYCLE_AUDIT_EVENTS_COLLECTION]) == 1


def test_atomic_profile_inactivation_rejects_malformed_profile_without_writes() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    db.values[("users", "target-1")] = {"active": True, "role": "customer"}
    before = deepcopy(db.values)
    with pytest.raises(LifecycleValidationError):
        repo.inactivate_profile(record.action_ref, now=NOW)
    assert db.values == before


def test_profile_inactivation_rejects_unresolved_timezone_without_writes() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    db.values[("users", "target-1")] = {
        "email": "target-1@example.test",
        "displayName": "Synthetic target-1",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": True,
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    # A real datetime with a tzinfo whose offset cannot be resolved is rejected
    # by the strict persisted-timestamp parser before any write is attempted.
    class BrokenTz(tzinfo):
        def utcoffset(self, _value):
            return None

        def dst(self, _value):
            return None

        def tzname(self, _value):
            return "broken"

    db.values[("users", "target-1")]["createdAt"] = NOW.replace(tzinfo=BrokenTz())
    before = deepcopy(db.values)
    with pytest.raises(LifecycleValidationError):
        repo.inactivate_profile(record.action_ref, now=NOW)
    assert db.values == before


def test_reactivation_reservation_lineage_and_final_activation_are_atomic() -> None:
    db = FakeDb()
    repo = repository(db)
    account_ref = "acct_v1_" + "a" * 64
    disable = LifecycleActionService(InMemoryLifecycleRepository(), clock=lambda: NOW).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="customer",
        operation="disable",
        idempotency_key="disable_001",
        account_ref=account_ref,
    )
    repo.reserve(disable)
    db.values[("users", "target-1")] = {
        "email": "target-1@example.test",
        "displayName": "Synthetic target-1",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": False,
        "accountState": "disabled",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    for state, result in (
        ("profile_inactivated", "profile_inactivated"),
        ("auth_disable_pending", "auth_disable_pending"),
        ("completed", "completed"),
    ):
        disable = repo.transition(
            disable.action_ref,
            expected_version=disable.version,
            to_state=state,
            result_code=result,
            now=NOW,
        )
    reactivate = LifecycleActionService(InMemoryLifecycleRepository(), clock=lambda: NOW).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="customer",
        operation="reactivate",
        idempotency_key="reactivate_001",
        account_ref=account_ref,
        previous_action_ref=disable.action_ref,
    )
    db.operations.clear()
    assert repo.reserve_reactivation(reactivate) == reactivate
    first_write = next(index for index, operation in enumerate(db.operations) if operation[0] == "write")
    assert all(operation[0] == "read" for operation in db.operations[:first_write])
    reactivate = repo.transition(
        reactivate.action_ref,
        expected_version=1,
        to_state="auth_enable_pending",
        result_code="auth_enable_pending",
        now=NOW,
    )
    reactivate = repo.transition(
        reactivate.action_ref,
        expected_version=2,
        to_state="profile_activation_pending",
        result_code="profile_activation_pending",
        now=NOW,
    )
    db.operations.clear()
    final = repo.activate_profile(reactivate.action_ref, expected_version=3, now=NOW)
    first_write = next(index for index, operation in enumerate(db.operations) if operation[0] == "write")
    assert all(operation[0] == "read" for operation in db.operations[:first_write])
    assert final.state == "completed"
    assert db.values[("users", "target-1")]["active"] is True
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "inactive" and guard["operation"] == "reactivate"
    assert len([key for key in db.values if key[0] == LIFECYCLE_AUDIT_EVENTS_COLLECTION]) == 6


def test_reactivation_proof_collision_or_malformed_lineage_fails_without_writes() -> None:
    db = FakeDb()
    repo = repository(db)
    record = make_record()
    repo.reserve(record)
    db.values[("users", "target-1")] = {
        "email": "target-1@example.test",
        "displayName": "Synthetic target-1",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": False,
        "accountState": "disabled",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    before = deepcopy(db.values)
    with pytest.raises(LifecycleReactivationNotEligible):
        repo.find_completed_disable_action(
            target_uid="target-1",
            account_ref="acct_v1_" + "a" * 64,
            target_role="customer",
        )
    assert db.values == before


def test_previous_action_reference_is_strict_and_cannot_self_reference() -> None:
    record = make_record(operation="reactivate", key="reactivate_001")
    with pytest.raises(LifecycleValidationError):
        replace(record, previous_action_ref=record.action_ref)
    disable = make_record(key="disable_001")
    with pytest.raises(LifecycleValidationError):
        replace(disable, previous_action_ref="a" * 64)


def test_stale_invalid_and_malformed_documents_fail_closed() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    with pytest.raises(LifecycleStateConflict):
        repo.transition(record.action_ref, expected_version=2, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)
    action_key = (LIFECYCLE_ACTIONS_COLLECTION, record.action_ref)
    db.values[action_key]["private"] = "no"
    with pytest.raises(LifecycleValidationError):
        repo.transition(record.action_ref, expected_version=1, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)


def test_failed_blocks_guard_and_owned_conflict_releases_only_own_guard() -> None:
    db = FakeDb()
    repo = repository(db)
    failed = repo.reserve(make_record(key="action_001"))
    failed = repo.transition(failed.action_ref, expected_version=1, to_state="failed", result_code="validation_failed", now=NOW)
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "blocked"
    other_db = FakeDb()
    other_repo = repository(other_db)
    other = other_repo.reserve(make_record(key="action_002"))
    other_repo.transition(other.action_ref, expected_version=1, to_state="conflict", result_code="lifecycle_conflict", now=NOW)
    guard = next(value for (collection, _), value in other_db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "inactive"


def test_inactive_guard_reacquires_with_monotonic_generation_and_immutable_created_at() -> None:
    db = FakeDb()
    repo = repository(db)
    first = repo.reserve(make_record())
    first = repo.transition(first.action_ref, expected_version=1, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)
    first = repo.transition(first.action_ref, expected_version=2, to_state="auth_disable_pending", result_code="auth_disable_pending", now=NOW)
    repo.transition(first.action_ref, expected_version=3, to_state="completed", result_code="completed", now=NOW)
    guard_key = next(key for key in db.values if key[0] == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    original_created = db.values[guard_key]["createdAt"]
    second = repo.reserve(make_record(operation="reactivate", key="action_002"))
    guard = db.values[guard_key]
    assert guard["actionRef"] == second.action_ref
    assert guard["operation"] == "reactivate"
    assert guard["state"] == "active"
    assert guard["version"] == 5
    assert guard["createdAt"] == original_created


def test_read_before_write_and_audit_vector() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    db.operations.clear()
    repo.transition(record.action_ref, expected_version=1, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)
    first_write = next(index for index, (kind, _) in enumerate(db.operations) if kind == "write")
    assert all(kind == "read" for kind, _ in db.operations[:first_write])
    assert lifecycle_audit_event_reference(
        action_ref=record.action_ref,
        operation="disable",
        from_state="reserved",
        to_state="profile_inactivated",
        result_code="profile_inactivated",
        version=2,
    ) == "54777eef81c11a4a5de6185fa4fd766a33c13f04dd5c1924eecfc7d6ebbd5dae"


def test_existing_audit_collision_is_a_persistence_conflict() -> None:
    db = FakeDb()
    repo = repository(db)
    record = repo.reserve(make_record())
    repo.transition(record.action_ref, expected_version=1, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)
    event_key = next(key for key in db.values if key[0] == LIFECYCLE_AUDIT_EVENTS_COLLECTION)
    db.values[event_key]["resultCode"] = "ok"
    with pytest.raises(LifecycleConflictError):
        repo.transition(record.action_ref, expected_version=1, to_state="profile_inactivated", result_code="profile_inactivated", now=NOW)


def test_reassignment_transaction_checks_bounded_work_and_preserves_profile() -> None:
    db = FakeDb()
    repo = repository(db)
    profile = {
        "email": "staff-1@example.test",
        "displayName": "Staff One",
        "locale": "en",
        "role": "staff",
        "departmentId": "account_support",
        "active": True,
        "accountState": "active",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    db.values[("users", "target-1")] = profile
    record = LifecycleActionService(repo, clock=lambda: NOW).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="staff",
        operation="reassign_department",
        idempotency_key="action_001",
        account_ref="acct_v1_" + "a" * 64,
        requested_department="card_atm",
    )
    db.operations.clear()
    result = repo.reassign_department(record.action_ref, expected_version=1, now=NOW)
    assert result.state == "completed"
    assert db.values[("users", "target-1")] == {
        **profile,
        "departmentId": "card_atm",
        "updatedAt": NOW,
    }
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "inactive"
    assert len([key for key in db.values if key[0] == LIFECYCLE_AUDIT_EVENTS_COLLECTION]) == 1
    writes = [index for index, operation in enumerate(db.operations) if operation[0] == "write"]
    reads = [index for index, operation in enumerate(db.operations) if operation[0] == "read"]
    assert max(reads) < min(writes)


def test_reassignment_assigned_unresolved_work_releases_guard_without_profile_change() -> None:
    db = FakeDb()
    repo = repository(db)
    db.values[("users", "target-1")] = {
        "email": "staff-1@example.test",
        "displayName": "Staff One",
        "locale": "en",
        "role": "staff",
        "departmentId": "account_support",
        "active": True,
        "accountState": "active",
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    db.values[("tickets", "ticket-1")] = {
        "assignedStaffId": "target-1",
        "status": "awaiting_customer",
    }
    record = LifecycleActionService(repo, clock=lambda: NOW).reserve(
        actor_uid="admin-actor",
        target_uid="target-1",
        target_role="staff",
        operation="reassign_department",
        idempotency_key="action_001",
        account_ref="acct_v1_" + "a" * 64,
        requested_department="card_atm",
    )
    result = repo.reassign_department(record.action_ref, expected_version=1, now=NOW)
    assert result.state == "conflict"
    assert result.result_code == "assigned_unresolved_work"
    assert db.values[("users", "target-1")]["departmentId"] == "account_support"
    guard = next(value for (collection, _), value in db.values.items() if collection == LIFECYCLE_TARGET_GUARDS_COLLECTION)
    assert guard["state"] == "inactive"
