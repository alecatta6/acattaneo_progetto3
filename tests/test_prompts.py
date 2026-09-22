"""Tests for the system prompt. Pure string work, no LLM and no environment."""

from __future__ import annotations

import datetime as dt
import typing

import pytest

from greenthumb.escalations_repository import EscalationReason
from greenthumb.prompts import (
    ESCALATION_CRITERIA,
    build_system_prompt,
    format_date_italian,
    format_escalation_criteria,
)
from greenthumb.tools.escalation_tool import TOOL_NAME as ESCALATION_TOOL
from greenthumb.tools.knowledge_base_tool import TOOL_NAME as KB_TOOL
from greenthumb.tools.order_status_tool import TOOL_NAME as ORDER_TOOL

AUTUMN = dt.date(2026, 10, 12)


# --- date and season ------------------------------------------------------------------


def test_business_date_appears_in_both_forms() -> None:
    """The model needs the human form to write it and the ISO form to reason with it."""
    prompt = build_system_prompt(AUTUMN)
    assert "12 ottobre 2026" in prompt
    assert "2026-10-12" in prompt


def test_season_is_derived_not_hardcoded() -> None:
    """Seasonal advice depends on the date, so the season must follow it."""
    assert "autunno" in build_system_prompt(AUTUMN)
    assert "primavera" in build_system_prompt(dt.date(2026, 4, 3))
    assert "inverno" in build_system_prompt(dt.date(2027, 1, 15))


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        (dt.date(2026, 10, 12), "12 ottobre 2026"),
        (dt.date(2026, 1, 1), "1 gennaio 2026"),
        (dt.date(2026, 12, 31), "31 dicembre 2026"),
    ],
)
def test_italian_date_formatting(date: dt.date, expected: str) -> None:
    """Dates are written the way an Italian reader expects them.

    Args:
        date: The date to render.
        expected: The expected rendering.
    """
    assert format_date_italian(date) == expected


def test_prompt_changes_with_the_date() -> None:
    """A prompt fixed at construction time would freeze the date (ADR-027)."""
    assert build_system_prompt(AUTUMN) != build_system_prompt(dt.date(2026, 4, 3))


# --- escalation criteria --------------------------------------------------------------


def test_every_enum_value_is_explained_to_the_model() -> None:
    """A criterion the tool accepts but the prompt never mentions is unreachable."""
    declared = set(typing.get_args(EscalationReason))
    assert set(ESCALATION_CRITERIA) == declared


def test_criteria_are_rendered_with_their_enum_value() -> None:
    """The model must write the exact enum value, not a paraphrase of it."""
    rendered = format_escalation_criteria()
    for reason in ESCALATION_CRITERIA:
        assert f"`{reason}`" in rendered


def test_out_of_scope_is_explicitly_not_an_escalation() -> None:
    """SPEC 8: out-of-scope questions get a polite refusal, never a ticket."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "fuori ambito" in flat
    assert "non aprire alcun ticket" in flat


def test_first_failed_lookup_does_not_escalate() -> None:
    """ADR-011: escalate only after the customer confirms the number a second time."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "primo** tentativo, non escalare" in flat or "primo tentativo, non escalare" in flat


# --- grounding ------------------------------------------------------------------------


def test_each_tool_is_named_with_its_exclusive_domain() -> None:
    """The model must not look for order data in the knowledge base, or the reverse."""
    prompt = build_system_prompt(AUTUMN)
    assert KB_TOOL in prompt
    assert ORDER_TOOL in prompt
    assert ESCALATION_TOOL in prompt


def test_grounding_forbids_falling_back_on_general_knowledge() -> None:
    """The knowledge base holds facts that differ from any other shop's."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "conoscenza generale" in flat
    assert "Non inventare mai" in flat


def test_prompt_asks_for_multi_tool_decomposition() -> None:
    """The assignment's own example needs two tools in one turn (SPEC 8, point 4)."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "piu' di uno strumento" in flat
    assert "a tutte le parti" in flat


def test_prompt_requires_asking_when_the_order_number_is_missing() -> None:
    """SPEC 8, point 5: ask before acting on an ambiguous request."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "senza dare il numero" in flat


# --- output discipline ----------------------------------------------------------------


def test_internal_details_are_forbidden_in_the_answer() -> None:
    """SPEC 8, point 7: the customer must not read about tools or scores."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "Non nominare mai gli strumenti" in flat
    assert "punteggi di ricerca" in flat


def test_structured_fields_are_explained() -> None:
    """cited_sources feeds the deterministic intersection, so its form matters (ADR-002)."""
    flat = " ".join(build_system_prompt(AUTUMN).split())
    assert "cited_sources" in flat
    assert "proposed_confidence" in flat
    assert "Lista vuota" in flat


def test_prompt_is_written_in_italian() -> None:
    """User-facing content is Italian; an English prompt invites English answers."""
    prompt = build_system_prompt(AUTUMN)
    for marker in ("Ruolo", "Data di oggi", "Come scrivere la risposta"):
        assert marker in prompt


def test_prompt_stays_within_a_reasonable_size() -> None:
    """Every turn pays for the prompt, and an unread instruction is worse than none."""
    words = len(build_system_prompt(AUTUMN).split())
    assert 400 <= words <= 1000, f"{words} parole"
