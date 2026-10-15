"""Wiring the two judges, in one place.

Both judges bypass LiteLLM and talk to OpenRouter's OpenAI-compatible endpoint directly,
so both need the provider's own model slug without the ``openrouter/`` route prefix
(ADR-033). They need it in different shapes, though — RAGAS takes a client object, DeepEval
reads the ambient environment — and that difference is the whole reason this module exists:
the shared part is the base URL, the key and the slug, and duplicating those across two
metric modules is how they come to disagree.

Importing this module has a deliberate side effect: it opts out of DeepEval's telemetry
before DeepEval can be imported anywhere (ADR-018, ADR-024). A delivery notebook must not
upload evaluation results to a third-party service without whoever runs it knowing.
"""

from __future__ import annotations

import os

# Read at import time by deepeval, so it has to be set before any deepeval import. Setting
# it here, rather than in each metric module, means no module can forget it.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from greenthumb.config import Settings, get_settings  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class MissingProviderKeyError(RuntimeError):
    """Raised when the evaluation is started without a provider key."""


def judge_slug_and_key(settings: Settings | None = None) -> tuple[str, str]:
    """Resolve the judge's model slug and the provider key.

    The judge model is validated here rather than at import of the package, so that the
    delivery notebook runs with the agent's secret alone (ADR-010).

    Args:
        settings: Runtime configuration; read from the environment when omitted.

    Returns:
        The provider slug and the API key.

    Raises:
        MissingProviderKeyError: If no provider key is configured.
    """
    settings = settings or get_settings()
    settings.require_eval_model()
    if settings.openai_api_key is None:
        raise MissingProviderKeyError(
            "Serve OPENAI_API_KEY per eseguire i giudici dell'evaluation. "
            "Impostala nel .env in locale, oppure nei Secrets su Colab."
        )
    return settings.judge_model_slug, settings.openai_api_key.get_secret_value()


def build_ragas_judge(settings: Settings | None = None, cache_dir: str | None = None):  # noqa: ANN201
    """Build the judge RAGAS metrics take in their constructor.

    Args:
        settings: Runtime configuration; read from the environment when omitted.
        cache_dir: When given, cache judge responses on disk there. Re-scoring the same
            traces then costs nothing, which matters in phase 7 where the evaluation runs
            twice around one corrective change (ADR-023).

    Returns:
        A RAGAS LLM wrapper, as ``ragas.metrics.collections`` metrics require.
    """
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    slug, key = judge_slug_and_key(settings)
    client = AsyncOpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)
    if cache_dir is None:
        return llm_factory(slug, provider="openai", client=client)

    from ragas.cache import DiskCacheBackend

    return llm_factory(
        slug, provider="openai", client=client, cache=DiskCacheBackend(cache_dir=cache_dir)
    )


def configure_deepeval(settings: Settings | None = None) -> str:
    """Point DeepEval at OpenRouter and return the judge slug.

    DeepEval builds its own OpenAI client from the environment rather than accepting one,
    so the endpoint is configured by setting the two variables its client reads.

    Args:
        settings: Runtime configuration; read from the environment when omitted.

    Returns:
        The provider slug to pass as each metric's ``model``, which DeepEval accepts as a
        plain string (ADR-024): with OpenAI-compatible endpoints no wrapper is needed.
    """
    slug, key = judge_slug_and_key(settings)
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_BASE_URL"] = OPENROUTER_BASE_URL
    return slug
