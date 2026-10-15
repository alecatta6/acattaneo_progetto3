"""Tests for the evaluation harness, with no LLM anywhere.

The harness is the instrument that measures the agent, and an instrument that is wrong
reports the system as wrong. Everything testable here is testable without a model: the
runner is driven by a stub service, the metrics are fed traces built by hand, and the
report is rendered from them (ADR-066).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from eval import metrics_deepeval, metrics_deterministic, partial, report, runner
from eval.dataset import Conversation, DatasetTurn, load_conversations
from eval.traces import TurnTrace, load_traces, merge_traces, write_traces

from greenthumb.response import RetrievedChunk
from greenthumb.schemas import ChatResponse
from greenthumb.service import ChatTurn


def make_trace(**overrides: Any) -> TurnTrace:
    """Build a trace, nominal unless overridden.

    Args:
        **overrides: Fields to replace in the nominal trace.

    Returns:
        The trace.
    """
    fields: dict[str, Any] = {
        "conversation_id": "conv_01",
        "category": "product_info",
        "turn_index": 1,
        "session_id": "sess-test",
        "user": "Quando si piantano i tulipani?",
        "reference_answer": "Da meta' ottobre a fine novembre.",
        "expected_sources": ["guides/bulbi_autunnali.md"],
        "expected_tools": ["search_knowledge_base"],
        "expected_needs_human": False,
        "answer": "Da meta' ottobre a fine novembre.",
        "confidence": "high",
        "sources": ["guides/bulbi_autunnali.md"],
        "needs_human": False,
        "retrieved_doc_ids": ["guides/bulbi_autunnali.md"],
        "retrieved_scores": [0.87],
        "retrieved_contexts": ["I bulbi si piantano da meta' ottobre a fine novembre."],
        "tools_invoked": ["search_knowledge_base"],
        "fallback": False,
        "summarization_fired": False,
    }
    fields.update(overrides)
    return TurnTrace(**fields)


# --- The dataset the runner replays ---------------------------------------------------


def test_the_real_dataset_parses_into_the_model() -> None:
    """``eval/conversations.jsonl`` validates against the dataset model."""
    conversations = load_conversations()
    assert len(conversations) == 20
    assert all(conversation.turns for conversation in conversations)


# --- Trace round-trip -----------------------------------------------------------------


def test_traces_survive_a_round_trip(tmp_path: pathlib.Path) -> None:
    """A trace written and read back is the same trace."""
    original = [make_trace(), make_trace(turn_index=2, confidence="low")]
    path = tmp_path / "traces.jsonl"
    assert write_traces(path, original) == 2
    assert load_traces(path) == original


def test_loading_missing_traces_names_the_command_that_makes_them(
    tmp_path: pathlib.Path,
) -> None:
    """The error tells the reader what to run, instead of only what is absent."""
    with pytest.raises(FileNotFoundError, match="eval.runner"):
        load_traces(tmp_path / "absent.jsonl")


def test_a_turn_without_contexts_is_not_scorable_by_ragas() -> None:
    """Retrieval that returned nothing above the threshold has nothing to score against."""
    assert make_trace().scorable_by_ragas is True
    assert make_trace(retrieved_contexts=[]).scorable_by_ragas is False
    assert make_trace(tools_invoked=["get_order_status"]).scorable_by_ragas is False


# --- The runner, driven by a stub ------------------------------------------------------


class StubService:
    """A chat service that answers from a script, so the runner can be tested offline."""

    def __init__(self, replies: list[ChatTurn]) -> None:
        """Bind the stub to its scripted replies.

        Args:
            replies: One reply per expected turn, in order.
        """
        self._replies = list(replies)
        self.seen: list[tuple[str, str]] = []

    def chat_detailed(self, message: str, session_id: str) -> ChatTurn:
        """Return the next scripted reply.

        Args:
            message: What the customer wrote.
            session_id: The conversation identifier.

        Returns:
            The next reply.
        """
        self.seen.append((message, session_id))
        return self._replies.pop(0)


def stub_turn(answer: str = "Risposta", needs_human: bool = False) -> ChatTurn:
    """Build one scripted service reply.

    Args:
        answer: The answer text.
        needs_human: The escalation flag.

    Returns:
        The reply.
    """
    return ChatTurn(
        response=ChatResponse(
            answer=answer,
            confidence="high",
            sources=["guides/bulbi_autunnali.md"],
            needs_human=needs_human,
        ),
        session_id="ignored",
        tools_invoked=["search_knowledge_base"],
        retrieved=[
            RetrievedChunk(
                doc_id="guides/bulbi_autunnali.md",
                score=0.88,
                chunk_id="guides/bulbi_autunnali.md#0",
                text="Si piantano da meta' ottobre.",
            )
        ],
    )


def test_the_runner_keeps_one_session_per_conversation() -> None:
    """Every turn of a conversation shares one session, so memory can work at all."""
    conversation = Conversation(
        conversation_id="conv_99",
        category="memory",
        turns=[
            DatasetTurn(
                user=f"domanda {n}",
                reference_answer="riferimento sufficientemente lungo per il giudice",
                expected_sources=[],
                expected_tools=[],
                expected_needs_human=False,
            )
            for n in range(1, 4)
        ],
    )
    service = StubService([stub_turn(f"risposta {n}") for n in range(1, 4)])
    traces = runner.replay_conversation(service, conversation)

    assert [trace.turn_index for trace in traces] == [1, 2, 3]
    assert len({trace.session_id for trace in traces}) == 1
    assert [message for message, _ in service.seen] == ["domanda 1", "domanda 2", "domanda 3"]


def test_the_runner_copies_the_expectations_into_the_trace() -> None:
    """A trace is self-contained: a score can be recomputed without the dataset."""
    conversation = Conversation(
        conversation_id="conv_98",
        category="escalation",
        turns=[
            DatasetTurn(
                user="Voglio un operatore",
                reference_answer="Ho aperto una richiesta, un operatore la contattera'.",
                expected_sources=["policies/contatti_orari.md"],
                expected_tools=["escalate_to_human"],
                expected_needs_human=True,
            )
        ],
    )
    (trace,) = runner.replay_conversation(StubService([stub_turn(needs_human=True)]), conversation)
    assert trace.expected_sources == ["policies/contatti_orari.md"]
    assert trace.expected_tools == ["escalate_to_human"]
    assert trace.expected_needs_human is True
    assert trace.needs_human is True
    assert trace.retrieved_contexts == ["Si piantano da meta' ottobre."]


# --- Deterministic metrics ------------------------------------------------------------


def test_needs_human_accuracy_counts_both_directions() -> None:
    """A missed escalation and a spurious one are both errors."""
    traces = [
        make_trace(),
        make_trace(turn_index=2, expected_needs_human=True, needs_human=False),
        make_trace(turn_index=3, expected_needs_human=False, needs_human=True),
    ]
    score = metrics_deterministic.needs_human_accuracy(traces)
    assert (score.passed, score.total) == (1, 3)
    assert score.failures == ["conv_01#2", "conv_01#3"]


def test_tool_selection_is_measured_by_inclusion() -> None:
    """An extra tool call does not count as an error, a missing one does (ADR-064)."""
    extra = make_trace(tools_invoked=["search_knowledge_base", "get_order_status"])
    missing = make_trace(turn_index=2, tools_invoked=["get_order_status"])
    assert metrics_deterministic.tool_selection_accuracy([extra]).value == 1.0
    assert metrics_deterministic.tool_selection_accuracy([missing]).value == 0.0


def test_tool_selection_excludes_turns_with_no_expectation() -> None:
    """Turns that expect no tool are left out instead of counted as free passes."""
    score = metrics_deterministic.tool_selection_accuracy(
        [make_trace(expected_tools=[], tools_invoked=[])]
    )
    assert score.total == 0
    assert score.value is None


def test_source_recall_ignores_extra_sources() -> None:
    """Recall asks whether the expected documents are there, not whether others are."""
    traces = [
        make_trace(sources=["guides/bulbi_autunnali.md", "products/substrato_bulbi_20l.md"]),
        make_trace(turn_index=2, sources=[]),
    ]
    score = metrics_deterministic.source_recall(traces)
    assert (score.passed, score.total) == (1, 2)
    assert score.failures == ["conv_01#2"]


def test_fallback_rate_separates_the_real_failures() -> None:
    """A fallback is the figure that carries information about failures."""
    traces = [make_trace(), make_trace(turn_index=2, fallback=True)]
    assert metrics_deterministic.schema_validity(traces).value == 1.0
    assert metrics_deterministic.fallback_rate(traces).value == 0.5


def test_memory_cases_that_never_summarized_are_reported_as_failures() -> None:
    """A memory conversation that never crossed the threshold proves nothing (ADR-028)."""
    fired = [
        make_trace(conversation_id="conv_17", category="memory", turn_index=n) for n in (1, 2)
    ] + [
        make_trace(
            conversation_id="conv_17", category="memory", turn_index=3, summarization_fired=True
        )
    ]
    never = [make_trace(conversation_id="conv_18", category="memory", turn_index=n) for n in (1, 2)]
    score = metrics_deterministic.summarization_fired_in_memory_cases(fired + never)
    assert (score.passed, score.total) == (1, 2)
    assert score.failures == ["conv_18#2"]


def test_a_metric_over_no_turns_reports_nothing_rather_than_a_perfect_score() -> None:
    """An empty population must not read as 100%, nor as 0%."""
    score = metrics_deterministic.source_recall([make_trace(expected_sources=[])])
    assert score.value is None
    assert score.to_dict()["value"] is None


def test_score_by_category_splits_the_population() -> None:
    """Per-category scoring keeps the categories apart."""
    traces = [
        make_trace(category="product_info"),
        make_trace(category="escalation", turn_index=2, expected_needs_human=True),
    ]
    by_category = metrics_deterministic.score_by_category(traces)
    assert set(by_category) == {"product_info", "escalation"}
    escalation = next(s for s in by_category["escalation"] if s.name == "needs_human accuracy")
    assert escalation.value == 0.0


# --- Judged metrics: aggregation only, no judge -----------------------------------------


def test_a_missing_judged_score_is_not_averaged_as_zero() -> None:
    """A judge failure must not depress the mean of the turns it never scored."""
    scores = [
        metrics_deepeval.ItemScore("conv_01", 1, "product_info", "answer_relevancy", 1.0),
        metrics_deepeval.ItemScore("conv_02", 1, "product_info", "answer_relevancy", None),
    ]
    rows = [score.to_dict() for score in scores]
    summary = partial.aggregate_rows(rows, "items")["answer_relevancy"]
    assert summary["mean"] == 1.0
    assert summary["items"] == 1
    assert summary["missing"] == 1


def test_judged_aggregation_splits_by_category() -> None:
    """Judged means are reported per category as well as overall."""
    scores = [
        metrics_deepeval.ItemScore("conv_01", 1, "product_info", "answer_relevancy", 1.0),
        metrics_deepeval.ItemScore("conv_14", 1, "escalation", "answer_relevancy", 0.0),
    ]
    rows = [score.to_dict() for score in scores]
    summary = partial.aggregate_rows(rows, "items")["answer_relevancy"]
    assert summary["mean"] == 0.5
    assert summary["by_category"] == {"escalation": 0.0, "product_info": 1.0}


# --- The report ------------------------------------------------------------------------


def test_the_report_renders_from_the_saved_scores(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report is built from the score files, with no number typed into it."""
    traces = [
        make_trace(),
        make_trace(
            conversation_id="conv_19",
            category="edge_cases",
            turn_index=1,
            expected_needs_human=True,
            needs_human=False,
            expected_sources=[],
            sources=[],
        ),
    ]
    traces_path = tmp_path / "traces.jsonl"
    write_traces(traces_path, traces)

    deterministic_path = tmp_path / "deterministic.json"
    deterministic_path.write_text(
        json.dumps(
            {
                "turns": 2,
                "overall": [s.to_dict() for s in metrics_deterministic.score_all(traces)],
                "by_category": {
                    category: [s.to_dict() for s in scores]
                    for category, scores in metrics_deterministic.score_by_category(traces).items()
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(metrics_deterministic, "SCORES_PATH", deterministic_path)
    monkeypatch.setattr(report.metrics_ragas, "SCORES_PATH", tmp_path / "absent-ragas.json")
    monkeypatch.setattr(report.metrics_deepeval, "SCORES_PATH", tmp_path / "absent-deepeval.json")

    monkeypatch.setattr(report, "ANALYSIS_PATH", tmp_path / "absent-analysis.md")

    text = report.build_report(traces_path=traces_path)
    assert "# Risultati dell'evaluation" in text
    assert "Metriche deterministiche" in text
    # The worst case is the turn that failed a deterministic expectation, not the nominal one.
    assert "### conv_19#1" in text
    assert "I 3 casi peggiori" in text
    # Sections whose score file is missing are omitted rather than faked.
    assert "Metriche RAGAS" not in text
    # A missing analysis is declared as missing, not quietly left out.
    assert "Non ancora scritta" in text


def test_the_report_includes_the_hand_written_analysis(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The analysis lives in its own file so regenerating the report cannot destroy it."""
    traces_path = tmp_path / "traces.jsonl"
    write_traces(traces_path, [make_trace()])
    analysis = tmp_path / "analysis.md"
    analysis.write_text("## Analisi\n\nLa causa era il prompt.\n", encoding="utf-8")

    monkeypatch.setattr(report, "ANALYSIS_PATH", analysis)
    for module in (metrics_deterministic, report.metrics_ragas, report.metrics_deepeval):
        monkeypatch.setattr(module, "SCORES_PATH", tmp_path / "absent.json")

    text = report.build_report(traces_path=traces_path)
    assert "La causa era il prompt." in text


# --- Partial re-replay and partial re-scoring -----------------------------------------


def test_merging_traces_replaces_only_the_replayed_conversations() -> None:
    """A partial replay must not drop the conversations it did not touch."""
    existing = [
        make_trace(conversation_id="conv_01", turn_index=1),
        make_trace(conversation_id="conv_17", category="memory", turn_index=1),
        make_trace(conversation_id="conv_17", category="memory", turn_index=2),
        make_trace(conversation_id="conv_20", category="edge_cases", turn_index=1),
    ]
    fresh = [
        make_trace(
            conversation_id="conv_17", category="memory", turn_index=n, run_label="memory-rerun"
        )
        for n in (1, 2, 3)
    ]
    merged = merge_traces(existing, fresh)

    assert [(t.conversation_id, t.turn_index) for t in merged] == [
        ("conv_01", 1),
        ("conv_17", 1),
        ("conv_17", 2),
        ("conv_17", 3),
        ("conv_20", 1),
    ]
    # The replayed conversation carries the new label, the others keep the old one.
    labels = {t.conversation_id: t.run_label for t in merged}
    assert labels == {"conv_01": "main", "conv_17": "memory-rerun", "conv_20": "main"}


def test_a_trace_written_before_the_label_existed_still_loads(
    tmp_path: pathlib.Path,
) -> None:
    """The provenance label has a default, so earlier trace files remain readable."""
    row = make_trace().model_dump()
    del row["run_label"]
    path = tmp_path / "traces.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert load_traces(path)[0].run_label == "main"


def test_merging_scores_keeps_the_metrics_that_were_not_recomputed(
    tmp_path: pathlib.Path,
) -> None:
    """Re-scoring one metric must not wipe another metric's saved scores."""
    path = tmp_path / "deepeval.json"
    path.write_text(
        json.dumps(
            {
                "summary": {},
                "items": [
                    {
                        "conversation_id": "conv_17",
                        "turn_index": 1,
                        "category": "memory",
                        "metric": "answer_relevancy",
                        "value": 0.5,
                        "reason": None,
                    },
                    {
                        "conversation_id": "conv_17",
                        "turn_index": None,
                        "category": "memory",
                        "metric": "knowledge_retention",
                        "value": 1.0,
                        "reason": None,
                    },
                    {
                        "conversation_id": "conv_01",
                        "turn_index": 1,
                        "category": "product_info",
                        "metric": "answer_relevancy",
                        "value": 1.0,
                        "reason": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    fresh = [
        metrics_deepeval.ItemScore("conv_17", 1, "memory", "answer_relevancy", 0.9),
    ]
    rows = partial.merge_rows(path, "items", fresh)

    keys = {(row["conversation_id"], row["metric"], row["value"]) for row in rows}
    # The recomputed pair is replaced...
    assert ("conv_17", "answer_relevancy", 0.9) in keys
    assert ("conv_17", "answer_relevancy", 0.5) not in keys
    # ...while the other metric of the same conversation, and the other conversation, stay.
    assert ("conv_17", "knowledge_retention", 1.0) in keys
    assert ("conv_01", "answer_relevancy", 1.0) in keys


def test_scoring_a_conversation_with_no_trace_fails_loudly() -> None:
    """A typo in --only must stop the run instead of silently scoring nothing."""
    with pytest.raises(SystemExit, match="conv_99"):
        partial.select([make_trace()], ["conv_99"])
