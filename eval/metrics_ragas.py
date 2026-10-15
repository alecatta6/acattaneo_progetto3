"""RAGAS metrics: faithfulness and context precision.

Both read the contexts the agent actually retrieved, which is why the retrieval tool
carries the chunk text in its artifact (ADR-059). The metrics of
``ragas.metrics.collections`` take the judge in their constructor and expose ``ascore``
with explicit parameters, so they are called once per turn rather than through the legacy
``evaluate()`` (ADR-023).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from eval.judges import build_ragas_judge
from eval.runner import RESULTS_DIR, TRACES_PATH
from eval.traces import TurnTrace, load_traces

logger = logging.getLogger(__name__)

SCORES_PATH = RESULTS_DIR / "ragas.json"

FAITHFULNESS = "faithfulness"
CONTEXT_PRECISION = "context_precision_with_reference"


@dataclass(frozen=True)
class TurnScore:
    """One judged turn.

    Attributes:
        conversation_id: Which conversation the turn belongs to.
        turn_index: Its one-based position.
        category: The dataset category, so results can be aggregated by it.
        metric: The metric's name.
        value: The score, or ``None`` when the judge could not produce one.
        reason: The judge's explanation, when it gave one.
    """

    conversation_id: str
    turn_index: int
    category: str
    metric: str
    value: float | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the score in a JSON-serialisable shape.

        Returns:
            The score's fields.
        """
        return {
            "conversation_id": self.conversation_id,
            "turn_index": self.turn_index,
            "category": self.category,
            "metric": self.metric,
            "value": self.value,
            "reason": self.reason,
        }


async def _score_turn(trace: TurnTrace, faithfulness, precision) -> list[TurnScore]:  # noqa: ANN001
    """Score one turn with both metrics.

    A judge failure is recorded as a missing value rather than allowed to abort the run:
    losing one turn of one metric is recoverable, losing an entire replay is not.

    Args:
        trace: The turn to score.
        faithfulness: The configured ``Faithfulness`` metric.
        precision: The configured ``ContextPrecisionWithReference`` metric.

    Returns:
        One score per metric.
    """
    scores: list[TurnScore] = []
    for metric_name, coroutine in (
        (
            FAITHFULNESS,
            faithfulness.ascore(
                user_input=trace.user,
                response=trace.answer,
                retrieved_contexts=trace.retrieved_contexts,
            ),
        ),
        (
            CONTEXT_PRECISION,
            precision.ascore(
                user_input=trace.user,
                reference=trace.reference_answer,
                retrieved_contexts=trace.retrieved_contexts,
            ),
        ),
    ):
        try:
            result = await coroutine
            value, reason = float(result.value), getattr(result, "reason", None)
        except Exception as error:  # noqa: BLE001 - one lost score beats a lost run
            logger.warning(
                "%s turno %d: %s non calcolata (%s)",
                trace.conversation_id,
                trace.turn_index,
                metric_name,
                error,
            )
            value, reason = None, f"errore del giudice: {error}"
        scores.append(
            TurnScore(
                conversation_id=trace.conversation_id,
                turn_index=trace.turn_index,
                category=trace.category,
                metric=metric_name,
                value=value,
                reason=reason,
            )
        )
    return scores


def score_traces(traces: Sequence[TurnTrace], cache_dir: str | None = None) -> list[TurnScore]:
    """Score every turn that retrieved something.

    Args:
        traces: Every trace.
        cache_dir: Optional judge cache directory, to make re-scoring free.

    Returns:
        The scores, two per judged turn.
    """
    from ragas.metrics.collections import ContextPrecisionWithReference, Faithfulness

    judged = [trace for trace in traces if trace.scorable_by_ragas]
    skipped = len(traces) - len(judged)
    logger.info(
        "RAGAS: %d turni da valutare, %d esclusi (nessun contesto recuperato)",
        len(judged),
        skipped,
    )

    judge = build_ragas_judge(cache_dir=cache_dir)
    faithfulness = Faithfulness(llm=judge)
    precision = ContextPrecisionWithReference(llm=judge)

    async def run_all() -> list[TurnScore]:
        """Score the judged turns one after another.

        Returns:
            Every score.
        """
        collected: list[TurnScore] = []
        for trace in judged:
            collected.extend(await _score_turn(trace, faithfulness, precision))
        return collected

    return asyncio.run(run_all())


def aggregate(scores: Sequence[TurnScore]) -> dict[str, dict[str, object]]:
    """Average each metric overall and per category.

    Turns whose judge failed are excluded from the mean and counted separately, so a
    missing score never reads as a zero.

    Args:
        scores: The per-turn scores.

    Returns:
        For each metric, its mean, the number of turns averaged, the number missing, and
        the per-category means.
    """
    summary: dict[str, dict[str, object]] = {}
    for metric in sorted({score.metric for score in scores}):
        rows = [score for score in scores if score.metric == metric]
        usable = [score.value for score in rows if score.value is not None]
        by_category: dict[str, float] = {}
        for category in sorted({score.category for score in rows}):
            values = [
                score.value
                for score in rows
                if score.category == category and score.value is not None
            ]
            if values:
                by_category[category] = sum(values) / len(values)
        summary[metric] = {
            "mean": (sum(usable) / len(usable)) if usable else None,
            "turns": len(usable),
            "missing": len(rows) - len(usable),
            "by_category": by_category,
        }
    return summary


def main() -> None:
    """Score the saved traces with RAGAS and write the results."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    traces = load_traces(TRACES_PATH)
    scores = score_traces(traces)
    summary = aggregate(scores)

    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.write_text(
        json.dumps(
            {"summary": summary, "turns": [score.to_dict() for score in scores]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for metric, row in summary.items():
        mean = row["mean"]
        shown = "n/d" if mean is None else f"{mean:.3f}"
        print(f"{metric:34s} {shown:>8s}  ({row['turns']} turni, {row['missing']} mancanti)")
    print(f"\nScritto {SCORES_PATH}")


if __name__ == "__main__":
    main()
