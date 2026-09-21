"""Spike 1: can structured output and tool artifacts coexist in create_agent?

This is the highest-risk assumption in the whole design. SPEC section 5 wants both:

* the agent returns a Pydantic object (answer, proposed_confidence, cited_sources), and
* response.py reads each tool's metadata from the ToolMessage ``artifact`` of the turn,
  so that ``sources`` can be intersected with what retrieval really returned (ADR-002).

If the structured-output step hides the ToolMessages, or if it is itself a tool call that
pollutes the tool-selection metric and burns an iteration, the deterministic layer needs a
different design. One real LLM call.
"""

from __future__ import annotations

import inspect
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel, Field

from greenthumb.config import get_settings

# The key in .env is an OpenRouter key, so the model identifier needs the openrouter/ route.
SPIKE_MODEL = "openrouter/openai/gpt-4.1-mini"
# The key has a spending cap; LiteLLM otherwise requests 65536 output tokens and gets a 402.
MAX_TOKENS = 1024


class AgentOutput(BaseModel):
    """What the LLM is asked to produce, before the deterministic layer runs."""

    answer: str = Field(description="Risposta al cliente, in italiano.")
    proposed_confidence: Literal["high", "medium", "low"] = Field(
        description="Quanto il modello si ritiene sicuro della risposta."
    )
    # No default: OpenAI's strict JSON schema requires every property to appear in
    # "required", so an optional field makes the whole request invalid. See ADR-026.
    cited_sources: list[str] = Field(
        description="doc_id dei documenti effettivamente usati; lista vuota se nessuno."
    )


@tool(response_format="content_and_artifact")
def search_knowledge_base(query: str) -> tuple[str, list[dict[str, object]]]:
    """Cerca informazioni su prodotti, guide di coltivazione e policy del negozio.

    Args:
        query: La domanda riformulata in modo autonomo.

    Returns:
        A tuple of the text shown to the model and the structured artifact for the
        deterministic layer.
    """
    content = (
        "[guides/bulbi_autunnali.md] I bulbi di tulipano si piantano da ottobre a novembre.\n"
        "[policies/resi.md] I bulbi non sono rimborsabili dopo 14 giorni dalla consegna."
    )
    artifact = [
        {"doc_id": "guides/bulbi_autunnali.md", "score": 0.91, "chunk_id": "c1"},
        {"doc_id": "policies/resi.md", "score": 0.84, "chunk_id": "c7"},
    ]
    return content, artifact


def main() -> None:
    """Run the spike and report exactly what the agent returns."""
    settings = get_settings()
    print(f"create_agent{inspect.signature(create_agent)}\n")
    if not settings.llm_model.startswith("openrouter/"):
        print(
            f"NOTE: overriding GREENTHUMB_LLM_MODEL={settings.llm_model!r} "
            f"with {SPIKE_MODEL!r} (the key in .env is an OpenRouter key).\n"
        )

    llm = ChatLiteLLM(
        model=SPIKE_MODEL,
        temperature=0,
        api_key=settings.openai_api_key.get_secret_value(),
        max_tokens=MAX_TOKENS,
    )
    agent = create_agent(
        model=llm,
        tools=[search_knowledge_base],
        system_prompt=(
            "Sei l'assistente di GreenThumb. Usa sempre il tool per informazioni su prodotti, "
            "guide e policy. Cita i doc_id che hai realmente usato."
        ),
        response_format=AgentOutput,
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content="Posso piantare i bulbi di tulipano adesso?")]}
    )

    print("== result keys ==")
    print(" ", list(result.keys()))

    print("\n== structured response ==")
    structured = result.get("structured_response")
    print("  type :", type(structured).__name__)
    print("  value:", structured)

    print("\n== message trace ==")
    tool_messages: list[ToolMessage] = []
    ai_tool_calls: list[dict[str, object]] = []
    for i, msg in enumerate(result["messages"]):
        kind = type(msg).__name__
        extra = ""
        if isinstance(msg, AIMessage) and msg.tool_calls:
            extra = f" tool_calls={[tc['name'] for tc in msg.tool_calls]}"
            ai_tool_calls.extend(msg.tool_calls)
        if isinstance(msg, ToolMessage):
            tool_messages.append(msg)
            extra = f" name={msg.name!r} has_artifact={msg.artifact is not None}"
        print(f"  [{i}] {kind}{extra}")

    print("\n== THE critical question: are artifacts readable? ==")
    for tm in tool_messages:
        print(f"  {tm.name}: artifact = {tm.artifact}")
    print(f"  ToolMessages found: {len(tool_messages)}")

    print("\n== does structured output cost an iteration? ==")
    names = [tc["name"] for tc in ai_tool_calls]
    print("  all tool calls made:", names)
    print("  real tool calls    :", [n for n in names if n == "search_knowledge_base"])
    print("  extra calls        :", [n for n in names if n != "search_knowledge_base"])
    print(f"  total messages     : {len(result['messages'])}")


if __name__ == "__main__":
    main()
