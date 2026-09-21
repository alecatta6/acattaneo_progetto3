"""The escalation ticket register.

Mirrors ``orders_repository.py``: this module owns the file, the tool stays thin. It
matters more than a log file usually would, because ``needs_human`` is derived from it
rather than from anything the model says (ADR-008), which makes the register the
authoritative answer to "does this conversation need an operator?".

The file is append-only JSONL and is not versioned: it is runtime state, and on a clean
Colab runtime it starts empty, so ticket numbering is reproducible.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The escalation criteria of SPEC section 8. Out-of-scope questions are deliberately
# absent: those get a polite refusal, not a ticket.
EscalationReason = Literal[
    "customer_request",
    "refund_exception",
    "damaged_or_wrong_item",
    "complaint",
    "order_not_found",
    "no_knowledge",
    "safety",
]

TICKET_PREFIX = "ESC-"
TICKET_DIGITS = 4


class EscalationTicket(BaseModel):
    """One handover to a human operator."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    session_id: str
    reason: EscalationReason
    summary: str = Field(min_length=1)
    order_id: str | None = None
    created_at: dt.date


class EscalationsRepository:
    """Append-only access to the escalation register."""

    def __init__(self, path: pathlib.Path) -> None:
        """Bind the repository to a file.

        Args:
            path: Path to the JSONL register. It need not exist yet.
        """
        self._path = path

    def load(self) -> list[EscalationTicket]:
        """Read every ticket recorded so far.

        A malformed line is skipped rather than raising: a corrupt log entry must not
        prevent the system from answering a customer. The cost is that a corrupted line
        is invisible, which is acceptable for a register that is rebuilt on every clean
        run.

        Returns:
            The tickets, in the order they were written.
        """
        if not self._path.exists():
            return []
        tickets: list[EscalationTicket] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                tickets.append(EscalationTicket.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return tickets

    def find(self, session_id: str, reason: EscalationReason) -> EscalationTicket | None:
        """Look for an existing ticket for this session and reason.

        Args:
            session_id: The conversation identifier.
            reason: The escalation reason.

        Returns:
            The existing ticket, or None when this session has not escalated for this
            reason yet.
        """
        for ticket in self.load():
            if ticket.session_id == session_id and ticket.reason == reason:
                return ticket
        return None

    def has_open_tickets(self, session_id: str) -> bool:
        """Report whether a session has escalated at all.

        This is what ``needs_human`` reads: the flag is session-scoped, so it stays true
        for the rest of the conversation once an operator has been involved (ADR-008).

        Args:
            session_id: The conversation identifier.

        Returns:
            True when the session has at least one ticket.
        """
        return any(ticket.session_id == session_id for ticket in self.load())

    def _next_ticket_id(self, existing: list[EscalationTicket]) -> str:
        """Compute the next progressive identifier.

        Args:
            existing: The tickets already recorded.

        Returns:
            An identifier such as ``ESC-0001``.
        """
        numbers = [
            int(ticket.ticket_id.removeprefix(TICKET_PREFIX))
            for ticket in existing
            if ticket.ticket_id.startswith(TICKET_PREFIX)
            and ticket.ticket_id.removeprefix(TICKET_PREFIX).isdigit()
        ]
        return f"{TICKET_PREFIX}{max(numbers, default=0) + 1:0{TICKET_DIGITS}d}"

    def create(
        self,
        session_id: str,
        reason: EscalationReason,
        summary: str,
        order_id: str | None,
        today: dt.date,
    ) -> tuple[EscalationTicket, bool]:
        """Open a ticket, or return the one this session already has for this reason.

        Idempotency is per session and reason (SPEC section 7): a customer who repeats a
        complaint should not generate a second ticket, but the same customer reporting a
        damaged item *and* asking for an operator legitimately produces two.

        Args:
            session_id: The conversation identifier.
            reason: The escalation reason.
            summary: The handover note for the operator.
            order_id: The order concerned, when there is one.
            today: The business date, used as the ticket timestamp.

        Returns:
            The ticket and whether it was newly created.
        """
        existing = self.load()
        for ticket in existing:
            if ticket.session_id == session_id and ticket.reason == reason:
                return ticket, False

        ticket = EscalationTicket(
            ticket_id=self._next_ticket_id(existing),
            session_id=session_id,
            reason=reason,
            summary=summary.strip(),
            order_id=order_id,
            created_at=today,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(ticket.model_dump_json() + "\n")
        return ticket, True
