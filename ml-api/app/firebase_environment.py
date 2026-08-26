"""Fail-closed Firebase environment validation for backend boundaries."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

LOCAL_EMULATOR_ENVIRONMENT = "local-emulator"
CLOUD_STAGING_ENVIRONMENT = "cloud-staging"
DEMO_PROJECT_ID = "demo-complaintguard"
CANDIDATE_CLOUD_PROJECT_ID = "complaintguard"
_CREDENTIAL_INDICATOR_KEYS = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "FIREBASE_ADMIN_CREDENTIALS",
    "FIREBASE_ADMIN_CREDENTIALS_JSON",
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
)
_EMULATOR_MODE_INDICATOR_KEYS = (
    "FIREBASE_USE_EMULATORS",
    "USE_FIREBASE_EMULATORS",
    "NEXT_PUBLIC_USE_FIREBASE_EMULATORS",
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


@dataclass(frozen=True)
class CloudStagingEnvironment:
    environment: str
    project_id: str


FirebaseEnvironment = LocalEmulatorEnvironment | CloudStagingEnvironment


def _project_id(values: Mapping[str, str | None]) -> str:
    project_values = [
        value.strip()
        for key in ("GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT")
        if (value := values.get(key)) and value.strip()
    ]
    if not project_values:
        raise FirebaseEnvironmentSafetyError("project_id_required")
    if len(set(project_values)) != 1:
        raise FirebaseEnvironmentSafetyError("project_id_conflict")
    return project_values[0]


def validate_local_emulator_environment(
    environment: Mapping[str, str | None] | None = None,
) -> LocalEmulatorEnvironment:
    values = os.environ if environment is None else environment
    if values.get("APP_ENV") != LOCAL_EMULATOR_ENVIRONMENT:
        raise FirebaseEnvironmentSafetyError("environment_mode_must_be_local_emulator")

    project_id = _project_id(values)
    if project_id != DEMO_PROJECT_ID:
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


def validate_firebase_environment(
    environment: Mapping[str, str | None] | None = None,
) -> FirebaseEnvironment:
    """Validate an explicit application environment without touching Firebase."""

    values = os.environ if environment is None else environment
    mode = values.get("APP_ENV")
    if mode == LOCAL_EMULATOR_ENVIRONMENT:
        return validate_local_emulator_environment(values)
    if mode != CLOUD_STAGING_ENVIRONMENT:
        raise FirebaseEnvironmentSafetyError("unsupported_environment_mode")

    project_id = _project_id(values)
    if project_id != CANDIDATE_CLOUD_PROJECT_ID:
        raise FirebaseEnvironmentSafetyError("cloud_staging_requires_candidate_project")
    if any(values.get(key) for key in ("FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST")):
        raise FirebaseEnvironmentSafetyError("cloud_staging_forbids_emulator_hosts")
    if any(values.get(key, "").lower() == "true" for key in _EMULATOR_MODE_INDICATOR_KEYS):
        raise FirebaseEnvironmentSafetyError("cloud_staging_forbids_emulator_mode")
    if values.get("FIREBASE_CONFIG") or any(
        values.get(key) for key in _CREDENTIAL_INDICATOR_KEYS
    ):
        raise FirebaseEnvironmentSafetyError("cloud_staging_credentials_not_approved")
    assert_no_credential_indicators(values)
    return CloudStagingEnvironment(
        environment=CLOUD_STAGING_ENVIRONMENT,
        project_id=CANDIDATE_CLOUD_PROJECT_ID,
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
