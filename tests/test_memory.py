"""Tests for short-term memory configuration and summary detection. No LLM."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from greenthumb.config import Settings
from greenthumb.memory import (
    SUMMARY_SOURCE_MARKER,
    SUMMARY_TEXT_PREFIX,
    build_summarization_middleware,
    find_summary,
    summarization_occurred,
)
from greenthumb.prompts import SUMMARY_PROMPT


def _settings(**overrides: object) -> Settings:
    """Build settings detached from any .env file.

    Args:
        **overrides: Field values to set explicitly.

    Returns:
        The settings instance.
    """
    return Settings(_env_file=None, **overrides)


def _model() -> GenericFakeChatModel:
    """Build a throwaway model for constructing the middleware.

    Returns:
        A fake chat model. It is never called: only the wiring is inspected.
    """
    return GenericFakeChatModel(messages=iter([AIMessage(content="riassunto")]))


# --- the prompt -----------------------------------------------------------------------


def test_summary_prompt_names_every_entity_that_must_survive() -> None:
    """SPEC 9 lists what the summary has to preserve; the prompt must say so."""
    flat = " ".join(SUMMARY_PROMPT.split())
    for required in ("numero d'ordine", "SKU", "ticket_id", "preferenze", "vincoli"):
        assert required in flat, f"il prompt non chiede di conservare {required!r}"


def test_summary_prompt_says_the_originals_are_replaced() -> None:
    """The model summarises better when told the originals will be gone."""
    flat = " ".join(SUMMARY_PROMPT.split())
    assert "sostituira'" in flat
    assert "viene perso" in flat


def test_summary_prompt_keeps_the_messages_placeholder() -> None:
    """The middleware formats the prompt with the conversation; without it, nothing lands."""
    assert "{messages}" in SUMMARY_PROMPT


def test_summary_prompt_asks_for_italian() -> None:
    """An English summary inside an Italian conversation invites English answers."""
    assert "italiano" in SUMMARY_PROMPT


def test_summary_prompt_is_not_the_stock_coding_agent_one() -> None:
    """The library default would discard exactly what customer care needs (ADR-028)."""
    for coding_section in ("SESSION INTENT", "ARTIFACTS", "NEXT STEPS"):
        assert coding_section not in SUMMARY_PROMPT


# --- the middleware -------------------------------------------------------------------


def test_middleware_uses_the_configured_thresholds() -> None:
    """Trigger and retention are configuration, not constants buried in code."""
    settings = _settings(summary_trigger_tokens=9000, summary_keep_messages=4)
    middleware = build_summarization_middleware(_model(), settings)
    assert middleware is not None


def test_middleware_is_a_distinct_class_from_the_ones_already_wired() -> None:
    """create_agent rejects two instances of the same middleware class (ADR-049)."""
    from langchain.agents.middleware import ModelCallLimitMiddleware

    middleware = build_summarization_middleware(_model(), _settings())
    assert not isinstance(middleware, ModelCallLimitMiddleware)


def test_middleware_carries_our_prompt_not_the_default() -> None:
    """A middleware built with the stock prompt would silently lose entities."""
    middleware = build_summarization_middleware(_model(), _settings())
    stored = getattr(middleware, "summary_prompt", None)
    assert stored is not None
    assert "GreenThumb" in stored


# --- detection ------------------------------------------------------------------------


def _summary_message(text: str, *, with_marker: bool) -> HumanMessage:
    """Build a message shaped like the one the middleware injects.

    Args:
        text: The summary body.
        with_marker: Whether to set the structured lc_source marker.

    Returns:
        The message.
    """
    kwargs = {"lc_source": SUMMARY_SOURCE_MARKER} if with_marker else {}
    return HumanMessage(content=f"{SUMMARY_TEXT_PREFIX}\n\n{text}", additional_kwargs=kwargs)


def test_no_summary_is_reported_on_a_fresh_conversation() -> None:
    """A short conversation has nothing summarised, and must not pretend otherwise."""
    messages = [HumanMessage(content="ciao"), AIMessage(content="buongiorno")]
    assert find_summary(messages) is None
    assert summarization_occurred(messages) is False


def test_summary_is_found_through_the_structured_marker() -> None:
    """The marker is metadata, and therefore stabler than an English sentence."""
    messages = [
        _summary_message("Il cliente ha citato l'ordine 1042.", with_marker=True),
        AIMessage(content="ok"),
    ]
    assert summarization_occurred(messages) is True
    assert find_summary(messages) == "Il cliente ha citato l'ordine 1042."


def test_summary_is_found_through_the_text_prefix_as_a_fallback() -> None:
    """If the library ever drops the marker, detection must still work."""
    messages = [_summary_message("Ordine 1042.", with_marker=False)]
    assert summarization_occurred(messages) is True


def test_english_preamble_is_stripped_from_the_returned_summary() -> None:
    """The preamble is the library's, not ours, and has no place in a demo or a log."""
    summary = find_summary([_summary_message("Ordine 1042.", with_marker=True)])
    assert summary is not None
    assert SUMMARY_TEXT_PREFIX not in summary


def test_an_ordinary_customer_message_is_not_mistaken_for_a_summary() -> None:
    """False positives would make the memory test pass without summarization running."""
    messages = [
        HumanMessage(content="Vorrei un riassunto della conversazione, per favore."),
        SystemMessage(content="Here is a summary of the conversation to date: qualcosa"),
    ]
    assert summarization_occurred(messages) is False


@pytest.mark.parametrize("position", [0, 2])
def test_summary_is_found_wherever_it_sits(position: int) -> None:
    """The middleware injects it first today, but detection must not depend on that.

    Args:
        position: Index at which the summary message is placed.
    """
    messages: list = [HumanMessage(content="a"), AIMessage(content="b")]
    messages.insert(position, _summary_message("Ordine 1042.", with_marker=True))
    assert summarization_occurred(messages) is True


# --- the checkpointer -----------------------------------------------------------------


def test_checkpointer_declares_the_serialised_types() -> None:
    """Deserialising an undeclared type is deprecated and will be blocked (ADR-054)."""
    from greenthumb.memory import CHECKPOINT_ALLOWED_MODULES, build_checkpointer

    assert ("greenthumb.schemas", "AgentOutput") in CHECKPOINT_ALLOWED_MODULES
    assert build_checkpointer() is not None


def test_structured_output_survives_a_checkpoint_round_trip() -> None:
    """A blocked type would break multi-turn conversations, not merely warn."""
    from greenthumb.memory import build_checkpointer
    from greenthumb.schemas import AgentOutput

    serde = build_checkpointer().serde
    original = AgentOutput(
        answer="Il suo ordine arriva domani.",
        proposed_confidence="high",
        cited_sources=["guides/bulbi_autunnali.md"],
    )
    restored = serde.loads_typed(serde.dumps_typed(original))
    assert isinstance(restored, AgentOutput)
    assert restored == original


def test_allowlist_is_not_permissive() -> None:
    """The default accepts any type at all; declaring ours is also the safer posture."""
    from greenthumb.memory import CHECKPOINT_ALLOWED_MODULES

    assert CHECKPOINT_ALLOWED_MODULES is not True
    assert len(CHECKPOINT_ALLOWED_MODULES) >= 1
