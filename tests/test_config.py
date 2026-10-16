"""Tests for the configuration layer."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from greenthumb.config import REPO_ROOT, MissingEvalModelError, Settings


def _settings(**overrides: object) -> Settings:
    """Build a Settings instance that ignores any local .env file.

    Args:
        **overrides: Field values to set explicitly.

    Returns:
        A Settings instance built only from the given overrides and the declared defaults.
    """
    return Settings(_env_file=None, **overrides)


def test_defaults_match_the_specification() -> None:
    """Defaults must reflect the approved decisions, not incidental values."""
    settings = _settings()
    assert settings.today == dt.date(2026, 10, 12)  # ADR-003
    assert settings.agent_max_iterations == 8  # ADR-012
    assert settings.summary_trigger_tokens == 6000  # ADR-004, ricalibrato in ADR-056/072
    assert settings.summary_keep_messages == 6
    assert settings.retrieval_top_k == 4
    assert settings.embedding_model == "intfloat/multilingual-e5-base"  # ADR-005


def test_retrieval_thresholds_are_the_calibrated_values() -> None:
    """Phase 2 measured these on the real corpus; see docs/RETRIEVAL_CALIBRATION.md."""
    settings = _settings()
    assert settings.retrieval_score_low == 0.813
    assert settings.retrieval_score_high == 0.863
    assert settings.retrieval_score_low < settings.retrieval_score_high


def test_project_variables_are_read_with_the_greenthumb_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project variables must carry the prefix that protects them on Colab (ADR-013).

    Args:
        monkeypatch: Pytest fixture used to set environment variables.
    """
    monkeypatch.setenv("GREENTHUMB_LLM_MODEL", "openai/some-model")
    monkeypatch.setenv("GREENTHUMB_AGENT_MAX_ITERATIONS", "11")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "openai/some-model"
    assert settings.agent_max_iterations == 11


def test_provider_key_is_read_without_a_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider key keeps the unprefixed name its SDK imposes.

    Args:
        monkeypatch: Pytest fixture used to set environment variables.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-value")
    settings = Settings(_env_file=None)
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test-value"


def test_provider_key_is_not_leaked_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secret must never appear in logs or tracebacks through a plain repr.

    Args:
        monkeypatch: Pytest fixture used to set environment variables.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-do-not-print")
    assert "sk-secret-do-not-print" not in repr(Settings(_env_file=None))


def test_high_threshold_below_low_threshold_is_rejected() -> None:
    """An inverted threshold pair is a configuration error, not something to tolerate."""
    with pytest.raises(ValidationError, match="retrieval_score_high"):
        _settings(retrieval_score_low=0.8, retrieval_score_high=0.5)


def test_require_eval_model_raises_when_unset() -> None:
    """The judge model is validated lazily, but strictly when it is actually needed."""
    with pytest.raises(MissingEvalModelError, match="GREENTHUMB_EVAL_MODEL"):
        _settings().require_eval_model()


def test_require_eval_model_returns_the_configured_model() -> None:
    """A configured judge model must be returned unchanged."""
    assert _settings(eval_model="openai/judge").require_eval_model() == "openai/judge"


def test_importing_settings_does_not_require_a_judge_model() -> None:
    """Building Settings must stay cheap and total, so the notebook runs with one secret."""
    assert _settings().eval_model == ""


def test_clock_is_pinned_to_the_configured_business_date() -> None:
    """The clock must follow configuration, never the wall clock."""
    settings = _settings(today=dt.date(2027, 3, 1))
    assert settings.clock().today() == dt.date(2027, 3, 1)


def test_derived_paths_sit_under_the_repository_root() -> None:
    """Every path is relative to the repo root, so Colab checkouts work unchanged."""
    settings = _settings()
    for path in (
        settings.data_dir,
        settings.kb_dir,
        settings.orders_path,
        settings.vector_store_dir,
        settings.escalations_path,
    ):
        assert path.is_absolute()
        assert REPO_ROOT in path.parents or path.parent == REPO_ROOT


def test_settings_ignore_a_leaked_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not inherit local configuration, however it reaches the environment.

    Regression guard for ADR-025: importing deepeval calls load_dotenv(), which injected
    the real .env into os.environ and silently made these tests depend on it.

    Args:
        monkeypatch: Pytest fixture used to simulate the leak.
    """
    monkeypatch.setenv("GREENTHUMB_EVAL_MODEL", "leaked/from-dotenv")
    # The isolated_environment fixture ran before this line, so a genuine leak from a
    # plugin at import time would already be gone; an explicit set must still be visible,
    # which proves the fixture strips rather than freezes the environment.
    assert Settings(_env_file=None).eval_model == "leaked/from-dotenv"


def test_output_cap_has_a_conservative_default() -> None:
    """Every call needs an explicit cap, or OpenRouter refuses it with a 402 (ADR-031)."""
    assert _settings().max_output_tokens == 1024


def test_output_cap_rejects_an_absurd_value() -> None:
    """A cap high enough to reproduce the 402 is a configuration error."""
    with pytest.raises(ValidationError, match="max_output_tokens"):
        _settings(max_output_tokens=65536)


def test_judge_slug_strips_the_litellm_route_prefix() -> None:
    """RAGAS and DeepEval call the provider directly, where the route prefix is not a model."""
    settings = _settings(eval_model="openrouter/openai/gpt-4.1")
    assert settings.eval_model == "openrouter/openai/gpt-4.1"
    assert settings.judge_model_slug == "openai/gpt-4.1"


def test_judge_slug_is_a_no_op_without_a_route_prefix() -> None:
    """A plain identifier must pass through untouched, so a provider switch stays safe."""
    assert _settings(eval_model="openai/gpt-4.1").judge_model_slug == "openai/gpt-4.1"


def test_zero_low_threshold_is_rejected() -> None:
    """A zero threshold accepts everything, silently disabling the relevance filter.

    Regression guard: a .env copied before the phase-2 calibration kept the 0.0
    placeholder and overrode the calibrated default with no visible symptom.
    """
    with pytest.raises(ValidationError, match="0.813"):
        _settings(retrieval_score_low=0.0)


def test_env_can_still_override_with_a_real_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tuning the threshold must stay possible; only the disabling value is refused.

    Args:
        monkeypatch: Fixture used to set environment variables.
    """
    monkeypatch.setenv("GREENTHUMB_RETRIEVAL_SCORE_LOW", "0.75")
    monkeypatch.setenv("GREENTHUMB_RETRIEVAL_SCORE_HIGH", "0.90")
    settings = Settings(_env_file=None)
    assert settings.retrieval_score_low == 0.75
    assert settings.retrieval_score_high == 0.90


def test_summary_trigger_is_the_calibrated_value() -> None:
    """Measured twice, not estimated.

    Phase 5 measured the request floor, which rules out the original 2500: it fires on
    every call. Phase 7 measured the *growth* and found ~600 tokens per turn rather than
    the ~1000 assumed, so 8000 landed around the twelfth turn and summarization never fired
    in the whole evaluation (ADR-072).
    """
    assert _settings().summary_trigger_tokens == 6000


def test_summary_trigger_below_the_measured_floor_is_rejected() -> None:
    """A trigger under the request floor makes summarization run before every call."""
    with pytest.raises(ValidationError, match="ADR-056"):
        _settings(summary_trigger_tokens=2500)


def test_a_higher_summary_trigger_is_allowed() -> None:
    """Tuning upward stays free; only the pathological range is refused."""
    assert _settings(summary_trigger_tokens=20000).summary_trigger_tokens == 20000
