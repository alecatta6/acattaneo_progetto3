"""Exercise the three tools individually, nominal cases and edge cases.

This is the phase-3 Definition of Done — every tool invocable on its own, without an agent
and without a single LLM call — and it is reused as the tool demo of the delivery notebook
(SPEC section 13, point 5).

The escalation register is written to a temporary file rather than the real
``escalations.jsonl``: running the demo twice must not accumulate tickets, or the notebook
output would change on every execution and ticket numbering would stop being reproducible.

Run with: uv run python scripts/demo_tools.py
"""

from __future__ import annotations

import pathlib
import tempfile
from typing import Any

from langchain_core.tools import StructuredTool

from greenthumb.clock import FrozenClock, season_of
from greenthumb.config import get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.orders_repository import OrdersRepository
from greenthumb.retrieval import open_index
from greenthumb.tools.escalation_tool import make_escalation_tool
from greenthumb.tools.knowledge_base_tool import make_knowledge_base_tool
from greenthumb.tools.order_status_tool import make_order_status_tool

WIDTH = 96
EXCERPT = 500


def _heading(title: str) -> None:
    """Print a section heading.

    Args:
        title: The section title.
    """
    print(f"\n{'=' * WIDTH}\n{title}\n{'=' * WIDTH}")


def _case(label: str) -> None:
    """Print a case label.

    Args:
        label: What this invocation demonstrates.
    """
    print(f"\n--- {label} ---")


def _show(content: str, artifact: dict[str, Any], limit: int = EXCERPT) -> None:
    """Print a tool result, truncating long content.

    Args:
        content: The text the model would read.
        artifact: The structured record the response layer would read.
        limit: How many characters of content to show.
    """
    text = content if len(content) <= limit else content[:limit] + "\n[...]"
    print(text)
    print(f"\n  artifact: {artifact}")


def _call(tool: StructuredTool, session: str | None = None, **arguments: Any) -> None:
    """Invoke a tool the way the agent does and print both halves of the result.

    Args:
        tool: The tool to invoke.
        session: Session identifier, for tools that read it from the runtime config.
        **arguments: The tool arguments.
    """
    config = {"configurable": {"thread_id": session}} if session else None
    message = tool.invoke(
        {"name": tool.name, "args": arguments, "id": "demo", "type": "tool_call"},
        config=config,
    )
    _show(message.content, message.artifact)


def demo_order_status(tool: StructuredTool) -> None:
    """Demonstrate the order status tool.

    Args:
        tool: The configured order status tool.
    """
    _heading("1. get_order_status — stato di un ordine")

    _case("caso nominale: l'esempio della traccia, con le date gia' calcolate")
    _call(tool, order_id="1042")

    _case("normalizzazione: il cliente non scrive mai un numero nudo")
    _call(tool, order_id="Ordine n. 1042")

    _case("caso limite: reso di un deperibile, con i giorni trascorsi precalcolati")
    _call(
        tool,
        order_id="1054",
    )

    _case("caso limite: ordine inesistente")
    _call(tool, order_id="9999")

    _case("caso limite: nessun numero nel testo")
    _call(tool, order_id="il mio ordine")

    _case("caso limite: due numeri, il tool non sceglie al posto del cliente")
    _call(tool, order_id="1042 e 1055")


def demo_knowledge_base(tool: StructuredTool) -> None:
    """Demonstrate the knowledge base search tool.

    Args:
        tool: The configured knowledge base tool.
    """
    _heading("2. search_knowledge_base — ricerca semantica sulla knowledge base")

    _case("caso nominale: domanda agronomica")
    _call(tool, query="Quando si piantano i bulbi di tulipano?")

    _case("filtro per tipo di documento: solo policy")
    _call(tool, query="Entro quanto tempo posso restituire delle sementi?", doc_type="policy")

    _case("caso limite: domanda fuori tema — la soglia deve rifiutare")
    _call(tool, query="Qual e' la capitale del Giappone?")

    _case("caso limite: query vuota")
    _call(tool, query="")


def demo_escalation(tool: StructuredTool) -> None:
    """Demonstrate the escalation tool.

    Args:
        tool: The configured escalation tool.
    """
    _heading("3. escalate_to_human — passaggio a un operatore")

    _case("caso nominale: rimborso fuori dai termini di policy")
    _call(
        tool,
        session="demo-cliente-1",
        reason="refund_exception",
        summary=(
            "Il cliente chiede il rimborso dei bulbi dell'ordine 1054, consegnato 41 giorni "
            "fa. I deperibili hanno un termine di 14 giorni. Chiede un'eccezione."
        ),
        order_id="1054",
    )

    _case("idempotenza: stesso motivo, stessa sessione -> nessun secondo ticket")
    _call(
        tool,
        session="demo-cliente-1",
        reason="refund_exception",
        summary="Il cliente insiste sulla stessa richiesta.",
        order_id="1054",
    )

    _case("motivo diverso, stessa sessione -> secondo ticket legittimo")
    _call(
        tool,
        session="demo-cliente-1",
        reason="customer_request",
        summary="Il cliente chiede esplicitamente di parlare con un operatore.",
    )

    _case("altra sessione, stesso motivo -> ticket proprio")
    _call(
        tool,
        session="demo-cliente-2",
        reason="refund_exception",
        summary="Un altro cliente con una richiesta analoga.",
    )

    _case("caso safety: rinvio immediato a un professionista")
    _call(
        tool,
        session="demo-cliente-3",
        reason="safety",
        summary="Il cane del cliente ha ingerito bulbi di narciso.",
    )


def main() -> int:
    """Build the three tools and run every demonstration.

    Returns:
        0 on success, 1 when the vector store has not been built yet.
    """
    settings = get_settings()
    today = settings.today

    print(f"Business date simulata: {today.isoformat()} (stagione: {season_of(today)})")
    print(
        f"Soglie di retrieval: low={settings.retrieval_score_low} "
        f"high={settings.retrieval_score_high}"
    )

    if not settings.vector_store_dir.exists():
        print("\nIndice non trovato. Eseguire prima: make index")
        return 1

    clock = FrozenClock(today)
    orders = OrdersRepository.from_file(settings.orders_path)
    store = open_index(settings.vector_store_dir, settings.embedding_model)

    # A temporary register keeps ticket numbering reproducible across runs.
    with tempfile.TemporaryDirectory(prefix="gt_demo_") as directory:
        register = EscalationsRepository(pathlib.Path(directory) / "escalations.jsonl")

        demo_order_status(make_order_status_tool(orders, clock))
        demo_knowledge_base(
            make_knowledge_base_tool(store, settings.retrieval_top_k, settings.retrieval_score_low)
        )
        demo_escalation(make_escalation_tool(register, clock))

    print(f"\n{'=' * WIDTH}")
    print("Tutti e tre i tool sono stati invocati singolarmente, senza agente e senza LLM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
