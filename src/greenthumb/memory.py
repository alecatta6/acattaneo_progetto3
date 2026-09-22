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
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from greenthumb.config import Settings
from greenthumb.prompts import SUMMARY_PROMPT

# Set by the middleware on the message it injects. Structured metadata, and therefore a far
# better handle than the English sentence the library hardcodes in front of the summary.
SUMMARY_SOURCE_MARKER = "summarization"

# The hardcoded preamble, kept only as a fallback for the marker. It is English text inside
# an otherwise entirely Italian conversation, and it is not configurable: a small blemish
# worth naming rather than hiding.
SUMMARY_TEXT_PREFIX = "Here is a summary of the conversation to date:"


def build_summarization_middleware(
    model: BaseChatModel, settings: Settings
) -> SummarizationMiddleware:
    """Build the summarization middleware from configuration.

    Args:
        model: The model used to write the summary. The agent's own model is reused, so no
            second provider is involved.
        settings: The runtime configuration supplying trigger and retention.

    Returns:
        The configured middleware, ready to pass to ``build_agent``.
    """
    return SummarizationMiddleware(
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
