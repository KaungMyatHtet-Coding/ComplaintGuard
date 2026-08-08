"""Canonical and legacy Firestore message-schema compatibility tests."""

import pytest

from app.message_schema import normalize_message_document


def test_complete_legacy_customer_message_normalizes_to_canonical_schema():
    normalized = normalize_message_document(
        {
            "senderId": "customer-1",
            "senderRole": "customer",
            "text": "Legacy customer reply.",
            "createdAt": "2026-08-08T10:00:00Z",
        }
    )

    assert normalized["authorId"] == "customer-1"
    assert normalized["authorRole"] == "customer"
    assert normalized["body"] == "Legacy customer reply."
    assert normalized["visibility"] == "participants"


@pytest.mark.parametrize(
    "message",
    [
        {"senderRole": "customer", "text": "Missing sender", "createdAt": "now"},
        {
            "authorId": "customer-1",
            "authorRole": "customer",
            "createdAt": "now",
        },
    ],
)
def test_incomplete_message_schema_is_rejected(message):
    with pytest.raises(ValueError, match="incomplete|no recognized"):
        normalize_message_document(message)
