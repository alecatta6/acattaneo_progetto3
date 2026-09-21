"""Shared test fixtures.

The central concern here is environment isolation. Importing ``deepeval`` calls
``load_dotenv()`` as a side effect, and its pytest plugin loads automatically, so the
developer's real ``.env`` leaks into ``os.environ`` for every test in the session. That
makes unit tests depend on local configuration and on whoever happens to have a ``.env``
(see ADR-025). The plugin is disabled in ``pyproject.toml``; this fixture is the second
line of defence, so a future plugin doing the same thing cannot silently break isolation.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Names that must never reach a unit test from the ambient environment.
_LEAKY_PREFIXES = ("GREENTHUMB_",)
_LEAKY_NAMES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip project configuration from the environment for the duration of a test.

    Args:
        monkeypatch: Pytest fixture used to remove environment variables.

    Yields:
        None. The environment is restored by monkeypatch on teardown.
    """
    for name in list(os.environ):
        if name.startswith(_LEAKY_PREFIXES) or name in _LEAKY_NAMES:
            monkeypatch.delenv(name, raising=False)
    yield
