"""Spike 5b/6b: run the RAGAS and DeepEval judges for real through OpenRouter.

The introspection spikes checked the APIs; this one checks the wiring, which turned out
to be the subtle part. Both judges bypass LiteLLM and talk to OpenRouter's
OpenAI-compatible endpoint directly, so they need the provider's own model slug without
the ``openrouter/`` route prefix that LiteLLM requires (ADR-033).

Roughly four LLM calls.
"""

from __future__ import annotations

import asyncio
import os

# Must be set before deepeval is imported anywhere: the flag is read at import time, and
# importing deepeval also calls load_dotenv() as a side effect (ADR-025).
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

from greenthumb.config import get_settings  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CONTEXTS = [
    "I bulbi di tulipano si piantano da ottobre a novembre, in terreno ben drenato, "
    "a una profondita' pari a circa tre volte l'altezza del bulbo."
]
QUESTION = "Quando si piantano i bulbi di tulipano?"
ANSWER = "I bulbi di tulipano si piantano tra ottobre e novembre, in terreno ben drenato."


def run_ragas(judge_slug: str, api_key: str) -> None:
    """Score one sample with RAGAS Faithfulness.

    Args:
        judge_slug: The provider's model slug, without the LiteLLM route prefix.
        api_key: The OpenRouter key.
    """
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecisionWithReference, Faithfulness

    client = AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
    judge = llm_factory(judge_slug, provider="openai", client=client)

    faithfulness = Faithfulness(llm=judge)
    result = asyncio.run(
        faithfulness.ascore(user_input=QUESTION, response=ANSWER, retrieved_contexts=CONTEXTS)
    )
    print(f"  Faithfulness                 -> {result}")

    precision = ContextPrecisionWithReference(llm=judge)
    result2 = asyncio.run(
        precision.ascore(user_input=QUESTION, reference=ANSWER, retrieved_contexts=CONTEXTS)
    )
    print(f"  ContextPrecisionWithReference -> {result2}")


def run_deepeval(judge_slug: str, api_key: str) -> None:
    """Score one sample with DeepEval AnswerRelevancy and GEval.

    Args:
        judge_slug: The provider's model slug, without the LiteLLM route prefix.
        api_key: The OpenRouter key.
    """
    # DeepEval builds its own OpenAI client from the ambient environment.
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = OPENROUTER_BASE_URL

    from deepeval.metrics import AnswerRelevancyMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    case = LLMTestCase(input=QUESTION, actual_output=ANSWER, retrieval_context=CONTEXTS)

    relevancy = AnswerRelevancyMetric(model=judge_slug)
    relevancy.measure(case)
    print(f"  AnswerRelevancy -> {relevancy.score}")

    geval = GEval(
        name="Correttezza escalation",
        criteria=(
            "La risposta riconosce i limiti di policy applicabili e, se il caso esce dai "
            "termini, comunica con chiarezza che un operatore umano lo prendera' in carico."
        ),
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=judge_slug,
    )
    escalation_case = LLMTestCase(
        input="Voglio essere rimborsato per dei bulbi comprati due mesi fa.",
        actual_output=(
            "I bulbi non sono rimborsabili oltre 14 giorni dalla consegna. Ho aperto il "
            "ticket ESC-0001: un operatore la contattera' entro un giorno lavorativo."
        ),
    )
    geval.measure(escalation_case)
    print(f"  GEval           -> {geval.score}")
    print(f"  GEval reason    -> {str(geval.reason)[:180]}")


def main() -> None:
    """Run both judges and report their scores."""
    settings = get_settings()
    judge_slug = settings.judge_model_slug
    api_key = settings.openai_api_key.get_secret_value()
    print(f"judge (LiteLLM form) : {settings.eval_model}")
    print(f"judge (provider slug): {judge_slug}\n")

    print("== RAGAS ==")
    run_ragas(judge_slug, api_key)

    print("\n== DeepEval ==")
    run_deepeval(judge_slug, api_key)


if __name__ == "__main__":
    main()
