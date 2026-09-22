"""Shared data models.

The order models mirror the structure written by ``scripts/generate_orders.py`` and fixed
by SPEC section 4.4. They are strict on purpose: a malformed order file should fail at load
time, in one place, rather than surfacing as a wrong figure in a customer-facing answer.

:class:`AgentOutput` is what the model is asked to produce. It is deliberately *not* the
response the API returns: ``sources``, ``needs_human`` and the final ``confidence`` are
computed from what actually happened during the turn, not from what the model claims
(ADR-002). The final contract lands in ``response.py``.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["high", "medium", "low"]

OrderStatus = Literal[
    "processing",
    "shipped",
    "delivered",
    "return_requested",
    "returned",
    "refunded",
    "cancelled",
]

# Statuses in which the customer is still waiting for something to arrive.
IN_TRANSIT_STATUSES: frozenset[str] = frozenset({"processing", "shipped"})


class OrderItem(BaseModel):
    """One line of an order."""

    model_config = ConfigDict(frozen=True)

    sku: str
    name: str
    quantity: int = Field(ge=1)
    unit_price_eur: float = Field(gt=0)

    @property
    def line_total_eur(self) -> float:
        """Return the line total.

        Returns:
            Quantity times unit price, rounded to two decimals.
        """
        return round(self.quantity * self.unit_price_eur, 2)


class OrderReturn(BaseModel):
    """The return or refund attached to an order, when one exists."""

    model_config = ConfigDict(frozen=True)

    requested_at: dt.date
    reason: str
    refund_amount_eur: float | None = None
    refunded_at: dt.date | None = None


class Order(BaseModel):
    """A customer order, as stored in data/orders.json."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    customer_name: str
    customer_email: str
    created_at: dt.date
    status: OrderStatus
    items: list[OrderItem] = Field(min_length=1)
    total_eur: float = Field(gt=0)
    carrier: str | None = None
    tracking_code: str | None = None
    estimated_delivery: dt.date | None = None
    delivered_at: dt.date | None = None
    return_info: OrderReturn | None = Field(default=None, alias="return")

    @property
    def is_in_transit(self) -> bool:
        """Report whether the customer is still waiting for the order.

        Returns:
            True when the order has not yet been delivered, returned or cancelled.
        """
        return self.status in IN_TRANSIT_STATUSES

    @property
    def has_perishable_items(self) -> bool:
        """Report whether the order contains seeds or bulbs.

        Perishables carry the shorter 14-day returns window
        (``policies/prodotti_deperibili.md``), so the distinction changes the answer.

        Returns:
            True when at least one line is a seed or bulb SKU.
        """
        return any(item.sku.startswith(("GT-SEM-", "GT-BUL-")) for item in self.items)


class AgentOutput(BaseModel):
    """The structured output the agent is asked to produce.

    No field carries a default, on purpose. The provider's strict JSON schema requires every
    property to appear in ``required``, and an optional field makes the whole request fail
    with ``Invalid schema for response_format`` (ADR-026). ``cited_sources`` is therefore
    mandatory, with an empty list when the knowledge base was not used.
    """

    model_config = ConfigDict(frozen=True)

    answer: str = Field(description="La risposta per il cliente, in italiano.")
    proposed_confidence: Confidence = Field(
        description=(
            "Quanto il modello ritiene la risposta coperta dalle fonti trovate. Il livello "
            "finale puo' essere abbassato dal livello deterministico, mai alzato."
        )
    )
    cited_sources: list[str] = Field(
        description=(
            "I doc_id dei documenti realmente usati, lista vuota se nessuno. Vengono "
            "intersecati con cio' che il retrieval ha davvero restituito."
        )
    )
