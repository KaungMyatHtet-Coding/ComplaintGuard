"""Seed one fixed, synthetic, already-triaged staff ticket for local verification."""

from __future__ import annotations

import argparse

import firebase_admin
from app.synthetic_fixture import build_synthetic_triaged_ticket
from firebase_admin import firestore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create one privacy-safe Day 14 fixture using Firebase Admin."
    )
    parser.add_argument(
        "--confirm-synthetic-only",
        action="store_true",
        help="Required acknowledgement that this is local synthetic demo data.",
    )
    args = parser.parse_args()
    if not args.confirm_synthetic_only:
        parser.error("--confirm-synthetic-only is required")

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()
    db = firestore.client()
    ticket = build_synthetic_triaged_ticket(firestore.SERVER_TIMESTAMP)
    reference = db.collection("tickets").document()
    reference.set(ticket)
    print(f"Created synthetic triaged ticket: {reference.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
