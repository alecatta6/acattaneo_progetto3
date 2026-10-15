"""Tests for the evaluation dataset.

``eval/conversations.jsonl`` is ground truth: every metric of SPEC section 10.3 is scored
against it. A wrong ``doc_id`` or an order number that does not exist would not raise
anywhere — it would silently depress source recall or make a reference answer unverifiable,
and the report would read as a finding about the agent rather than about the dataset. These
tests therefore check the dataset against the real knowledge base and the real orders,
rather than against a copy of the expectations (ADR-063).
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from greenthumb.config import REPO_ROOT
from greenthumb.kb_loader import load_knowledge_base
from greenthumb.orders_repository import OrdersRepository
from greenthumb.tools.escalation_tool import TOOL_NAME as ESCALATION_TOOL
from greenthumb.tools.knowledge_base_tool import TOOL_NAME as KB_TOOL
from greenthumb.tools.order_status_tool import TOOL_NAME as ORDER_TOOL

DATASET_PATH = REPO_ROOT / "eval" / "conversations.jsonl"

# SPEC section 10.1, with the redistribution of ADR-016.
EXPECTED_DISTRIBUTION = {
    "product_info": 3,
    "agronomic_advice": 3,
    "order_status": 2,
    "returns_policy": 2,
    "multi_tool": 3,
    "escalation": 3,
    "memory": 2,
    "edge_cases": 2,
}

TOOL_NAMES = frozenset({KB_TOOL, ORDER_TOOL, ESCALATION_TOOL})

TURN_KEYS = frozenset(
    {"user", "reference_answer", "expected_sources", "expected_tools", "expected_needs_human"}
)

# Sized by measurement, not by estimate. The first evaluation run showed summarization
# never firing on conversations of six and seven turns: real turns add ~600 tokens, not the
# ~1000 ADR-056 assumed. With the re-calibrated 6000-token trigger the summarizer fires
# around the eighth turn, so a ``memory`` conversation shorter than nine turns would again
# test a mechanism that never ran — the mistake of ADR-028, in its third form (ADR-072).
MEMORY_MIN_TURNS = 9


@pytest.fixture(scope="module")
def conversations() -> list[dict[str, Any]]:
    """Load the dataset once.

    Returns:
        One dictionary per conversation, in file order.

    Raises:
        AssertionError: If a line is not valid JSON.
    """
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    parsed: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        assert line.strip(), f"line {number} is empty: JSONL allows no blank lines"
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as error:  # pragma: no cover - fails the suite anyway
            raise AssertionError(f"line {number} is not valid JSON: {error}") from error
    return parsed


@pytest.fixture(scope="module")
def known_doc_ids() -> frozenset[str]:
    """Collect every doc_id present in the knowledge base.

    Returns:
        The identifiers, in the single representation of ADR-006.
    """
    return frozenset(doc.doc_id for doc in load_knowledge_base(REPO_ROOT / "data" / "kb"))


@pytest.fixture(scope="module")
def orders() -> OrdersRepository:
    """Load the generated orders once.

    Returns:
        The repository backing ``get_order_status``.
    """
    return OrdersRepository.from_file(REPO_ROOT / "data" / "orders.json")


def _turns(conversations: list[dict[str, Any]]) -> list[tuple[str, int, dict[str, Any]]]:
    """Flatten the dataset into addressable turns.

    Args:
        conversations: The parsed dataset.

    Returns:
        Triples of conversation id, one-based turn number and the turn itself.
    """
    return [
        (conversation["conversation_id"], number, turn)
        for conversation in conversations
        for number, turn in enumerate(conversation["turns"], start=1)
    ]


def test_requirement_r6_minimum_size(conversations: list[dict[str, Any]]) -> None:
    """The dataset meets the fifteen-conversation floor of requirement R6."""
    assert len(conversations) >= 15


def test_distribution_matches_the_specification(conversations: list[dict[str, Any]]) -> None:
    """Every category holds the number of conversations SPEC section 10.1 assigns it."""
    counts: dict[str, int] = {}
    for conversation in conversations:
        counts[conversation["category"]] = counts.get(conversation["category"], 0) + 1
    assert counts == EXPECTED_DISTRIBUTION


def test_conversation_ids_are_unique_and_well_formed(
    conversations: list[dict[str, Any]],
) -> None:
    """Identifiers are unique and follow the ``conv_NN`` shape used in the traces."""
    ids = [conversation["conversation_id"] for conversation in conversations]
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"conv_\d{2}", identifier) for identifier in ids)


def test_every_turn_carries_exactly_the_expected_keys(
    conversations: list[dict[str, Any]],
) -> None:
    """No turn is missing a field, and none carries an unread extra one."""
    for conversation_id, number, turn in _turns(conversations):
        assert set(turn) == TURN_KEYS, f"{conversation_id} turn {number}"


def test_at_least_six_conversations_are_multi_turn(
    conversations: list[dict[str, Any]],
) -> None:
    """SPEC section 10.1 requires at least six multi-turn conversations."""
    multi_turn = [c for c in conversations if len(c["turns"]) > 1]
    assert len(multi_turn) >= 6


def test_memory_conversations_are_long_enough_to_trigger_summarization(
    conversations: list[dict[str, Any]],
) -> None:
    """A ``memory`` conversation must be long enough for the summarizer to fire."""
    for conversation in conversations:
        if conversation["category"] != "memory":
            continue
        assert len(conversation["turns"]) >= MEMORY_MIN_TURNS, conversation["conversation_id"]


def test_expected_sources_exist_in_the_knowledge_base(
    conversations: list[dict[str, Any]], known_doc_ids: frozenset[str]
) -> None:
    """Every expected source is a real document.

    A typo here would depress source recall without raising anywhere, and the report would
    blame the retrieval for a defect of the dataset.
    """
    for conversation_id, number, turn in _turns(conversations):
        for doc_id in turn["expected_sources"]:
            assert doc_id in known_doc_ids, f"{conversation_id} turn {number}: {doc_id}"


def test_expected_tools_are_real_tool_names(conversations: list[dict[str, Any]]) -> None:
    """Every expected tool is one of the three the agent actually exposes."""
    for conversation_id, number, turn in _turns(conversations):
        for tool in turn["expected_tools"]:
            assert tool in TOOL_NAMES, f"{conversation_id} turn {number}: {tool}"


def test_order_numbers_mentioned_by_the_customer_exist(
    conversations: list[dict[str, Any]], orders: OrdersRepository
) -> None:
    """Four-digit numbers in a customer message resolve to a real order.

    The one exception is the deliberately missing order of the ``edge_cases``
    conversation, which must *not* exist for the case to mean anything.
    """
    missing_on_purpose = {"9999"}
    for conversation_id, number, turn in _turns(conversations):
        for candidate in re.findall(r"\b\d{4}\b", turn["user"]):
            if candidate in missing_on_purpose:
                assert orders.get(candidate) is None, f"order {candidate} should not exist"
                continue
            assert orders.get(candidate) is not None, (
                f"{conversation_id} turn {number} cites unknown order {candidate}"
            )


def test_a_turn_that_expects_the_escalation_tool_expects_the_flag(
    conversations: list[dict[str, Any]],
) -> None:
    """Calling the escalation tool and ``needs_human`` cannot disagree (ADR-002)."""
    for conversation_id, number, turn in _turns(conversations):
        if ESCALATION_TOOL in turn["expected_tools"]:
            assert turn["expected_needs_human"] is True, f"{conversation_id} turn {number}"


def test_needs_human_never_goes_back_to_false_within_a_conversation(
    conversations: list[dict[str, Any]],
) -> None:
    """``needs_human`` has session semantics, so it is monotonic (ADR-008)."""
    for conversation in conversations:
        flags = [turn["expected_needs_human"] for turn in conversation["turns"]]
        assert flags == sorted(flags), conversation["conversation_id"]


def test_the_escalation_category_covers_every_reason_of_the_enum(
    conversations: list[dict[str, Any]],
) -> None:
    """The dataset exercises escalation often enough to cover the seven reasons.

    The reasons themselves are chosen by the model at run time, so the dataset cannot
    assert them directly. What it can guarantee is the budget: ADR-016 raised the category
    to three conversations precisely so that the enum could be covered, and the turns that
    must escalate are spread across ``escalation`` and ``edge_cases``.
    """
    escalating = [
        (conversation["category"], number)
        for conversation in conversations
        for number, turn in enumerate(conversation["turns"], start=1)
        if ESCALATION_TOOL in turn["expected_tools"]
    ]
    assert len(escalating) >= 7
    categories = {category for category, _ in escalating}
    # ``memory`` escalates too, on purpose: it is how the dataset checks that the flag
    # survives summarization (ADR-008).
    assert {"escalation", "edge_cases"} <= categories


def test_the_first_attempt_on_a_missing_order_does_not_escalate(
    conversations: list[dict[str, Any]],
) -> None:
    """ADR-011: the first miss asks for confirmation, the confirmed second one escalates."""
    conversation = next(
        c for c in conversations if any("9999" in turn["user"] for turn in c["turns"])
    )
    first, second = conversation["turns"][0], conversation["turns"][1]
    assert first["expected_needs_human"] is False
    assert ESCALATION_TOOL not in first["expected_tools"]
    assert second["expected_needs_human"] is True
    assert ESCALATION_TOOL in second["expected_tools"]


def test_order_data_is_never_declared_a_source(conversations: list[dict[str, Any]]) -> None:
    """Order details are structured data, not a knowledge-base source (SPEC section 5)."""
    for conversation_id, number, turn in _turns(conversations):
        if turn["expected_tools"] == [ORDER_TOOL]:
            assert turn["expected_sources"] == [], f"{conversation_id} turn {number}"


def test_a_turn_expecting_sources_also_expects_the_retrieval_tool(
    conversations: list[dict[str, Any]],
) -> None:
    """Sources can only come from retrieval, so the two expectations travel together."""
    for conversation_id, number, turn in _turns(conversations):
        if turn["expected_sources"]:
            assert KB_TOOL in turn["expected_tools"], f"{conversation_id} turn {number}"


def test_reference_answers_are_substantial(conversations: list[dict[str, Any]]) -> None:
    """Reference answers carry enough content for a judge to score against.

    A one-line reference would make RAGAS context precision and the GEval criteria score
    noise rather than behaviour.
    """
    for conversation_id, number, turn in _turns(conversations):
        words = len(turn["reference_answer"].split())
        assert 10 <= words <= 200, f"{conversation_id} turn {number}: {words} words"


def test_no_reference_answer_leaks_internal_details(
    conversations: list[dict[str, Any]],
) -> None:
    """The customer never reads tool names, scores or doc_id paths (SPEC section 8)."""
    forbidden = (*TOOL_NAMES, "doc_id", "confidence", "needs_human", ".md")
    for conversation_id, number, turn in _turns(conversations):
        for token in forbidden:
            assert token not in turn["reference_answer"], (
                f"{conversation_id} turn {number} leaks {token!r}"
            )
