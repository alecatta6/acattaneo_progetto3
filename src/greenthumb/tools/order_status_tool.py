"""The order status tool.

Two decisions shape this tool.

**All date arithmetic happens here.** The tool reports every date twice, in ISO form and
relative to the business date ("domani", "3 giorni fa"), and pre-computes the days elapsed
since delivery. Language models are unreliable at date arithmetic, and a wrong answer about
when a parcel arrives is exactly the kind of error a customer notices.

**The tool does not apply policy.** It reports that an order contains perishables and that
it was delivered 30 days ago; it does not decide whether a return is still possible. That
threshold lives in the knowledge base, retrieved through the other tool. Code does the
arithmetic, the knowledge base holds the rule, the model combines them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from greenthumb.clock import Clock, describe_delta
from greenthumb.orders_repository import OrdersRepository, normalize_order_id
from greenthumb.schemas import Order

TOOL_NAME = "get_order_status"

# Written for the model: it decides on this text alone whether to call the tool.
TOOL_DESCRIPTION = """\
Recupera lo stato reale di un ordine GreenThumb a partire dal suo numero.

USALO quando il cliente chiede dove sia il suo ordine, quando arriva, cosa conteneva, se e'
stato consegnato, oppure quando una domanda su reso o rimborso riguarda un ordine specifico
e hai bisogno delle date effettive.

NON USARLO per informazioni su prodotti, consigli di coltivazione o condizioni di reso e
spedizione: quelle stanno nella knowledge base, non negli ordini. NON inventare un numero
d'ordine: se il cliente non lo ha fornito, chiediglielo.

Accetta il numero in qualunque forma il cliente lo scriva ("1042", "#1042", "ordine 1042").
Restituisce le date sia in formato ISO sia in forma relativa a oggi, gia' calcolate: non
devi fare aritmetica sulle date."""

STATUS_LABELS: dict[str, str] = {
    "processing": "in preparazione",
    "shipped": "spedito, in transito",
    "delivered": "consegnato",
    "return_requested": "reso richiesto dal cliente",
    "returned": "reso ricevuto in magazzino",
    "refunded": "rimborsato",
    "cancelled": "annullato",
}

NOT_FOUND_MESSAGE = """\
Nessun ordine trovato con il numero indicato ({raw!r}).

Il numero d'ordine e' di quattro cifre e si trova nell'email di conferma e nell'area
personale del cliente. Chiedi al cliente di verificarlo e di ripeterlo. Non inventare dati
e non supporre lo stato dell'ordine."""

AMBIGUOUS_MESSAGE = """\
Il testo fornito ({raw!r}) non contiene un numero d'ordine utilizzabile: manca del tutto
oppure ne contiene piu' di uno.

Chiedi al cliente di indicare un solo numero d'ordine. Non sceglierne uno al posto suo."""


class OrderStatusInput(BaseModel):
    """Input schema for the order status tool."""

    order_id: str = Field(
        description=(
            "Il numero d'ordine come lo ha scritto il cliente. Sono accettate le forme "
            "'1042', '#1042', 'ordine 1042'."
        )
    )


def _format_date(label: str, date: dt.date | None, today: dt.date) -> str | None:
    """Render one date in both absolute and relative form.

    Args:
        label: Human-readable name of the date.
        date: The date to render, or None when absent.
        today: The business date.

    Returns:
        A formatted line, or None when the date is absent.
    """
    if date is None:
        return None
    return f"- {label}: {date.isoformat()} ({describe_delta(date, today)})"


def _format_order(order: Order, today: dt.date) -> str:
    """Render an order as the text the model reads.

    Args:
        order: The order to render.
        today: The business date.

    Returns:
        The formatted description.
    """
    lines = [
        f"Ordine {order.order_id} — stato: {STATUS_LABELS[order.status]}",
        f"Intestato a: {order.customer_name}",
        "",
        "Articoli:",
    ]
    lines += [
        f"- {item.quantity} x {item.name} ({item.sku}) — "
        f"{item.unit_price_eur:.2f} EUR cadauno, {item.line_total_eur:.2f} EUR di riga"
        for item in order.items
    ]
    lines += ["", f"Totale ordine: {order.total_eur:.2f} EUR", "", "Date:"]

    dates = [
        _format_date("Ordine effettuato il", order.created_at, today),
        _format_date("Consegna stimata", order.estimated_delivery, today),
        _format_date("Consegnato il", order.delivered_at, today),
    ]
    lines += [line for line in dates if line]

    if order.carrier:
        tracking = order.tracking_code or "non ancora disponibile"
        lines += ["", f"Corriere: {order.carrier} — codice di tracciatura: {tracking}"]

    if order.delivered_at is not None:
        elapsed = (today - order.delivered_at).days
        lines += [
            "",
            f"Giorni trascorsi dalla consegna: {elapsed}.",
        ]
        if order.has_perishable_items:
            lines.append(
                "L'ordine contiene prodotti deperibili (sementi o bulbi), per i quali valgono "
                "termini di reso diversi: verificali nella knowledge base prima di rispondere."
            )

    if order.return_info is not None:
        info = order.return_info
        lines += ["", "Pratica di reso o rimborso:"]
        line = _format_date("Richiesta il", info.requested_at, today)
        if line:
            lines.append(line)
        lines.append(f"- Motivo dichiarato: {info.reason}")
        if info.refund_amount_eur is not None:
            partial = " (rimborso parziale)" if info.refund_amount_eur < order.total_eur else ""
            lines.append(f"- Importo rimborsato: {info.refund_amount_eur:.2f} EUR{partial}")
        refunded = _format_date("Rimborsato il", info.refunded_at, today)
        if refunded:
            lines.append(refunded)
        if order.delivered_at is not None:
            gap = (info.requested_at - order.delivered_at).days
            lines.append(f"- Richiesta presentata {gap} giorni dopo la consegna.")

    return "\n".join(lines)


def _artifact(order: Order | None, today: dt.date, found: bool) -> dict[str, Any]:
    """Build the structured record for the deterministic response layer.

    Args:
        order: The order, when one was found.
        today: The business date.
        found: Whether the lookup succeeded.

    Returns:
        A JSON-serialisable record. Order data is never a "source" (SPEC section 5), so
        this record exists to tell response.py that structured data was used, not to
        contribute citations.
    """
    if order is None or not found:
        return {"tool": TOOL_NAME, "found": False, "order_id": None}
    days_since_delivery = (
        (today - order.delivered_at).days if order.delivered_at is not None else None
    )
    return {
        "tool": TOOL_NAME,
        "found": True,
        "order_id": order.order_id,
        "status": order.status,
        "has_perishable_items": order.has_perishable_items,
        "days_since_delivery": days_since_delivery,
    }


def make_order_status_tool(repository: OrdersRepository, clock: Clock) -> StructuredTool:
    """Build the order status tool with its dependencies bound.

    Args:
        repository: The order repository.
        clock: The business-date source.

    Returns:
        The tool, ready to hand to ``create_agent``.
    """

    def _run(order_id: str) -> tuple[str, dict[str, Any]]:
        """Look up an order and describe it.

        Args:
            order_id: The identifier as the customer wrote it.

        Returns:
            The text for the model and the artifact for the response layer.
        """
        today = clock.today()
        order = repository.get(order_id)
        if order is not None:
            return _format_order(order, today), _artifact(order, today, found=True)

        # Distinguish "no usable number" from "number not in the dataset": the first is a
        # question for the customer, the second a verification request (ADR-011).
        message = NOT_FOUND_MESSAGE if normalize_order_id(order_id) else AMBIGUOUS_MESSAGE
        return message.format(raw=order_id), _artifact(None, today, found=False)

    return StructuredTool.from_function(
        func=_run,
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        args_schema=OrderStatusInput,
        response_format="content_and_artifact",
    )
