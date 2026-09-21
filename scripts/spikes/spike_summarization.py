"""Spike 3: does the summarization middleware preserve the entities we care about?

SPEC section 9 chose summarization over trimming because customer care conversations refer
back to entities mentioned many turns earlier ("e quello di prima?"). This checks the real
API shape and, more importantly, whether an order number from turn 1 survives a
summarization and is still usable afterwards.

The trigger is set absurdly low so the middleware fires after a couple of short turns,
keeping the spike cheap. Roughly five LLM calls.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: F401
from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.memory import InMemorySaver

from greenthumb.config import get_settings

SPIKE_MODEL = "openrouter/openai/gpt-4.1-mini"
MAX_TOKENS = 400

# A message-count trigger is deterministic: a token trigger of 250 did NOT fire on a
# four-turn conversation, which made the first run of this spike inconclusive.
TRIGGER = ("messages", 4)
KEEP_MESSAGES = 2

# The stock prompt is written for a coding agent (SESSION INTENT / ARTIFACTS / NEXT STEPS)
# and would discard exactly what customer care needs. This is the replacement SPEC 9 asks for.
CUSTOMER_CARE_SUMMARY_PROMPT = """Riassumi la conversazione fra un cliente e l'assistente di
GreenThumb. Il riassunto sostituira' i messaggi originali, quindi deve conservare
OBBLIGATORIAMENTE, se presenti:

- ogni numero d'ordine citato;
- ogni prodotto o SKU discusso;
- eventuali escalation aperte, con il loro ticket_id;
- preferenze e vincoli espressi dal cliente (es. "coltivo sul balcone", "non ho giardino");
- le domande del cliente rimaste senza risposta.

Scrivi in italiano, in forma sintetica. Rispondi SOLO con il riassunto.

<messages>
{messages}
</messages>"""

TURNS = [
    "Buongiorno, ho un problema con l'ordine 1042.",
    "Coltivo solo sul balcone, in vaso, e ho poco sole diretto.",
    "Mi interessano i bulbi di tulipano, sono adatti al vaso?",
    "Senti, ricordami: qual era il numero del mio ordine?",
]


def main() -> None:
    """Run a conversation long enough to trigger summarization and inspect the result."""
    settings = get_settings()
    llm = ChatLiteLLM(
        model=SPIKE_MODEL,
        temperature=0,
        api_key=settings.openai_api_key.get_secret_value(),
        max_tokens=MAX_TOKENS,
    )
    agent = create_agent(
        model=llm,
        tools=[],
        system_prompt="Sei l'assistente di GreenThumb. Rispondi in italiano, molto brevemente.",
        middleware=[
            SummarizationMiddleware(
                model=llm,
                trigger=TRIGGER,
                keep=("messages", KEEP_MESSAGES),
                summary_prompt=CUSTOMER_CARE_SUMMARY_PROMPT,
            )
        ],
        checkpointer=InMemorySaver(),
    )

    config = {"configurable": {"thread_id": "spike-session"}}
    for i, text in enumerate(TURNS, start=1):
        result = agent.invoke({"messages": [HumanMessage(content=text)]}, config)
        messages = result["messages"]
        last = messages[-1]
        reply = last.content if isinstance(last, AIMessage) else str(last.content)
        print(f"--- turno {i} ---")
        print(f"  utente : {text}")
        print(f"  agente : {reply.strip()[:220]}")
        print(
            f"  messaggi in stato: {len(messages)}  tipi: {[type(m).__name__[0] for m in messages]}"
        )
        system_like = [m for m in messages if isinstance(m, SystemMessage)]
        if system_like:
            print(f"  RIASSUNTO PRESENTE ({len(system_like)} SystemMessage):")
            for sm in system_like:
                print(f"    {str(sm.content)[:400]}")
        print()

    print("== dove finisce il riassunto? stato finale completo ==")
    state = agent.get_state(config).values
    for i, m in enumerate(state["messages"]):
        print(f"  [{i}] {type(m).__name__}:")
        print(f"      {str(m.content)[:700]}")
    print("\n  chiavi di stato:", list(state.keys()))


if __name__ == "__main__":
    main()
