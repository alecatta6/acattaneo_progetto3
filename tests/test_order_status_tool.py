"""Tests for the order status tool. No LLM is involved."""

from __future__ import annotations

import datetime as dt

import pytest
from langchain_core.tools import StructuredTool

from greenthumb.clock import FrozenClock
from greenthumb.config import get_settings
from greenthumb.orders_repository import OrdersRepository
from greenthumb.tools.order_status_tool import TOOL_NAME, make_order_status_tool

BUSINESS_DATE = dt.date(2026, 10, 12)


@pytest.fixture(scope="module")
def repository() -> OrdersRepository:
    """Load the committed order dataset once.

    Returns:
        The populated repository.
    """
    return OrdersRepository.from_file(get_settings().orders_path)


@pytest.fixture
def order_tool(repository: OrdersRepository) -> StructuredTool:
    """Build the tool pinned to the business date.

    Args:
        repository: The loaded repository.

    Returns:
        The configured tool.
    """
    return make_order_status_tool(repository, FrozenClock(BUSINESS_DATE))


def _run(tool: StructuredTool, order_id: str) -> tuple[str, dict]:
    """Invoke the tool and return both halves of its result.

    Args:
        tool: The tool under test.
        order_id: The identifier to look up.

    Returns:
        The content string and the artifact dictionary.
    """
    return tool.func(order_id=order_id)


# --- contract -------------------------------------------------------------------------


def test_tool_declares_the_artifact_response_format(order_tool: StructuredTool) -> None:
    """response.py reads artifacts from ToolMessages, which requires this format.

    Args:
        order_tool: The tool under test.
    """
    assert order_tool.name == TOOL_NAME
    assert order_tool.response_format == "content_and_artifact"


def test_description_says_when_not_to_use_the_tool(order_tool: StructuredTool) -> None:
    """SPEC 7 requires the description to steer the model away from misuse.

    Args:
        order_tool: The tool under test.
    """
    description = order_tool.description
    assert "NON USARLO" in description
    assert "knowledge base" in description


# --- nominal case ---------------------------------------------------------------------


def test_reports_the_assignment_example_correctly(order_tool: StructuredTool) -> None:
    """Order 1042 must read as shipped and arriving tomorrow.

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "1042")
    assert "Ordine 1042" in content
    assert "spedito" in content
    assert "2026-10-13 (domani)" in content
    assert "15.80 EUR" in content
    assert "BRT00012345" in content
    assert artifact["found"] is True
    assert artifact["order_id"] == "1042"
    assert artifact["status"] == "shipped"


@pytest.mark.parametrize("raw", ["1042", "#1042", "ordine 1042", "Ordine n. 1042", "  1042 "])
def test_accepts_the_phrasings_customers_actually_use(order_tool: StructuredTool, raw: str) -> None:
    """The model should not have to clean the identifier before calling.

    Args:
        order_tool: The tool under test.
        raw: The identifier as a customer might write it.
    """
    _, artifact = _run(order_tool, raw)
    assert artifact["order_id"] == "1042"


# --- relative dates -------------------------------------------------------------------


def test_dates_are_relative_to_the_injected_clock(repository: OrdersRepository) -> None:
    """Moving the business date must move every relative phrase with it.

    Args:
        repository: The loaded repository.
    """
    day_before = make_order_status_tool(
        repository, FrozenClock(BUSINESS_DATE - dt.timedelta(days=1))
    )
    content, _ = day_before.func(order_id="1042")
    assert "2026-10-13 (fra 2 giorni)" in content

    delivery_day = make_order_status_tool(repository, FrozenClock(dt.date(2026, 10, 13)))
    content, _ = delivery_day.func(order_id="1042")
    assert "2026-10-13 (oggi)" in content


def test_every_date_is_given_in_both_forms(order_tool: StructuredTool) -> None:
    """ISO for precision, relative so the model never does date arithmetic.

    Args:
        order_tool: The tool under test.
    """
    content, _ = _run(order_tool, "1042")
    assert "2026-10-08 (4 giorni fa)" in content


# --- perishables and returns ----------------------------------------------------------


def test_days_since_delivery_are_precomputed(order_tool: StructuredTool) -> None:
    """The 14-day rule needs an elapsed count the model must not compute itself.

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "1054")
    assert artifact["days_since_delivery"] == 41
    assert "Giorni trascorsi dalla consegna: 41" in content
    assert "Richiesta presentata 30 giorni dopo la consegna" in content


def test_perishable_orders_are_flagged_without_applying_the_policy(
    order_tool: StructuredTool,
) -> None:
    """Code does arithmetic, the knowledge base holds the threshold, the model combines.

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "1054")
    assert artifact["has_perishable_items"] is True
    assert "deperibili" in content
    assert "knowledge base" in content
    # The tool must not state the rule itself, or it would bypass retrieval.
    assert "14 giorni" not in content.replace(
        "Richiesta di rimborso oltre i 14 giorni su prodotto deperibile", ""
    )


def test_partial_refund_is_marked_as_partial(order_tool: StructuredTool) -> None:
    """A partial refund read as a full one would be a wrong answer about money.

    Args:
        order_tool: The tool under test.
    """
    content, _ = _run(order_tool, "1059")
    assert "rimborso parziale" in content


# --- failure modes --------------------------------------------------------------------


def test_unknown_order_asks_the_customer_to_verify(order_tool: StructuredTool) -> None:
    """A missing order is not an error: it is a request to check the number (ADR-011).

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "9999")
    assert artifact["found"] is False
    assert artifact["order_id"] is None
    assert "verificarlo" in content
    assert "Non inventare" in content


def test_input_without_a_number_asks_for_one(order_tool: StructuredTool) -> None:
    """A phrase like 'il mio ordine' carries no identifier, so the tool must ask for one.

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "il mio ordine")
    assert artifact["found"] is False
    assert "un solo numero d'ordine" in content


def test_ambiguous_input_refuses_to_choose(order_tool: StructuredTool) -> None:
    """Two numbers in one message is a clarification, not a coin flip.

    Args:
        order_tool: The tool under test.
    """
    content, artifact = _run(order_tool, "1042 e 1055")
    assert artifact["found"] is False
    assert "Non sceglierne uno al posto suo" in content


def test_no_exception_escapes_to_the_agent(order_tool: StructuredTool) -> None:
    """A raising tool would break the turn; every input must produce an answer.

    Args:
        order_tool: The tool under test.
    """
    for raw in ["", "   ", "???", "0", "99999999999999", "ordine"]:
        content, artifact = _run(order_tool, raw)
        assert isinstance(content, str) and content
        assert artifact["found"] is False


def test_never_leaks_another_order(order_tool: StructuredTool) -> None:
    """One lookup must reveal exactly one order and nothing about the others.

    Args:
        order_tool: The tool under test.
    """
    content, _ = _run(order_tool, "1042")
    assert "Giulia Ferri" in content
    for other in ("1043", "1044", "1054", "1059"):
        assert f"Ordine {other}" not in content
