"""Tests for the injected time source."""

from __future__ import annotations

import datetime as dt

import pytest

from greenthumb.clock import Clock, FrozenClock, SystemClock, describe_delta, season_of

BUSINESS_DATE = dt.date(2026, 10, 12)


def test_frozen_clock_always_returns_the_pinned_date() -> None:
    """A frozen clock must not drift between calls."""
    clock = FrozenClock(BUSINESS_DATE)
    assert clock.today() == BUSINESS_DATE
    assert clock.today() == BUSINESS_DATE


def test_system_clock_returns_the_real_date() -> None:
    """The system clock must agree with the host date."""
    assert SystemClock().today() == dt.date.today()


@pytest.mark.parametrize("implementation", [FrozenClock(BUSINESS_DATE), SystemClock()])
def test_implementations_satisfy_the_protocol(implementation: object) -> None:
    """Both clocks must be usable wherever a Clock is expected.

    Args:
        implementation: The clock implementation under test.
    """
    assert isinstance(implementation, Clock)


@pytest.mark.parametrize(
    ("month", "expected"),
    [(1, "inverno"), (3, "primavera"), (7, "estate"), (10, "autunno"), (12, "inverno")],
)
def test_season_of_maps_each_month(month: int, expected: str) -> None:
    """Season lookup must cover the whole year.

    Args:
        month: The month to classify.
        expected: The expected Italian season name.
    """
    assert season_of(dt.date(2026, month, 15)) == expected


def test_default_business_date_falls_in_autumn() -> None:
    """ADR-003 relies on the default date being autumn, so bulb questions are in season."""
    assert season_of(BUSINESS_DATE) == "autunno"


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(0, "oggi"), (1, "domani"), (-1, "ieri"), (5, "fra 5 giorni"), (-3, "3 giorni fa")],
)
def test_describe_delta_renders_relative_dates(offset: int, expected: str) -> None:
    """Relative dates are computed in code, never left to the model.

    Args:
        offset: Days between the target date and the business date.
        expected: The expected Italian phrase.
    """
    target = BUSINESS_DATE + dt.timedelta(days=offset)
    assert describe_delta(target, BUSINESS_DATE) == expected
