"""Unit tests for ``select_customers_to_link`` — the quota/reauth decision in
the Google Ads account-linking worker.

The bug: an expired account was counted against the plan limit, so a reauth
(re-linking an already-connected customer) was rejected with
``account_limit_reached`` and the connection never refreshed.  The helper must
always allow reauths and only spend quota on genuinely new customers.
"""

from adcopilot.interfaces.worker.tasks import select_customers_to_link


def test_reauth_existing_customer_at_quota_is_allowed() -> None:
    """A starter user at quota reauthorizing their one account: still linked."""
    result = select_customers_to_link(
        customer_ids=["1111111111"],
        existing_customer_ids={"1111111111"},
        slots_remaining=0,  # 1/1 plan — full
    )
    assert result == ["1111111111"]


def test_new_customer_at_quota_is_dropped() -> None:
    """A genuinely new customer must not be linked when no slots remain."""
    result = select_customers_to_link(
        customer_ids=["2222222222"],
        existing_customer_ids={"1111111111"},
        slots_remaining=0,
    )
    assert result == []


def test_reauth_takes_priority_over_new_within_slots() -> None:
    """Reauths are never quota-limited; new customers fill remaining slots only."""
    result = select_customers_to_link(
        customer_ids=["new-1", "existing", "new-2"],
        existing_customer_ids={"existing"},
        slots_remaining=1,
    )
    # existing (reauth) always; then one new customer (new-1) for the single slot.
    assert result == ["existing", "new-1"]
    assert "new-2" not in result


def test_first_connection_uses_available_slots() -> None:
    """Fresh user, no existing accounts: links up to the plan limit."""
    result = select_customers_to_link(
        customer_ids=["a", "b", "c"],
        existing_customer_ids=set(),
        slots_remaining=3,
    )
    assert result == ["a", "b", "c"]


def test_negative_slots_never_link_new_customers() -> None:
    """Defensive: negative slots (over quota) must not slice from the tail."""
    result = select_customers_to_link(
        customer_ids=["new"],
        existing_customer_ids=set(),
        slots_remaining=-2,
    )
    assert result == []
