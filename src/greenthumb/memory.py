"""Short-term memory: summarization of long conversations.

Customer care conversations refer back to things said many turns earlier — "e quello di
prima?" pointing at an order number from turn one — so the strategy is summarization rather
than trimming, which would simply drop the oldest messages along with those entities
(ADR-004).

Two things here are not obvious from the library's API.

**The stock prompt is wrong for this domain.** It is written for a coding agent and would
discard precisely what has to survive, so the replacement in ``prompts.py`` is required,
not cosmetic.

**Detecting that summarization happened is not straightforward.** The middleware leaves no
flag in the agent state: it replaces the message list with a ``HumanMessage`` carrying the
summary. That message is identifiable by the ``lc_source`` marker the middleware sets on it,
which is what :func:`find_summary` looks for.

The checkpointer here is not the default one either, because the structured response is
stored in the checkpoint and deserialising it raises a deprecation that says it "will be
blocked in a future version" — a warning today, a broken multi-turn conversation whenever
that version lands (ADR-054).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from greenthumb.config import Settings
from greenthumb.prompts import SUMMARY_PROMPT

logger = logging.getLogger(__name__)

# Set by the middleware on the message it injects. Structured metadata, and therefore a far
# better handle than the English sentence the library hardcodes in front of the summary.
SUMMARY_SOURCE_MARKER = "summarization"

# La frase fissa che il middleware premette al riassunto. La tengo solo come ripiego se il
# marcatore manca. E' testo inglese dentro una conversazione tutta italiana e non e'
# configurabile: un piccolo difetto che preferisco dichiarare invece di nascondere.
SUMMARY_TEXT_PREFIX = "Here is a summary of the conversation to date:"


class LoggingSummarizationMiddleware(SummarizationMiddleware):
    """Summarization middleware that announces when it fires.

    The library leaves no signal that a summary was produced: it simply replaces the
    message list. Knowing the moment it happens is useful for the notebook demo and for
    reading a trace afterwards, and ``before_model`` is the public hook that returns a
    dictionary exactly when it summarised and ``None`` otherwise.
    """

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Summarise if the threshold is crossed, and log it when it happens.

        Args:
            state: The agent state.
            runtime: The LangGraph runtime.

        Returns:
            The state update when a summary was produced, otherwise None.
        """
        incoming = state.get("messages", []) or []
        result = super().before_model(state, runtime)
        if result is None:
            return result

        # The update is [RemoveMessage(REMOVE_ALL), summary, *preserved], so the two leading
        # entries are not conversation messages and must not be counted.
        updated = result.get("messages", []) or []
        preserved = updated[2:]
        tokens_before = self.token_counter(incoming)
        tokens_after = self.token_counter(updated[1:])
        logger.info(
            "Summarization scattata: %d messaggi (%d token) -> 1 riassunto + %d conservati "
            "(%d token).",
            len(incoming),
            tokens_before,
            len(preserved),
            tokens_after,
        )
        return result


def build_summarization_middleware(
    model: BaseChatModel, settings: Settings
) -> LoggingSummarizationMiddleware:
    """Build the summarization middleware from configuration.

    Args:
        model: The model used to write the summary. The agent's own model is reused, so no
            second provider is involved.
        settings: The runtime configuration supplying trigger and retention.

    Returns:
        The configured middleware, ready to pass to ``build_agent``.
    """
    return LoggingSummarizationMiddleware(
        model=model,
        # Tuples, not integers: the API takes a (unit, amount) pair (ADR-028).
        trigger=("tokens", settings.summary_trigger_tokens),
        keep=("messages", settings.summary_keep_messages),
        summary_prompt=SUMMARY_PROMPT,
    )


def find_summary(messages: Sequence[BaseMessage]) -> str | None:
    """Return the conversation summary, when one has been produced.

    Args:
        messages: The messages from the agent state.

    Returns:
        The summary text without the library's English preamble, or None when
        summarization has not fired yet.
    """
    for message in messages:
        if not isinstance(message, HumanMessage):
            continue
        source = (message.additional_kwargs or {}).get("lc_source")
        # `.text` is a property on this version; calling it as a method is deprecated.
        content = message.text if isinstance(message.text, str) else str(message.content)
        if source == SUMMARY_SOURCE_MARKER or content.startswith(SUMMARY_TEXT_PREFIX):
            return content.removeprefix(SUMMARY_TEXT_PREFIX).strip()
    return None


def summarization_occurred(messages: Sequence[BaseMessage]) -> bool:
    """Report whether the conversation has been summarised.

    Used by the memory tests and by the notebook demo. A memory test that checks only that
    an entity survived proves nothing unless it also checks that summarization actually
    ran: on a short conversation the entity survives simply because nothing was summarised
    (ADR-028).

    Args:
        messages: The messages from the agent state.

    Returns:
        True when a summary is present.
    """
    return find_summary(messages) is not None


# I tipi che finiscono nei checkpoint. L'output strutturato dell'agente e' uno di questi, e
# deserializzare un tipo non registrato e' deprecato: oggi passa, in una versione futura
# verra' bloccato. Dichiararlo tiene in piedi le conversazioni multi-turno dopo un
# aggiornamento, ed e' comunque piu' sicuro: la modalita' permissiva accetta qualsiasi tipo
# (ADR-054).
CHECKPOINT_ALLOWED_MODULES = {("greenthumb.schemas", "AgentOutput")}


def build_checkpointer() -> InMemorySaver:
    """Build the conversation store with our serialised types declared.

    Sessions live in memory only: they are lost when the process restarts, which is a known
    limit rather than an oversight (SPEC section 9). Production would use a persistent
    checkpointer, and the swap is a single argument.

    Returns:
        The checkpointer, keyed by ``thread_id`` and therefore by session.
    """
    return InMemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_ALLOWED_MODULES)
    )
