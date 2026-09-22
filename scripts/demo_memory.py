"""Demonstrate short-term memory: a conversation that outgrows its context.

This is the memory demonstration the delivery notebook needs (SPEC section 13, point 7),
and the visible proof of why summarization was chosen over trimming (ADR-004): an order
number mentioned in the first turn is still usable several turns later, after the original
messages have been replaced.

The trigger is lowered from the production value so the threshold is crossed in a handful
of turns. With 2500 tokens a realistic conversation takes much longer to get there, and
every extra turn is a paid call.

Run with: uv run python scripts/demo_memory.py
"""

from __future__ import annotations

import logging
import pathlib
import tempfile

from langchain_core.messages import HumanMessage

from greenthumb.agent import build_agent, build_chat_model, build_tools
from greenthumb.config import get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.memory import build_summarization_middleware, find_summary
from greenthumb.orders_repository import OrdersRepository
from greenthumb.retrieval import open_index

WIDTH = 96
# The trigger must sit comfortably ABOVE the token size of what is retained, or the
# middleware summarises again on the very next model call and keeps doing so, paying for an
# extra LLM call each time. Measured on this knowledge base: four retained messages run to
# roughly 700-1000 tokens, dominated by the retrieved chunks in the ToolMessages (ADR-055).
DEMO_TRIGGER_TOKENS = 1500
DEMO_KEEP_MESSAGES = 4

CONVERSATION = (
    "Buongiorno, ho un problema con l'ordine 1042.",
    "Coltivo solo sul balcone, in vaso, e ho pochissimo sole diretto.",
    "Mi interessano i bulbi di tulipano: sono adatti alla coltivazione in vaso?",
    "Quanto costa la spedizione per un ordine piccolo?",
)
RECALL = "Senta, mi ricorda qual era il numero del mio ordine?"


def _configure_logging() -> None:
    """Route the summarization log line to the console, and nothing else."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("    >>> %(message)s"))
    memory_logger = logging.getLogger("greenthumb.memory")
    memory_logger.setLevel(logging.INFO)
    memory_logger.addHandler(handler)
    memory_logger.propagate = False


def main() -> int:
    """Run the conversation and show what memory preserved.

    Returns:
        0 on success, 1 when the vector store has not been built.
    """
    settings = get_settings()
    if not settings.vector_store_dir.exists():
        print("Indice non trovato. Eseguire prima: make index")
        return 1

    _configure_logging()
    settings = settings.model_copy(
        update={
            "summary_trigger_tokens": DEMO_TRIGGER_TOKENS,
            "summary_keep_messages": DEMO_KEEP_MESSAGES,
        }
    )
    clock = settings.clock()
    model = build_chat_model(settings)

    with tempfile.TemporaryDirectory(prefix="gt_memory_demo_") as directory:
        tools = build_tools(
            settings=settings,
            clock=clock,
            orders=OrdersRepository.from_file(settings.orders_path),
            escalations=EscalationsRepository(pathlib.Path(directory) / "escalations.jsonl"),
            store=open_index(settings.vector_store_dir, settings.embedding_model),
        )
        agent = build_agent(
            model=model,
            tools=tools,
            clock=clock,
            max_iterations=settings.agent_max_iterations,
            extra_middleware=[build_summarization_middleware(model, settings)],
        )

        print(
            f"Soglia di summarization abbassata a {DEMO_TRIGGER_TOKENS} token "
            f"(in produzione: {get_settings().summary_trigger_tokens})."
        )
        print("=" * WIDTH)

        config = {"configurable": {"thread_id": "demo-memoria"}}
        state: dict = {}
        for number, message in enumerate(CONVERSATION, start=1):
            print(f"\n[turno {number}] cliente: {message}")
            state = agent.invoke({"messages": [HumanMessage(content=message)]}, config)
            answer = state["structured_response"].answer
            print(f"           agente : {' '.join(answer.split())[:160]}")
            print(f"           stato  : {len(state['messages'])} messaggi")

        print(f"\n{'=' * WIDTH}\nRIASSUNTO CHE HA SOSTITUITO I MESSAGGI\n{'=' * WIDTH}")
        print(find_summary(state["messages"]) or "(nessun riassunto prodotto)")

        print(f"\n{'=' * WIDTH}\nLA PROVA\n{'=' * WIDTH}")
        print(f"[turno {len(CONVERSATION) + 1}] cliente: {RECALL}")
        final = agent.invoke({"messages": [HumanMessage(content=RECALL)]}, config)
        answer = final["structured_response"].answer
        print(f"           agente : {' '.join(answer.split())}")
        print()
        print(
            "Il numero d'ordine del primo turno e' ancora utilizzabile: "
            f"{'SI' if '1042' in answer else 'NO'}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
