"""The trace record: what one replayed turn leaves behind.

Every metric module reads this one shape, rather than each digging the fields it needs out
of a raw dictionary. One representation, defined once, for the same reason ``doc_id`` has
one (ADR-006): the alternative is four modules that agree about a key name until one of
them stops.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from greenthumb.schemas import ChatResponse, Confidence
from greenthumb.tools.knowledge_base_tool import TOOL_NAME as KB_TOOL


class TurnTrace(BaseModel):
    """One replayed turn: what was asked, what was expected, what happened.

    The expectations are copied in from the dataset so that a trace file is
    self-contained: a score can be recomputed, and a bad case read, without holding the
    dataset alongside it.
    """

    model_config = ConfigDict(frozen=True)

    # --- Identity ---
    conversation_id: str
    category: str
    turn_index: int
    session_id: str

    # --- From the dataset ---
    user: str
    reference_answer: str
    expected_sources: list[str]
    expected_tools: list[str]
    expected_needs_human: bool

    # --- What the agent returned ---
    answer: str
    confidence: Confidence
    sources: list[str]
    needs_human: bool

    # --- How it got there ---
    retrieved_doc_ids: list[str]
    retrieved_scores: list[float]
    retrieved_contexts: list[str]
    tools_invoked: list[str]
    fallback: bool
    summarization_fired: bool

    @property
    def used_retrieval(self) -> bool:
        """Report whether the turn searched the knowledge base.

        Returns:
            True when the retrieval tool was invoked, whatever it returned.
        """
        return KB_TOOL in self.tools_invoked

    @property
    def scorable_by_ragas(self) -> bool:
        """Report whether RAGAS can score this turn.

        Faithfulness and context precision measure an answer *against its contexts*, so a
        turn that retrieved nothing above the threshold has nothing to be scored against
        — and scoring it anyway would quietly average zeros into the result.

        Returns:
            True when retrieval ran and returned at least one context.
        """
        return self.used_retrieval and bool(self.retrieved_contexts)

    @property
    def response(self) -> ChatResponse:
        """Rebuild the four-field contract this turn returned.

        Returns:
            The response, re-validated against the schema.
        """
        return ChatResponse(
            answer=self.answer,
            confidence=self.confidence,
            sources=self.sources,
            needs_human=self.needs_human,
        )


def write_traces(path: pathlib.Path, traces: Iterable[TurnTrace]) -> int:
    """Write traces as JSON Lines.

    Args:
        path: Destination file; parent directories are created.
        traces: The traces to write, in order.

    Returns:
        How many traces were written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(trace.model_dump_json() + "\n")
            written += 1
    return written


def load_traces(path: pathlib.Path) -> list[TurnTrace]:
    """Read traces back.

    Args:
        path: The trace file written by :func:`write_traces`.

    Returns:
        The traces, in file order.

    Raises:
        FileNotFoundError: If the trace file does not exist, with the command that makes it.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Nessuna trace in {path}. Esegui prima il runner: uv run python -m eval.runner"
        )
    return [
        TurnTrace.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
