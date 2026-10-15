"""Re-scoring only some conversations, and splicing the result into the saved scores.

The judges are the expensive part of the evaluation. When only two conversations of the
dataset change, re-scoring the other eighteen buys nothing and costs the larger half of a
full run, so both judged-metric modules accept a list of conversations and merge their new
scores into the existing file (ADR-072).

The merge is by conversation *and* metric: a module that scores two metrics must not wipe
the scores of a metric it did not recompute.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections.abc import Sequence
from typing import Any, Protocol


class HasProvenance(Protocol):
    """A per-item score that knows which conversation and metric it belongs to."""

    conversation_id: str
    metric: str

    def to_dict(self) -> dict[str, object]:
        """Return the score in a JSON-serialisable shape."""
        ...


def parse_args(description: str) -> argparse.Namespace:
    """Parse the arguments both judged-metric modules accept.

    Args:
        description: The module's help text.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--only",
        metavar="CONVERSATION_ID",
        nargs="+",
        help="score only these conversations, merging into the existing scores",
    )
    return parser.parse_args()


def select(traces: Sequence[Any], only: Sequence[str] | None) -> list[Any]:
    """Narrow the traces to the requested conversations.

    Args:
        traces: Every trace.
        only: The conversations to keep, or None for all of them.

    Returns:
        The selected traces.

    Raises:
        SystemExit: If a requested conversation has no trace.
    """
    if only is None:
        return list(traces)
    wanted = set(only)
    selected = [trace for trace in traces if trace.conversation_id in wanted]
    missing = wanted - {trace.conversation_id for trace in selected}
    if missing:
        raise SystemExit(f"Nessuna trace per {sorted(missing)}: esegui prima il runner.")
    return selected


def merge_rows(
    path: pathlib.Path, key: str, fresh: Sequence[HasProvenance]
) -> list[dict[str, object]]:
    """Splice freshly computed scores into the ones already saved.

    Args:
        path: The existing score file; absent means there is nothing to carry over.
        key: The payload key holding the rows, ``turns`` or ``items``.
        fresh: The scores just computed.

    Returns:
        The merged rows: every saved row whose conversation and metric were not recomputed,
        followed by the fresh ones.
    """
    recomputed = {(score.conversation_id, score.metric) for score in fresh}
    carried: list[dict[str, object]] = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        carried = [
            row
            for row in payload.get(key, [])
            if (row["conversation_id"], row["metric"]) not in recomputed
        ]
    return [*carried, *(score.to_dict() for score in fresh)]


def aggregate_rows(
    rows: Sequence[dict[str, object]], count_key: str
) -> dict[str, dict[str, object]]:
    """Average each metric overall and per category, from already-serialised rows.

    Aggregation works on rows rather than on score objects because after a partial
    re-scoring the rows come from two places: the file and this run.

    Turns whose judge failed are excluded from the mean and counted separately, so a
    missing score never reads as a zero (ADR-067).

    Args:
        rows: The score rows.
        count_key: The name to report the count under, ``turns`` or ``items``.

    Returns:
        For each metric, its mean, the number averaged, the number missing, and the
        per-category means.
    """
    summary: dict[str, dict[str, object]] = {}
    for metric in sorted({str(row["metric"]) for row in rows}):
        selected = [row for row in rows if row["metric"] == metric]
        usable = [float(row["value"]) for row in selected if row["value"] is not None]
        by_category: dict[str, float] = {}
        for category in sorted({str(row["category"]) for row in selected}):
            values = [
                float(row["value"])
                for row in selected
                if row["category"] == category and row["value"] is not None
            ]
            if values:
                by_category[category] = sum(values) / len(values)
        summary[metric] = {
            "mean": (sum(usable) / len(usable)) if usable else None,
            count_key: len(usable),
            "missing": len(selected) - len(usable),
            "by_category": by_category,
        }
    return summary
