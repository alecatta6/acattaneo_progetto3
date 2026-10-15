"""Replay the dataset and save one trace per turn.

Three properties make a replay comparable with the next one (SPEC section 10.2):

* the business date comes from a :class:`~greenthumb.clock.FrozenClock`, so "domani" means
  the same day in every run;
* each conversation gets a fresh ``session_id``, so the checkpointer never carries state
  across conversations;
* each run gets its own escalation register, so ``needs_human`` is decided by what this run
  did and not by tickets a previous run left behind (ADR-065).
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import tempfile
from collections.abc import Sequence

from eval.dataset import Conversation, load_conversations
from eval.traces import TurnTrace, load_traces, merge_traces, write_traces
from greenthumb.config import REPO_ROOT, Settings, get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.service import ChatService, build_chat_service, new_session_id

logger = logging.getLogger(__name__)

RESULTS_DIR = REPO_ROOT / "eval" / "results"
TRACES_PATH = RESULTS_DIR / "traces.jsonl"


def replay_conversation(
    service: ChatService, conversation: Conversation, run_label: str = "main"
) -> list[TurnTrace]:
    """Replay one conversation in a fresh session.

    Args:
        service: The chat service under evaluation.
        conversation: The conversation to replay.
        run_label: Provenance label recorded on every trace of this replay.

    Returns:
        One trace per turn, in order.
    """
    session_id = new_session_id()
    traces: list[TurnTrace] = []
    for index, turn in enumerate(conversation.turns, start=1):
        result = service.chat_detailed(turn.user, session_id)
        traces.append(
            TurnTrace(
                conversation_id=conversation.conversation_id,
                category=conversation.category,
                turn_index=index,
                session_id=session_id,
                run_label=run_label,
                user=turn.user,
                reference_answer=turn.reference_answer,
                expected_sources=turn.expected_sources,
                expected_tools=turn.expected_tools,
                expected_needs_human=turn.expected_needs_human,
                answer=result.response.answer,
                confidence=result.response.confidence,
                sources=list(result.response.sources),
                needs_human=result.response.needs_human,
                retrieved_doc_ids=[chunk.doc_id for chunk in result.retrieved],
                retrieved_scores=[chunk.score for chunk in result.retrieved],
                retrieved_contexts=result.retrieved_contexts,
                tools_invoked=list(result.tools_invoked),
                fallback=result.fallback,
                summarization_fired=result.summarization_fired,
            )
        )
        flags = [
            f"conf={result.response.confidence}",
            f"human={str(result.response.needs_human).lower()}",
            f"tools={','.join(result.tools_invoked) or '-'}",
        ]
        if result.fallback:
            flags.append("FALLBACK")
        if result.summarization_fired:
            flags.append("summarized")
        logger.info("%s turno %d: %s", conversation.conversation_id, index, " ".join(flags))
    return traces


def run(
    settings: Settings | None = None,
    only: Sequence[str] | None = None,
    traces_path: pathlib.Path | None = None,
    merge: bool = False,
    run_label: str = "main",
) -> list[TurnTrace]:
    """Replay the whole dataset, or some conversations of it.

    Args:
        settings: Runtime configuration; read from the environment when omitted.
        only: ``conversation_id`` values to replay alone, for a cheap partial run.
        traces_path: Where to write the traces; defaults to ``eval/results/traces.jsonl``.
        merge: With ``only``, splice the new traces into the existing file instead of
            replacing it, so the conversations that were not replayed are kept.
        run_label: Provenance label recorded on every trace of this replay.

    Returns:
        Every trace written, including the ones carried over by a merge.

    Raises:
        SystemExit: If ``only`` names a conversation the dataset does not contain.
    """
    settings = settings or get_settings()
    conversations = load_conversations()
    if only is not None:
        wanted = set(only)
        conversations = [c for c in conversations if c.conversation_id in wanted]
        missing = wanted - {c.conversation_id for c in conversations}
        if missing:
            raise SystemExit(f"Nessuna conversazione con id {sorted(missing)}")

    # A register of this run only: needs_human must reflect this replay (ADR-065).
    with tempfile.TemporaryDirectory(prefix="greenthumb-eval-") as directory:
        register = EscalationsRepository(pathlib.Path(directory) / "escalations.jsonl")
        service = build_chat_service(settings=settings, escalations=register)
        traces = [
            trace
            for conversation in conversations
            for trace in replay_conversation(service, conversation, run_label)
        ]

    destination = traces_path or TRACES_PATH
    if merge and destination.exists():
        previous = load_traces(destination)
        traces = merge_traces(previous, traces)
        logger.info(
            "Fuse nelle trace esistenti: %d conversazioni rigiocate, %d turni totali",
            len(conversations),
            len(traces),
        )
    written = write_traces(destination, traces)
    logger.info("Scritte %d trace in %s", written, destination)
    return traces


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Replay the evaluation dataset.")
    parser.add_argument(
        "--only",
        metavar="CONVERSATION_ID",
        nargs="+",
        help="replay only these conversations (cheap partial run)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="with --only, splice into the existing traces instead of replacing them",
    )
    parser.add_argument(
        "--label",
        default="main",
        help="provenance label recorded on every trace of this replay",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        help="where to write the traces (default: eval/results/traces.jsonl)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    traces = run(only=args.only, traces_path=args.out, merge=args.merge, run_label=args.label)
    conversations = len({trace.conversation_id for trace in traces})
    print(f"\n{len(traces)} turni su {conversations} conversazioni.")


if __name__ == "__main__":
    main()
