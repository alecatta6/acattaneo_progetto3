"""Spike 2: verify ChatLiteLLM against the configured provider.

Two real LLM calls: one plain, one with a bound tool. This is the cheapest check that the
credentials, the model identifier and the tool-calling path all work, so it runs before the
more elaborate structured-output spike.
"""

from __future__ import annotations

import inspect

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_litellm import ChatLiteLLM

from greenthumb.config import get_settings


@tool
def get_plant_watering_days(plant: str) -> int:
    """Return how many days to wait between waterings for a plant.

    Args:
        plant: The common name of the plant.

    Returns:
        The number of days between waterings.
    """
    return 3


def main() -> None:
    """Run the spike and print what the provider actually returns."""
    settings = get_settings()
    print(f"model: {settings.llm_model}")
    print(f"ChatLiteLLM.__init__{inspect.signature(ChatLiteLLM.__init__)}\n")

    llm = ChatLiteLLM(model=settings.llm_model, temperature=0)

    print("== call 1: plain ==")
    reply = llm.invoke([HumanMessage(content="Rispondi con una sola parola: capitale d'Italia?")])
    print("  type    :", type(reply).__name__)
    print("  content :", repr(reply.content))
    print("  usage   :", reply.usage_metadata)

    print("\n== call 2: with a bound tool ==")
    bound = llm.bind_tools([get_plant_watering_days])
    reply2 = bound.invoke(
        [HumanMessage(content="Ogni quanti giorni devo annaffiare il basilico? Usa il tool.")]
    )
    print("  content    :", repr(reply2.content))
    print("  tool_calls :", reply2.tool_calls)
    print("  usage      :", reply2.usage_metadata)

    print("\n== structured output strategy probe ==")
    print("  bind_tools present :", hasattr(llm, "bind_tools"))
    print("  with_structured_output present :", hasattr(llm, "with_structured_output"))
    if hasattr(llm, "with_structured_output"):
        print(f"  with_structured_output{inspect.signature(llm.with_structured_output)}")


if __name__ == "__main__":
    main()
