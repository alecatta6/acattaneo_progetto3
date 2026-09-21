"""Time source for the agent.

The system never reads the wall clock directly. Every date-dependent behaviour — order
delivery estimates, seasonal advice, escalation timestamps — goes through an injected
``Clock``. This keeps the simulated business date (ADR-003) consistent no matter when the
delivery notebook is executed.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

# Meteorological seasons for the northern hemisphere, keyed by starting month.
_SEASON_BY_MONTH: dict[int, str] = {
    1: "inverno",
    2: "inverno",
    3: "primavera",
    4: "primavera",
    5: "primavera",
    6: "estate",
    7: "estate",
    8: "estate",
    9: "autunno",
    10: "autunno",
    11: "autunno",
    12: "inverno",
}


@runtime_checkable
class Clock(Protocol):
    """Source of the current business date.

    Implementations must be side-effect free and cheap to call: the agent queries the
    clock on every turn to inject the date into the system prompt.
    """

    def today(self) -> dt.date:
        """Return the current business date.

        Returns:
            The date the system should treat as "today".
        """
        ...


class FrozenClock:
    """Clock pinned to a fixed date, used in tests, evaluation and the delivery notebook."""

    def __init__(self, today: dt.date) -> None:
        """Initialise the clock.

        Args:
            today: The date this clock always reports.
        """
        self._today = today

    def today(self) -> dt.date:
        """Return the pinned date.

        Returns:
            The date supplied at construction time.
        """
        return self._today

    def __repr__(self) -> str:
        """Return a debug representation naming the pinned date.

        Returns:
            A string such as ``FrozenClock(2026-10-12)``.
        """
        return f"FrozenClock({self._today.isoformat()})"


class SystemClock:
    """Clock backed by the real system date, for genuine production use."""

    def today(self) -> dt.date:
        """Return the real current date.

        Returns:
            Today's date according to the host system.
        """
        return dt.date.today()

    def __repr__(self) -> str:
        """Return a debug representation.

        Returns:
            The string ``SystemClock()``.
        """
        return "SystemClock()"


def season_of(date: dt.date) -> str:
    """Return the meteorological season for a date, in Italian.

    Seasons drive agronomic advice ("can I plant bulbs now?"), so they are computed from
    the business date rather than asked of the model.

    Args:
        date: The date to classify.

    Returns:
        One of ``"inverno"``, ``"primavera"``, ``"estate"``, ``"autunno"``.
    """
    return _SEASON_BY_MONTH[date.month]


def describe_delta(target: dt.date, today: dt.date) -> str:
    """Describe a date relative to the business date, in Italian.

    Date arithmetic is done here rather than by the LLM, which is unreliable at it. Used by
    the order tool to render delivery estimates as "domani" or "3 giorni fa".

    Args:
        target: The date to describe.
        today: The current business date.

    Returns:
        A short Italian phrase such as ``"oggi"``, ``"domani"``, ``"fra 5 giorni"``,
        ``"ieri"`` or ``"3 giorni fa"``.
    """
    delta = (target - today).days
    if delta == 0:
        return "oggi"
    if delta == 1:
        return "domani"
    if delta == -1:
        return "ieri"
    if delta > 1:
        return f"fra {delta} giorni"
    return f"{abs(delta)} giorni fa"
