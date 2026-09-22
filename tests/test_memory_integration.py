"""Memory tests against a real provider. Marked ``llm`` and excluded from `make test`.

The one lesson these tests exist to honour: a memory test that only checks an entity
survived proves nothing. On a short conversation the entity survives because nothing was
summarised. Every test here asserts that summarization actually fired *and* that what had
to survive did (ADR-028).

The trigger is lowered from the production value so the threshold is crossed within a few
turns. What is under test is the mechanism, not the number: with 2500 tokens a realistic
conversation takes far longer to get there, and each extra turn costs a call.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from greenthumb.agent import build_agent, build_chat_model, build_tools
from greenthumb.clock import FrozenClock
from greenthumb.config import REPO_ROOT, Settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.memory import build_summarization_middleware, find_summary, summarization_occurred
from greenthumb.orders_repository import OrdersRepository
from greenthumb.retrieval import open_index

pytestmark = pytest.mark.llm

BUSINESS_DATE = dt.date(2026, 10, 12)

# Low enough that a few short turns cross it; the production value is 8000. Applied with
# model_copy, which does not re-run the validator that refuses this value in production.
TEST_TRIGGER_TOKENS = 3500
TEST_KEEP_MESSAGES = 4

# Each turn introduces something that has to survive the summary.
CONVERSATION = (
    "Buongiorno, ho un problema con l'ordine 1042.",
    "Coltivo solo sul balcone, in vaso, e ho pochissimo sole diretto.",
    "Mi interessano i bulbi di tulipano: sono adatti alla coltivazione in vaso?",
    "Quanto costa la spedizione per un ordine piccolo?",
)
RECALL_QUESTION = "Senta, mi ricorda qual era il numero del mio ordine?"


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    """Read the real configuration, bypassing the suite's isolation.

    Returns:
        The settings built from the project's .env file, with the test thresholds applied.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        pytest.skip(".env assente: i test di integrazione richiedono un provider configurato")
    settings = Settings(_env_file=env_file)
    if not settings.llm_model.strip() or settings.openai_api_key is None:
        pytest.skip("modello o chiave non configurati")
    if not settings.vector_store_dir.exists():
        pytest.skip("indice non costruito: eseguire `make index`")
    return settings.model_copy(
        update={
            "summary_trigger_tokens": TEST_TRIGGER_TOKENS,
            "summary_keep_messages": TEST_KEEP_MESSAGES,
        }
    )


@pytest.fixture(scope="module")
def conversation(
    live_settings: Settings, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Any]:
    """Run one long conversation once and share its result across assertions.

    Args:
        live_settings: The real configuration with lowered memory thresholds.
        tmp_path_factory: Pytest factory for module-scoped temporary directories.

    Returns:
        A dictionary with the message counts per turn, the final state and the recall answer.
    """
    register = tmp_path_factory.mktemp("escalations") / "escalations.jsonl"
    clock = FrozenClock(BUSINESS_DATE)
    model = build_chat_model(live_settings)
    tools = build_tools(
        settings=live_settings,
        clock=clock,
        orders=OrdersRepository.from_file(live_settings.orders_path),
        escalations=EscalationsRepository(pathlib.Path(register)),
        store=open_index(live_settings.vector_store_dir, live_settings.embedding_model),
    )
    agent = build_agent(
        model=model,
        tools=tools,
        clock=clock,
        max_iterations=live_settings.agent_max_iterations,
        extra_middleware=[build_summarization_middleware(model, live_settings)],
    )

    config = {"configurable": {"thread_id": "memory-test"}}
    counts: list[int] = []
    state: dict[str, Any] = {}
    for message in CONVERSATION:
        state = agent.invoke({"messages": [HumanMessage(content=message)]}, config)
        counts.append(len(state["messages"]))

    recall = agent.invoke({"messages": [HumanMessage(content=RECALL_QUESTION)]}, config)
    return {
        "counts": counts,
        "state": state,
        "recall": recall,
        "recall_answer": recall["structured_response"].answer,
    }


# --- the trigger actually fired -------------------------------------------------------


def test_summarization_fired(conversation: dict[str, Any]) -> None:
    """Without this assertion every other memory test is vacuous (ADR-028).

    Args:
        conversation: The shared conversation result.
    """
    assert summarization_occurred(conversation["recall"]["messages"]), (
        "la summarization non e' scattata: il resto del test non dimostrerebbe nulla"
    )


def test_message_count_stops_growing(conversation: dict[str, Any]) -> None:
    """Summarization exists to bound the context, so the list must stop expanding.

    Args:
        conversation: The shared conversation result.
    """
    counts = conversation["counts"]
    assert max(counts) < 2 * len(CONVERSATION) + 2, f"i messaggi crescono senza limite: {counts}"


# --- what had to survive --------------------------------------------------------------


def test_order_number_from_the_first_turn_is_still_usable(
    conversation: dict[str, Any],
) -> None:
    """The whole reason for choosing summarization over trimming (ADR-004).

    Args:
        conversation: The shared conversation result.
    """
    assert "1042" in conversation["recall_answer"], conversation["recall_answer"]


def test_summary_preserves_the_order_number(conversation: dict[str, Any]) -> None:
    """The entity must be in the summary itself, not merely in a surviving message.

    Args:
        conversation: The shared conversation result.
    """
    summary = find_summary(conversation["recall"]["messages"])
    assert summary is not None
    assert "1042" in summary, summary


def test_summary_preserves_the_customer_constraint(
    conversation: dict[str, Any],
) -> None:
    """A balcony with little sun changes every piece of advice that follows (SPEC 9).

    Args:
        conversation: The shared conversation result.
    """
    summary = (find_summary(conversation["recall"]["messages"]) or "").lower()
    assert any(word in summary for word in ("balcone", "vaso", "sole")), summary


def test_summary_is_written_in_italian(conversation: dict[str, Any]) -> None:
    """An English summary inside an Italian conversation invites English answers.

    Args:
        conversation: The shared conversation result.
    """
    summary = (find_summary(conversation["recall"]["messages"]) or "").lower()
    assert any(word in summary for word in ("cliente", "ordine", "il ", "la ")), summary


def test_returned_summary_has_no_english_preamble(
    conversation: dict[str, Any],
) -> None:
    """The preamble is the library's, and has no place in a log or a notebook demo.

    Args:
        conversation: The shared conversation result.
    """
    summary = find_summary(conversation["recall"]["messages"])
    assert summary is not None
    assert not summary.startswith("Here is a summary")
