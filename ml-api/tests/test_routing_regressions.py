"""Short user-style regression coverage for the authenticated ticket pipeline."""

from pathlib import Path
from typing import Any

import pytest
from app.config import MODEL_SHA256
from app.main import create_app
from app.routing import RoutingPrediction
from fastapi.testclient import TestClient


class RecordingTicketBackend:
    server_timestamp = "server-time"

    def __init__(self) -> None:
        self.document: dict[str, Any] | None = None

    def verify_id_token(self, token: str) -> str:
        if token != "customer-token":
            raise ValueError("invalid token")
        return "customer-short-routing"

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        assert uid == "customer-short-routing"
        return {"active": True, "role": "customer"}

    def create_ticket(self, document: dict[str, Any], *, idempotency_key: str) -> str:
        assert idempotency_key
        self.document = dict(document)
        return "ticket-short-routing"

    def persist_prediction(
        self, _ticket_id: str, prediction: RoutingPrediction
    ) -> None:
        assert self.document is not None
        manual_review = prediction.requires_manual_review
        self.document.update(
            {
                "departmentId": None if manual_review else prediction.department_id,
                "predictedDepartmentId": prediction.department_id,
                "predictionConfidence": prediction.confidence,
                "routingSource": "manual_review" if manual_review else "model",
                "status": "submitted" if manual_review else "triaged",
                "manualReviewReason": prediction.manual_review_reason,
            }
        )

    def persist_inference_failure(
        self, _ticket_id: str, *, code: str, detected_language: str
    ) -> None:
        raise AssertionError(
            f"unexpected inference failure: {code}/{detected_language}"
        )


@pytest.fixture
def routing_client():
    artifact = (
        Path(__file__).resolve().parents[2]
        / "models"
        / "generated"
        / "cfpb_department_model_v1.joblib"
    )
    if not artifact.is_file():
        pytest.skip("ignored frozen model artifact is not installed")
    backend = RecordingTicketBackend()
    with TestClient(create_app(ticket_backend=backend)) as client:
        assert client.get("/health").json()["model_loaded"] is True
        yield client, backend


def submit(client: TestClient, text: str, action_id: str) -> None:
    response = client.post(
        "/tickets",
        headers={"Authorization": "Bearer customer-token"},
        json={"complaintText": text, "inputLocale": "en", "actionId": action_id},
    )
    assert response.status_code == 201


def test_mobile_transfer_failed_remains_unassigned_for_manual_review(
    routing_client,
) -> None:
    client, backend = routing_client
    submit(client, "Mobile transfer failed", "short-transfer-001")

    assert backend.document is not None
    assert backend.document["predictionConfidence"] < 0.60
    assert backend.document["departmentId"] is None
    assert backend.document["routingSource"] == "manual_review"
    assert backend.document["manualReviewReason"] == "low_prediction_confidence"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known frozen-v1 defect: clear mobile transfer intent is routed to "
        "account_support with high uncalibrated confidence"
    ),
)
def test_clear_mobile_transfer_routes_to_transfer_payment(routing_client) -> None:
    client, backend = routing_client
    submit(
        client,
        (
            "I transferred money through mobile banking. The amount was deducted "
            "from my account, but the recipient did not receive it."
        ),
        "clear-transfer-001",
    )

    assert backend.document is not None
    assert backend.document["predictedDepartmentId"] == "transfer_payment"
    assert backend.document["departmentId"] == "transfer_payment"
    assert backend.document["routingSource"] == "model"


def test_mobile_banking_account_access_routes_to_account_support(
    routing_client,
) -> None:
    client, backend = routing_client
    submit(
        client,
        "I cannot access my mobile banking account.",
        "account-access-001",
    )

    assert backend.document is not None
    assert backend.document["predictedDepartmentId"] == "account_support"
    assert backend.document["departmentId"] == "account_support"
    assert backend.document["routingSource"] == "model"


def test_card_payment_routes_to_card_atm(routing_client) -> None:
    client, backend = routing_client
    submit(
        client,
        "My debit card payment was declined at the store.",
        "card-payment-001",
    )

    assert backend.document is not None
    assert backend.document["predictedDepartmentId"] == "card_atm"
    assert backend.document["departmentId"] == "card_atm"
    assert backend.document["routingSource"] == "model"
    assert backend.document["predictionConfidence"] >= 0.60


def test_model_hash_contract_used_by_regressions() -> None:
    assert MODEL_SHA256 == (
        "bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5"
    )
