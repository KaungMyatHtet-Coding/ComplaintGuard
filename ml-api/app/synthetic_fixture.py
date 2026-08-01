"""Fixed privacy-safe Day 14 fixture; never exposed through an API endpoint."""

from typing import Any


def build_synthetic_triaged_ticket(server_timestamp: object) -> dict[str, Any]:
    """Represent a synthetic complaint that already completed manual triage."""

    return {
        "customerId": "synthetic-day14-customer",
        "complaintText": "Synthetic card payment complaint for staff workflow testing.",
        "inputLocale": "en",
        "departmentId": "card_atm",
        "assignedStaffId": None,
        "status": "triaged",
        "priority": "normal",
        "predictedDepartmentId": None,
        "predictionConfidence": None,
        "routingSource": "manual_review",
        "escalated": False,
        "resolutionSummary": None,
        "createdAt": server_timestamp,
        "updatedAt": server_timestamp,
        "resolvedAt": None,
    }
