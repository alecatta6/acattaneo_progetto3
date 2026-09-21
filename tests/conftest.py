"""Shared test fixtures.

The central concern is environment isolation, and it has bitten three times.

1. Importing ``deepeval`` calls ``load_dotenv()`` as a side effect, and its pytest plugin
   loads automatically, so the developer's ``.env`` landed in ``os.environ`` for the whole
   session (ADR-025).
2. Even with the environment clean, ``Settings`` reads ``.env`` from disk by itself, so a
   stale threshold in that file failed tests that had nothing to do with it (ADR-043).
3. Module-scoped fixtures run before function-scoped ones, so per-test isolation arrived
   too late for any fixture that reads configuration at module scope.

Hence a session-scoped fixture that detaches Settings from the file once, before anything
else runs, plus a per-test one that keeps the environment clean between tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from greenthumb.config import Settings, get_settings

# Names that must never reach a unit test from the ambient environment.
_LEAKY_PREFIXES = ("GREENTHUMB_",)
_LEAKY_NAMES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")


def _strip_leaky_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove project configuration from the process environment.

    Args:
        monkeypatch: The patcher to record the removals against.
    """
    for name in list(os.environ):
        if name.startswith(_LEAKY_PREFIXES) or name in _LEAKY_NAMES:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session", autouse=True)
def detach_from_local_configuration() -> Iterator[None]:
    """Detach the whole session from the developer's .env file.

    Session scope is deliberate: module-scoped fixtures that read configuration run before
    any function-scoped fixture, so isolation applied per test would arrive too late.

    Yields:
        None. The patches are undone when the session ends.
    """
    patcher = pytest.MonkeyPatch()
    _strip_leaky_variables(patcher)
    patcher.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    patcher.undo()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the environment clean between individual tests.

    Args:
        monkeypatch: Pytest fixture used to remove environment variables.

    Yields:
        None. The environment is restored by monkeypatch on teardown.
    """
    _strip_leaky_variables(monkeypatch)
    yield
