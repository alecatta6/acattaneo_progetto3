"""Generate data/orders.json deterministically.

The file is a deliverable and is committed, so the generator is seeded: running it twice
must produce a byte-identical file. Dates are expressed relative to the simulated business
date (ADR-003) rather than to the wall clock, so a delivery "tomorrow" stays tomorrow
whenever the notebook is executed.

Run with: uv run python scripts/generate_orders.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
from typing import Any

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "data" / "catalog.yaml"
ORDERS_PATH = REPO_ROOT / "data" / "orders.json"

# Fixed seed: the generated file is committed and must never churn.
SEED = 20261012
BUSINESS_DATE = dt.date(2026, 10, 12)

CARRIERS = ("BRT", "GLS")

FIRST_NAMES = (
    "Giulia",
    "Marco",
    "Elena",
    "Davide",
    "Chiara",
    "Luca",
    "Sara",
    "Matteo",
    "Francesca",
    "Andrea",
    "Silvia",
    "Paolo",
    "Martina",
    "Stefano",
    "Alessia",
    "Riccardo",
    "Valentina",
    "Simone",
    "Beatrice",
    "Tommaso",
    "Ilaria",
    "Nicola",
    "Federica",
    "Giorgio",
)
LAST_NAMES = (
    "Ferri",
    "Bianchi",
    "Conti",
    "Greco",
    "Marchetti",
    "Rinaldi",
    "Villa",
    "Sartori",
    "Gallo",
    "Lombardi",
    "Moretti",
    "Barbieri",
    "Fontana",
    "Caruso",
    "Mancini",
    "Costa",
    "Rizzo",
    "De Luca",
    "Pellegrini",
    "Serra",
    "Vitali",
    "Orlando",
    "Bernardi",
    "Coppola",
)

RETURN_REASONS = (
    "Prodotto non conforme alla descrizione",
    "Articolo arrivato danneggiato",
    "Ripensamento del cliente",
    "Bulbi ammuffiti all'apertura della confezione",
    "Taglia del vaso diversa da quella attesa",
)


def load_catalog() -> list[dict[str, Any]]:
    """Read the product catalogue.

    Returns:
        The list of product dictionaries.
    """
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["products"]


def _iso(date: dt.date | None) -> str | None:
    """Render a date as an ISO string, passing None through.

    Args:
        date: The date to render, or None.

    Returns:
        The ISO-8601 string, or None.
    """
    return date.isoformat() if date is not None else None


def _customer(rng: random.Random) -> tuple[str, str]:
    """Draw a customer name and a matching example email address.

    Args:
        rng: The seeded random generator.

    Returns:
        A tuple of full name and email address.
    """
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    slug = f"{first}.{last}".lower().replace(" ", "")
    return f"{first} {last}", f"{slug}@example.com"


def _line_items(
    rng: random.Random,
    catalog: list[dict[str, Any]],
    count: int,
    force_skus: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build the line items of an order.

    Args:
        rng: The seeded random generator.
        catalog: The product catalogue.
        count: How many distinct products to include.
        force_skus: SKUs that must appear, used to pin the deliberate edge cases.

    Returns:
        The list of line-item dictionaries.
    """
    if force_skus:
        by_sku = {p["sku"]: p for p in catalog}
        chosen = [by_sku[s] for s in force_skus]
        remaining = [p for p in catalog if p["sku"] not in force_skus]
        chosen += rng.sample(remaining, max(0, count - len(chosen)))
    else:
        chosen = rng.sample(catalog, count)
    return [
        {
            "sku": product["sku"],
            "name": product["name"],
            "quantity": rng.randint(1, 3),
            "unit_price_eur": product["price_eur"],
        }
        for product in chosen
    ]


def _total(items: list[dict[str, Any]]) -> float:
    """Sum the line items.

    Args:
        items: The order line items.

    Returns:
        The order total, rounded to two decimals.
    """
    return round(sum(i["quantity"] * i["unit_price_eur"] for i in items), 2)


def _build_order(
    rng: random.Random,
    catalog: list[dict[str, Any]],
    order_id: str,
    status: str,
    *,
    created_offset: int,
    delivery_offset: int,
    item_count: int = 1,
    force_skus: tuple[str, ...] | None = None,
    quantities: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """Assemble one order in the shape defined by SPEC section 4.4.

    Args:
        rng: The seeded random generator.
        catalog: The product catalogue.
        order_id: The numeric identifier, as a string.
        status: One of the seven allowed statuses.
        created_offset: Days from the business date to the creation date (negative = past).
        delivery_offset: Days from the business date to the estimated delivery.
        item_count: How many distinct products the order contains.
        force_skus: SKUs that must appear in the order.
        quantities: Fixed quantities per line, in order, when the total must be exact.

    Returns:
        The order dictionary.
    """
    name, email = _customer(rng)
    items = _line_items(rng, catalog, item_count, force_skus)
    if quantities:
        for item, qty in zip(items, quantities, strict=False):
            item["quantity"] = qty
    created = BUSINESS_DATE + dt.timedelta(days=created_offset)
    estimated = BUSINESS_DATE + dt.timedelta(days=delivery_offset)

    shipped = status in {"shipped", "delivered", "return_requested", "returned", "refunded"}
    delivered_at = estimated if status != "shipped" and shipped else None

    order: dict[str, Any] = {
        "order_id": order_id,
        "customer_name": name,
        "customer_email": email,
        "created_at": _iso(created),
        "status": status,
        "items": items,
        "total_eur": _total(items),
        "carrier": rng.choice(CARRIERS) if shipped else None,
        "tracking_code": None,
        "estimated_delivery": _iso(estimated) if status != "cancelled" else None,
        "delivered_at": _iso(delivered_at),
        "return": None,
    }
    if shipped:
        prefix = order["carrier"]
        order["tracking_code"] = f"{prefix}{rng.randint(10_000_000, 99_999_999)}"

    if status in {"return_requested", "returned", "refunded"}:
        requested = (delivered_at or estimated) + dt.timedelta(days=rng.randint(1, 10))
        refunded = requested + dt.timedelta(days=4) if status == "refunded" else None
        order["return"] = {
            "requested_at": _iso(requested),
            "reason": rng.choice(RETURN_REASONS),
            "refund_amount_eur": order["total_eur"] if status == "refunded" else None,
            "refunded_at": _iso(refunded),
        }
    return order


def _traccia_order(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Build order 1042 exactly as the assignment's example shows it.

    This order is pinned rather than generated: the example in SPEC section 4.4 fixes the
    customer, the dates, the tracking code and the 15.80 total, and the evaluation asserts
    against them.

    Args:
        catalog: The product catalogue.

    Returns:
        The order dictionary for 1042.
    """
    bulbs = next(p for p in catalog if p["sku"] == "GT-BUL-001")
    items = [
        {
            "sku": bulbs["sku"],
            "name": bulbs["name"],
            "quantity": 2,
            "unit_price_eur": bulbs["price_eur"],
        }
    ]
    return {
        "order_id": "1042",
        "customer_name": "Giulia Ferri",
        "customer_email": "giulia.ferri@example.com",
        "created_at": _iso(BUSINESS_DATE - dt.timedelta(days=4)),
        "status": "shipped",
        "items": items,
        "total_eur": _total(items),
        "carrier": "BRT",
        "tracking_code": "BRT00012345",
        "estimated_delivery": _iso(BUSINESS_DATE + dt.timedelta(days=1)),
        "delivered_at": None,
        "return": None,
    }


# (order_id, status, created_offset, delivery_offset, item_count, force_skus)
# Offsets are days from the business date; negative is in the past.
ORDER_PLAN: tuple[tuple[str, str, int, int, int, tuple[str, ...] | None], ...] = (
    # processing: paid, not yet shipped
    ("1043", "processing", -1, 4, 1, None),
    ("1044", "processing", 0, 5, 2, None),
    ("1045", "processing", -2, 3, 1, ("GT-SEM-002",)),
    # shipped: in transit
    ("1046", "shipped", -3, 2, 1, None),
    ("1047", "shipped", -5, 0, 3, None),  # multi-item, arriving today
    # delivered
    ("1048", "delivered", -12, -8, 1, None),
    ("1049", "delivered", -20, -16, 2, None),
    ("1050", "delivered", -6, -1, 1, ("GT-BUL-002",)),  # bulbs delivered yesterday
    ("1051", "delivered", -35, -31, 1, None),
    ("1052", "delivered", -9, -5, 4, None),  # large multi-item
    # return_requested
    ("1053", "return_requested", -18, -14, 1, None),
    ("1054", "return_requested", -45, -41, 1, ("GT-BUL-003",)),  # perishable, out of term
    ("1055", "return_requested", -11, -7, 2, None),
    # returned
    ("1056", "returned", -30, -26, 1, None),
    ("1057", "returned", -25, -21, 2, None),
    # refunded
    ("1058", "refunded", -40, -36, 1, None),
    ("1059", "refunded", -28, -24, 3, None),  # partial refund, adjusted below
    ("1060", "refunded", -22, -18, 1, ("GT-ATT-001",)),
    # cancelled
    ("1061", "cancelled", -7, 0, 1, None),
    ("1062", "cancelled", -2, 0, 2, None),
    # filler, mixed
    ("1063", "delivered", -15, -11, 1, ("GT-TER-002",)),
    ("1064", "shipped", -4, 1, 2, None),
    ("1065", "processing", 0, 6, 1, ("GT-VAS-003",)),
    ("1066", "delivered", -60, -56, 1, None),
    ("1067", "shipped", -8, -4, 1, None),  # late: estimated delivery is 4 days past
)


def build_orders() -> list[dict[str, Any]]:
    """Build the full order list, deterministically.

    Returns:
        The orders, ordered by identifier.
    """
    rng = random.Random(SEED)
    catalog = load_catalog()

    orders = [_traccia_order(catalog)]
    for order_id, status, created, delivery, items, forced in ORDER_PLAN:
        orders.append(
            _build_order(
                rng,
                catalog,
                order_id,
                status,
                created_offset=created,
                delivery_offset=delivery,
                item_count=items,
                force_skus=forced,
            )
        )

    by_id = {o["order_id"]: o for o in orders}

    # Deliberate edge case: a partial refund, where only part of the order came back.
    partial = by_id["1059"]
    partial["return"]["refund_amount_eur"] = round(
        partial["items"][0]["quantity"] * partial["items"][0]["unit_price_eur"], 2
    )
    partial["return"]["reason"] = "Reso parziale: un solo articolo restituito"

    # Deliberate edge case: a perishable return requested well past the 14-day window.
    # The generic path only pushes the request 1-10 days after delivery, which would sit
    # inside the term and quietly defeat the purpose of this case.
    late = by_id["1054"]
    delivered = dt.date.fromisoformat(late["delivered_at"])
    late["return"]["requested_at"] = _iso(delivered + dt.timedelta(days=30))
    late["return"]["reason"] = "Richiesta di rimborso oltre i 14 giorni su prodotto deperibile"

    return sorted(orders, key=lambda o: int(o["order_id"]))


def main() -> None:
    """Write data/orders.json and print a short summary."""
    orders = build_orders()
    ORDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ORDERS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(orders, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    statuses: dict[str, int] = {}
    for order in orders:
        statuses[order["status"]] = statuses.get(order["status"], 0) + 1
    print(f"scritti {len(orders)} ordini in {ORDERS_PATH.relative_to(REPO_ROOT)}")
    for status, count in sorted(statuses.items()):
        print(f"  {status:<18} {count}")


if __name__ == "__main__":
    main()
