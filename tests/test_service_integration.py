"""The public entry point against a real provider. Marked ``llm``.

These are the tests behind the phase-6 Definition of Done: every response produced by a
real turn must validate against the contract the API promises.
"""

from __future__ import annotations

import datetime as dt

import pytest

from greenthumb.clock import FrozenClock
from greenthumb.config import REPO_ROOT, Settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.schemas import ChatResponse
from greenthumb.service import ChatService, build_chat_service, new_session_id

pytestmark = pytest.mark.llm

BUSINESS_DATE = dt.date(2026, 10, 12)

QUESTIONS = (
    "Quando arriva l'ordine 1042? Posso piantare adesso i bulbi di tulipano?",
    "Entro quanto tempo posso restituire delle sementi?",
    "Mi consiglia un buon ristorante a Milano?",
    "Vorrei parlare con un operatore, per favore.",
)


@pytest.fixture(scope="module")
def service(tmp_path_factory: pytest.TempPathFactory) -> ChatService:
    """Build the real service, with a temporary escalation register.

    Args:
        tmp_path_factory: Pytest factory for module-scoped temporary directories.

    Returns:
        The service.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        pytest.skip(".env assente: i test di integrazione richiedono un provider configurato")
    settings = Settings(_env_file=env_file)
    if not settings.llm_model.strip() or settings.openai_api_key is None:
        pytest.skip("modello o chiave non configurati")
    if not settings.vector_store_dir.exists():
        pytest.skip("indice non costruito: eseguire `make index`")

    # A temporary register, shared by the tool and the service, so the real one stays
    # clean and the two cannot diverge (ADR-060).
    register = EscalationsRepository(tmp_path_factory.mktemp("escalations") / "escalations.jsonl")
    return build_chat_service(
        settings=settings, clock=FrozenClock(BUSINESS_DATE), escalations=register
    )


@pytest.fixture(scope="module")
def responses(service: ChatService) -> list[ChatResponse]:
    """Run every question once and share the results.

    Args:
        service: The real service.

    Returns:
        One response per question.
    """
    return [service.chat(question, new_session_id()) for question in QUESTIONS]


def test_every_response_validates_against_the_contract(
    responses: list[ChatResponse],
) -> None:
    """The phase-6 DoD: 100% schema validity across the integration turns.

    Args:
        responses: The collected responses.
    """
    for response in responses:
        assert isinstance(response, ChatResponse)
        ChatResponse.model_validate(response.model_dump())


def test_every_response_has_exactly_four_fields(responses: list[ChatResponse]) -> None:
    """The assignment's example shows four; more or fewer breaks the contract.

    Args:
        responses: The collected responses.
    """
    for response in responses:
        assert set(response.model_dump()) == {
            "answer",
            "confidence",
            "sources",
            "needs_human",
        }


def test_sources_are_real_documents(responses: list[ChatResponse]) -> None:
    """Every cited identifier must exist on disk (ADR-002).

    Args:
        responses: The collected responses.
    """
    kb_dir = Settings(_env_file=None).kb_dir
    for response in responses:
        for source in response.sources:
            assert (kb_dir / source).exists(), f"fonte inesistente: {source}"


def test_grounded_question_cites_something(service: ChatService) -> None:
    """A policy question answered from the knowledge base must carry its source.

    Args:
        service: The real service.
    """
    turn = service.chat_detailed(
        "Entro quanto tempo posso restituire delle sementi?", new_session_id()
    )
    assert turn.response.sources, "una risposta di policy senza fonti non e' verificabile"
    assert turn.fallback is False


def test_out_of_scope_question_cites_nothing_and_opens_no_ticket(
    service: ChatService,
) -> None:
    """SPEC 8: a polite refusal, with no sources invented to justify it.

    Args:
        service: The real service.
    """
    turn = service.chat_detailed("Mi consiglia un buon ristorante a Milano?", new_session_id())
    assert turn.response.needs_human is False
    assert "escalate_to_human" not in turn.tools_invoked


def test_escalation_sets_the_session_flag(service: ChatService) -> None:
    """needs_human is read from the register, and stays true afterwards (ADR-008).

    Args:
        service: The real service.
    """
    session = new_session_id()
    first = service.chat_detailed("Non voglio un bot, mi passi un operatore.", session)
    assert "escalate_to_human" in first.tools_invoked
    assert first.response.needs_human is True

    later = service.chat("Grazie, intanto una curiosita': quando si piantano i tulipani?", session)
    assert later.needs_human is True, "il flag deve restare vero per il resto della sessione"
