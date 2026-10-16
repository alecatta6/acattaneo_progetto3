"""The trace record: what one replayed turn leaves behind.

Every metric module reads this one shape, rather than each digging the fields it needs out
of a raw dictionary. One representation, defined once, for the same reason ``doc_id`` has
one (ADR-006): the alternative is four modules that agree about a key name until one of
them stops.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable, Sequence

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
    # Da quale esecuzione viene questa riga. Un file di trace puo' mescolare esecuzioni,
    # perche' rigiocare due conversazioni costa molto meno che rigiocarne venti quando solo
    # quelle due sono cambiate. L'etichetta rende la cosa verificabile invece che invisibile
    # (ADR-072), e ha un default, cosi' le trace scritte prima si caricano ancora.
    run_label: str = "main"

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


def merge_traces(
    existing: Sequence[TurnTrace], replacements: Sequence[TurnTrace]
) -> list[TurnTrace]:
    """Replace the traces of the re-replayed conversations, keeping every other one.

    Args:
        existing: The traces already on disk.
        replacements: The traces just produced.

    Returns:
        The merged traces, in dataset order: each replayed conversation appears once, with
        its new rows, at the position its old rows occupied.
    """
    replayed = {trace.conversation_id for trace in replacements}
    by_conversation: dict[str, list[TurnTrace]] = {}
    order: list[str] = []
    for trace in [*existing, *replacements]:
        if trace.conversation_id not in order:
            order.append(trace.conversation_id)
        if trace.conversation_id in replayed and trace not in replacements:
            continue
        by_conversation.setdefault(trace.conversation_id, []).append(trace)
    return [
        trace
        for conversation_id in order
        for trace in sorted(by_conversation[conversation_id], key=lambda t: t.turn_index)
    ]


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
