"""Tests for the escalation register and tool. No LLM is involved."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest
from langchain_core.tools import StructuredTool

from greenthumb.clock import FrozenClock
from greenthumb.config import get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.tools.escalation_tool import (
    HANDOVER_TIMES,
    TOOL_NAME,
    make_escalation_tool,
)

BUSINESS_DATE = dt.date(2026, 10, 12)
ALL_REASONS = tuple(HANDOVER_TIMES)


@pytest.fixture
def register(tmp_path: pathlib.Path) -> EscalationsRepository:
    """Build an empty register in a temporary directory.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        The register, bound to a file that does not exist yet.
    """
    return EscalationsRepository(tmp_path / "escalations.jsonl")


@pytest.fixture
def escalation_tool(register: EscalationsRepository) -> StructuredTool:
    """Build the tool pinned to the business date.

    Args:
        register: The escalation register.

    Returns:
        The configured tool.
    """
    return make_escalation_tool(register, FrozenClock(BUSINESS_DATE))


def _call(tool: StructuredTool, session: str, **arguments: object) -> tuple[str, dict]:
    """Invoke the tool the way the agent does, through a tool call.

    Args:
        tool: The tool under test.
        session: The session identifier to pass as thread_id.
        **arguments: The tool arguments.

    Returns:
        The content and the artifact.
    """
    message = tool.invoke(
        {"name": tool.name, "args": arguments, "id": "call-1", "type": "tool_call"},
        config={"configurable": {"thread_id": session}},
    )
    return message.content, message.artifact


# --- contract -------------------------------------------------------------------------


def test_tool_declares_the_artifact_response_format(escalation_tool: StructuredTool) -> None:
    """needs_human is derived from this artifact, so the format is not optional.

    Args:
        escalation_tool: The tool under test.
    """
    assert escalation_tool.name == TOOL_NAME
    assert escalation_tool.response_format == "content_and_artifact"


def test_session_id_is_not_exposed_to_the_model(escalation_tool: StructuredTool) -> None:
    """The model must not be able to choose, invent or omit the session (ADR-047).

    Args:
        escalation_tool: The tool under test.
    """
    assert set(escalation_tool.args_schema.model_fields) == {"reason", "summary", "order_id"}


def test_description_excludes_out_of_scope_questions(
    escalation_tool: StructuredTool,
) -> None:
    """Out-of-scope questions get a polite refusal, never a ticket (SPEC 8).

    Args:
        escalation_tool: The tool under test.
    """
    flat = " ".join(escalation_tool.description.split())
    assert "NON USARLO per domande fuori ambito" in flat
    for reason in ALL_REASONS:
        assert reason in flat, f"il criterio {reason} non e' documentato per il modello"


# --- ticket creation ------------------------------------------------------------------


def test_opens_a_ticket_and_reports_it(escalation_tool: StructuredTool) -> None:
    """The first escalation of a session opens ESC-0001.

    Args:
        escalation_tool: The tool under test.
    """
    content, artifact = _call(
        escalation_tool,
        "sess-1",
        reason="refund_exception",
        summary="Rimborso bulbi oltre i termini",
        order_id="1054",
    )
    assert artifact["escalated"] is True
    assert artifact["ticket_id"] == "ESC-0001"
    assert artifact["created"] is True
    assert artifact["order_id"] == "1054"
    assert "ESC-0001" in content


def test_ticket_ids_are_progressive(escalation_tool: StructuredTool) -> None:
    """Numbering must not restart or collide across sessions.

    Args:
        escalation_tool: The tool under test.
    """
    _, first = _call(escalation_tool, "sess-1", reason="complaint", summary="a")
    _, second = _call(escalation_tool, "sess-2", reason="complaint", summary="b")
    _, third = _call(escalation_tool, "sess-3", reason="safety", summary="c")
    assert [first["ticket_id"], second["ticket_id"], third["ticket_id"]] == [
        "ESC-0001",
        "ESC-0002",
        "ESC-0003",
    ]


def test_ticket_is_timestamped_from_the_business_date(
    register: EscalationsRepository, escalation_tool: StructuredTool
) -> None:
    """Tickets must not carry the wall clock (ADR-003).

    Args:
        register: The escalation register.
        escalation_tool: The tool under test.
    """
    _call(escalation_tool, "sess-1", reason="complaint", summary="a")
    assert register.load()[0].created_at == BUSINESS_DATE


# --- idempotency ----------------------------------------------------------------------


def test_repeating_a_reason_returns_the_same_ticket(
    escalation_tool: StructuredTool, register: EscalationsRepository
) -> None:
    """A customer repeating a complaint must not generate a second ticket (SPEC 7).

    Args:
        escalation_tool: The tool under test.
        register: The escalation register.
    """
    _, first = _call(escalation_tool, "sess-1", reason="complaint", summary="primo")
    _, second = _call(escalation_tool, "sess-1", reason="complaint", summary="secondo")
    assert second["ticket_id"] == first["ticket_id"]
    assert second["created"] is False
    assert len(register.load()) == 1


def test_a_different_reason_in_the_same_session_opens_a_second_ticket(
    escalation_tool: StructuredTool,
) -> None:
    """Idempotency is per session *and* reason: two real problems deserve two tickets.

    Args:
        escalation_tool: The tool under test.
    """
    _, first = _call(escalation_tool, "sess-1", reason="damaged_or_wrong_item", summary="a")
    _, second = _call(escalation_tool, "sess-1", reason="customer_request", summary="b")
    assert first["ticket_id"] != second["ticket_id"]


def test_sessions_do_not_share_tickets(escalation_tool: StructuredTool) -> None:
    """Two customers with the same problem must get their own ticket each.

    Args:
        escalation_tool: The tool under test.
    """
    _, first = _call(escalation_tool, "sess-1", reason="complaint", summary="a")
    _, second = _call(escalation_tool, "sess-2", reason="complaint", summary="b")
    assert first["session_id"] == "sess-1"
    assert second["session_id"] == "sess-2"
    assert first["ticket_id"] != second["ticket_id"]


# --- the needs_human source -----------------------------------------------------------


def test_register_reports_open_tickets_per_session(
    escalation_tool: StructuredTool, register: EscalationsRepository
) -> None:
    """needs_human is session-scoped and reads this (ADR-008).

    Args:
        escalation_tool: The tool under test.
        register: The escalation register.
    """
    assert register.has_open_tickets("sess-1") is False
    _call(escalation_tool, "sess-1", reason="complaint", summary="a")
    assert register.has_open_tickets("sess-1") is True
    assert register.has_open_tickets("sess-2") is False


# --- customer-facing message ----------------------------------------------------------


@pytest.mark.parametrize("reason", ALL_REASONS)
def test_every_reason_states_a_handover_time(escalation_tool: StructuredTool, reason: str) -> None:
    """A customer told their case was escalated must be told when someone will look.

    Args:
        escalation_tool: The tool under test.
        reason: The escalation criterion under test.
    """
    content, _ = _call(escalation_tool, "sess-1", reason=reason, summary="x")
    assert HANDOVER_TIMES[reason] in " ".join(content.split())


def test_handover_times_match_the_policy_document() -> None:
    """Guards the deliberate duplication in the tool against drift.

    The tool repeats the handover times so the customer learns them in the same breath as
    the ticket number. That duplication is only acceptable while it stays true.
    """
    policy = (get_settings().kb_dir / "policies" / "contatti_orari.md").read_text(encoding="utf-8")
    flat = " ".join(policy.split())
    for phrase in set(HANDOVER_TIMES.values()):
        assert phrase in flat, (
            f"{phrase!r} non compare in policies/contatti_orari.md: "
            "la duplicazione dei tempi nel tool e' andata fuori sincrono"
        )


def test_safety_cases_redirect_to_a_professional(escalation_tool: StructuredTool) -> None:
    """A health question must not wait for a callback (policies/contatti_orari.md).

    Args:
        escalation_tool: The tool under test.
    """
    content, _ = _call(escalation_tool, "sess-1", reason="safety", summary="ingestione")
    flat = " ".join(content.split())
    assert "medico o a un veterinario" in flat
    assert HANDOVER_TIMES["safety"] in flat


# --- register robustness --------------------------------------------------------------


def test_missing_file_reads_as_empty(register: EscalationsRepository) -> None:
    """A fresh runtime has no register yet, which is normal, not an error.

    Args:
        register: The escalation register.
    """
    assert register.load() == []
    assert register.has_open_tickets("qualsiasi") is False


def test_corrupt_line_is_skipped_not_fatal(tmp_path: pathlib.Path) -> None:
    """A bad log line must not stop the system answering a customer.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "escalations.jsonl"
    good = {
        "ticket_id": "ESC-0001",
        "session_id": "sess-1",
        "reason": "complaint",
        "summary": "ok",
        "order_id": None,
        "created_at": "2026-10-12",
    }
    path.write_text(f"non json\n{json.dumps(good)}\n\n", encoding="utf-8")
    register = EscalationsRepository(path)
    assert [t.ticket_id for t in register.load()] == ["ESC-0001"]


def test_numbering_continues_after_existing_tickets(tmp_path: pathlib.Path) -> None:
    """Restarting the process must not reuse an identifier.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "escalations.jsonl"
    register = EscalationsRepository(path)
    register.create("sess-1", "complaint", "a", None, BUSINESS_DATE)
    register.create("sess-2", "complaint", "b", None, BUSINESS_DATE)

    reopened = EscalationsRepository(path)
    ticket, created = reopened.create("sess-3", "complaint", "c", None, BUSINESS_DATE)
    assert created is True
    assert ticket.ticket_id == "ESC-0003"
