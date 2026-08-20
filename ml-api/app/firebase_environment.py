"""Fail-closed environment validation for local Firebase mutation scripts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

LOCAL_EMULATOR_ENVIRONMENT = "local-emulator"
DEMO_PROJECT_ID = "demo-complaintguard"
_CREDENTIAL_INDICATOR_KEYS = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "FIREBASE_ADMIN_CREDENTIALS",
    "FIREBASE_ADMIN_CREDENTIALS_JSON",
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
)
_LOOPBACK_HOST_PATTERN = re.compile(
    r"^(?P<host>127\.0\.0\.1|localhost|\[::1\]):(?P<port>\d{1,5})$"
)


class FirebaseEnvironmentSafetyError(ValueError):
    """Raised when a Firebase mutation target is not the isolated emulator."""


@dataclass(frozen=True)
class LocalEmulatorEnvironment:
    environment: str
    project_id: str
    auth_emulator_host: str
    firestore_emulator_host: str


def validate_local_emulator_environment(
    environment: Mapping[str, str | None] | None = None,
) -> LocalEmulatorEnvironment:
    values = os.environ if environment is None else environment
    if values.get("APP_ENV") != LOCAL_EMULATOR_ENVIRONMENT:
        raise FirebaseEnvironmentSafetyError("environment_mode_must_be_local_emulator")

    project_values = [
        value.strip()
        for key in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT")
        if (value := values.get(key)) and value.strip()
    ]
    if not project_values:
        raise FirebaseEnvironmentSafetyError("project_id_required")
    if len(set(project_values)) != 1:
        raise FirebaseEnvironmentSafetyError("project_id_conflict")
    if project_values[0] != DEMO_PROJECT_ID:
        raise FirebaseEnvironmentSafetyError("project_id_must_be_demo_emulator")

    assert_no_credential_indicators(values)
    auth_host = parse_loopback_emulator_host(values.get("FIREBASE_AUTH_EMULATOR_HOST"), "auth")
    firestore_host = parse_loopback_emulator_host(
        values.get("FIRESTORE_EMULATOR_HOST"), "firestore"
    )
    if auth_host[1] == firestore_host[1]:
        raise FirebaseEnvironmentSafetyError("emulator_hosts_must_use_distinct_ports")
    return LocalEmulatorEnvironment(
        environment=LOCAL_EMULATOR_ENVIRONMENT,
        project_id=DEMO_PROJECT_ID,
        auth_emulator_host=auth_host[0],
        firestore_emulator_host=firestore_host[0],
    )


def parse_loopback_emulator_host(value: str | None, name: str) -> tuple[str, int]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FirebaseEnvironmentSafetyError(f"{name}_emulator_host_required")
    match = _LOOPBACK_HOST_PATTERN.fullmatch(value)
    if not match:
        raise FirebaseEnvironmentSafetyError(f"{name}_emulator_host_must_be_loopback")
    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        raise FirebaseEnvironmentSafetyError(f"{name}_emulator_port_invalid")
    return value, port


def assert_no_credential_indicators(environment: Mapping[str, str | None]) -> None:
    for key in _CREDENTIAL_INDICATOR_KEYS:
        if key in environment and environment.get(key):
            raise FirebaseEnvironmentSafetyError("cloud_credential_indicator_present")
    firebase_config = environment.get("FIREBASE_CONFIG")
    if isinstance(firebase_config, str) and re.search(
        r"private[_-]?key|client[_-]?email|credential", firebase_config, re.IGNORECASE
    ):
        raise FirebaseEnvironmentSafetyError("credential_json_in_firebase_config")
