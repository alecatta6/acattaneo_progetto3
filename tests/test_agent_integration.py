"""Integration tests against a real provider. Marked ``llm`` and excluded from `make test`.

These are the only tests that spend money, so they are written to get the most out of each
call: every one exercises a behaviour that cannot be checked without a real model, and the
assertions target structure — which tools ran, what the deterministic fields say — rather
than exact wording, which would make them brittle against a model that is free to phrase
its answer differently.

The test suite is deliberately detached from the developer's .env (ADR-044), so these tests
re-attach explicitly through the ``live_settings`` fixture rather than relying on ambient
configuration.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from greenthumb.agent import build_agent, build_chat_model, build_tools
from greenthumb.clock import FrozenClock
from greenthumb.config import REPO_ROOT, Settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.orders_repository import OrdersRepository
from greenthumb.retrieval import open_index
from greenthumb.schemas import AgentOutput

pytestmark = pytest.mark.llm

BUSINESS_DATE = dt.date(2026, 10, 12)


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    """Read the real configuration, bypassing the suite's isolation.

    Returns:
        The settings built from the project's .env file.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        pytest.skip(".env assente: i test di integrazione richiedono un provider configurato")
    settings = Settings(_env_file=env_file)
    if not settings.llm_model.strip() or settings.openai_api_key is None:
        pytest.skip("modello o chiave non configurati")
    if not settings.vector_store_dir.exists():
        pytest.skip("indice non costruito: eseguire `make index`")
    return settings


@pytest.fixture(scope="module")
def agent(live_settings: Settings, tmp_path_factory: pytest.TempPathFactory):  # noqa: ANN201
    """Build the real agent once for the whole module.

    The escalation register is temporary: integration tests must not append tickets to the
    developer's real one, and ticket numbering stays predictable.

    Args:
        live_settings: The real configuration.
        tmp_path_factory: Pytest factory for module-scoped temporary directories.

    Returns:
        The compiled agent.
    """
    register = tmp_path_factory.mktemp("escalations") / "escalations.jsonl"
    clock = FrozenClock(BUSINESS_DATE)
    tools = build_tools(
        settings=live_settings,
        clock=clock,
        orders=OrdersRepository.from_file(live_settings.orders_path),
        escalations=EscalationsRepository(pathlib.Path(register)),
        store=open_index(live_settings.vector_store_dir, live_settings.embedding_model),
    )
    return build_agent(
        model=build_chat_model(live_settings),
        tools=tools,
        clock=clock,
        max_iterations=live_settings.agent_max_iterations,
    )


def _ask(agent: Any, message: str) -> dict[str, Any]:
    """Run one turn in a fresh session and summarise what happened.

    Args:
        agent: The compiled agent.
        message: The customer's message.

    Returns:
        A dictionary with the structured output, the tools invoked, their artifacts and
        the raw messages.
    """
    session = f"test-{uuid.uuid4().hex[:8]}"
    state = agent.invoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": session}},
    )
    messages = state["messages"]
    tool_calls = [
        call["name"]
        for message_ in messages
        if isinstance(message_, AIMessage)
        for call in message_.tool_calls
    ]
    artifacts = [m.artifact for m in messages if isinstance(m, ToolMessage) and m.artifact]
    return {
        "output": state.get("structured_response"),
        "tools": tool_calls,
        "artifacts": artifacts,
        "messages": messages,
        "session": session,
    }


def _artifact_for(result: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    """Find the artifact produced by a given tool.

    Args:
        result: The dictionary returned by :func:`_ask`.
        tool_name: The tool whose artifact is wanted.

    Returns:
        The artifact, or None when the tool did not run.
    """
    for artifact in result["artifacts"]:
        if isinstance(artifact, dict) and artifact.get("tool") == tool_name:
            return artifact
    return None


# --- the assignment's own example -----------------------------------------------------


@pytest.fixture(scope="module")
def traccia_result(agent: Any) -> dict[str, Any]:
    """Run the example from the assignment once and share it across assertions.

    Args:
        agent: The compiled agent.

    Returns:
        The summarised turn.
    """
    return _ask(
        agent,
        "Quando arriva l'ordine 1042? Posso piantare adesso i bulbi di tulipano?",
    )


def test_assignment_example_uses_both_tools(traccia_result: dict[str, Any]) -> None:
    """The question spans an order and the knowledge base, so it needs both (SPEC 8).

    Args:
        traccia_result: The summarised turn.
    """
    assert "get_order_status" in traccia_result["tools"]
    assert "search_knowledge_base" in traccia_result["tools"]


def test_assignment_example_produces_a_valid_structured_output(
    traccia_result: dict[str, Any],
) -> None:
    """Every turn must yield the schema the API contract promises.

    Args:
        traccia_result: The summarised turn.
    """
    output = traccia_result["output"]
    assert isinstance(output, AgentOutput)
    assert output.answer.strip()
    assert output.proposed_confidence in {"high", "medium", "low"}


def test_assignment_example_answers_the_delivery_question(
    traccia_result: dict[str, Any],
) -> None:
    """Part one: the parcel is due the day after the business date.

    Args:
        traccia_result: The summarised turn.
    """
    answer = traccia_result["output"].answer.lower()
    assert "domani" in answer or "13 ottobre" in answer or "2026-10-13" in answer


def test_assignment_example_answers_the_planting_question(
    traccia_result: dict[str, Any],
) -> None:
    """Part two: mid-October is inside the planting window, so the answer is yes.

    Args:
        traccia_result: The summarised turn.
    """
    answer = traccia_result["output"].answer.lower()
    assert any(word in answer for word in ("piantare", "mettere a dimora", "piantarli"))
    assert any(word in answer for word in ("ottobre", "novembre", "autunno", "adesso", "ora"))


def test_assignment_example_cites_a_real_document(
    traccia_result: dict[str, Any],
) -> None:
    """Citations must name documents retrieval actually returned (ADR-002).

    Args:
        traccia_result: The summarised turn.
    """
    retrieved = {
        entry["doc_id"]
        for artifact in traccia_result["artifacts"]
        if isinstance(artifact, dict) and artifact.get("tool") == "search_knowledge_base"
        for entry in artifact.get("results", [])
    }
    assert retrieved, "il retrieval non ha restituito nulla sopra soglia"
    cited = set(traccia_result["output"].cited_sources)
    assert cited & retrieved, f"citate {cited}, recuperate {retrieved}"


def test_assignment_example_does_not_escalate(traccia_result: dict[str, Any]) -> None:
    """A question the agent can answer must not open a ticket.

    Args:
        traccia_result: The summarised turn.
    """
    assert "escalate_to_human" not in traccia_result["tools"]


def test_assignment_example_hides_internal_details(
    traccia_result: dict[str, Any],
) -> None:
    """SPEC 8, point 7: the customer reads an answer, not the machinery.

    Args:
        traccia_result: The summarised turn.
    """
    answer = traccia_result["output"].answer.lower()
    for leak in ("search_knowledge_base", "get_order_status", "chunk", "similarit"):
        assert leak not in answer


# --- escalation -----------------------------------------------------------------------


def test_explicit_request_for_a_human_escalates(agent: Any) -> None:
    """The customer asking for a person is the clearest escalation criterion.

    Args:
        agent: The compiled agent.
    """
    result = _ask(agent, "Non voglio parlare con un bot, mi passi un operatore umano.")
    assert "escalate_to_human" in result["tools"]
    artifact = _artifact_for(result, "escalate_to_human")
    assert artifact is not None
    assert artifact["reason"] == "customer_request"
    assert artifact["ticket_id"].startswith("ESC-")


# --- out of scope ---------------------------------------------------------------------


def test_out_of_scope_question_is_refused_without_a_ticket(agent: Any) -> None:
    """SPEC 8: out of scope is a polite refusal, never an escalation.

    Args:
        agent: The compiled agent.
    """
    result = _ask(agent, "Mi consiglia un buon ristorante di pesce a Milano?")
    assert "escalate_to_human" not in result["tools"], (
        "una domanda fuori ambito non deve aprire un ticket"
    )
    answer = result["output"].answer.lower()
    assert any(word in answer for word in ("giardinaggio", "greenthumb", "non posso", "mi occupo"))


# --- ambiguity ------------------------------------------------------------------------


def test_missing_order_number_is_asked_for(agent: Any) -> None:
    """SPEC 8, point 5: ask before acting, rather than guessing an order.

    Args:
        agent: The compiled agent.
    """
    result = _ask(agent, "Buongiorno, quando arriva il mio ordine?")
    answer = result["output"].answer.lower()
    assert "numero" in answer, f"non ha chiesto il numero d'ordine: {answer!r}"
    artifact = _artifact_for(result, "get_order_status")
    assert artifact is None or artifact["found"] is False, (
        "non deve inventare un ordine quando il numero manca"
    )
