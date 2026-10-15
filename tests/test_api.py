"""Tests for the FastAPI deployment, with a stubbed service and no LLM.

The contract under test is narrow and explicit: the body of ``POST /chat`` carries exactly
four fields, and everything else the caller needs rides in headers (SPEC section 11,
ADR-009). These tests therefore assert on the *shape* of the body as much as on its
content, because an extra field would break the assignment's contract just as surely as a
wrong answer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from greenthumb.api import (
    FALLBACK_HEADER,
    MAX_MESSAGE_LENGTH,
    SESSION_HEADER,
    app,
    current_settings,
)
from greenthumb.config import Settings
from greenthumb.schemas import ChatResponse
from greenthumb.service import ChatTurn

CONTRACT_FIELDS = {"answer", "confidence", "sources", "needs_human"}


class StubService:
    """A chat service that answers from a script, so the API can be tested offline."""

    def __init__(
        self,
        response: ChatResponse | None = None,
        fallback: bool = False,
        raises: Exception | None = None,
    ) -> None:
        """Bind the stub to its scripted behaviour.

        Args:
            response: The response to return; a nominal one when omitted.
            fallback: Whether to report the turn as a provider fallback.
            raises: When given, raised instead of answering.
        """
        self._response = response or ChatResponse(
            answer="I bulbi di tulipano si piantano da meta' ottobre a fine novembre.",
            confidence="high",
            sources=["guides/bulbi_autunnali.md"],
            needs_human=False,
        )
        self._fallback = fallback
        self._raises = raises
        self.calls: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def chat_detailed(self, message: str, session_id: str) -> ChatTurn:
        """Return the scripted turn.

        Args:
            message: What the customer wrote.
            session_id: The conversation identifier.

        Returns:
            The scripted turn.

        Raises:
            Exception: Whatever the stub was configured to raise.
        """
        self.calls.append((message, session_id))
        if self._raises is not None:
            raise self._raises
        return ChatTurn(response=self._response, session_id=session_id, fallback=self._fallback)

    def reset_session(self, session_id: str) -> None:
        """Record the deletion.

        Args:
            session_id: The conversation to forget.
        """
        self.deleted.append(session_id)


@pytest.fixture
def stub() -> StubService:
    """Return a nominal stub service.

    Returns:
        The stub.
    """
    return StubService()


@pytest.fixture
def client(stub: StubService) -> Any:
    """Return a test client wired to the stub, with the real agent never built.

    Args:
        stub: The scripted service.

    Yields:
        The configured client.
    """
    app.state.service = stub
    app.dependency_overrides[current_settings] = lambda: Settings(
        _env_file=None,
        llm_model="test/model",
        today=dt.date(2026, 10, 12),
        retrieval_score_low=0.813,
        retrieval_score_high=0.863,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.state.service = None


# --- The four-field contract ----------------------------------------------------------


def test_chat_returns_exactly_the_four_contract_fields(client: Any) -> None:
    """An extra field would break the contract as surely as a wrong answer."""
    reply = client.post("/chat", json={"message": "Quando si piantano i tulipani?"})
    assert reply.status_code == 200
    assert set(reply.json()) == CONTRACT_FIELDS


def test_chat_body_matches_the_assignment_example(client: Any) -> None:
    """The body validates against the schema the assignment fixes."""
    reply = client.post("/chat", json={"message": "Quando si piantano i tulipani?"})
    parsed = ChatResponse.model_validate(reply.json())
    assert parsed.sources == ["guides/bulbi_autunnali.md"]
    assert parsed.confidence == "high"
    assert parsed.needs_human is False


# --- Session handling -----------------------------------------------------------------


def test_a_request_without_a_session_gets_one_in_the_header(client: Any, stub: StubService) -> None:
    """A new conversation is minted server-side and announced in a header, not in the body."""
    reply = client.post("/chat", json={"message": "Buongiorno"})
    session_id = reply.headers[SESSION_HEADER]
    assert session_id.startswith("sess-")
    assert "session_id" not in reply.json()
    assert stub.calls == [("Buongiorno", session_id)]


def test_a_supplied_session_is_used_and_echoed(client: Any, stub: StubService) -> None:
    """A client continuing a conversation gets its own identifier back."""
    reply = client.post(
        "/chat", json={"message": "E quello di prima?", "session_id": "sess-abc123"}
    )
    assert reply.headers[SESSION_HEADER] == "sess-abc123"
    assert stub.calls == [("E quello di prima?", "sess-abc123")]


def test_deleting_a_session_forgets_it(client: Any, stub: StubService) -> None:
    """``DELETE /sessions/{id}`` resets the conversation and returns no content."""
    reply = client.delete("/sessions/sess-abc123")
    assert reply.status_code == 204
    assert not reply.content
    assert stub.deleted == ["sess-abc123"]


def test_deleting_an_unknown_session_is_not_an_error(client: Any) -> None:
    """The caller wants the conversation gone, and it is."""
    assert client.delete("/sessions/sess-never-existed").status_code == 204


# --- Input validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "message mancante"),
        ({"message": ""}, "messaggio vuoto"),
        ({"message": "x" * (MAX_MESSAGE_LENGTH + 1)}, "messaggio troppo lungo"),
        ({"message": "ciao", "extra": "non previsto"}, "campo sconosciuto"),
        ({"message": 42}, "tipo sbagliato"),
    ],
)
def test_invalid_input_is_rejected_with_422(
    client: Any, stub: StubService, payload: dict[str, Any], reason: str
) -> None:
    """Bad input is refused before a model call is spent on it.

    Args:
        client: The test client.
        stub: The scripted service, which must not be reached.
        payload: The malformed body.
        reason: What is wrong with it, for the failure message.
    """
    assert client.post("/chat", json=payload).status_code == 422, reason
    assert stub.calls == [], f"{reason}: il servizio non doveva essere invocato"


def test_a_message_at_the_limit_is_accepted(client: Any) -> None:
    """The boundary itself is valid: 2000 characters is the limit, not the first refusal."""
    reply = client.post("/chat", json={"message": "x" * MAX_MESSAGE_LENGTH})
    assert reply.status_code == 200


# --- Failure modes --------------------------------------------------------------------


def test_a_provider_fallback_keeps_the_contract_and_sets_the_header() -> None:
    """A provider outage must stay observable without changing the JSON (ADR-009)."""
    fallback = ChatResponse(
        answer="Mi scuso, non riesco a completare la richiesta.",
        confidence="low",
        sources=[],
        needs_human=True,
    )
    app.state.service = StubService(response=fallback, fallback=True)
    with TestClient(app) as test_client:
        reply = test_client.post("/chat", json={"message": "Quando arriva l'ordine 1042?"})
    app.state.service = None

    assert reply.status_code == 200
    assert set(reply.json()) == CONTRACT_FIELDS
    assert reply.headers[FALLBACK_HEADER] == "true"
    assert reply.json()["needs_human"] is True


def test_a_nominal_turn_sets_no_fallback_header(client: Any) -> None:
    """The header is a signal, so it must be absent when nothing went wrong."""
    reply = client.post("/chat", json={"message": "Buongiorno"})
    assert FALLBACK_HEADER not in reply.headers


def test_an_unexpected_error_still_returns_the_contract() -> None:
    """A crash further out than the service must not reach the customer as a 500."""
    app.state.service = StubService(raises=RuntimeError("qualcosa si e' rotto"))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        reply = test_client.post("/chat", json={"message": "Buongiorno"})
    app.state.service = None

    assert reply.status_code == 200
    assert set(reply.json()) == CONTRACT_FIELDS
    assert reply.json()["needs_human"] is True
    assert reply.headers[FALLBACK_HEADER] == "true"


# --- Health ---------------------------------------------------------------------------


def test_health_reports_configuration_without_secrets(client: Any) -> None:
    """Health is for operators, and must not leak the provider key."""
    payload = client.get("/health").json()
    assert payload["business_date"] == "2026-10-12"
    assert payload["season"] == "autunno"
    assert payload["llm_model"] == "test/model"
    assert payload["retrieval_score_low"] == 0.813
    serialised = str(payload).lower()
    for forbidden in ("api_key", "sk-", "secret", "token"):
        assert forbidden not in serialised
