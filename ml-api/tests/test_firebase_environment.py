"""Pure tests for the local Firebase mutation safety contract."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.firebase_environment import (
    FirebaseEnvironmentSafetyError,
    validate_local_emulator_environment,
)


VALID = {
    "APP_ENV": "local-emulator",
    "GCLOUD_PROJECT": "demo-complaintguard",
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8185",
}


def rejected(environment: dict[str, str | None]) -> None:
    with pytest.raises(FirebaseEnvironmentSafetyError):
        validate_local_emulator_environment(environment)


def test_valid_local_environment() -> None:
    result = validate_local_emulator_environment(VALID)
    assert result.project_id == "demo-complaintguard"
    assert result.auth_emulator_host == "127.0.0.1:9099"
    assert result.firestore_emulator_host == "127.0.0.1:8185"


@pytest.mark.parametrize("mode", [None, "", "unknown", "cloud-staging", "staging", "production"])
def test_invalid_modes_fail(mode: str | None) -> None:
    rejected({**VALID, "APP_ENV": mode})


@pytest.mark.parametrize(
    "environment",
    [
        {**VALID, "GCLOUD_PROJECT": "complaintguard"},
        {**VALID, "GCLOUD_PROJECT": "other-project"},
        {**VALID, "GOOGLE_CLOUD_PROJECT": "other-project"},
        {**VALID, "GCLOUD_PROJECT": None, "GOOGLE_CLOUD_PROJECT": None},
    ],
)
def test_invalid_projects_fail(environment: dict[str, str | None]) -> None:
    rejected(environment)


@pytest.mark.parametrize(
    "environment",
    [
        {**VALID, "FIREBASE_AUTH_EMULATOR_HOST": None},
        {**VALID, "FIRESTORE_EMULATOR_HOST": None},
        {**VALID, "FIREBASE_AUTH_EMULATOR_HOST": "192.168.1.10:9099"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "8.8.8.8:8185"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "http://127.0.0.1:8185"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "user@127.0.0.1:8185"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8185/path"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8185?query=value"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:not-a-port"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:0"},
        {**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:65536"},
    ],
)
def test_invalid_hosts_fail(environment: dict[str, str | None]) -> None:
    rejected(environment)


def test_ipv6_loopback_is_supported() -> None:
    result = validate_local_emulator_environment(
        {**VALID, "FIREBASE_AUTH_EMULATOR_HOST": "[::1]:9099"}
    )
    assert result.auth_emulator_host == "[::1]:9099"


def test_duplicate_ports_fail() -> None:
    rejected({**VALID, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:9099"})


@pytest.mark.parametrize(
    "key",
    [
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "FIREBASE_ADMIN_CREDENTIALS",
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
    ],
)
def test_credential_indicators_fail_without_printing_values(key: str) -> None:
    rejected({**VALID, key: "sensitive-value"})
    rejected({**VALID, "FIREBASE_CONFIG": '{"private_key":"sensitive-value"}'})


def load_seeder_module():
    path = Path(__file__).parents[1] / "scripts" / "seed_synthetic_staff_ticket.py"
    spec = importlib.util.spec_from_file_location("synthetic_staff_ticket_seeder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_python_seeder_rejects_before_firebase_import(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_seeder_module()
    monkeypatch.setenv("APP_ENV", "cloud-staging")
    monkeypatch.setattr(sys, "argv", ["seed_synthetic_staff_ticket.py", "--confirm-synthetic-only"])
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "firebase_admin" or name.startswith("firebase_admin."):
            raise AssertionError("firebase_admin imported before safety validation")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(SystemExit):
        module.main()


def test_python_seeder_valid_contract_reaches_only_mocked_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_seeder_module()
    calls = []

    class FakeReference:
        id = "local-synthetic-ticket"

        def set(self, value):
            calls.append(value)

    class FakeCollection:
        def document(self):
            return FakeReference()

    class FakeDatabase:
        def collection(self, name):
            assert name == "tickets"
            return FakeCollection()

    class FakeFirestore:
        SERVER_TIMESTAMP = object()

    monkeypatch.setenv("APP_ENV", "local-emulator")
    monkeypatch.setenv("GCLOUD_PROJECT", "demo-complaintguard")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8185")
    monkeypatch.setattr(
        module,
        "initialize_local_firestore",
        lambda environment: (FakeFirestore, FakeDatabase()),
    )
    monkeypatch.setattr(module, "build_synthetic_triaged_ticket", lambda timestamp: {"synthetic": True})
    monkeypatch.setattr(
        sys,
        "argv",
        ["seed_synthetic_staff_ticket.py", "--confirm-synthetic-only"],
    )

    assert module.main() == 0
    assert calls == [{"synthetic": True}]
