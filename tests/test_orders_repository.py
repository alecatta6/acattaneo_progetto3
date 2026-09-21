"""Tests for order lookup and identifier normalisation."""

from __future__ import annotations

import json
import pathlib

import pytest

from greenthumb.config import get_settings
from greenthumb.orders_repository import (
    OrdersRepository,
    OrdersRepositoryError,
    normalize_order_id,
)


@pytest.fixture(scope="module")
def repository() -> OrdersRepository:
    """Load the committed order dataset once.

    Returns:
        The populated repository.
    """
    return OrdersRepository.from_file(get_settings().orders_path)


# --- normalisation --------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["1042", "#1042", "ordine 1042", "Ordine n. 1042", "ORD-1042", "  1042  ", "l'ordine 1042!"],
)
def test_customer_phrasings_normalise_to_the_bare_number(raw: str) -> None:
    """Customers never type a bare identifier, so the tool must not require one.

    Args:
        raw: The identifier as a customer might write it.
    """
    assert normalize_order_id(raw) == "1042"


def test_leading_zeros_are_stripped() -> None:
    """An identifier copied from a padded field must still resolve."""
    assert normalize_order_id("01042") == "1042"


@pytest.mark.parametrize("raw", ["", "   ", "boh", "il mio ordine", "#", "0", "0000"])
def test_inputs_without_a_usable_number_are_rejected(raw: str) -> None:
    """No digits means nothing to look up; guessing would be worse than asking.

    Args:
        raw: An input carrying no usable identifier.
    """
    assert normalize_order_id(raw) is None


@pytest.mark.parametrize("raw", ["1042 e 1043", "ordini 1042, 1055"])
def test_ambiguous_inputs_are_rejected(raw: str) -> None:
    """Two numbers is a question for the customer, not a coin flip.

    Args:
        raw: An input naming more than one order.
    """
    assert normalize_order_id(raw) is None


# --- lookup ---------------------------------------------------------------------------


def test_lookup_accepts_customer_phrasings(repository: OrdersRepository) -> None:
    """Lookup applies the same normalisation, so the tool needs no pre-cleaning.

    Args:
        repository: The loaded repository.
    """
    for raw in ("1042", "#1042", "ordine 1042"):
        order = repository.get(raw)
        assert order is not None
        assert order.order_id == "1042"


def test_unknown_order_returns_none(repository: OrdersRepository) -> None:
    """A missing order is a normal outcome, not an exception.

    Args:
        repository: The loaded repository.
    """
    assert repository.get("9999") is None


def test_unusable_input_returns_none(repository: OrdersRepository) -> None:
    """Garbage in must not raise: the tool has to answer, not crash the turn.

    Args:
        repository: The loaded repository.
    """
    assert repository.get("nessun numero") is None


def test_committed_dataset_loads_and_validates(repository: OrdersRepository) -> None:
    """Every stored order must satisfy the schema.

    Args:
        repository: The loaded repository.
    """
    assert len(repository) == 26


# --- domain helpers -------------------------------------------------------------------


def test_order_1042_matches_the_assignment_example(repository: OrdersRepository) -> None:
    """The example order drives the integration tests and the evaluation.

    Args:
        repository: The loaded repository.
    """
    order = repository.get("1042")
    assert order is not None
    assert order.status == "shipped"
    assert order.is_in_transit is True
    assert order.has_perishable_items is True
    assert order.total_eur == pytest.approx(15.80)
    assert order.items[0].line_total_eur == pytest.approx(15.80)
    assert order.return_info is None


def test_return_alias_is_parsed(repository: OrdersRepository) -> None:
    """The JSON key `return` is a Python keyword, so the field is aliased.

    Args:
        repository: The loaded repository.
    """
    order = repository.get("1054")
    assert order is not None
    assert order.return_info is not None
    assert order.return_info.reason


def test_perishable_detection_distinguishes_categories(
    repository: OrdersRepository,
) -> None:
    """The 14-day window applies only to seeds and bulbs, so the flag changes answers.

    Args:
        repository: The loaded repository.
    """
    bulbs = repository.get("1042")
    tools_only = next(
        o
        for o in (repository.get(str(i)) for i in range(1042, 1068))
        if o is not None and not o.has_perishable_items
    )
    assert bulbs is not None and bulbs.has_perishable_items
    assert not tools_only.has_perishable_items


# --- failure modes --------------------------------------------------------------------


def test_missing_file_is_reported_with_the_remedy(tmp_path: pathlib.Path) -> None:
    """The error should say what to run, not just what is absent.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with pytest.raises(OrdersRepositoryError, match="make data"):
        OrdersRepository.from_file(tmp_path / "assente.json")


def test_invalid_json_is_reported(tmp_path: pathlib.Path) -> None:
    """A truncated file must fail loudly at load time.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "orders.json"
    path.write_text("[{", encoding="utf-8")
    with pytest.raises(OrdersRepositoryError, match="JSON valido"):
        OrdersRepository.from_file(path)


def test_order_failing_the_schema_names_the_order(tmp_path: pathlib.Path) -> None:
    """A malformed order must be identified, or the file is a haystack.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "orders.json"
    path.write_text(json.dumps([{"order_id": "1234", "status": "inventato"}]), encoding="utf-8")
    with pytest.raises(OrdersRepositoryError, match="ordine 1234"):
        OrdersRepository.from_file(path)


def test_empty_dataset_is_rejected(tmp_path: pathlib.Path) -> None:
    """An empty file would make every lookup fail with a misleading "not found".

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "orders.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(OrdersRepositoryError, match="non contiene ordini"):
        OrdersRepository.from_file(path)
