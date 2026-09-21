"""The escalation tool.

Calling this tool is the only thing that makes ``needs_human`` true (ADR-008). The flag is
never a judgement the model reports; it is derived from the register this tool writes. That
is the whole point of ADR-002, and it means the tool's contract has to be exact.

One duplication is deliberate. The handover times below mirror the table in
``policies/contatti_orari.md``, because a customer told their case has been escalated
should be told when someone will look at it, in the same breath, without a second retrieval
round-trip. Duplication invites drift, so a test asserts that these times still appear in
the policy document.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from greenthumb.clock import Clock
from greenthumb.escalations_repository import EscalationReason, EscalationsRepository

TOOL_NAME = "escalate_to_human"

DEFAULT_SESSION_ID = "sessione-anonima"

# Written for the model: it decides on this text alone whether to hand over.
TOOL_DESCRIPTION = """\
Apre un ticket e passa la conversazione a un operatore umano.

USALO quando:
- il cliente chiede esplicitamente di parlare con una persona (customer_request);
- una richiesta di reso o rimborso e' fuori dai termini di policy, o il cliente chiede
  un'eccezione (refund_exception);
- la merce e' arrivata danneggiata, errata o incompleta (damaged_or_wrong_item);
- il cliente presenta un reclamo o e' chiaramente insoddisfatto (complaint);
- un ordine non risulta dopo che il cliente ha confermato il numero una seconda volta
  (order_not_found);
- la domanda e' pertinente ma la knowledge base non contiene la risposta (no_knowledge);
- c'e' un rischio per la salute di persone o animali: ingestione, tossicita', reazioni
  allergiche (safety).

NON USARLO per domande fuori ambito, cioe' non legate al giardinaggio o al negozio: a quelle
si risponde con un rifiuto cortese, senza aprire alcun ticket. NON usarlo per una normale
domanda su un prodotto o una policy a cui la knowledge base sa rispondere.

Il campo summary e' letto da un operatore umano, non dal cliente: scrivi cosa ha chiesto il
cliente, cosa hai gia' verificato e cosa resta da decidere. Indica order_id se la questione
riguarda un ordine.

Una seconda chiamata con lo stesso motivo nella stessa conversazione non apre un secondo
ticket: restituisce quello gia' aperto."""

# Mirrors the SLA table in policies/contatti_orari.md. Guarded by a test.
HANDOVER_TIMES: dict[str, str] = {
    "customer_request": "entro 1 giorno lavorativo",
    "refund_exception": "entro 1 giorno lavorativo",
    "damaged_or_wrong_item": "entro 4 ore lavorative",
    "complaint": "entro 1 giorno lavorativo",
    "order_not_found": "entro 1 giorno lavorativo",
    "no_knowledge": "entro 1 giorno lavorativo",
    "safety": "entro 4 ore lavorative",
}

CONFIRMATION = """\
Ticket {ticket_id} {verb}.

Comunica al cliente che la sua richiesta e' stata presa in carico con il riferimento
{ticket_id} e che un operatore lo contattera' {handover}. Gli orari del servizio clienti sono
dal lunedi' al venerdi' 9:00-13:00 e 14:00-18:00, il sabato 9:00-12:30.

Riporta il numero di ticket al cliente. Non inventare tempi diversi da quelli indicati qui."""

SAFETY_ADDENDUM = """\

Trattandosi di un caso che riguarda la salute, invita il cliente a rivolgersi SUBITO a un
medico o a un veterinario senza attendere il nostro richiamo."""


class EscalationInput(BaseModel):
    """Input schema for the escalation tool."""

    reason: EscalationReason = Field(
        description="Il criterio di escalation che si applica a questo caso."
    )
    summary: str = Field(
        min_length=1,
        description=(
            "Sintesi per l'operatore umano: cosa ha chiesto il cliente, cosa hai gia' "
            "verificato, cosa resta da decidere."
        ),
    )
    order_id: str | None = Field(
        default=None,
        description="Il numero d'ordine, se la questione ne riguarda uno.",
    )


def _session_id(config: RunnableConfig | None) -> str:
    """Extract the session identifier from the runtime configuration.

    The agent runs with ``thread_id = session_id`` (SPEC section 8), so the identifier
    arrives through the runnable config rather than as a tool argument: the model must not
    be able to choose, invent or omit it.

    Args:
        config: The runtime configuration, when one was supplied.

    Returns:
        The session identifier, or a placeholder when the tool is called outside a session.
    """
    # Callers inside a session always provide it; the fallback covers direct invocation.
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get("thread_id") or DEFAULT_SESSION_ID)


def make_escalation_tool(repository: EscalationsRepository, clock: Clock) -> StructuredTool:
    """Build the escalation tool with its dependencies bound.

    Args:
        repository: The escalation register.
        clock: The business-date source, used to timestamp tickets.

    Returns:
        The tool, ready to hand to ``create_agent``.
    """

    def _run(
        reason: EscalationReason,
        summary: str,
        config: RunnableConfig,
        order_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Open or retrieve a ticket for this conversation.

        The ``config`` parameter deliberately carries no default. LangChain injects the
        runnable config only into a parameter annotated ``RunnableConfig`` *without* one;
        adding ``= None`` looks defensive and silently disables the injection, which here
        would collapse every conversation into one shared session identifier and break both
        the idempotency of tickets and the ``needs_human`` flag derived from them (ADR-047).

        Args:
            reason: The escalation criterion.
            summary: The handover note for the operator.
            config: Runtime configuration carrying the session identifier, injected by
                LangChain and never supplied by the model.
            order_id: The order concerned, when there is one.

        Returns:
            The text for the model and the artifact for the response layer.
        """
        session_id = _session_id(config)
        ticket, created = repository.create(
            session_id=session_id,
            reason=reason,
            summary=summary,
            order_id=order_id,
            today=clock.today(),
        )

        message = CONFIRMATION.format(
            ticket_id=ticket.ticket_id,
            verb="aperto" if created else "gia' aperto per questa conversazione",
            handover=HANDOVER_TIMES[reason],
        )
        if reason == "safety":
            message += SAFETY_ADDENDUM

        return message, {
            "tool": TOOL_NAME,
            "escalated": True,
            "ticket_id": ticket.ticket_id,
            "reason": ticket.reason,
            "order_id": ticket.order_id,
            "session_id": ticket.session_id,
            "created": created,
        }

    return StructuredTool.from_function(
        func=_run,
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        args_schema=EscalationInput,
        response_format="content_and_artifact",
    )
