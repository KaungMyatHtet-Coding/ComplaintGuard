"""Pure/fake tests for the local-only initial Admin bootstrap."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts.bootstrap_local_admin import (
    FIXED_DISPLAY_NAME,
    FIXED_EMAIL,
    FIXED_LOCALE,
    FIXED_ROLE,
    FIXED_UID,
    AuthRecord,
    BootstrapConflict,
    BootstrapDependencyError,
    BootstrapInputError,
    bootstrap_local_admin,
    validate_bootstrap_environment,
)

VALID_ENV = {
    "APP_ENV": "local-emulator",
    "GCLOUD_PROJECT": "demo-complaintguard",
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8185",
}


class FakeBootstrapBackend:
    server_timestamp = "SERVER_TIMESTAMP"

    def __init__(self) -> None:
        self.auth_by_uid: dict[str, AuthRecord] = {}
        self.auth_by_email: dict[str, AuthRecord] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.active_admin_uids: set[str] = set()
        self.events: list[tuple[str, Any]] = []
        self.fail_create = False
        self.fail_profile = False
        self.fail_enable = False
        self.fail_activate = False
        self.password_seen: str | None = None

    def get_auth_by_uid(self, uid: str) -> AuthRecord | None:
        return deepcopy(self.auth_by_uid.get(uid))

    def get_auth_by_email(self, email: str) -> AuthRecord | None:
        return deepcopy(self.auth_by_email.get(email))

    def list_active_admin_uids(self) -> set[str]:
        return set(self.active_admin_uids)

    def get_profile(self, uid: str) -> dict[str, Any] | None:
        return deepcopy(self.profiles.get(uid))

    def create_auth(
        self,
        *,
        uid: str,
        email: str,
        display_name: str,
        password: str,
    ) -> AuthRecord:
        self.events.append(("create_auth", uid))
        if self.fail_create:
            raise RuntimeError("synthetic Auth failure")
        self.password_seen = password
        record = AuthRecord(uid, email, display_name, True)
        self.auth_by_uid[uid] = record
        self.auth_by_email[email] = record
        return record

    def set_auth_disabled(self, uid: str, disabled: bool) -> None:
        self.events.append(("set_auth_disabled", disabled))
        if self.fail_enable:
            raise RuntimeError("synthetic enable failure")
        current = self.auth_by_uid[uid]
        updated = AuthRecord(current.uid, current.email, current.display_name, disabled)
        self.auth_by_uid[uid] = updated
        self.auth_by_email[current.email] = updated

    def ensure_inactive_profile(self, uid: str) -> None:
        self.events.append(("ensure_inactive_profile", uid))
        if self.fail_profile:
            raise RuntimeError("synthetic profile failure")
        if uid in self.profiles:
            return
        self.profiles[uid] = {
            "email": FIXED_EMAIL,
            "displayName": FIXED_DISPLAY_NAME,
            "locale": FIXED_LOCALE,
            "role": FIXED_ROLE,
            "departmentId": None,
            "active": False,
            "createdAt": self.server_timestamp,
            "updatedAt": self.server_timestamp,
        }

    def activate_profile(self, uid: str) -> None:
        self.events.append(("activate_profile", uid))
        if self.fail_activate:
            raise RuntimeError("synthetic activation failure")
        self.profiles[uid]["active"] = True
        self.profiles[uid]["updatedAt"] = self.server_timestamp


def matching_profile(*, active: bool, created: str = "created") -> dict[str, Any]:
    return {
        "email": FIXED_EMAIL,
        "displayName": FIXED_DISPLAY_NAME,
        "locale": FIXED_LOCALE,
        "role": FIXED_ROLE,
        "departmentId": None,
        "active": active,
        "createdAt": created,
        "updatedAt": "updated",
    }


def matching_auth(*, disabled: bool) -> AuthRecord:
    return AuthRecord(FIXED_UID, FIXED_EMAIL, FIXED_DISPLAY_NAME, disabled)


def password_reader(password: str = "SyntheticAdmin2026!"):
    values = iter([password, password])
    return lambda _prompt: next(values)


def test_valid_environment_is_accepted_without_firebase_initialization() -> None:
    result = validate_bootstrap_environment(VALID_ENV)
    assert result.project_id == "demo-complaintguard"


@pytest.mark.parametrize(
    "changes",
    [
        {"APP_ENV": "cloud-staging"},
        {"APP_ENV": "production"},
        {"APP_ENV": "unknown"},
        {"GCLOUD_PROJECT": "complaintguard"},
        {"FIREBASE_AUTH_EMULATOR_HOST": "192.168.1.5:9099"},
        {"FIRESTORE_EMULATOR_HOST": None},
        {"GOOGLE_APPLICATION_CREDENTIALS": "not-read"},
    ],
)
def test_invalid_environment_is_rejected_before_backend_creation(
    changes: dict[str, str | None],
) -> None:
    values = {**VALID_ENV, **changes}
    with pytest.raises(BootstrapDependencyError) as error:
        validate_bootstrap_environment(values)
    assert error.value.code == "environment_invalid"


def test_empty_explicit_environment_does_not_fall_back_to_process_environment() -> None:
    with pytest.raises(BootstrapDependencyError):
        validate_bootstrap_environment({})


def test_new_admin_uses_hidden_two_prompt_password_and_safe_sequence() -> None:
    backend = FakeBootstrapBackend()
    result = bootstrap_local_admin(
        backend=backend,
        environment=VALID_ENV,
        password_reader=password_reader(),
    )
    assert result.status == "created"
    assert backend.auth_by_uid[FIXED_UID].disabled is False
    assert backend.profiles[FIXED_UID]["active"] is True
    assert backend.profiles[FIXED_UID]["createdAt"] == "SERVER_TIMESTAMP"
    assert backend.profiles[FIXED_UID]["updatedAt"] == "SERVER_TIMESTAMP"
    assert backend.events == [
        ("create_auth", FIXED_UID),
        ("ensure_inactive_profile", FIXED_UID),
        ("set_auth_disabled", False),
        ("activate_profile", FIXED_UID),
    ]
    assert backend.password_seen == "SyntheticAdmin2026!"


@pytest.mark.parametrize(
    "values, code",
    [
        (["SyntheticAdmin2026!", "Different2026!"], "password_mismatch"),
        (["short", "short"], "password_weak"),
    ],
)
def test_password_confirmation_and_strength_are_required(
    values: list[str], code: str
) -> None:
    backend = FakeBootstrapBackend()
    iterator = iter(values)
    with pytest.raises(BootstrapInputError) as error:
        bootstrap_local_admin(
            backend=backend,
            environment=VALID_ENV,
            password_reader=lambda _prompt: next(iterator),
        )
    assert error.value.code == code
    assert not backend.auth_by_uid
    assert not backend.profiles


def test_existing_complete_admin_is_preserved_without_prompt() -> None:
    backend = FakeBootstrapBackend()
    backend.auth_by_uid[FIXED_UID] = matching_auth(disabled=False)
    backend.auth_by_email[FIXED_EMAIL] = matching_auth(disabled=False)
    backend.profiles[FIXED_UID] = matching_profile(active=True, created="original")
    before = deepcopy(backend.profiles)
    result = bootstrap_local_admin(
        backend=backend,
        environment=VALID_ENV,
        password_reader=lambda _prompt: pytest.fail("password must not be requested"),
    )
    assert result.status == "existing"
    assert backend.profiles == before
    assert backend.events == []


def test_disabled_auth_missing_profile_resumes_without_prompt() -> None:
    backend = FakeBootstrapBackend()
    backend.auth_by_uid[FIXED_UID] = matching_auth(disabled=True)
    backend.auth_by_email[FIXED_EMAIL] = matching_auth(disabled=True)
    result = bootstrap_local_admin(
        backend=backend,
        environment=VALID_ENV,
        password_reader=lambda _prompt: pytest.fail("password must not be requested"),
    )
    assert result.status == "resumed"
    assert backend.auth_by_uid[FIXED_UID].disabled is False
    assert backend.profiles[FIXED_UID]["active"] is True


def test_disabled_auth_inactive_profile_resumes_and_preserves_creation_time() -> None:
    backend = FakeBootstrapBackend()
    backend.auth_by_uid[FIXED_UID] = matching_auth(disabled=True)
    backend.auth_by_email[FIXED_EMAIL] = matching_auth(disabled=True)
    backend.profiles[FIXED_UID] = matching_profile(active=False, created="original")
    result = bootstrap_local_admin(
        backend=backend,
        environment=VALID_ENV,
        password_reader=lambda _prompt: pytest.fail("password must not be requested"),
    )
    assert result.status == "resumed"
    assert backend.profiles[FIXED_UID]["createdAt"] == "original"
    assert backend.profiles[FIXED_UID]["active"] is True


def test_active_profile_with_disabled_auth_only_enables_auth() -> None:
    backend = FakeBootstrapBackend()
    backend.auth_by_uid[FIXED_UID] = matching_auth(disabled=True)
    backend.auth_by_email[FIXED_EMAIL] = matching_auth(disabled=True)
    backend.profiles[FIXED_UID] = matching_profile(active=True)
    before = deepcopy(backend.profiles)
    result = bootstrap_local_admin(backend=backend, environment=VALID_ENV)
    assert result.status == "resumed"
    assert backend.auth_by_uid[FIXED_UID].disabled is False
    assert backend.profiles[FIXED_UID] == before[FIXED_UID]


@pytest.mark.parametrize(
    "setup, code",
    [
        ("non_admin_profile", "profile_conflict"),
        ("email_other_uid", "email_identity_conflict"),
        ("profile_without_auth", "profile_without_auth"),
        ("another_admin", "admin_already_exists"),
        ("enabled_partial", "enabled_partial_bootstrap"),
    ],
)
def test_conflicts_are_safe_and_preserve_existing_state(setup: str, code: str) -> None:
    backend = FakeBootstrapBackend()
    if setup == "non_admin_profile":
        backend.profiles[FIXED_UID] = {**matching_profile(active=False), "role": "manager"}
    elif setup == "email_other_uid":
        other = AuthRecord("other-uid", FIXED_EMAIL, "Other", True)
        backend.auth_by_email[FIXED_EMAIL] = other
    elif setup == "profile_without_auth":
        backend.profiles[FIXED_UID] = matching_profile(active=False)
    elif setup == "another_admin":
        backend.active_admin_uids.add("other-admin")
    elif setup == "enabled_partial":
        backend.auth_by_uid[FIXED_UID] = matching_auth(disabled=False)
        backend.auth_by_email[FIXED_EMAIL] = matching_auth(disabled=False)
        backend.profiles[FIXED_UID] = matching_profile(active=False)
    before = deepcopy(backend.__dict__)
    with pytest.raises(BootstrapConflict) as error:
        bootstrap_local_admin(
            backend=backend,
            environment=VALID_ENV,
            password_reader=lambda _prompt: pytest.fail("password must not be requested"),
        )
    assert error.value.code == code
    if setup != "another_admin":
        assert backend.profiles == before["profiles"]


def test_auth_creation_failure_creates_no_profile() -> None:
    backend = FakeBootstrapBackend()
    backend.fail_create = True
    with pytest.raises(BootstrapDependencyError) as error:
        bootstrap_local_admin(
            backend=backend,
            environment=VALID_ENV,
            password_reader=password_reader(),
        )
    assert error.value.code == "auth_creation_failed"
    assert not backend.profiles


def test_profile_failure_leaves_created_auth_disabled_and_no_secret_in_error() -> None:
    backend = FakeBootstrapBackend()
    backend.fail_profile = True
    with pytest.raises(BootstrapDependencyError) as error:
        bootstrap_local_admin(
            backend=backend,
            environment=VALID_ENV,
            password_reader=password_reader(),
        )
    assert error.value.code == "bootstrap_incomplete"
    assert backend.auth_by_uid[FIXED_UID].disabled is True
    assert not backend.profiles
    assert "SyntheticAdmin2026!" not in str(error.value)


def test_enable_failure_leaves_profile_inactive() -> None:
    backend = FakeBootstrapBackend()
    backend.fail_enable = True
    with pytest.raises(BootstrapDependencyError):
        bootstrap_local_admin(
            backend=backend,
            environment=VALID_ENV,
            password_reader=password_reader(),
        )
    assert backend.auth_by_uid[FIXED_UID].disabled is True
    assert backend.profiles[FIXED_UID]["active"] is False


def test_no_password_or_credentials_are_written_to_profile_or_output(capsys) -> None:
    backend = FakeBootstrapBackend()
    bootstrap_local_admin(
        backend=backend,
        environment=VALID_ENV,
        password_reader=password_reader("SyntheticAdmin2026!"),
    )
    captured = capsys.readouterr()
    assert "SyntheticAdmin2026!" not in captured.out + captured.err
    assert "password" not in str(backend.profiles).lower()
    assert "claims" not in str(backend.profiles).lower()
