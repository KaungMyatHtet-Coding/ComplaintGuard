from __future__ import annotations

import pytest

from app.account_state import (
    AccountStateValidationError,
    validate_account_state,
    validate_profile_account_state,
)


@pytest.mark.parametrize(
    ("active", "role", "state"),
    [
        (True, "customer", "active"),
        (True, "staff", "active"),
        (True, "manager", "active"),
        (True, "admin", "active"),
        (False, "staff", "pending_setup"),
        (False, "manager", "pending_setup"),
        (False, "customer", "disabled"),
        (False, "staff", "disabled"),
        (False, "manager", "disabled"),
        (False, "admin", "inactive_unverified"),
    ],
)
def test_allowlisted_states_and_role_invariants(active: bool, role: str, state: str) -> None:
    assert validate_account_state(active=active, role=role, account_state=state) == state


@pytest.mark.parametrize(
    ("active", "role", "state"),
    [
        (False, "customer", "active"),
        (True, "customer", "disabled"),
        (False, "customer", "pending_setup"),
        (False, "admin", "pending_setup"),
        (False, "staff", "unknown"),
        ("false", "staff", "disabled"),
        (False, "staff", None),
    ],
)
def test_unknown_or_contradictory_state_fails_closed(active: object, role: object, state: object) -> None:
    with pytest.raises(AccountStateValidationError):
        validate_account_state(active=active, role=role, account_state=state)


def test_profile_validator_does_not_authorize_from_state() -> None:
    profile = {"active": True, "role": "customer", "accountState": "active"}
    assert validate_profile_account_state(profile) == "active"
    profile["active"] = False
    with pytest.raises(AccountStateValidationError):
        validate_profile_account_state(profile)
