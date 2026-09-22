"""Tests for the deterministic response layer.

Every trace here is built by hand. The agent cannot be driven by a fake model (ADR-049),
and running the real one would make these tests slow, costly and non-deterministic — while
what is under test is pure logic that deserves none of those properties.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from greenthumb.memory import SUMMARY_SOURCE_MARKER, SUMMARY_TEXT_PREFIX
from greenthumb.response import (
    TurnEvidence,
    build_chat_response,
    confidence_cap,
    extract_turn_evidence,
    lower_of,
    messages_of_current_turn,
    output_from_state,
    resolve_sources,
)
from greenthumb.schemas import AgentOutput, ChatResponse

LOW = 0.813
HIGH = 0.863

BULBS = "guides/bulbi_autunnali.md"
RETURNS = "policies/resi_rimborsi.md"
INVENTED = "policies/garanzie_inesistenti.md"


def _kb_message(results: list[tuple[str, float]], best: float | None = None) -> ToolMessage:
    """Build a ToolMessage shaped like the knowledge base tool's output.

    Args:
        results: Pairs of document identifier and similarity, above the threshold.
        best: Best similarity seen, including below the threshold.

    Returns:
        The message.
    """
    return ToolMessage(
        content="estratti",
        tool_call_id="kb",
        name="search_knowledge_base",
        artifact={
            "tool": "search_knowledge_base",
            "query": "q",
            "doc_type": None,
            "threshold": LOW,
            "best_similarity": best if best is not None else (results[0][1] if results else None),
            "results": [
                {"doc_id": doc_id, "score": score, "chunk_id": f"{doc_id}#0"}
                for doc_id, score in results
            ],
        },
    )


def _order_message(found: bool = True) -> ToolMessage:
    """Build a ToolMessage shaped like the order tool's output.

    Args:
        found: Whether the order was found.

    Returns:
        The message.
    """
    return ToolMessage(
        content="ordine",
        tool_call_id="ord",
        name="get_order_status",
        artifact={
            "tool": "get_order_status",
            "found": found,
            "order_id": "1042" if found else None,
        },
    )


def _escalation_message() -> ToolMessage:
    """Build a ToolMessage shaped like the escalation tool's output.

    Returns:
        The message.
    """
    return ToolMessage(
        content="ticket",
        tool_call_id="esc",
        name="escalate_to_human",
        artifact={
            "tool": "escalate_to_human",
            "escalated": True,
            "ticket_id": "ESC-0001",
            "reason": "refund_exception",
            "order_id": "1054",
            "session_id": "s",
            "created": True,
        },
    )


def _output(
    answer: str = "Risposta.",
    confidence: str = "high",
    cited: list[str] | None = None,
) -> AgentOutput:
    """Build an agent output.

    Args:
        answer: The answer text.
        confidence: The confidence the model proposes.
        cited: The documents the model claims to have used.

    Returns:
        The output.
    """
    return AgentOutput(
        answer=answer,
        proposed_confidence=confidence,  # type: ignore[arg-type]
        cited_sources=cited if cited is not None else [],
    )


# --- isolating the turn ---------------------------------------------------------------


def test_turn_starts_at_the_last_customer_message() -> None:
    """Citations must not be matched against documents retrieved three turns ago."""
    messages = [
        HumanMessage(content="primo turno"),
        _kb_message([(RETURNS, 0.90)]),
        AIMessage(content="risposta 1"),
        HumanMessage(content="secondo turno"),
        _kb_message([(BULBS, 0.88)]),
        AIMessage(content="risposta 2"),
    ]
    evidence = extract_turn_evidence(messages)
    assert evidence.retrieved_doc_ids == [BULBS]


def test_the_summary_is_not_mistaken_for_a_customer_message() -> None:
    """The summary is a HumanMessage, and taking it as the turn start would lose evidence."""
    summary = HumanMessage(
        content=f"{SUMMARY_TEXT_PREFIX}\n\nRiassunto.",
        additional_kwargs={"lc_source": SUMMARY_SOURCE_MARKER},
    )
    messages = [
        HumanMessage(content="domanda del cliente"),
        _kb_message([(BULBS, 0.88)]),
        AIMessage(content="risposta"),
    ]
    assert extract_turn_evidence([summary, *messages]).retrieved_doc_ids == [BULBS]
    assert len(messages_of_current_turn([summary, *messages])) == 3


def test_a_turn_without_a_customer_message_falls_back_to_everything() -> None:
    """Defensive: an unexpected shape must not silently drop the evidence."""
    messages = [_kb_message([(BULBS, 0.88)]), AIMessage(content="x")]
    assert extract_turn_evidence(messages).retrieval_ran is True


# --- reading the artifacts ------------------------------------------------------------


def test_evidence_is_read_from_artifacts_not_from_text() -> None:
    """Tool text is written for the model; the response layer reads structure (ADR-027)."""
    evidence = extract_turn_evidence(
        [HumanMessage(content="q"), _kb_message([(BULBS, 0.88), (RETURNS, 0.84)])]
    )
    assert [c.doc_id for c in evidence.retrieved] == [BULBS, RETURNS]
    assert [c.chunk_id for c in evidence.retrieved] == [f"{BULBS}#0", f"{RETURNS}#0"]


def test_several_chunks_of_one_document_collapse_to_one_source() -> None:
    """A customer wants the document cited once, not once per chunk."""
    message = _kb_message([(BULBS, 0.88), (BULBS, 0.86), (RETURNS, 0.84)])
    evidence = extract_turn_evidence([HumanMessage(content="q"), message])
    assert evidence.retrieved_doc_ids == [BULBS, RETURNS]


def test_tool_messages_without_artifacts_are_ignored() -> None:
    """A malformed artifact must not raise in front of a customer."""
    broken = ToolMessage(content="x", tool_call_id="t", name="search_knowledge_base")
    evidence = extract_turn_evidence([HumanMessage(content="q"), broken])
    assert evidence.retrieval_ran is False
    assert evidence.retrieved == []


def test_order_and_escalation_artifacts_are_recognised() -> None:
    """Each tool contributes a different fact to the turn's evidence."""
    evidence = extract_turn_evidence(
        [HumanMessage(content="q"), _order_message(), _escalation_message()]
    )
    assert evidence.order_lookup_succeeded is True
    assert evidence.escalated_in_turn is True
    assert evidence.retrieval_ran is False


# --- sources --------------------------------------------------------------------------


def test_invented_source_never_reaches_the_customer() -> None:
    """The point of ADR-002: a plausible-looking citation that does not exist."""
    evidence = extract_turn_evidence([HumanMessage(content="q"), _kb_message([(BULBS, 0.88)])])
    sources = resolve_sources([INVENTED], evidence)
    assert INVENTED not in sources


def test_citation_is_intersected_with_what_was_retrieved() -> None:
    """Citing one of four retrieved documents must yield exactly that one."""
    evidence = extract_turn_evidence(
        [HumanMessage(content="q"), _kb_message([(BULBS, 0.88), (RETURNS, 0.84)])]
    )
    assert resolve_sources([BULBS], evidence) == [BULBS]


def test_no_citation_falls_back_to_what_was_retrieved() -> None:
    """A model that answers well but cites nothing must not lose its sources (SPEC 5)."""
    evidence = extract_turn_evidence(
        [HumanMessage(content="q"), _kb_message([(BULBS, 0.88), (RETURNS, 0.84)])]
    )
    assert resolve_sources([], evidence) == [BULBS, RETURNS]


def test_entirely_invented_citations_fall_back_instead_of_emptying() -> None:
    """Nothing fabricated is emitted, but the real documents are not thrown away."""
    evidence = extract_turn_evidence([HumanMessage(content="q"), _kb_message([(BULBS, 0.88)])])
    assert resolve_sources([INVENTED, "products/inesistente.md"], evidence) == [BULBS]


def test_no_retrieval_means_no_sources() -> None:
    """Order data is not a source (SPEC 5), so an order-only turn cites nothing."""
    evidence = extract_turn_evidence([HumanMessage(content="q"), _order_message()])
    assert resolve_sources([BULBS], evidence) == []


def test_sources_keep_the_retrieval_ranking() -> None:
    """The best-matching document should be the first a customer sees."""
    evidence = extract_turn_evidence(
        [HumanMessage(content="q"), _kb_message([(RETURNS, 0.89), (BULBS, 0.84)])]
    )
    assert resolve_sources([], evidence) == [RETURNS, BULBS]


# --- confidence -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("best", "expected"),
    [(0.95, "high"), (HIGH, "high"), (0.84, "medium"), (LOW, "medium")],
)
def test_retrieval_quality_sets_the_cap(best: float, expected: str) -> None:
    """The cap follows the score bands calibrated in phase 2.

    Args:
        best: Best similarity of the turn.
        expected: The expected cap.
    """
    evidence = TurnEvidence(retrieval_ran=True, best_similarity=best)
    assert confidence_cap(evidence, LOW, HIGH) == expected


def test_retrieval_with_nothing_above_the_threshold_caps_low() -> None:
    """The engine always returns something; below the threshold it means nothing relevant."""
    evidence = TurnEvidence(retrieval_ran=True, best_similarity=0.74)
    assert confidence_cap(evidence, LOW, HIGH) == "low"


def test_order_only_turn_is_not_capped() -> None:
    """Order data is a structured source, exact by construction (SPEC 5)."""
    evidence = TurnEvidence(order_lookup_succeeded=True)
    assert confidence_cap(evidence, LOW, HIGH) == "high"


def test_turn_without_tools_caps_medium() -> None:
    """A refusal and an ungrounded claim look identical from here (ADR-058)."""
    assert confidence_cap(TurnEvidence(), LOW, HIGH) == "medium"


def test_escalation_does_not_touch_confidence() -> None:
    """ADR-007: confidence qualifies the answer, needs_human routes it."""
    grounded = TurnEvidence(retrieval_ran=True, best_similarity=0.90, escalated_in_turn=True)
    assert confidence_cap(grounded, LOW, HIGH) == "high"


def test_the_cap_can_only_lower_the_model_claim() -> None:
    """The model may be less sure than the scores suggest; it may not be more."""
    evidence = TurnEvidence(retrieval_ran=True, best_similarity=0.90)
    assert (
        build_chat_response(_output(confidence="low"), evidence, False, LOW, HIGH).confidence
        == "low"
    )
    assert (
        build_chat_response(_output(confidence="high"), evidence, False, LOW, HIGH).confidence
        == "high"
    )


def test_a_confident_model_over_weak_retrieval_is_lowered() -> None:
    """The case the cap exists for."""
    evidence = TurnEvidence(retrieval_ran=True, best_similarity=0.74)
    response = build_chat_response(_output(confidence="high"), evidence, False, LOW, HIGH)
    assert response.confidence == "low"


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("high", "low", "low"),
        ("low", "high", "low"),
        ("medium", "high", "medium"),
        ("high", "high", "high"),
    ],
)
def test_lower_of(first: str, second: str, expected: str) -> None:
    """The helper must be symmetric and order-independent.

    Args:
        first: One level.
        second: The other level.
        expected: The expected result.
    """
    assert lower_of(first, second) == expected  # type: ignore[arg-type]


# --- needs_human ----------------------------------------------------------------------


def test_needs_human_comes_from_the_caller_not_from_the_turn() -> None:
    """It is session-scoped and read from the register, not from this turn (ADR-008)."""
    evidence = TurnEvidence(retrieval_ran=True, best_similarity=0.90)
    assert build_chat_response(_output(), evidence, True, LOW, HIGH).needs_human is True
    assert build_chat_response(_output(), evidence, False, LOW, HIGH).needs_human is False


def test_escalation_in_the_turn_does_not_by_itself_set_the_flag() -> None:
    """The register decides, so a turn's evidence cannot contradict it."""
    evidence = extract_turn_evidence([HumanMessage(content="q"), _escalation_message()])
    assert evidence.escalated_in_turn is True
    assert build_chat_response(_output(), evidence, False, LOW, HIGH).needs_human is False


# --- the whole response ---------------------------------------------------------------


def test_response_has_exactly_the_four_contract_fields() -> None:
    """SPEC 5: the API body carries exactly these, as the assignment's example shows."""
    assert set(ChatResponse.model_fields) == {"answer", "confidence", "sources", "needs_human"}


def test_a_full_turn_assembles_correctly() -> None:
    """The assignment's own shape: an order plus a guide, cited and grounded."""
    messages = [
        HumanMessage(content="Quando arriva l'ordine 1042? Posso piantare i bulbi?"),
        _order_message(),
        _kb_message([(BULBS, 0.8722), (RETURNS, 0.82)]),
        AIMessage(content="ok"),
    ]
    evidence = extract_turn_evidence(messages)
    response = build_chat_response(
        _output(answer="L'ordine arriva domani.", confidence="high", cited=[BULBS]),
        evidence,
        needs_human=False,
        score_low=LOW,
        score_high=HIGH,
    )
    assert response.answer == "L'ordine arriva domani."
    assert response.confidence == "high"
    assert response.sources == [BULBS]
    assert response.needs_human is False


# --- the fallback ---------------------------------------------------------------------


def test_missing_structured_response_falls_back() -> None:
    """The iteration limit ends the run without one (ADR-050)."""
    output = output_from_state({"messages": []})
    assert output.proposed_confidence == "low"
    assert "operatore" in output.answer


def test_malformed_structured_response_falls_back() -> None:
    """A parsing failure must never become a 500 towards a customer (SPEC 5)."""
    output = output_from_state({"structured_response": {"answer": "x"}})
    assert output.proposed_confidence == "low"
    assert "operatore" in output.answer


def test_a_dict_matching_the_schema_is_accepted() -> None:
    """Serialisation round-trips can hand back a dictionary rather than the model."""
    output = output_from_state(
        {
            "structured_response": {
                "answer": "Risposta.",
                "proposed_confidence": "medium",
                "cited_sources": [BULBS],
            }
        }
    )
    assert output.answer == "Risposta."
    assert output.cited_sources == [BULBS]


def test_fallback_produces_a_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even the worst turn must satisfy the contract the API promises.

    Args:
        monkeypatch: Unused, present to document that no patching is needed.
    """
    response = build_chat_response(
        output_from_state({}), TurnEvidence(), needs_human=True, score_low=LOW, score_high=HIGH
    )
    assert isinstance(response, ChatResponse)
    assert response.confidence == "low"
    assert response.sources == []
    assert response.needs_human is True


def test_evidence_survives_an_unexpected_artifact_type() -> None:
    """A tool returning a list instead of a dict must not break the turn."""
    odd: Any = ToolMessage(
        content="x", tool_call_id="t", name="search_knowledge_base", artifact=["not", "a", "dict"]
    )
    evidence = extract_turn_evidence([HumanMessage(content="q"), odd])
    assert evidence.retrieval_ran is False
