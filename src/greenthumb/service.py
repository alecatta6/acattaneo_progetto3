"""The public entry point: one turn in, one ChatResponse out.

Everything above this line — the API, the evaluation runner, the notebook — goes through
here, so the deterministic assembly cannot be bypassed or reimplemented differently by one
of them.

Three consumers with three appetites, served by two methods. :meth:`ChatService.chat` is
the contract the assignment asks for and returns exactly the four fields. The API and the
evaluation need more: whether the reply was a fallback, so the API can set ``X-Fallback``
(ADR-009), and which chunks were retrieved with their text, so RAGAS can score faithfulness
against real contexts (SPEC section 10.2). :meth:`ChatService.chat_detailed` returns those
alongside the response, rather than making each caller dig them out of the raw state.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from greenthumb.agent import (
    build_chat_model,
    build_default_agent,
    fallback_output,
    is_fallback_output,
)
from greenthumb.clock import Clock
from greenthumb.config import Settings, get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.memory import build_summarization_middleware, summarization_occurred
from greenthumb.response import (
    RetrievedChunk,
    TurnEvidence,
    build_chat_response,
    extract_turn_evidence,
    messages_of_current_turn,
    output_from_state,
)
from greenthumb.schemas import ChatResponse

logger = logging.getLogger(__name__)


def new_session_id() -> str:
    """Mint an identifier for a conversation.

    Returns:
        A fresh session identifier, used as the checkpointer's thread key.
    """
    return f"sess-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class ChatTurn:
    """One completed turn, with everything its three consumers need.

    Attributes:
        response: The four-field contract returned to the customer.
        session_id: The conversation this turn belongs to.
        tools_invoked: Every tool called during the turn, in order.
        retrieved: The chunks retrieval returned above the threshold.
        fallback: Whether the reply came from the fallback rather than the model.
        summarization_fired: Whether the conversation has been summarised.
    """

    response: ChatResponse
    session_id: str
    tools_invoked: list[str] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    fallback: bool = False
    summarization_fired: bool = False

    @property
    def retrieved_contexts(self) -> list[str]:
        """Return the chunk texts, in the shape RAGAS expects.

        Returns:
            One string per retrieved chunk.
        """
        return [chunk.text for chunk in self.retrieved if chunk.text]


def _tools_invoked(messages: Sequence[BaseMessage]) -> list[str]:
    """Collect every tool called during the turn.

    Tool calls arrive batched: the model routinely emits two in a single ``AIMessage``
    (ADR-053), so reading only the last message would undercount them.

    Args:
        messages: The messages of the current turn.

    Returns:
        The tool names, in call order.
    """
    return [
        call["name"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in (message.tool_calls or [])
    ]


class ChatService:
    """Runs one conversation turn and assembles its response."""

    def __init__(
        self,
        agent: Any,
        escalations: EscalationsRepository,
        settings: Settings,
    ) -> None:
        """Bind the service to an agent and a register.

        Args:
            agent: The compiled agent.
            escalations: The escalation register, which decides ``needs_human`` (ADR-008).
            settings: The runtime configuration supplying the retrieval thresholds.
        """
        self._agent = agent
        self._escalations = escalations
        self._settings = settings

    def chat(self, message: str, session_id: str) -> ChatResponse:
        """Run one turn and return the four-field contract.

        Args:
            message: What the customer wrote.
            session_id: The conversation identifier, used as the checkpointer thread key.

        Returns:
            The response.
        """
        return self.chat_detailed(message, session_id).response

    def chat_detailed(self, message: str, session_id: str) -> ChatTurn:
        """Run one turn and return the response along with what produced it.

        A provider failure is caught here rather than escaping towards a customer: the turn
        yields the courteous fallback with ``needs_human`` set, and the caller learns it was
        a fallback so the API can say so in a header (SPEC section 11, ADR-009).

        Args:
            message: What the customer wrote.
            session_id: The conversation identifier.

        Returns:
            The completed turn.
        """
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = self._agent.invoke({"messages": [HumanMessage(content=message)]}, config)
        except Exception:
            logger.exception("Il provider ha fallito durante la sessione %s", session_id)
            return self._fallback_turn(session_id)

        messages = state.get("messages") or []
        turn_messages = messages_of_current_turn(messages)
        evidence = extract_turn_evidence(messages)
        output = output_from_state(state)

        response = build_chat_response(
            output=output,
            evidence=evidence,
            needs_human=self._escalations.has_open_tickets(session_id),
            score_low=self._settings.retrieval_score_low,
            score_high=self._settings.retrieval_score_high,
        )
        return ChatTurn(
            response=response,
            session_id=session_id,
            tools_invoked=_tools_invoked(turn_messages),
            retrieved=evidence.retrieved,
            # Covers both a missing structured response and one that failed to parse.
            fallback=is_fallback_output(output),
            summarization_fired=summarization_occurred(messages),
        )

    def reset_session(self, session_id: str) -> None:
        """Forget a conversation.

        Args:
            session_id: The conversation to delete.
        """
        checkpointer = getattr(self._agent, "checkpointer", None)
        if checkpointer is not None and hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(session_id)

    def _fallback_turn(self, session_id: str) -> ChatTurn:
        """Build the turn returned when the provider could not be reached.

        Args:
            session_id: The conversation identifier.

        Returns:
            A turn carrying the fallback reply, flagged as such.
        """
        response = build_chat_response(
            output=fallback_output(),
            evidence=TurnEvidence(),
            # A customer whose turn failed outright should reach a person, whatever the
            # register says about this session so far.
            needs_human=True,
            score_low=self._settings.retrieval_score_low,
            score_high=self._settings.retrieval_score_high,
        )
        return ChatTurn(response=response, session_id=session_id, fallback=True)


def build_chat_service(
    settings: Settings | None = None,
    clock: Clock | None = None,
    with_memory: bool = True,
    escalations: EscalationsRepository | None = None,
) -> ChatService:
    """Build the production service, wiring every dependency from configuration.

    Args:
        settings: The runtime configuration; read from the environment when omitted.
        clock: The business-date source; built from configuration when omitted.
        with_memory: Whether to attach the summarization middleware.
        escalations: The escalation register, shared between the tool that writes tickets
            and the service that reads them (ADR-060); built from configuration when
            omitted.

    Returns:
        The service, ready to answer.
    """
    settings = settings or get_settings()
    clock = clock or settings.clock()

    # One model instance, shared by the agent and by the summarization middleware, and
    # one register, shared by the escalation tool and by this service.
    model = build_chat_model(settings)
    register = escalations or EscalationsRepository(settings.escalations_path)
    extra: list[Any] = []
    if with_memory:
        extra.append(build_summarization_middleware(model, settings))

    agent = build_default_agent(
        settings=settings,
        clock=clock,
        extra_middleware=extra,
        model=model,
        escalations=register,
    )
    return ChatService(agent=agent, escalations=register, settings=settings)
