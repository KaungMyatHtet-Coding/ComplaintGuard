"""Unit tests for Day 16 Manager Workflow Service & API endpoints."""

from typing import Any
from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.manager_workflow import (
    InMemoryManagerBackend,
    InvalidDepartmentError,
    ManagerWorkflowService,
    TicketNotFound,
)


class FakeAuthTicketBackend:
    def __init__(self) -> None:
        self.user_profiles: dict[str, dict[str, Any]] = {
            "mgr_01": {"role": "manager", "active": True},
            "cust_01": {"role": "customer", "active": True},
        }

    def verify_id_token(self, token: str) -> str:
        if token in self.user_profiles:
            return token
        raise ValueError("Invalid token")

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        return self.user_profiles.get(uid)


@pytest.fixture
def manager_backend():
    return InMemoryManagerBackend()


@pytest.fixture
def ticket_backend():
    return FakeAuthTicketBackend()


@pytest.fixture
def client(manager_backend, ticket_backend):
    app = create_app(
        manager_backend=manager_backend,
        ticket_backend=ticket_backend,
    )
    return TestClient(app)


def test_manager_analytics_calculation(manager_backend):
    service = ManagerWorkflowService(manager_backend)
    analytics = service.get_analytics()

    assert analytics["totalTickets"] == 4
    assert analytics["activeTickets"] == 3
    assert analytics["resolvedTickets"] == 1
    assert analytics["lowConfidenceCount"] == 2
    assert len(analytics["departmentMetrics"]) == 6


def test_low_confidence_ticket_filtering(manager_backend):
    service = ManagerWorkflowService(manager_backend)
    low_conf = service.list_low_confidence_tickets()

    assert len(low_conf) == 2
    ids = {t["id"] for t in low_conf}
    assert "cg_ticket_lc01" in ids
    assert "cg_ticket_lc02" in ids


def test_manager_override_success(manager_backend):
    service = ManagerWorkflowService(manager_backend)
    doc = service.override_department(
        ticket_id="cg_ticket_lc01",
        new_department_id="fraud_security",
        manager_id="mgr_01",
        reason="Security concern identified",
    )

    assert doc["assignedDepartmentId"] == "fraud_security"
    assert doc["routingSource"] == "manager_override"
    assert len(manager_backend.overrides) == 1
    assert manager_backend.overrides[0]["newDepartmentId"] == "fraud_security"


def test_manager_override_invalid_ticket(manager_backend):
    service = ManagerWorkflowService(manager_backend)
    with pytest.raises(TicketNotFound):
        service.override_department(
            ticket_id="non_existent",
            new_department_id="fraud_security",
            manager_id="mgr_01",
        )


def test_manager_override_invalid_department(manager_backend):
    service = ManagerWorkflowService(manager_backend)
    with pytest.raises(InvalidDepartmentError):
        service.override_department(
            ticket_id="cg_ticket_lc01",
            new_department_id="invalid_dept",
            manager_id="mgr_01",
        )


def test_api_manager_analytics_endpoint(client):
    headers = {"Authorization": "Bearer mgr_01"}
    response = client.get("/manager/analytics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "totalTickets" in data
    assert "departmentMetrics" in data


def test_api_low_confidence_tickets_endpoint(client):
    headers = {"Authorization": "Bearer mgr_01"}
    response = client.get("/manager/low-confidence-tickets", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_api_manager_override_endpoint(client):
    headers = {"Authorization": "Bearer mgr_01"}
    response = client.post(
        "/manager/tickets/cg_ticket_lc01/override",
        headers=headers,
        json={"newDepartmentId": "fraud_security", "reason": "High risk pattern"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticketId"] == "cg_ticket_lc01"
    assert data["assignedDepartmentId"] == "fraud_security"
    assert data["routingSource"] == "manager_override"


def test_api_manager_access_denied_for_customer(client):
    headers = {"Authorization": "Bearer cust_01"}
    response = client.get("/manager/analytics", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "manager_role_required"
