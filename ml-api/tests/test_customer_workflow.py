from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.customer_workflow import (
    CustomerWorkflowService,
    InMemoryCustomerBackend,
    InvalidTicketState,
    TicketAccessDenied,
    TicketNotFound,
    _sample_dev_tickets,
)
from app.main import create_app


def test_customer_list_tickets():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    svc = CustomerWorkflowService(backend)
    tickets = svc.list_tickets("demo_customer_uid")
    assert len(tickets) == 2
    assert tickets[0]["customerId"] == "demo_customer_uid"


def test_customer_get_ticket_detail():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    svc = CustomerWorkflowService(backend)
    detail = svc.get_ticket_detail("cg_ticket_cust1", "demo_customer_uid")
    assert detail["id"] == "cg_ticket_cust1"
    assert len(detail["messages"]) == 1


def test_customer_access_denied_other_customer():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    svc = CustomerWorkflowService(backend)
    with pytest.raises(TicketAccessDenied):
        svc.get_ticket_detail("cg_ticket_cust1", "other_customer_uid")


def test_customer_add_message():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    svc = CustomerWorkflowService(backend)
    msg = svc.add_customer_message("cg_ticket_cust1", "demo_customer_uid", "Checking update.")
    assert msg["text"] == "Checking update."
    assert msg["senderRole"] == "customer"


def test_customer_feedback_resolved_ticket():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    svc = CustomerWorkflowService(backend)
    res = svc.submit_feedback("cg_ticket_cust2", "demo_customer_uid", 5, "Great service")
    assert res["rating"] == 5


def test_customer_api_endpoints():
    backend = InMemoryCustomerBackend(_sample_dev_tickets())
    app = create_app(customer_backend=backend)
    client = TestClient(app)

    headers = {"Authorization": "Bearer demo_customer_token"}
    resp = client.get("/customer/tickets", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    resp_detail = client.get("/customer/tickets/cg_ticket_cust1", headers=headers)
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == "cg_ticket_cust1"
