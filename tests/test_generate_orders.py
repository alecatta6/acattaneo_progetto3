"""Tests for the deterministic order generator."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from generate_orders import BUSINESS_DATE, build_orders, load_catalog

STATUSES = {
    "processing",
    "shipped",
    "delivered",
    "return_requested",
    "returned",
    "refunded",
    "cancelled",
}


@pytest.fixture(scope="module")
def orders() -> list[dict[str, Any]]:
    """Build the order list once for the whole module.

    Returns:
        The generated orders.
    """
    return build_orders()


def test_generation_is_deterministic() -> None:
    """The file is committed, so two runs must produce identical data."""
    assert build_orders() == build_orders()


def test_enough_orders(orders: list[dict[str, Any]]) -> None:
    """SPEC 4.4 requires at least twenty-four orders.

    Args:
        orders: The generated orders.
    """
    assert len(orders) >= 24


def test_every_status_has_at_least_two_orders(orders: list[dict[str, Any]]) -> None:
    """Each status needs coverage, or the evaluation cannot exercise it.

    Args:
        orders: The generated orders.
    """
    counts = {status: 0 for status in STATUSES}
    for order in orders:
        counts[order["status"]] += 1
    thin = {status: n for status, n in counts.items() if n < 2}
    assert not thin, f"stati con meno di due ordini: {thin}"


def test_order_ids_are_unique_numeric_strings(orders: list[dict[str, Any]]) -> None:
    """Identifiers are strings of digits, as the order tool expects.

    Args:
        orders: The generated orders.
    """
    ids = [o["order_id"] for o in orders]
    assert len(set(ids)) == len(ids)
    assert all(isinstance(i, str) and i.isdigit() for i in ids)


def test_totals_match_the_line_items(orders: list[dict[str, Any]]) -> None:
    """A wrong total would make the agent state a wrong figure with confidence.

    Args:
        orders: The generated orders.
    """
    for order in orders:
        expected = round(sum(i["quantity"] * i["unit_price_eur"] for i in order["items"]), 2)
        assert order["total_eur"] == pytest.approx(expected), order["order_id"]


def test_prices_come_from_the_catalogue(orders: list[dict[str, Any]]) -> None:
    """Order prices must not drift from the catalogue.

    Args:
        orders: The generated orders.
    """
    prices = {p["sku"]: p["price_eur"] for p in load_catalog()}
    for order in orders:
        for item in order["items"]:
            assert item["unit_price_eur"] == prices[item["sku"]], order["order_id"]


def test_order_1042_matches_the_assignment_example(orders: list[dict[str, Any]]) -> None:
    """Order 1042 is fixed by SPEC 4.4 and the evaluation asserts against it.

    Args:
        orders: The generated orders.
    """
    order = next(o for o in orders if o["order_id"] == "1042")
    assert order["status"] == "shipped"
    assert order["customer_name"] == "Giulia Ferri"
    assert order["carrier"] == "BRT"
    assert order["tracking_code"] == "BRT00012345"
    assert order["total_eur"] == pytest.approx(15.80)
    assert order["delivered_at"] is None
    assert [i["sku"] for i in order["items"]] == ["GT-BUL-001"]
    assert order["estimated_delivery"] == (BUSINESS_DATE + dt.timedelta(days=1)).isoformat()


def test_returns_are_present_exactly_where_the_status_requires(
    orders: list[dict[str, Any]],
) -> None:
    """A return object must accompany the return statuses and no others.

    Args:
        orders: The generated orders.
    """
    for order in orders:
        if order["status"] in {"return_requested", "returned", "refunded"}:
            assert order["return"] is not None, order["order_id"]
            assert order["return"]["reason"], order["order_id"]
        elif order["status"] in {"processing", "cancelled"}:
            assert order["return"] is None, order["order_id"]


def test_deliberate_edge_cases_exist(orders: list[dict[str, Any]]) -> None:
    """SPEC 4.4 asks for specific awkward cases; without them the evaluation is toothless.

    Args:
        orders: The generated orders.
    """
    by_id = {o["order_id"]: o for o in orders}
    perishable = {
        "GT-BUL-001",
        "GT-BUL-002",
        "GT-BUL-003",
        "GT-SEM-001",
        "GT-SEM-002",
        "GT-SEM-003",
    }

    late = [
        o
        for o in orders
        if o["status"] == "shipped" and o["estimated_delivery"] < BUSINESS_DATE.isoformat()
    ]
    assert late, "nessun ordine in ritardo"

    assert any(len(o["items"]) >= 3 for o in orders), "nessun ordine multi-articolo"

    out_of_term = by_id["1054"]
    assert out_of_term["status"] == "return_requested"
    assert any(i["sku"] in perishable for i in out_of_term["items"])
    delivered = dt.date.fromisoformat(out_of_term["delivered_at"])
    requested = dt.date.fromisoformat(out_of_term["return"]["requested_at"])
    assert (requested - delivered).days > 14, "il reso deperibile non e' fuori termine"

    partial = by_id["1059"]
    assert partial["status"] == "refunded"
    assert partial["return"]["refund_amount_eur"] < partial["total_eur"]

    just_delivered = by_id["1050"]
    assert just_delivered["delivered_at"] == (BUSINESS_DATE - dt.timedelta(days=1)).isoformat()
    assert any(i["sku"] in perishable for i in just_delivered["items"])
