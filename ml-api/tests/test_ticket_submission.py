"""Focused tests for trusted Day 13 complaint submission."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model import Prediction
from app.schemas import DepartmentId
from app.ticketing import DEPARTMENT_IDS, validate_routing_state


class FakeClassifier:
    model_version = "v1"

    def predict(self, _text: str) -> Prediction:
        return Prediction("general_support", 0.5, True, "low_classifier_confidence")


class FakeBackend:
    server_timestamp = object()

    def __init__(self) -> None:
        self.uid = "verified-customer-uid"
        self.profile: dict[str, Any] | None = {"role": "customer", "active": True}
        self.documents: list[dict[str, Any]] = []
        self.fail_write = False

    def verify_id_token(self, token: str) -> str:
        if token != "valid-token":
            raise ValueError("invalid token")
        return self.uid

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        assert uid == self.uid
        return self.profile

    def create_ticket(self, document: dict[str, Any]) -> str:
        if self.fail_write:
            raise RuntimeError("synthetic Firestore failure")
        self.documents.append(document)
        return "ticket-day13-001"


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def client(tmp_path: Path, backend: FakeBackend):
    settings = Settings(model_path=tmp_path / "model.joblib", expected_model_sha256="a")
    with TestClient(
        create_app(
            settings=settings,
            model_loader=lambda *_args, **_kwargs: FakeClassifier(),
            ticket_backend=backend,
        )
    ) as api:
        yield api


def submit(client: TestClient, payload: dict[str, object], token: str = "valid-token"):
    return client.post(
        "/tickets", json=payload, headers={"Authorization": f"Bearer {token}"}
    )


def test_valid_authenticated_submission_creates_pending_ticket(
    client: TestClient, backend: FakeBackend
) -> None:
    response = submit(
        client,
        {"complaintText": "  A synthetic   payment complaint. ", "inputLocale": "en"},
    )
    assert response.status_code == 201
    assert response.json() == {"complaintId": "ticket-day13-001", "status": "submitted"}
    assert backend.documents == [
        {
            "customerId": "verified-customer-uid",
            "complaintText": "A synthetic payment complaint.",
            "inputLocale": "en",
            "departmentId": None,
            "assignedStaffId": None,
            "status": "submitted",
            "priority": "normal",
            "predictedDepartmentId": None,
            "predictionConfidence": None,
            "routingSource": "pending",
            "escalated": False,
            "resolutionSummary": None,
            "createdAt": backend.server_timestamp,
            "updatedAt": backend.server_timestamp,
            "resolvedAt": None,
        }
    ]


@pytest.mark.parametrize("token", ["", "invalid-token"])
def test_missing_or_invalid_token_is_rejected(client: TestClient, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        "/tickets",
        json={"complaintText": "Synthetic complaint", "inputLocale": "en"},
        headers=headers,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_uid_spoofing_and_protected_fields_are_rejected(
    client: TestClient, backend: FakeBackend
) -> None:
    for field, value in [
        ("customerId", "spoofed-uid"),
        ("departmentId", "fraud_security"),
        ("status", "triaged"),
        ("routingSource", "model"),
        ("priority", "urgent"),
    ]:
        response = submit(
            client,
            {"complaintText": "Synthetic complaint", "inputLocale": "en", field: value},
        )
        assert response.status_code == 422
    assert backend.documents == []


def test_non_customer_role_is_rejected(
    client: TestClient, backend: FakeBackend
) -> None:
    backend.profile = {"role": "staff", "active": True, "departmentId": "card_atm"}
    response = submit(
        client, {"complaintText": "Synthetic complaint", "inputLocale": "en"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("text", ["", "  \t\n  "])
def test_invalid_or_whitespace_only_complaint_is_rejected(
    client: TestClient, text: str
) -> None:
    assert (
        submit(client, {"complaintText": text, "inputLocale": "en"}).status_code == 422
    )


def test_pii_is_redacted_before_persistence(
    client: TestClient, backend: FakeBackend
) -> None:
    response = submit(
        client,
        {
            "complaintText": "Password: fictionalSecret PIN 1234 card number 4111 1111 1111 1111 and account 1234567890 were included.",
            "inputLocale": "en",
        },
    )
    assert response.status_code == 201
    stored = backend.documents[0]["complaintText"]
    assert stored.count("[REDACTED]") == 4
    assert (
        "fictionalSecret" not in stored
        and "4111" not in stored
        and "1234567890" not in stored
    )


def test_firestore_failure_returns_retryable_error(
    client: TestClient, backend: FakeBackend
) -> None:
    backend.fail_write = True
    response = submit(
        client, {"complaintText": "Synthetic complaint", "inputLocale": "my"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ticket_creation_unavailable"


def test_routing_invariants_reject_unknown_and_null_routed_departments() -> None:
    validate_routing_state(
        department_id=None, status="submitted", routing_source="pending"
    )
    validate_routing_state(
        department_id="card_atm", status="triaged", routing_source="model"
    )
    with pytest.raises(ValueError, match="unknown"):
        validate_routing_state(
            department_id="pending", status="triaged", routing_source="model"
        )
    with pytest.raises(ValueError, match="requires"):
        validate_routing_state(
            department_id=None, status="triaged", routing_source="model"
        )
    with pytest.raises(ValueError, match="must not"):
        validate_routing_state(
            department_id="card_atm", status="submitted", routing_source="pending"
        )


def test_only_six_operational_departments_exist() -> None:
    assert DEPARTMENT_IDS == frozenset(DepartmentId.__args__)
    assert len(DEPARTMENT_IDS) == 6
    assert "pending" not in DEPARTMENT_IDS and "unassigned" not in DEPARTMENT_IDS


def test_firestore_rule_does_not_grant_staff_access_to_null_department() -> None:
    rules = (Path(__file__).parents[2] / "firebase" / "firestore.rules").read_text()
    assert "currentUser().data.departmentId is string" in rules
    assert "currentUser().data.departmentId == ticket.data.departmentId" in rules
    assert "allow create, update, delete: if false;" in rules
