"""Single source of configuration for the whole system.

No module reads ``os.environ`` directly: everything goes through :class:`Settings`, loaded
from ``.env`` locally and from exported Colab Secrets on Colab. Project variables carry the
``GREENTHUMB_`` prefix to avoid collisions in Colab's shared environment (ADR-013); the
provider key keeps the name its SDK imposes.
"""

from __future__ import annotations

import datetime as dt
import functools
import pathlib

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from greenthumb.clock import Clock, FrozenClock

# src/greenthumb/config.py -> src/greenthumb -> src -> repository root
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_BUSINESS_DATE = dt.date(2026, 10, 12)


class MissingEvalModelError(RuntimeError):
    """Raised when the evaluation is started without a judge model configured."""


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    Attributes are documented inline via ``Field`` descriptions. Retrieval thresholds
    default to 0.0 because they are calibrated empirically in phase 2 (see docs/PLAN.md):
    a guessed threshold is worse than an obviously unset one.
    """

    model_config = SettingsConfigDict(
        env_prefix="GREENTHUMB_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Models ---
    llm_model: str = Field(default="", description="LiteLLM identifier of the agent model.")
    eval_model: str = Field(
        default="",
        description="LiteLLM identifier of the judge model. Validated lazily (ADR-010).",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="Provider key. Unprefixed: the name is imposed by the SDK.",
    )

    # --- Business date (ADR-003) ---
    today: dt.date = Field(
        default=DEFAULT_BUSINESS_DATE,
        description="Simulated business date, so the system stays reproducible over time.",
    )

    # --- Retrieval ---
    embedding_model: str = Field(default="intfloat/multilingual-e5-base")
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    # Calibrated in phase 2 on the real knowledge base; see docs/retrieval_calibration.md
    # and ADR-040. Expressed as cosine similarity, 1 - distance (ADR-021).
    retrieval_score_low: float = Field(
        default=0.813,
        ge=0.0,
        le=1.0,
        description="Below this, no document counts as relevant.",
    )
    retrieval_score_high: float = Field(
        default=0.864,
        ge=0.0,
        le=1.0,
        description="At or above this, retrieval quality allows high confidence.",
    )

    # --- Short-term memory (ADR-004) ---
    summary_trigger_tokens: int = Field(default=2500, ge=200)
    summary_keep_messages: int = Field(default=6, ge=2)

    # --- Agent ---
    agent_max_iterations: int = Field(default=8, ge=1, le=30)
    max_output_tokens: int = Field(
        default=1024,
        ge=64,
        le=8192,
        description="Explicit output cap on every model call. Without one LiteLLM requests "
        "65536 tokens and OpenRouter rejects the call with 402 (ADR-031).",
    )

    @field_validator("retrieval_score_high")
    @classmethod
    def _high_not_below_low(cls, value: float, info) -> float:  # noqa: ANN001
        """Reject a high threshold that sits below the low one.

        Args:
            value: The candidate high threshold.
            info: Pydantic validation context, carrying the already-validated fields.

        Returns:
            The validated high threshold.

        Raises:
            ValueError: If the high threshold is below the low one.
        """
        low = info.data.get("retrieval_score_low")
        if low is not None and value < low:
            raise ValueError(
                f"retrieval_score_high ({value}) must not be below retrieval_score_low ({low})"
            )
        return value

    # --- Derived paths ---
    @property
    def data_dir(self) -> pathlib.Path:
        """Return the directory holding the catalogue, knowledge base and orders.

        Returns:
            Absolute path to ``data/``.
        """
        return REPO_ROOT / "data"

    @property
    def kb_dir(self) -> pathlib.Path:
        """Return the knowledge base root.

        Returns:
            Absolute path to ``data/kb/``.
        """
        return self.data_dir / "kb"

    @property
    def orders_path(self) -> pathlib.Path:
        """Return the generated orders file.

        Returns:
            Absolute path to ``data/orders.json``.
        """
        return self.data_dir / "orders.json"

    @property
    def vector_store_dir(self) -> pathlib.Path:
        """Return the persistent Chroma directory.

        Returns:
            Absolute path to ``vector_store/``, which is not versioned.
        """
        return REPO_ROOT / "vector_store"

    @property
    def escalations_path(self) -> pathlib.Path:
        """Return the escalation ticket log.

        Returns:
            Absolute path to ``escalations.jsonl``, which is not versioned.
        """
        return REPO_ROOT / "escalations.jsonl"

    @property
    def judge_model_slug(self) -> str:
        """Return the judge model in the form the provider's own API expects.

        The project carries two forms of the same identifier. LiteLLM, which drives the
        agent, needs a route prefix (``openrouter/openai/gpt-4.1``). RAGAS and DeepEval
        bypass LiteLLM and talk to the OpenAI-compatible endpoint directly, where that
        prefix is not a model and the call fails. See ADR-033.

        Returns:
            The judge model identifier without the LiteLLM route prefix.
        """
        return self.eval_model.removeprefix("openrouter/")

    # --- Behaviour ---
    def clock(self) -> Clock:
        """Build the clock for the configured business date.

        Returns:
            A :class:`~greenthumb.clock.FrozenClock` pinned to :attr:`today`.
        """
        return FrozenClock(self.today)

    def require_eval_model(self) -> str:
        """Return the judge model, failing loudly if it is not configured.

        Called only when the evaluation actually runs, never at import time, so that the
        delivery notebook can load saved results with a single secret configured (ADR-010).

        Returns:
            The LiteLLM identifier of the judge model.

        Raises:
            MissingEvalModelError: If no judge model is configured.
        """
        if not self.eval_model.strip():
            raise MissingEvalModelError(
                "GREENTHUMB_EVAL_MODEL is not set. The evaluation needs a judge model distinct "
                "from the agent model, so that the agent does not grade its own answers "
                "(ADR-010). Set it in .env, or in Colab Secrets, and run again."
            )
        return self.eval_model


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Cached so that the environment is read once. Tests that need a different environment
    should call ``get_settings.cache_clear()`` or construct :class:`Settings` directly.

    Returns:
        The shared :class:`Settings` instance.
    """
    return Settings()
