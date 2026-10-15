"""FastAPI deployment of the agent.

The response body of ``POST /chat`` is **exactly** the four fields of
:class:`~greenthumb.schemas.ChatResponse`, as the assignment's example shows. Everything
the caller also needs but that would change that shape travels in headers instead:
``X-Session-Id`` so a client can continue a conversation, and ``X-Fallback`` so that a
provider outage stays observable without breaking the contract (ADR-009).

The agent and the vector store are built once, in the lifespan, because loading the
embedding model takes seconds and doing it per request would make the API unusable.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from greenthumb.clock import season_of
from greenthumb.config import Settings, get_settings
from greenthumb.schemas import ChatResponse
from greenthumb.service import ChatService, build_chat_service, new_session_id

logger = logging.getLogger(__name__)

# SPEC section 11: an empty message carries no question, and 2000 characters is already far
# beyond anything a customer types. Both are rejected with 422 rather than spent on a model
# call.
MIN_MESSAGE_LENGTH = 1
MAX_MESSAGE_LENGTH = 2000

SESSION_HEADER = "X-Session-Id"
FALLBACK_HEADER = "X-Fallback"


class ChatRequest(BaseModel):
    """The request body of ``POST /chat``.

    ``session_id`` is optional: omitting it starts a new conversation, and the identifier
    the server minted comes back in the ``X-Session-Id`` header.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=MIN_MESSAGE_LENGTH,
        max_length=MAX_MESSAGE_LENGTH,
        description="Il messaggio del cliente.",
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="La conversazione da continuare. Assente: ne viene creata una nuova.",
    )


class HealthResponse(BaseModel):
    """What ``GET /health`` reports.

    Deliberately free of secrets: the model identifiers are configuration, the API key is
    never read here.
    """

    model_config = ConfigDict(frozen=True)

    status: str
    business_date: str
    season: str
    llm_model: str
    embedding_model: str
    vector_store_ready: bool
    retrieval_score_low: float
    retrieval_score_high: float


def _service(app: FastAPI) -> ChatService:
    """Return the service built at startup.

    Args:
        app: The running application.

    Returns:
        The shared :class:`ChatService`.

    Raises:
        RuntimeError: If the lifespan has not run, which would mean a programming error
            rather than a client one.
    """
    service = getattr(app.state, "service", None)
    if service is None:  # pragma: no cover - only reachable if the lifespan is bypassed
        raise RuntimeError("Il servizio non e' stato inizializzato dal lifespan.")
    return service


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the agent once, before the first request.

    Args:
        app: The application being started.

    Yields:
        Nothing; the agent lives in ``app.state`` for the process's lifetime.
    """
    settings = get_settings()
    logger.info("Avvio: modello %s, data di business %s", settings.llm_model, settings.today)
    app.state.settings = settings
    # Already built by a test or an embedding application? Then leave it alone.
    if getattr(app.state, "service", None) is None:
        app.state.service = build_chat_service(settings=settings)
    yield
    logger.info("Arresto.")


app = FastAPI(
    title="GreenThumb Customer Care",
    version="1.0.0",
    summary="Agente ReAct per il customer care di primo livello di GreenThumb Marketplace.",
    lifespan=lifespan,
)


def current_settings() -> Settings:
    """Return the settings, as a dependency so tests can override them.

    Returns:
        The process-wide settings.
    """
    return get_settings()


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Rispondi a un messaggio del cliente.",
)
def chat(request: ChatRequest, response: Response) -> ChatResponse:
    """Answer one customer message.

    Args:
        request: The customer message and, optionally, the conversation to continue.
        response: The outgoing response, whose headers carry the session and the fallback
            flag.

    Returns:
        Exactly the four fields of the assignment's contract.
    """
    session_id = request.session_id or new_session_id()
    turn = _service(app).chat_detailed(request.message, session_id)

    response.headers[SESSION_HEADER] = turn.session_id
    if turn.fallback:
        # The body stays a valid ChatResponse and the status stays 200, because the
        # assignment fixes both. The header is what makes the outage visible (ADR-009).
        response.headers[FALLBACK_HEADER] = "true"
    return turn.response


@app.get("/health", response_model=HealthResponse, summary="Stato del servizio.")
def health(settings: Annotated[Settings, Depends(current_settings)]) -> HealthResponse:
    """Report configuration and readiness, without revealing any secret.

    Args:
        settings: The runtime configuration.

    Returns:
        The health payload.
    """
    today = settings.clock().today()
    # Chroma writes a sqlite file in the directory; an empty directory means `make index`
    # has not been run, and saying so here is more useful than a failure on first use.
    vector_store_ready = settings.vector_store_dir.is_dir() and any(
        settings.vector_store_dir.iterdir()
    )
    return HealthResponse(
        status="ok" if vector_store_ready else "degraded",
        business_date=today.isoformat(),
        season=season_of(today),
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        vector_store_ready=vector_store_ready,
        retrieval_score_low=settings.retrieval_score_low,
        retrieval_score_high=settings.retrieval_score_high,
    )


@app.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dimentica una conversazione.",
)
def reset_session(session_id: str) -> Response:
    """Forget a conversation.

    Deleting a session that does not exist is not an error: the caller's intent is that the
    conversation be gone, and it is.

    Args:
        session_id: The conversation to delete.

    Returns:
        An empty 204 response.
    """
    _service(app).reset_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.exception_handler(Exception)
async def unhandled_error(request: Any, exception: Exception) -> JSONResponse:
    """Return the courtesy fallback instead of a stack trace.

    ``ChatService`` already catches provider failures and answers with the fallback, so
    reaching here means something further out broke. The customer still gets the
    four-field contract, and the operator still gets the log.

    Args:
        request: The request that failed.
        exception: What went wrong.

    Returns:
        A 200 response carrying the fallback body and the ``X-Fallback`` header.
    """
    logger.exception("Errore non gestito su %s", getattr(request, "url", "?"))
    fallback = ChatResponse(
        answer=(
            "Mi scuso, in questo momento non riesco a completare la richiesta. "
            "Ho segnalato il problema e un operatore la ricontattera' al piu' presto. "
            "Puo' anche scriverci ad assistenza@greenthumb.example."
        ),
        confidence="low",
        sources=[],
        needs_human=True,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=fallback.model_dump(),
        headers={FALLBACK_HEADER: "true"},
    )
