from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.bootstrap_local_admin import (
    AuthRecord,
    BootstrapConflict,
    BootstrapDependencyError,
    BootstrapInputError,
)

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "activate_pending_user.py"
SPEC = importlib.util.spec_from_file_location("activate_pending_user", SCRIPT_PATH)
assert SPEC and SPEC.loader
activation = importlib.util.module_from_spec(SPEC)
sys.modules["activate_pending_user"] = activation
SPEC.loader.exec_module(activation)


ENVIRONMENT = {
    "APP_ENV": "local-emulator",
    "GCLOUD_PROJECT": "demo-complaintguard",
    "GOOGLE_CLOUD_PROJECT": "demo-complaintguard",
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8185",
}


def _admin_profile() -> dict[str, object]:
    return {
        "email": "admin.demo@complaintguard.test",
        "displayName": "ComplaintGuard Admin",
        "locale": "en",
        "role": "admin",
        "departmentId": None,
        "active": True,
        "createdAt": "created",
        "updatedAt": "updated",
    }


def _target_profile(role: str = "staff", department: str | None = "card_atm") -> dict[str, object]:
    return {
        "email": "pending@complaintguard.test",
        "displayName": "Pending Operator",
        "locale": "my",
        "role": role,
        "departmentId": department if role == "staff" else None,
        "active": False,
        "createdAt": "created",
        "updatedAt": "updated",
    }


def _action(status: str = "pending_setup", target_uid: str = "target-uid") -> dict[str, object]:
    return {
        "actionId": "action-1",
        "actorUid": "admin-uid",
        "targetUid": target_uid,
        "operation": "create_pending_user",
        "requestFingerprint": "request-fingerprint",
        "idempotencyKeyFingerprint": "key-fingerprint",
        "status": status,
        "createdAt": "created",
        "updatedAt": "updated",
    }


class FakeBackend:
    server_timestamp = "SERVER_TIMESTAMP"

    def __init__(self, *, role: str = "staff", department: str | None = "card_atm", action_status: str = "pending_setup") -> None:
        self.auth = AuthRecord("target-uid", "pending@complaintguard.test", "Pending Operator", True)
        self.profile = _target_profile(role, department)
        self.actor_profile = _admin_profile()
        self.actions = [_action(action_status)]
        self.events: list[tuple[str, str]] = []
        self.passwords: list[str] = []
        self.fail_on: set[str] = set()

    def get_auth_by_email(self, email: str) -> AuthRecord | None:
        return self.auth if email == self.auth.email else None

    def get_profile(self, uid: str) -> dict[str, object] | None:
        return copy.deepcopy(self.profile) if uid == self.auth.uid else None

    def list_actions_for_target(self, uid: str) -> list[dict[str, object]]:
        return copy.deepcopy(self.actions) if uid == self.auth.uid else []

    def get_profile_for_actor(self, uid: str) -> dict[str, object] | None:
        return copy.deepcopy(self.actor_profile) if uid == "admin-uid" else None

    def update_action_status(self, action_id: str, target_uid: str, status: str) -> None:
        if status in self.fail_on:
            raise RuntimeError("safe fake failure")
        self.events.append(("action", status))
        self.actions[0]["status"] = status
        self.actions[0]["updatedAt"] = self.server_timestamp

    def set_password(self, uid: str, password: str) -> None:
        if "set_password" in self.fail_on:
            raise RuntimeError("safe fake failure")
        assert self.auth.disabled is True
        self.events.append(("password", "set"))
        self.passwords.append(password)

    def enable_auth(self, uid: str) -> None:
        if "enable_auth" in self.fail_on:
            raise RuntimeError("safe fake failure")
        self.events.append(("auth", "enable"))
        self.auth = AuthRecord(self.auth.uid, self.auth.email, self.auth.display_name, False)

    def activate_profile(self, uid: str) -> None:
        if "activate_profile" in self.fail_on:
            raise RuntimeError("safe fake failure")
        self.events.append(("profile", "activate"))
        self.profile["active"] = True
        self.profile["updatedAt"] = self.server_timestamp


def _run(backend: FakeBackend, passwords: list[str] | None = None) -> activation.ActivationResult:
    values = iter(passwords or ["SafePassword123", "SafePassword123"])
    return activation.activate_pending_user(
        backend=backend,
        environment=ENVIRONMENT,
        email_reader=lambda _: " PENDING@COMPLAINTGUARD.TEST ",
        password_reader=lambda _: next(values),
    )


APPROVED_DEPARTMENTS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)


def test_valid_staff_all_departments_and_manager() -> None:
    for department in APPROVED_DEPARTMENTS:
        backend = FakeBackend(department=department)
        assert _run(backend).status == "completed"
        assert backend.profile["active"] is True
        assert backend.profile["departmentId"] == department
        assert backend.auth.disabled is False
        assert backend.passwords == ["SafePassword123"]
    manager = FakeBackend(role="manager", department=None)
    assert _run(manager).status == "completed"
    assert manager.profile["departmentId"] is None


@pytest.mark.parametrize("role", ["customer", "admin", "unknown"])
def test_non_staff_manager_roles_are_rejected(role: str) -> None:
    backend = FakeBackend(role=role, department=None)
    with pytest.raises(BootstrapConflict):
        _run(backend)
    assert backend.auth.disabled is True
    assert backend.profile["active"] is False


def test_invalid_department_and_missing_provenance_are_rejected() -> None:
    invalid = FakeBackend(department="unknown")
    with pytest.raises(BootstrapConflict):
        _run(invalid)
    missing = FakeBackend()
    missing.actions = []
    with pytest.raises(BootstrapConflict):
        _run(missing)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda backend: backend.profile.pop("updatedAt"),
        lambda backend: backend.profile.update({"email": "other@complaintguard.test"}),
        lambda backend: backend.profile.update({"departmentId": None}),
        lambda backend: backend.profile.update({"active": "false"}),
        lambda backend: backend.actor_profile.update({"role": "manager"}),
        lambda backend: backend.actions[0].update({"requestFingerprint": ""}),
    ],
)
def test_malformed_or_untrusted_provenance_is_rejected(mutator) -> None:
    backend = FakeBackend()
    mutator(backend)
    with pytest.raises(BootstrapConflict):
        _run(backend)


def test_mismatched_action_and_conflicting_actions_are_rejected() -> None:
    backend = FakeBackend()
    backend.actions[0]["targetUid"] = "other-uid"
    with pytest.raises(BootstrapConflict):
        _run(backend)
    backend = FakeBackend()
    backend.actions.append(copy.deepcopy(backend.actions[0]))
    with pytest.raises(BootstrapConflict):
        _run(backend)


def test_sequence_sets_password_disabled_then_enables_then_activates() -> None:
    backend = FakeBackend()
    before = copy.deepcopy(backend.profile)
    assert _run(backend).status == "completed"
    assert backend.events == [
        ("action", "activation_started"),
        ("password", "set"),
        ("action", "password_configured"),
        ("auth", "enable"),
        ("action", "auth_enabled"),
        ("profile", "activate"),
        ("action", "active"),
    ]
    for key in before:
        if key not in {"active", "updatedAt"}:
            assert backend.profile[key] == before[key]
    assert backend.profile["active"] is True
    assert backend.profile["updatedAt"] == backend.server_timestamp


def test_existing_activation_is_unchanged_and_does_not_prompt() -> None:
    backend = FakeBackend(action_status="active")
    backend.auth = AuthRecord(backend.auth.uid, backend.auth.email, backend.auth.display_name, False)
    backend.profile["active"] = True
    before = copy.deepcopy(backend.profile)
    result = activation.activate_pending_user(
        backend=backend,
        environment=ENVIRONMENT,
        email_reader=lambda _: backend.auth.email,
        password_reader=lambda _: pytest.fail("password must not be requested"),
    )
    assert result.status == "existing"
    assert backend.profile == before
    assert backend.passwords == []


def test_recovery_states_do_not_reset_password() -> None:
    backend = FakeBackend(action_status="password_configured")
    result = _run(backend, passwords=[])
    assert result.status == "completed"
    assert backend.passwords == []
    assert backend.auth.disabled is False

    backend = FakeBackend(action_status="auth_enabled")
    backend.auth = AuthRecord(backend.auth.uid, backend.auth.email, backend.auth.display_name, False)
    assert _run(backend, passwords=[]).status == "completed"
    assert backend.passwords == []


def test_active_profile_retries_finalize_action_without_password_reset() -> None:
    backend = FakeBackend(action_status="auth_enabled")
    backend.auth = AuthRecord(backend.auth.uid, backend.auth.email, backend.auth.display_name, False)
    backend.profile["active"] = True
    backend.fail_on.add("active")
    with pytest.raises(BootstrapDependencyError):
        _run(backend, passwords=[])
    backend.fail_on.remove("active")
    assert _run(backend, passwords=[]).status == "completed"
    assert backend.actions[0]["status"] == "active"
    assert backend.passwords == []


def test_ambiguous_activation_state_fails_closed() -> None:
    backend = FakeBackend(action_status="activation_started")
    with pytest.raises(BootstrapDependencyError) as error:
        _run(backend)
    assert error.value.code == "activation_incomplete"
    assert backend.auth.disabled is True
    assert backend.profile["active"] is False


@pytest.mark.parametrize("failure", ["set_password", "enable_auth", "activate_profile"])
def test_partial_failures_never_activate_account(failure: str) -> None:
    backend = FakeBackend()
    backend.fail_on.add(failure)
    with pytest.raises(BootstrapDependencyError):
        _run(backend)
    if failure != "activate_profile":
        assert backend.auth.disabled is True
    assert backend.profile["active"] is False


def test_password_validation_and_no_password_in_safe_error() -> None:
    for values, expected in [
        (["short", "short"], "password_weak"),
        (["SafePassword123", "DifferentPassword123"], "password_mismatch"),
    ]:
        backend = FakeBackend()
        with pytest.raises(BootstrapInputError) as error:
            _run(backend, values)
        assert error.value.code == expected
        assert "SafePassword" not in str(error.value)
        assert backend.auth.disabled is True
        assert backend.profile["active"] is False


def test_environment_rejected_before_backend_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    class UnexpectedBackend:
        def __init__(self) -> None:
            nonlocal called
            called = True

    monkeypatch.setattr(activation, "FirebaseAdminActivationBackend", UnexpectedBackend)
    bad = dict(ENVIRONMENT, APP_ENV="production")
    with pytest.raises(BootstrapDependencyError):
        activation.activate_pending_user(
            environment=bad,
            email_reader=lambda _: "pending@complaintguard.test",
        )
    assert called is False


def test_target_is_email_only_and_normalized() -> None:
    backend = FakeBackend()
    assert activation.normalize_target_email(" PENDING@COMPLAINTGUARD.TEST ") == backend.auth.email
    with pytest.raises(activation.ActivationError):
        activation.normalize_target_email("not-an-email")
