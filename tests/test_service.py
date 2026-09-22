"""Tests for the public entry point. A stub agent stands in: no provider, no network."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from greenthumb.agent import FALLBACK_ANSWER
from greenthumb.config import Settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.schemas import AgentOutput, ChatResponse
from greenthumb.service import ChatService, ChatTurn, new_session_id

BULBS = "guides/bulbi_autunnali.md"


def _settings() -> Settings:
    """Build settings detached from any .env file.

    Returns:
        The settings instance.
    """
    return Settings(_env_file=None)


class _StubAgent:
    """Returns a prepared state, or raises, standing in for the compiled agent."""

    def __init__(self, state: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        """Prepare the stub.

        Args:
            state: The state to return from invoke.
            error: An exception to raise instead.
        """
        self._state = state or {}
        self._error = error
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.checkpointer = _StubCheckpointer()

    def invoke(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Record the call and return the prepared state.

        Args:
            payload: The message payload.
            config: The runnable configuration.

        Returns:
            The prepared state.

        Raises:
            Exception: The prepared error, when one was given.
        """
        self.calls.append((payload, config))
        if self._error is not None:
            raise self._error
        return self._state


class _StubCheckpointer:
    """Records which threads were deleted."""

    def __init__(self) -> None:
        """Initialise the recorder."""
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        """Record a deletion.

        Args:
            thread_id: The thread to delete.
        """
        self.deleted.append(thread_id)


def _kb_message(doc_id: str = BULBS, score: float = 0.88, text: str = "estratto") -> ToolMessage:
    """Build a ToolMessage shaped like the knowledge base tool's output.

    Args:
        doc_id: The retrieved document.
        score: Its similarity.
        text: The chunk text.

    Returns:
        The message.
    """
    return ToolMessage(
        content="estratti",
        tool_call_id="kb",
        name="search_knowledge_base",
        artifact={
            "tool": "search_knowledge_base",
            "query": "q",
            "doc_type": None,
            "threshold": 0.813,
            "best_similarity": score,
            "results": [
                {"doc_id": doc_id, "score": score, "chunk_id": f"{doc_id}#0", "text": text}
            ],
        },
    )


def _state(
    answer: str = "Risposta.",
    confidence: str = "high",
    cited: list[str] | None = None,
    tool_calls: list[str] | None = None,
) -> dict[str, Any]:
    """Build an agent state for one completed turn.

    Args:
        answer: The answer the model produced.
        confidence: The confidence it proposed.
        cited: The documents it claims to have used.
        tool_calls: Names of tools called in a single AIMessage.

    Returns:
        The state.
    """
    names = tool_calls if tool_calls is not None else ["search_knowledge_base"]
    calls = [
        {"name": n, "args": {}, "id": f"c{i}", "type": "tool_call"} for i, n in enumerate(names)
    ]
    return {
        "messages": [
            HumanMessage(content="domanda"),
            AIMessage(content="", tool_calls=calls),
            _kb_message(),
            AIMessage(content="finale"),
        ],
        "structured_response": AgentOutput(
            answer=answer,
            proposed_confidence=confidence,  # type: ignore[arg-type]
            cited_sources=cited if cited is not None else [BULBS],
        ),
    }


def _service(
    agent: _StubAgent,
    register: EscalationsRepository | None = None,
    tmp: pathlib.Path | None = None,
) -> ChatService:
    """Build a service over a stub agent.

    Args:
        agent: The stub agent.
        register: The escalation register, created empty when omitted.
        tmp: Temporary directory for the register file.

    Returns:
        The service.
    """
    path = (tmp or pathlib.Path(".")) / "escalations.jsonl"
    return ChatService(
        agent=agent, escalations=register or EscalationsRepository(path), settings=_settings()
    )


# --- the contract ---------------------------------------------------------------------


def test_chat_returns_the_four_field_contract(tmp_path: pathlib.Path) -> None:
    """The DoD asks for exactly this signature and exactly these fields.

    Args:
        tmp_path: Pytest temporary directory.
    """
    service = _service(_StubAgent(_state()), tmp=tmp_path)
    response = service.chat("domanda", "sess-1")
    assert isinstance(response, ChatResponse)
    assert set(response.model_dump()) == {"answer", "confidence", "sources", "needs_human"}


def test_session_id_reaches_the_checkpointer(tmp_path: pathlib.Path) -> None:
    """thread_id keys the conversation and feeds the escalation tool (ADR-047).

    Args:
        tmp_path: Pytest temporary directory.
    """
    agent = _StubAgent(_state())
    _service(agent, tmp=tmp_path).chat("domanda", "sess-42")
    _, config = agent.calls[0]
    assert config["configurable"]["thread_id"] == "sess-42"


def test_new_session_ids_are_distinct() -> None:
    """Two conversations must never share a thread."""
    assert new_session_id() != new_session_id()


# --- the detailed turn ----------------------------------------------------------------


def test_detailed_turn_reports_every_tool_call(tmp_path: pathlib.Path) -> None:
    """Calls arrive batched in one AIMessage, so counting must not stop at the last (ADR-053).

    Args:
        tmp_path: Pytest temporary directory.
    """
    state = _state(tool_calls=["get_order_status", "search_knowledge_base"])
    turn = _service(_StubAgent(state), tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.tools_invoked == ["get_order_status", "search_knowledge_base"]


def test_detailed_turn_exposes_the_retrieved_contexts(tmp_path: pathlib.Path) -> None:
    """RAGAS scores faithfulness against the chunk texts (SPEC 10.2).

    Args:
        tmp_path: Pytest temporary directory.
    """
    turn = _service(_StubAgent(_state()), tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.retrieved_contexts == ["estratto"]
    assert turn.retrieved[0].doc_id == BULBS


def test_detailed_turn_is_not_flagged_as_fallback_when_the_model_answered(
    tmp_path: pathlib.Path,
) -> None:
    """A normal turn must not make the API advertise a provider failure.

    Args:
        tmp_path: Pytest temporary directory.
    """
    turn = _service(_StubAgent(_state()), tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.fallback is False


# --- provider failure -----------------------------------------------------------------


def test_provider_failure_yields_a_courteous_answer(tmp_path: pathlib.Path) -> None:
    """A customer must never receive a stack trace (SPEC 11).

    Args:
        tmp_path: Pytest temporary directory.
    """
    agent = _StubAgent(error=RuntimeError("provider irraggiungibile"))
    turn = _service(agent, tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.response.answer == FALLBACK_ANSWER
    assert turn.fallback is True


def test_provider_failure_routes_to_a_human(tmp_path: pathlib.Path) -> None:
    """A turn that failed outright should reach a person.

    Args:
        tmp_path: Pytest temporary directory.
    """
    agent = _StubAgent(error=RuntimeError("boom"))
    turn = _service(agent, tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.response.needs_human is True
    assert turn.response.confidence == "low"
    assert turn.response.sources == []


def test_missing_structured_response_is_flagged_as_fallback(tmp_path: pathlib.Path) -> None:
    """The iteration limit ends the run without one (ADR-050).

    Args:
        tmp_path: Pytest temporary directory.
    """
    state = {"messages": [HumanMessage(content="q")], "structured_response": None}
    turn = _service(_StubAgent(state), tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert turn.fallback is True
    assert turn.response.answer == FALLBACK_ANSWER


# --- needs_human ----------------------------------------------------------------------


def test_needs_human_reads_the_session_register(tmp_path: pathlib.Path) -> None:
    """Session-scoped: true for the rest of the conversation once a ticket exists (ADR-008).

    Args:
        tmp_path: Pytest temporary directory.
    """
    register = EscalationsRepository(tmp_path / "escalations.jsonl")
    service = _service(_StubAgent(_state()), register=register, tmp=tmp_path)

    assert service.chat("domanda", "sess-1").needs_human is False

    import datetime as dt

    register.create("sess-1", "complaint", "reclamo", None, dt.date(2026, 10, 12))
    assert service.chat("altra domanda", "sess-1").needs_human is True
    assert service.chat("domanda", "sess-2").needs_human is False


# --- session reset --------------------------------------------------------------------


def test_reset_session_forgets_the_conversation(tmp_path: pathlib.Path) -> None:
    """DELETE /sessions/{id} must actually clear the thread (SPEC 11).

    Args:
        tmp_path: Pytest temporary directory.
    """
    agent = _StubAgent(_state())
    _service(agent, tmp=tmp_path).reset_session("sess-1")
    assert agent.checkpointer.deleted == ["sess-1"]


def test_reset_session_tolerates_a_checkpointer_without_deletion(
    tmp_path: pathlib.Path,
) -> None:
    """A future checkpointer lacking the method must not crash the endpoint.

    Args:
        tmp_path: Pytest temporary directory.
    """
    agent = _StubAgent(_state())
    agent.checkpointer = object()  # type: ignore[assignment]
    _service(agent, tmp=tmp_path).reset_session("sess-1")


# --- the deterministic layer is not bypassed ------------------------------------------


def test_invented_citation_is_filtered_by_the_service(tmp_path: pathlib.Path) -> None:
    """Everything goes through here, so ADR-002 cannot be bypassed by a caller.

    Args:
        tmp_path: Pytest temporary directory.
    """
    state = _state(cited=["policies/inesistente.md"])
    response = _service(_StubAgent(state), tmp=tmp_path).chat("domanda", "sess-1")
    assert "policies/inesistente.md" not in response.sources
    assert response.sources == [BULBS]


def test_confidence_is_capped_by_the_service(tmp_path: pathlib.Path) -> None:
    """The cap applies here too, not only in the layer below.

    Args:
        tmp_path: Pytest temporary directory.
    """
    state = _state(confidence="high")
    state["messages"][2] = _kb_message(score=0.74)
    response = _service(_StubAgent(state), tmp=tmp_path).chat("domanda", "sess-1")
    assert response.confidence == "low"


def test_chat_turn_is_immutable(tmp_path: pathlib.Path) -> None:
    """A completed turn is a record of what happened, not a mutable buffer.

    Args:
        tmp_path: Pytest temporary directory.
    """
    turn = _service(_StubAgent(_state()), tmp=tmp_path).chat_detailed("domanda", "sess-1")
    assert isinstance(turn, ChatTurn)
    with pytest.raises((AttributeError, TypeError)):
        turn.fallback = True  # type: ignore[misc]
