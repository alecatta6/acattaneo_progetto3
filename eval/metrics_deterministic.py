"""Metrics that need no judge, and no second opinion.

These come for free from ADR-002: because ``sources``, ``needs_human`` and the tool calls
are facts about what the turn did rather than claims the model makes about itself, they can
be compared with the dataset by arithmetic. They are also the only metrics here that cost
nothing to recompute, which makes them the right place to look first when a judged score
surprises.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from eval.runner import RESULTS_DIR, TRACES_PATH
from eval.traces import TurnTrace, load_traces

logger = logging.getLogger(__name__)

SCORES_PATH = RESULTS_DIR / "deterministic.json"


@dataclass(frozen=True)
class Score:
    """One metric over one population of turns.

    Attributes:
        name: The metric's name, as it appears in the report.
        passed: How many turns met the expectation.
        total: How many turns the metric applied to.
        failures: The turns that did not meet it, as ``conversation_id#turn`` labels.
    """

    name: str
    passed: int
    total: int
    failures: list[str]

    @property
    def value(self) -> float | None:
        """Return the metric as a fraction.

        Returns:
            ``passed / total``, or ``None`` when the metric applied to no turn — which is
            reported as such rather than as a perfect or a zero score.
        """
        return self.passed / self.total if self.total else None

    def to_dict(self) -> dict[str, object]:
        """Return the score in a JSON-serialisable shape.

        Returns:
            The metric's fields, with ``value`` already computed.
        """
        return {
            "name": self.name,
            "value": self.value,
            "passed": self.passed,
            "total": self.total,
            "failures": self.failures,
        }


def _label(trace: TurnTrace) -> str:
    """Build the short label used to point at a turn in the report.

    Args:
        trace: The turn.

    Returns:
        A label such as ``conv_07#1``.
    """
    return f"{trace.conversation_id}#{trace.turn_index}"


def _score(
    name: str,
    traces: Sequence[TurnTrace],
    applies: Callable[[TurnTrace], bool],
    holds: Callable[[TurnTrace], bool],
) -> Score:
    """Score one predicate over the turns it applies to.

    Args:
        name: The metric's name.
        traces: Every trace.
        applies: Whether the metric is defined for a given turn.
        holds: Whether the expectation is met for that turn.

    Returns:
        The score.
    """
    relevant = [trace for trace in traces if applies(trace)]
    failures = [_label(trace) for trace in relevant if not holds(trace)]
    return Score(
        name=name, passed=len(relevant) - len(failures), total=len(relevant), failures=failures
    )


def needs_human_accuracy(traces: Sequence[TurnTrace]) -> Score:
    """Score the escalation flag against the dataset.

    Args:
        traces: Every trace.

    Returns:
        The score over all turns.
    """
    return _score(
        "needs_human accuracy",
        traces,
        applies=lambda _: True,
        holds=lambda t: t.needs_human == t.expected_needs_human,
    )


def tool_selection_accuracy(traces: Sequence[TurnTrace]) -> Score:
    """Score whether each turn invoked the tools it could not be answered without.

    Measured by inclusion, not equality: the model groups or splits its tool calls
    differently between identical runs (ADR-061), and re-reading an order already
    discussed is correct behaviour rather than an error (ADR-064). Turns whose expectation
    is empty are excluded, because inclusion holds trivially there and counting them would
    inflate the figure.

    Args:
        traces: Every trace.

    Returns:
        The score over turns that expect at least one tool.
    """
    return _score(
        "tool selection accuracy",
        traces,
        applies=lambda t: bool(t.expected_tools),
        holds=lambda t: set(t.expected_tools) <= set(t.tools_invoked),
    )


def source_recall(traces: Sequence[TurnTrace]) -> Score:
    """Score whether the expected documents appear in the response sources.

    Args:
        traces: Every trace.

    Returns:
        The score over turns that expect at least one source.
    """
    return _score(
        "source recall",
        traces,
        applies=lambda t: bool(t.expected_sources),
        holds=lambda t: set(t.expected_sources) <= set(t.sources),
    )


def _is_valid_response(trace: TurnTrace) -> bool:
    """Report whether the recorded response still validates against the contract.

    Args:
        trace: The turn.

    Returns:
        True when the four fields rebuild a valid :class:`ChatResponse`.
    """
    try:
        _ = trace.response
    except ValidationError:
        return False
    return True


def schema_validity(traces: Sequence[TurnTrace]) -> Score:
    """Score how many turns returned a well-formed response.

    Honest reading: this metric is close to vacuous by construction. The deterministic
    layer builds ``ChatResponse`` itself and a parsing failure is caught and turned into
    the courtesy fallback (SPEC section 5), so an invalid response cannot reach a caller.
    It is reported because the assignment asks for it, and because a value below 1.0 would
    mean a real regression in that layer. :func:`fallback_rate` is the figure that actually
    carries information about failures.

    Args:
        traces: Every trace.

    Returns:
        The score over all turns.
    """
    return _score("schema validity", traces, applies=lambda _: True, holds=_is_valid_response)


def fallback_rate(traces: Sequence[TurnTrace]) -> Score:
    """Score how many turns answered without falling back.

    Args:
        traces: Every trace.

    Returns:
        The score over all turns, where a pass means no fallback was used.
    """
    return _score(
        "answered without fallback", traces, applies=lambda _: True, holds=lambda t: not t.fallback
    )


def summarization_fired_in_memory_cases(traces: Sequence[TurnTrace]) -> Score:
    """Score whether the ``memory`` conversations actually triggered summarization.

    A memory conversation that never crossed the threshold proves nothing: the entity from
    turn one survived because nothing was ever summarised (ADR-028). This metric makes that
    failure visible instead of letting it pass as a success.

    Args:
        traces: Every trace.

    Returns:
        The score over the last turn of each ``memory`` conversation.
    """
    last_turns = {}
    for trace in traces:
        if trace.category != "memory":
            continue
        current = last_turns.get(trace.conversation_id)
        if current is None or trace.turn_index > current.turn_index:
            last_turns[trace.conversation_id] = trace
    traces_by_id = list(last_turns.values())
    return _score(
        "summarization fired (memory)",
        traces_by_id,
        applies=lambda _: True,
        holds=lambda t: t.summarization_fired,
    )


METRICS: tuple[Callable[[Sequence[TurnTrace]], Score], ...] = (
    needs_human_accuracy,
    tool_selection_accuracy,
    source_recall,
    schema_validity,
    fallback_rate,
    summarization_fired_in_memory_cases,
)


def score_all(traces: Sequence[TurnTrace]) -> list[Score]:
    """Compute every deterministic metric.

    Args:
        traces: Every trace.

    Returns:
        The scores, in reporting order.
    """
    return [metric(traces) for metric in METRICS]


def score_by_category(traces: Sequence[TurnTrace]) -> dict[str, list[Score]]:
    """Compute every deterministic metric once per category.

    Args:
        traces: Every trace.

    Returns:
        The scores, keyed by the dataset category.
    """
    categories = sorted({trace.category for trace in traces})
    return {
        category: score_all([t for t in traces if t.category == category])
        for category in categories
    }


def main() -> None:
    """Score the saved traces and write the deterministic results."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    traces = load_traces(TRACES_PATH)
    overall = score_all(traces)
    payload = {
        "turns": len(traces),
        "overall": [score.to_dict() for score in overall],
        "by_category": {
            category: [score.to_dict() for score in scores]
            for category, scores in score_by_category(traces).items()
        },
    }
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for score in overall:
        shown = "n/d" if score.value is None else f"{score.value:.2%}"
        print(f"{score.name:34s} {shown:>8s}  ({score.passed}/{score.total})")
        if score.failures:
            print(f"{'':34s}          casi: {', '.join(score.failures)}")
    print(f"\nScritto {SCORES_PATH}")


if __name__ == "__main__":
    main()
