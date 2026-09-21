"""Tests for the data validator.

A validator that only ever passes is indistinguishable from no validator at all, so most
of these tests corrupt the data on purpose and assert that the corruption is caught.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import yaml

import validate_data
from validate_data import (
    CATALOG_PATH,
    ORDERS_PATH,
    check_catalog,
    check_knowledge_base,
    check_orders,
)


@pytest.fixture(scope="module")
def catalog() -> list[dict[str, Any]]:
    """Load the real catalogue once.

    Returns:
        The parsed product list.
    """
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))["products"]


@pytest.fixture(scope="module")
def orders() -> list[dict[str, Any]]:
    """Load the generated orders once.

    Returns:
        The parsed order list.
    """
    return json.loads(ORDERS_PATH.read_text(encoding="utf-8"))


def _orders_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> list[str]:
    """Run the order checks against a temporary orders file.

    Args:
        monkeypatch: Fixture used to redirect the validator at the temporary file.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The (possibly corrupted) order list to check.

    Returns:
        The list of reported errors.
    """
    path = tmp_path / "orders.json"
    path.write_text(json.dumps(orders), encoding="utf-8")
    monkeypatch.setattr(validate_data, "ORDERS_PATH", path)
    return check_orders(catalog)


# --- the happy path ------------------------------------------------------------------


def test_real_data_passes_every_check(catalog: list[dict[str, Any]]) -> None:
    """The committed data must be valid, or `make data` is broken.

    Args:
        catalog: The product catalogue.
    """
    assert check_catalog(catalog) == []
    assert check_knowledge_base(catalog) == []
    assert check_orders(catalog) == []


# --- catalogue ------------------------------------------------------------------------


def test_malformed_sku_is_rejected(catalog: list[dict[str, Any]]) -> None:
    """The SKU format is what ties orders, sheets and guides together.

    Args:
        catalog: The product catalogue.
    """
    broken = copy.deepcopy(catalog)
    broken[0]["sku"] = "BUL-1"
    assert any("formato SKU" in e for e in check_catalog(broken))


def test_perishable_flag_must_match_the_category(catalog: list[dict[str, Any]]) -> None:
    """The flag drives the 14-day rule, so a wrong value changes policy answers.

    Args:
        catalog: The product catalogue.
    """
    broken = copy.deepcopy(catalog)
    bulbs = next(p for p in broken if p["category"] == "bulbi")
    bulbs["perishable"] = False
    assert any("perishable" in e for e in check_catalog(broken))


def test_invalid_season_is_rejected(catalog: list[dict[str, Any]]) -> None:
    """Seasons must stay comparable with clock.season_of (ADR-034).

    Args:
        catalog: The product catalogue.
    """
    broken = copy.deepcopy(catalog)
    broken[0]["season"] = ["autunno", "monsone"]
    assert any("stagioni non valide" in e for e in check_catalog(broken))


def test_kb_path_without_extension_is_rejected(catalog: list[dict[str, Any]]) -> None:
    """ADR-006 fixed one identifier form; a bare path would reintroduce two.

    Args:
        catalog: The product catalogue.
    """
    broken = copy.deepcopy(catalog)
    broken[0]["kb_path"] = broken[0]["kb_path"].removesuffix(".md")
    assert any("estensione" in e for e in check_catalog(broken))


def test_missing_product_sheet_is_detected(catalog: list[dict[str, Any]]) -> None:
    """Every catalogue entry needs its sheet, or retrieval has nothing to return.

    Args:
        catalog: The product catalogue.
    """
    broken = copy.deepcopy(catalog)
    broken[0]["kb_path"] = "products/non_esiste.md"
    errors = check_catalog(broken)
    assert any("scheda prodotto assente" in e for e in errors)


# --- knowledge base -------------------------------------------------------------------


def test_unknown_sku_in_frontmatter_is_detected(catalog: list[dict[str, Any]]) -> None:
    """A related_skus entry that matches nothing would dangle silently.

    Args:
        catalog: The product catalogue.
    """
    shrunk = [p for p in catalog if p["sku"] != "GT-BUL-001"]
    errors = check_knowledge_base(shrunk)
    assert any("related_skus inesistenti" in e for e in errors)


# --- orders ---------------------------------------------------------------------------


def test_wrong_total_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> None:
    """A wrong total is the worst kind of error: the agent would state it confidently.

    Args:
        monkeypatch: Fixture used to redirect the validator.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The generated orders.
    """
    broken = copy.deepcopy(orders)
    broken[0]["total_eur"] = 999.99
    assert any("totale" in e for e in _orders_errors(monkeypatch, tmp_path, catalog, broken))


def test_price_drift_from_the_catalogue_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> None:
    """Order prices and catalogue prices must never diverge.

    Args:
        monkeypatch: Fixture used to redirect the validator.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The generated orders.
    """
    broken = copy.deepcopy(orders)
    broken[0]["items"][0]["unit_price_eur"] = 1.0
    errors = _orders_errors(monkeypatch, tmp_path, catalog, broken)
    assert any("diverso dal catalogo" in e for e in errors)


def test_missing_order_1042_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> None:
    """Order 1042 is the assignment's own example and must always be present.

    Args:
        monkeypatch: Fixture used to redirect the validator.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The generated orders.
    """
    broken = [o for o in orders if o["order_id"] != "1042"]
    errors = _orders_errors(monkeypatch, tmp_path, catalog, broken)
    assert any("1042" in e for e in errors)


def test_wrong_delivery_date_on_1042_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> None:
    """The example fixes delivery at business date plus one day.

    Args:
        monkeypatch: Fixture used to redirect the validator.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The generated orders.
    """
    broken = copy.deepcopy(orders)
    next(o for o in broken if o["order_id"] == "1042")["estimated_delivery"] = "2027-01-01"
    errors = _orders_errors(monkeypatch, tmp_path, catalog, broken)
    assert any("consegna stimata" in e for e in errors)


def test_thin_status_coverage_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    catalog: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> None:
    """Each status needs two orders, so the evaluation can exercise all of them.

    Args:
        monkeypatch: Fixture used to redirect the validator.
        tmp_path: Pytest temporary directory.
        catalog: The product catalogue.
        orders: The generated orders.
    """
    broken = [o for o in orders if o["status"] != "cancelled"]
    broken.append(copy.deepcopy(next(o for o in orders if o["status"] == "cancelled")))
    errors = _orders_errors(monkeypatch, tmp_path, catalog, broken)
    assert any("stato cancelled" in e for e in errors)
