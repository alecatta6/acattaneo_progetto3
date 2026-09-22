"""Deterministic assembly of the response.

This module is where ADR-002 becomes code. The model writes ``answer`` and proposes two
values; everything else is derived from what the turn actually did, read from the tool
artifacts rather than from anything the model says about itself.

Three derivations, each with a reason to exist:

* **``sources``** are intersected with the documents retrieval really returned. A model that
  cites a plausible-looking ``policies/garanzie.md`` that does not exist would otherwise put
  a fabricated citation in front of a customer.
* **``needs_human``** is read from the escalation register for the session, not from the
  model's opinion, and stays true for the rest of the conversation once a ticket exists
  (ADR-008).
* **``confidence``** can only be lowered by the deterministic layer, never raised. The model
  is allowed to be less sure than the retrieval scores suggest; it is not allowed to be more.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from greenthumb.memory import SUMMARY_SOURCE_MARKER, SUMMARY_TEXT_PREFIX
from greenthumb.schemas import AgentOutput, ChatResponse, Confidence

KNOWLEDGE_BASE_TOOL = "search_knowledge_base"
ORDER_TOOL = "get_order_status"
ESCALATION_TOOL = "escalate_to_human"

# Ordered from most to least confident, so "the lower of two" is a min() on the index.
_CONFIDENCE_ORDER: tuple[Confidence, ...] = ("high", "medium", "low")


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk retrieval returned above the relevance threshold.

    Attributes:
        doc_id: Identifier of the source document, extension included.
        score: Cosine similarity, as computed by ``retrieval.search``.
        chunk_id: Identifier of the chunk within its document.
        text: The chunk text, which the evaluation scores faithfulness against.
    """

    doc_id: str
    score: float
    chunk_id: str
    text: str = ""


@dataclass(frozen=True)
class TurnEvidence:
    """What the tools actually did during one turn.

    Attributes:
        retrieved: Chunks above the threshold, in the order retrieval ranked them.
        best_similarity: Best score seen, including below the threshold, or None when
            retrieval did not run.
        retrieval_ran: Whether the knowledge base was searched at all.
        order_lookup_succeeded: Whether an order was found.
        escalated_in_turn: Whether a ticket was opened or reused during this turn.
    """

    retrieved: list[RetrievedChunk] = field(default_factory=list)
    best_similarity: float | None = None
    retrieval_ran: bool = False
    order_lookup_succeeded: bool = False
    escalated_in_turn: bool = False

    @property
    def retrieved_doc_ids(self) -> list[str]:
        """Return the distinct documents retrieved, best score first.

        Several chunks of one document are common, and a customer wants the document cited
        once.

        Returns:
            The document identifiers, deduplicated, ranking order preserved.
        """
        seen: dict[str, None] = {}
        for chunk in self.retrieved:
            seen.setdefault(chunk.doc_id, None)
        return list(seen)


def _is_summary(message: BaseMessage) -> bool:
    """Report whether a message is the injected conversation summary.

    Args:
        message: The message to classify.

    Returns:
        True when the message is a summary rather than something the customer wrote.
    """
    if not isinstance(message, HumanMessage):
        return False
    if (message.additional_kwargs or {}).get("lc_source") == SUMMARY_SOURCE_MARKER:
        return True
    return str(message.content).startswith(SUMMARY_TEXT_PREFIX)


def messages_of_current_turn(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Return the messages belonging to the turn that just ran.

    The agent state holds the whole conversation, so the evidence for *this* turn has to be
    isolated: intersecting citations against documents retrieved three turns ago would let a
    stale source reach the customer. A turn starts at the last message the customer actually
    wrote, which is the last ``HumanMessage`` that is not the injected summary.

    Args:
        messages: The messages from the agent state.

    Returns:
        The messages from the customer's last message onwards, or all of them when no
        customer message is present.
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, HumanMessage) and not _is_summary(message):
            return list(messages[index:])
    return list(messages)


def extract_turn_evidence(messages: Sequence[BaseMessage]) -> TurnEvidence:
    """Read what the tools did, from the artifacts of the current turn.

    Artifacts are structured records the tools attach to their ``ToolMessage``, so nothing
    here parses the text the model was shown (ADR-027).

    Args:
        messages: The messages from the agent state.

    Returns:
        The evidence for the turn that just ran.
    """
    retrieved: list[RetrievedChunk] = []
    best_similarity: float | None = None
    retrieval_ran = False
    order_found = False
    escalated = False

    for message in messages_of_current_turn(messages):
        if not isinstance(message, ToolMessage):
            continue
        artifact = message.artifact
        if not isinstance(artifact, dict):
            continue

        tool = artifact.get("tool")
        if tool == KNOWLEDGE_BASE_TOOL:
            retrieval_ran = True
            candidate = artifact.get("best_similarity")
            if isinstance(candidate, (int, float)):
                best_similarity = max(best_similarity or 0.0, float(candidate))
            for entry in artifact.get("results") or []:
                retrieved.append(
                    RetrievedChunk(
                        doc_id=str(entry["doc_id"]),
                        score=float(entry["score"]),
                        chunk_id=str(entry["chunk_id"]),
                        text=str(entry.get("text", "")),
                    )
                )
        elif tool == ORDER_TOOL:
            order_found = order_found or bool(artifact.get("found"))
        elif tool == ESCALATION_TOOL:
            escalated = escalated or bool(artifact.get("escalated"))

    return TurnEvidence(
        retrieved=retrieved,
        best_similarity=best_similarity,
        retrieval_ran=retrieval_ran,
        order_lookup_succeeded=order_found,
        escalated_in_turn=escalated,
    )


def resolve_sources(cited: Sequence[str], evidence: TurnEvidence) -> list[str]:
    """Reconcile what the model cited with what retrieval returned.

    Args:
        cited: The identifiers the model claims to have used.
        evidence: What the tools did this turn.

    Returns:
        The documents to show the customer, in retrieval ranking order.
    """
    available = evidence.retrieved_doc_ids
    if not available:
        return []

    intersection = [doc_id for doc_id in available if doc_id in set(cited)]
    if intersection:
        return intersection

    # Either the model cited nothing, or it cited only documents that do not exist. Both
    # end here: a fabricated identifier never reaches the customer, and the documents the
    # answer was actually built from are not lost (SPEC section 5).
    return available


def confidence_cap(evidence: TurnEvidence, score_low: float, score_high: float) -> Confidence:
    """Compute the highest confidence the turn's evidence can justify.

    Args:
        evidence: What the tools did this turn.
        score_low: Minimum similarity for a document to count as relevant.
        score_high: Similarity at or above which retrieval quality allows high confidence.

    Returns:
        The cap. Escalation deliberately plays no part: confidence qualifies the answer,
        ``needs_human`` routes it (ADR-007).
    """
    if evidence.retrieval_ran:
        best = evidence.best_similarity
        if best is None or best < score_low:
            return "low"
        return "high" if best >= score_high else "medium"

    if evidence.order_lookup_succeeded:
        # A structured source, exact by construction: no cap (SPEC section 5).
        return "high"

    # No tool ran. Either a refusal or a clarifying question, both legitimate, or the model
    # answered from its own knowledge, which the prompt forbids. The two are
    # indistinguishable from here, so the cautious reading applies (ADR-058).
    return "medium"


def lower_of(first: Confidence, second: Confidence) -> Confidence:
    """Return the less confident of two levels.

    Args:
        first: One level.
        second: The other.

    Returns:
        The lower of the two.
    """
    return _CONFIDENCE_ORDER[max(_CONFIDENCE_ORDER.index(first), _CONFIDENCE_ORDER.index(second))]


def build_chat_response(
    output: AgentOutput,
    evidence: TurnEvidence,
    needs_human: bool,
    score_low: float,
    score_high: float,
) -> ChatResponse:
    """Assemble the response the API returns.

    Args:
        output: What the model produced.
        evidence: What the tools did this turn.
        needs_human: Whether the session holds an escalation ticket (ADR-008).
        score_low: Minimum similarity for a document to count as relevant.
        score_high: Similarity at or above which high confidence is allowed.

    Returns:
        The validated response.
    """
    return ChatResponse(
        answer=output.answer,
        confidence=lower_of(
            output.proposed_confidence, confidence_cap(evidence, score_low, score_high)
        ),
        sources=resolve_sources(output.cited_sources, evidence),
        needs_human=needs_human,
    )


def output_from_state(state: dict[str, Any]) -> AgentOutput:
    """Read the structured output, falling back when it is absent or malformed.

    The iteration limit ends the run without producing one (ADR-050), and a parsing failure
    would otherwise surface as a 500 towards a customer, which SPEC section 5 forbids.

    Args:
        state: The state returned by the agent.

    Returns:
        The model's output, or the courteous fallback.
    """
    from greenthumb.agent import fallback_output

    candidate = state.get("structured_response")
    if isinstance(candidate, AgentOutput):
        return candidate
    if isinstance(candidate, dict):
        try:
            return AgentOutput.model_validate(candidate)
        except ValueError:
            return fallback_output()
    return fallback_output()
