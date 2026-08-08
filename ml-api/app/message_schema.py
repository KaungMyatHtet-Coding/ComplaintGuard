"""Canonical Firestore message-document compatibility helpers."""

from __future__ import annotations

from typing import Any

CANONICAL_MESSAGE_FIELDS = frozenset(
    {"authorId", "authorRole", "body", "visibility", "createdAt"}
)
LEGACY_CUSTOMER_MESSAGE_FIELDS = frozenset(
    {"senderId", "senderRole", "text", "createdAt"}
)


def normalize_message_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return a complete canonical message or reject an incomplete/unknown shape."""
    fields = set(document)
    if CANONICAL_MESSAGE_FIELDS <= fields:
        return dict(document)

    if fields & (CANONICAL_MESSAGE_FIELDS - {"createdAt"}):
        raise ValueError("message document has an incomplete canonical schema")

    if LEGACY_CUSTOMER_MESSAGE_FIELDS <= fields:
        normalized = dict(document)
        normalized.update(
            {
                "authorId": document["senderId"],
                "authorRole": document["senderRole"],
                "body": document["text"],
                "visibility": "participants",
            }
        )
        return normalized

    raise ValueError("message document has no recognized complete schema")
