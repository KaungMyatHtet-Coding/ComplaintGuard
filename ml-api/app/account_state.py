"""Trusted durable profile account-state invariants."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

AccountState = Literal["active", "pending_setup", "disabled", "inactive_unverified"]
ACCOUNT_STATES = frozenset({"active", "pending_setup", "disabled", "inactive_unverified"})
PENDING_SETUP_ROLES = frozenset({"staff", "manager"})


class AccountStateValidationError(ValueError):
    """A persisted account state is missing, malformed, or contradictory."""


def validate_account_state(*, active: Any, role: Any, account_state: Any) -> AccountState:
    """Validate the durable state without granting any authorization."""

    if type(active) is not bool or not isinstance(role, str) or account_state not in ACCOUNT_STATES:
        raise AccountStateValidationError("account state is invalid")
    if account_state == "active" and active is not True:
        raise AccountStateValidationError("active account state is contradictory")
    if account_state != "active" and active is not False:
        raise AccountStateValidationError("inactive account state is contradictory")
    if account_state == "pending_setup" and role not in PENDING_SETUP_ROLES:
        raise AccountStateValidationError("pending setup role is invalid")
    return account_state


def validate_profile_account_state(profile: Mapping[str, Any]) -> AccountState:
    """Validate persisted state fields without authorizing the caller."""

    return validate_account_state(
        active=profile.get("active"),
        role=profile.get("role"),
        account_state=profile.get("accountState"),
    )


def active_account_state() -> AccountState:
    return "active"


def pending_setup_account_state() -> AccountState:
    return "pending_setup"


def disabled_account_state() -> AccountState:
    return "disabled"
