"""Access to the order dataset.

The repository is the only place that reads ``orders.json``. It also owns identifier
normalisation, because customers do not type bare identifiers: "#1042", "ordine 1042" and
"Ordine n. 1042" all mean the same order, and every caller would otherwise reinvent the
same cleaning badly.
"""

from __future__ import annotations

import json
import pathlib
import re

from pydantic import ValidationError

from greenthumb.schemas import Order

# Customers wrap the number in words and punctuation; the digits are the identifier.
_DIGITS = re.compile(r"\d+")


class OrdersRepositoryError(RuntimeError):
    """Raised when the order dataset cannot be read or is malformed."""


def normalize_order_id(raw: str) -> str | None:
    """Extract the order identifier from whatever the customer typed.

    Handles the forms that actually arrive: ``"1042"``, ``"#1042"``, ``"ordine 1042"``,
    ``"Ordine n. 1042"``, ``"ORD-1042"`` and stray whitespace.

    Args:
        raw: The identifier as the customer wrote it.

    Returns:
        The digit sequence, or None when the input contains no digits or more than one
        distinct number — an ambiguous input the agent should ask about rather than guess.
    """
    if not raw:
        return None
    matches = _DIGITS.findall(raw)
    if len(matches) != 1:
        return None
    # Leading zeros carry no meaning here, and an all-zero string is not an identifier.
    return matches[0].lstrip("0") or None


class OrdersRepository:
    """Read-only access to the orders, indexed by identifier."""

    def __init__(self, orders: dict[str, Order]) -> None:
        """Build the repository from an already-parsed mapping.

        Args:
            orders: Orders keyed by identifier.
        """
        self._orders = orders

    @classmethod
    def from_file(cls, path: pathlib.Path) -> OrdersRepository:
        """Load the repository from the JSON dataset.

        Args:
            path: Path to ``orders.json``.

        Returns:
            The populated repository.

        Raises:
            OrdersRepositoryError: If the file is missing, is not valid JSON, or contains
                an order that does not match the schema.
        """
        if not path.exists():
            raise OrdersRepositoryError(f"{path} non esiste: eseguire `make data` per generarlo")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OrdersRepositoryError(f"{path} non e' JSON valido: {exc}") from exc

        orders: dict[str, Order] = {}
        for entry in raw:
            try:
                order = Order.model_validate(entry)
            except ValidationError as exc:
                identifier = entry.get("order_id", "<senza id>")
                raise OrdersRepositoryError(f"ordine {identifier} non valido: {exc}") from exc
            orders[order.order_id] = order
        if not orders:
            raise OrdersRepositoryError(f"{path} non contiene ordini")
        return cls(orders)

    def get(self, raw_order_id: str) -> Order | None:
        """Look up an order by whatever the customer typed.

        Args:
            raw_order_id: The identifier, possibly wrapped in words or punctuation.

        Returns:
            The order, or None when the identifier is unusable or unknown.
        """
        normalized = normalize_order_id(raw_order_id)
        if normalized is None:
            return None
        return self._orders.get(normalized)

    def __len__(self) -> int:
        """Return how many orders are loaded.

        Returns:
            The number of orders.
        """
        return len(self._orders)
