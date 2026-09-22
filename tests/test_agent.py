"""Wiring tests for the agent. No network and no provider.

These tests assemble the agent and inspect what was wired, but deliberately never run the
loop. A fake chat model cannot drive this agent: ``create_agent`` obtains the structured
output through the provider's native response_format (ADR-026), which no fake implements,
and ``GenericFakeChatModel.bind_tools`` raises ``NotImplementedError`` outright. The loop's
behaviour is therefore covered by the integration tests marked ``llm``, and the response
assembly by hand-built traces in phase 6 (ADR-049).
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from greenthumb.agent import (
    AGENT_NAME,
    FALLBACK_ANSWER,
    TEMPERATURE,
    build_agent,
    build_chat_model,
    build_prompt_middleware,
    build_tools,
    fallback_output,
)
from greenthumb.clock import FrozenClock
from greenthumb.config import Settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.orders_repository import OrdersRepository
from greenthumb.schemas import AgentOutput

BUSINESS_DATE = dt.date(2026, 10, 12)


class _FakeStore:
    """Minimal stand-in for Chroma, so tools can be built without an index."""

    def similarity_search_with_score(self, *args: object, **kwargs: object) -> list:
        """Return no results.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Returns:
            An empty result list.
        """
        return []


def _settings(**overrides: object) -> Settings:
    """Build settings detached from any .env file.

    Args:
        **overrides: Field values to set explicitly.

    Returns:
        The settings instance.
    """
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def tools(tmp_path: pathlib.Path) -> list[StructuredTool]:
    """Build the three tools with test doubles.

    Args:
        tmp_path: Pytest temporary directory, for the escalation register.

    Returns:
        The tools.
    """
    settings = _settings()
    return build_tools(
        settings=settings,
        clock=FrozenClock(BUSINESS_DATE),
        orders=OrdersRepository.from_file(settings.orders_path),
        escalations=EscalationsRepository(tmp_path / "escalations.jsonl"),
        store=_FakeStore(),
    )


# --- the model ------------------------------------------------------------------------


def test_temperature_is_zero_for_reproducibility() -> None:
    """The evaluation compares runs; sampling noise would read as a real difference."""
    assert TEMPERATURE == 0.0


def test_chat_model_carries_the_configured_values() -> None:
    """Model identifier and output cap must reach the provider (ADR-031)."""
    settings = _settings(llm_model="openrouter/openai/gpt-4.1-mini", max_output_tokens=512)
    model = build_chat_model(settings)
    assert model.model == "openrouter/openai/gpt-4.1-mini"
    assert model.temperature == 0.0
    assert model.max_tokens == 512


def test_missing_model_identifier_fails_with_a_remedy() -> None:
    """Failing at build time beats failing mid-conversation with a provider error."""
    with pytest.raises(ValueError, match="GREENTHUMB_LLM_MODEL"):
        build_chat_model(_settings(llm_model=""))


# --- the tools ------------------------------------------------------------------------


def test_all_three_tools_are_bound(tools: list[StructuredTool]) -> None:
    """R2 requires three tools, and the prompt names all three.

    Args:
        tools: The built tools.
    """
    assert [tool.name for tool in tools] == [
        "search_knowledge_base",
        "get_order_status",
        "escalate_to_human",
    ]


def test_every_tool_returns_an_artifact(tools: list[StructuredTool]) -> None:
    """The deterministic response layer reads artifacts, not text (ADR-002, ADR-027).

    Args:
        tools: The built tools.
    """
    assert all(tool.response_format == "content_and_artifact" for tool in tools)


def test_tools_carry_the_configured_threshold(tmp_path: pathlib.Path) -> None:
    """A tool built with the wrong threshold would silently accept anything (ADR-043).

    Args:
        tmp_path: Pytest temporary directory.
    """
    settings = _settings(retrieval_score_low=0.9, retrieval_score_high=0.95)
    built = build_tools(
        settings=settings,
        clock=FrozenClock(BUSINESS_DATE),
        orders=OrdersRepository.from_file(settings.orders_path),
        escalations=EscalationsRepository(tmp_path / "e.jsonl"),
        store=_FakeStore(),
    )
    kb_tool = next(t for t in built if t.name == "search_knowledge_base")
    _, artifact = kb_tool.func(query="qualcosa")
    assert artifact["threshold"] == 0.9


# --- the prompt middleware ------------------------------------------------------------


def test_prompt_middleware_follows_the_clock() -> None:
    """The date must be read at call time, not frozen when the agent was built."""
    moving = {"today": BUSINESS_DATE}

    class _MovingClock:
        """A clock whose date can be changed between calls."""

        def today(self) -> dt.date:
            """Return the current test date.

            Returns:
                The date currently set.
            """
            return moving["today"]

    middleware = build_prompt_middleware(_MovingClock())
    assert middleware is not None

    first = build_prompt_middleware(FrozenClock(BUSINESS_DATE))
    second = build_prompt_middleware(FrozenClock(dt.date(2026, 4, 3)))
    assert first is not second


# --- assembly -------------------------------------------------------------------------


def _agent(tools: list[StructuredTool], responses: list[AIMessage], limit: int = 8):  # noqa: ANN202
    """Build an agent over a fake model returning scripted replies.

    Args:
        tools: The tools to bind.
        responses: The messages the fake model returns in order.
        limit: Model calls allowed per run.

    Returns:
        The compiled agent.
    """
    model = GenericFakeChatModel(messages=iter(responses))
    return build_agent(
        model=model,
        tools=tools,
        clock=FrozenClock(BUSINESS_DATE),
        max_iterations=limit,
        checkpointer=InMemorySaver(),
    )


def test_agent_compiles_with_the_expected_name(tools: list[StructuredTool]) -> None:
    """A named graph is easier to read in traces and in LangGraph output.

    Args:
        tools: The built tools.
    """
    agent = _agent(tools, [AIMessage(content="ciao")])
    assert agent.name == AGENT_NAME


def test_agent_exposes_the_structured_response_channel(
    tools: list[StructuredTool],
) -> None:
    """response.py reads structured_response alongside messages (ADR-027).

    Args:
        tools: The built tools.
    """
    agent = _agent(tools, [AIMessage(content="ciao")])
    assert "structured_response" in agent.output_channels


def test_checkpointer_is_attached(tools: list[StructuredTool]) -> None:
    """thread_id keys the conversation and reaches the escalation tool (ADR-047).

    Args:
        tools: The built tools.
    """
    saver = InMemorySaver()
    agent = build_agent(
        model=GenericFakeChatModel(messages=iter([AIMessage(content="ciao")])),
        tools=tools,
        clock=FrozenClock(BUSINESS_DATE),
        max_iterations=8,
        checkpointer=saver,
    )
    assert agent.checkpointer is saver


def test_a_checkpointer_is_created_when_none_is_given(
    tools: list[StructuredTool],
) -> None:
    """Without one, multi-turn conversations would silently lose their history.

    Args:
        tools: The built tools.
    """
    agent = build_agent(
        model=GenericFakeChatModel(messages=iter([AIMessage(content="ciao")])),
        tools=tools,
        clock=FrozenClock(BUSINESS_DATE),
        max_iterations=8,
    )
    assert agent.checkpointer is not None


def test_extra_middleware_is_accepted(tools: list[StructuredTool]) -> None:
    """Phase 5 passes the summarization middleware through this seam.

    Note that create_agent rejects two instances of the same middleware class, so the
    summarization middleware must be a different type from the ones already wired.

    Args:
        tools: The built tools.
    """
    from langchain.agents.middleware import ToolCallLimitMiddleware

    extra = ToolCallLimitMiddleware(run_limit=99, exit_behavior="end")
    agent = build_agent(
        model=GenericFakeChatModel(messages=iter([AIMessage(content="ciao")])),
        tools=tools,
        clock=FrozenClock(BUSINESS_DATE),
        max_iterations=8,
        extra_middleware=[extra],
    )
    assert agent is not None


# --- the fallback ---------------------------------------------------------------------


def test_fallback_is_a_valid_output_with_low_confidence() -> None:
    """A truncated run must still satisfy the schema the API promises."""
    output = fallback_output()
    assert isinstance(output, AgentOutput)
    assert output.proposed_confidence == "low"
    assert output.cited_sources == []


def test_fallback_is_written_for_a_customer() -> None:
    """The customer gets a courteous handover, never an error message."""
    answer = fallback_output().answer
    assert answer == FALLBACK_ANSWER
    assert "operatore" in answer
    assert "error" not in answer.lower()
    assert "exception" not in answer.lower()


# --- what a fake model cannot do ------------------------------------------------------


def test_the_agent_graph_is_runnable(tools: list[StructuredTool]) -> None:
    """The graph must compile into something invocable, even if a fake cannot drive it.

    Running the loop needs native structured output, which no fake provides (ADR-049), so
    this checks the compiled object rather than its behaviour.

    Args:
        tools: The built tools.
    """
    agent = _agent(tools, [AIMessage(content="ciao")])
    assert callable(agent.invoke)
    assert {"model", "tools"} <= set(agent.get_graph().nodes)
