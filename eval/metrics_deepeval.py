"""DeepEval metrics: answer relevancy, escalation correctness, knowledge retention.

Three metrics on three different populations, because they answer three different
questions (SPEC section 10.3):

* **Answer relevancy**, on every turn: does the reply answer what was asked? ADR-033 warns
  that this metric scored 0.5 on a correct, pertinent answer during the spike, probably
  penalising accessory statements. A low score here is to be attributed to the right cause
  before the agent is "corrected".
* **Escalation correctness**, a ``GEval`` criterion, on the turns where handing over to a
  person is in play: was the handover justified *and* communicated well? The deterministic
  ``needs_human`` accuracy already says whether the flag was right; this says whether the
  customer was treated well while it happened.
* **Knowledge retention**, conversational, on the ``memory`` conversations: did the agent
  keep what the customer told it?

The judge is passed as a plain string, which DeepEval accepts (ADR-024), and its telemetry
is switched off by importing :mod:`eval.judges`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from eval import partial
from eval.judges import configure_deepeval
from eval.runner import RESULTS_DIR, TRACES_PATH
from eval.traces import TurnTrace, load_traces

logger = logging.getLogger(__name__)

SCORES_PATH = RESULTS_DIR / "deepeval.json"

ANSWER_RELEVANCY = "answer_relevancy"
ESCALATION_CORRECTNESS = "escalation_correctness"
KNOWLEDGE_RETENTION = "knowledge_retention"

# Categories where a handover to a person is at stake, either because it must happen or
# because it must *not*: a courteous refusal and a first missed order are the cases where
# escalating would be the error (SPEC section 8, ADR-011).
ESCALATION_CATEGORIES = frozenset({"escalation", "edge_cases"})

ESCALATION_CRITERIA = (
    "Valuta se la risposta gestisce correttamente il passaggio a un operatore umano. "
    "La risposta e' buona quando: (a) se il caso richiede un operatore — richiesta "
    "esplicita del cliente, rimborso fuori dai termini di policy, merce danneggiata o "
    "errata, reclamo, questioni di sicurezza per persone o animali, domanda pertinente "
    "senza documentazione a supporto — lo dichiara con chiarezza e dice al cliente cosa "
    "aspettarsi; (b) se il caso NON lo richiede — una domanda fuori dall'ambito del "
    "giardinaggio, oppure un numero d'ordine sbagliato al primo tentativo — non annuncia "
    "nessun operatore e invece rifiuta cortesemente o chiede di verificare il numero. "
    "Penalizza sia il mancato passaggio quando serviva, sia il passaggio annunciato "
    "quando non serviva. Valuta anche il tono: la risposta deve restare cortese e "
    "concreta, senza scaricare il problema sul cliente."
)


@dataclass(frozen=True)
class ItemScore:
    """One judged item: a turn, or a whole conversation for the conversational metric.

    Attributes:
        conversation_id: Which conversation the item belongs to.
        turn_index: The turn's position, or ``None`` for a whole-conversation metric.
        category: The dataset category.
        metric: The metric's name.
        value: The score, or ``None`` when the judge could not produce one.
        reason: The judge's explanation, when it gave one.
    """

    conversation_id: str
    turn_index: int | None
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


def _measure(metric, case, label: str) -> tuple[float | None, str | None]:  # noqa: ANN001
    """Run one DeepEval metric, turning a judge failure into a missing value.

    Args:
        metric: The configured metric.
        case: The test case to score.
        label: A human-readable label for the log line.

    Returns:
        The score and the judge's reason, or ``(None, message)`` on failure.
    """
    try:
        metric.measure(case)
    except Exception as error:  # noqa: BLE001 - one lost score beats a lost run
        logger.warning("%s: metrica non calcolata (%s)", label, error)
        return None, f"errore del giudice: {error}"
    score = None if metric.score is None else float(metric.score)
    return score, getattr(metric, "reason", None)


def score_answer_relevancy(traces: Sequence[TurnTrace], judge: str) -> list[ItemScore]:
    """Score every turn for answer relevancy.

    Args:
        traces: Every trace.
        judge: The judge's provider slug.

    Returns:
        One score per turn.
    """
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase

    metric = AnswerRelevancyMetric(model=judge)
    scores: list[ItemScore] = []
    for trace in traces:
        case = LLMTestCase(
            input=trace.user,
            actual_output=trace.answer,
            retrieval_context=trace.retrieved_contexts or None,
        )
        value, reason = _measure(
            metric, case, f"{trace.conversation_id}#{trace.turn_index} relevancy"
        )
        scores.append(
            ItemScore(
                conversation_id=trace.conversation_id,
                turn_index=trace.turn_index,
                category=trace.category,
                metric=ANSWER_RELEVANCY,
                value=value,
                reason=reason,
            )
        )
    return scores


def score_escalation_correctness(traces: Sequence[TurnTrace], judge: str) -> list[ItemScore]:
    """Score the escalation and edge-case turns with a GEval criterion.

    Args:
        traces: Every trace.
        judge: The judge's provider slug.

    Returns:
        One score per judged turn.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    metric = GEval(
        name="Correttezza escalation",
        criteria=ESCALATION_CRITERIA,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        model=judge,
    )
    judged = [trace for trace in traces if trace.category in ESCALATION_CATEGORIES]
    logger.info("GEval escalation: %d turni da valutare", len(judged))

    scores: list[ItemScore] = []
    for trace in judged:
        case = LLMTestCase(
            input=trace.user,
            actual_output=trace.answer,
            expected_output=trace.reference_answer,
        )
        value, reason = _measure(
            metric, case, f"{trace.conversation_id}#{trace.turn_index} escalation"
        )
        scores.append(
            ItemScore(
                conversation_id=trace.conversation_id,
                turn_index=trace.turn_index,
                category=trace.category,
                metric=ESCALATION_CORRECTNESS,
                value=value,
                reason=reason,
            )
        )
    return scores


def score_knowledge_retention(traces: Sequence[TurnTrace], judge: str) -> list[ItemScore]:
    """Score each ``memory`` conversation for knowledge retention.

    The whole conversation is rebuilt as alternating turns, because retention is a property
    of the conversation and not of any single reply.

    Args:
        traces: Every trace.
        judge: The judge's provider slug.

    Returns:
        One score per ``memory`` conversation.
    """
    from deepeval.metrics import KnowledgeRetentionMetric
    from deepeval.test_case import ConversationalTestCase, Turn

    metric = KnowledgeRetentionMetric(model=judge)
    conversation_ids = sorted(
        {trace.conversation_id for trace in traces if trace.category == "memory"}
    )
    logger.info("Knowledge retention: %d conversazioni da valutare", len(conversation_ids))

    scores: list[ItemScore] = []
    for conversation_id in conversation_ids:
        rows = sorted(
            (t for t in traces if t.conversation_id == conversation_id),
            key=lambda t: t.turn_index,
        )
        turns: list[Turn] = []
        for row in rows:
            turns.append(Turn(role="user", content=row.user))
            turns.append(
                Turn(
                    role="assistant",
                    content=row.answer,
                    retrieval_context=row.retrieved_contexts or None,
                )
            )
        value, reason = _measure(
            metric, ConversationalTestCase(turns=turns), f"{conversation_id} retention"
        )
        scores.append(
            ItemScore(
                conversation_id=conversation_id,
                turn_index=None,
                category="memory",
                metric=KNOWLEDGE_RETENTION,
                value=value,
                reason=reason,
            )
        )
    return scores


def score_traces(traces: Sequence[TurnTrace]) -> list[ItemScore]:
    """Run all three DeepEval metrics.

    Args:
        traces: Every trace.

    Returns:
        Every score.
    """
    judge = configure_deepeval()
    return [
        *score_answer_relevancy(traces, judge),
        *score_escalation_correctness(traces, judge),
        *score_knowledge_retention(traces, judge),
    ]


def main() -> None:
    """Score the saved traces with DeepEval and write the results.

    With ``--only`` it scores just those conversations and merges the result into the
    existing score file, which is what makes re-running two conversations cheap (ADR-072).
    """
    args = partial.parse_args("Score the saved traces with DeepEval.")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    traces = load_traces(TRACES_PATH)
    selected = partial.select(traces, args.only)
    scores = score_traces(selected)
    rows = partial.merge_rows(SCORES_PATH, "items", scores)
    summary = partial.aggregate_rows(rows, "items")

    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.write_text(
        json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for metric, row in summary.items():
        mean = row["mean"]
        shown = "n/d" if mean is None else f"{mean:.3f}"
        print(f"{metric:34s} {shown:>8s}  ({row['items']}, {row['missing']} mancanti)")
    print(f"\nScritto {SCORES_PATH}")


if __name__ == "__main__":
    main()
