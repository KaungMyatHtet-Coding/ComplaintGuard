"""Seed one fixed, synthetic, already-triaged staff ticket for local verification."""

from __future__ import annotations

import argparse
import os

from app.firebase_environment import (
    LocalEmulatorEnvironment,
    validate_local_emulator_environment,
)
from app.synthetic_fixture import build_synthetic_triaged_ticket


def validate_seed_environment() -> LocalEmulatorEnvironment:
    return validate_local_emulator_environment(os.environ)


def initialize_local_firestore(environment: LocalEmulatorEnvironment):
    import firebase_admin
    from firebase_admin import firestore
    from google.auth.credentials import AnonymousCredentials

    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(
            credential=AnonymousCredentials(),
            options={"projectId": environment.project_id},
        )
    if app.project_id != environment.project_id:
        raise RuntimeError("firebase_app_project_id_mismatch")
    return firestore, firestore.client()


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
        environment = validate_seed_environment()
    except ValueError as error:
        parser.error(str(error))

    firestore, db = initialize_local_firestore(environment)
    ticket = build_synthetic_triaged_ticket(firestore.SERVER_TIMESTAMP)
    reference = db.collection("tickets").document()
    reference.set(ticket)
    print(f"Created synthetic triaged ticket: {reference.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
