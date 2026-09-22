"""Construction of the ReAct agent.

The agent itself is thin: `create_agent` provides the loop, and the interesting decisions
are in what gets handed to it.

* **The system prompt is rebuilt on every model call**, through `dynamic_prompt`, so the
  business date and season are always current rather than frozen at construction time
  (SPEC section 8, ADR-027).
* **The iteration limit ends the run rather than raising.** A customer facing a pathological
  loop should get a polite answer and a handover, not a stack trace, so the middleware exits
  to the end of the graph and :func:`fallback_output` supplies the reply.
* **Everything is injected.** Nothing here reads configuration or builds a repository on its
  own, which is what lets the wiring be tested with a fake model and no network.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    dynamic_prompt,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from greenthumb.clock import Clock
from greenthumb.config import Settings, get_settings
from greenthumb.escalations_repository import EscalationsRepository
from greenthumb.memory import build_checkpointer
from greenthumb.orders_repository import OrdersRepository
from greenthumb.prompts import build_system_prompt
from greenthumb.retrieval import open_index
from greenthumb.schemas import AgentOutput
from greenthumb.tools.escalation_tool import make_escalation_tool
from greenthumb.tools.knowledge_base_tool import make_knowledge_base_tool
from greenthumb.tools.order_status_tool import make_order_status_tool

# Zero, not merely "low": the evaluation compares runs, and sampling noise would show up as
# a difference in scores that no change of ours caused.
TEMPERATURE = 0.0

AGENT_NAME = "greenthumb_agent"

FALLBACK_ANSWER = (
    "Mi scusi, non sono riuscito a completare la sua richiesta. La metto in contatto con un "
    "operatore, che potra' aiutarla meglio di me. Puo' anche scriverci a "
    "assistenza@greenthumb.example indicando il suo numero d'ordine."
)


def fallback_output() -> AgentOutput:
    """Build the reply used when the agent could not produce one.

    Two situations lead here: the iteration limit cut the run short, and the structured
    output failed to parse. In both the customer gets a courteous handover rather than an
    error, because a 500 towards a customer is never the right answer (SPEC section 5).

    Returns:
        A low-confidence output citing no sources.
    """
    return AgentOutput(answer=FALLBACK_ANSWER, proposed_confidence="low", cited_sources=[])


def build_chat_model(settings: Settings) -> ChatLiteLLM:
    """Build the chat model from configuration.

    Args:
        settings: The runtime configuration.

    Returns:
        The configured model.

    Raises:
        ValueError: If no model identifier is configured.
    """
    if not settings.llm_model.strip():
        raise ValueError(
            "GREENTHUMB_LLM_MODEL non e' impostato: senza un modello l'agente non puo' "
            "essere costruito. Impostalo nel .env o nei Secrets di Colab."
        )
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return ChatLiteLLM(
        model=settings.llm_model,
        temperature=TEMPERATURE,
        # Never leave this unset: LiteLLM otherwise requests 65536 output tokens (ADR-031).
        max_tokens=settings.max_output_tokens,
        api_key=api_key,
    )


def build_tools(
    settings: Settings,
    clock: Clock,
    orders: OrdersRepository,
    escalations: EscalationsRepository,
    store: object,
) -> list[BaseTool]:
    """Build the three tools with their dependencies bound.

    Args:
        settings: The runtime configuration.
        clock: The business-date source.
        orders: The order repository.
        escalations: The escalation register.
        store: The Chroma vector store.

    Returns:
        The tools, in the order the model sees them.
    """
    return [
        make_knowledge_base_tool(store, settings.retrieval_top_k, settings.retrieval_score_low),
        make_order_status_tool(orders, clock),
        make_escalation_tool(escalations, clock),
    ]


def build_prompt_middleware(clock: Clock) -> AgentMiddleware:
    """Build middleware that rebuilds the system prompt on every model call.

    Args:
        clock: The business-date source, read at each call rather than once.

    Returns:
        The middleware.
    """

    @dynamic_prompt
    def _prompt(request: ModelRequest) -> str:
        """Return the system prompt for the current business date.

        Args:
            request: The model request, unused: the prompt depends only on the clock.

        Returns:
            The system prompt.
        """
        return build_system_prompt(clock.today())

    return _prompt


def build_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    clock: Clock,
    max_iterations: int,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_middleware: Sequence[AgentMiddleware] = (),
) -> CompiledStateGraph:
    """Assemble the agent.

    Args:
        model: The chat model, real or fake.
        tools: The tools the agent may call.
        clock: The business-date source, used by the prompt middleware.
        max_iterations: Model calls allowed per run before the loop is cut short.
        checkpointer: Conversation store; an in-memory one is created when omitted.
        extra_middleware: Additional middleware, appended after the built-in ones. Phase 5
            passes the summarization middleware here.

    Returns:
        The compiled agent.
    """
    middleware: list[AgentMiddleware] = [
        build_prompt_middleware(clock),
        # "end" rather than "error": a pathological loop must reach the customer as a
        # courteous handover, not as an exception (SPEC section 8).
        ModelCallLimitMiddleware(run_limit=max_iterations, exit_behavior="end"),
        *extra_middleware,
    ]
    return create_agent(
        model=model,
        tools=list(tools),
        middleware=middleware,
        response_format=AgentOutput,
        checkpointer=checkpointer if checkpointer is not None else build_checkpointer(),
        name=AGENT_NAME,
    )


def build_default_agent(
    settings: Settings | None = None,
    clock: Clock | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_middleware: Sequence[AgentMiddleware] = (),
) -> CompiledStateGraph:
    """Build the production agent, wiring every dependency from configuration.

    Args:
        settings: The runtime configuration; read from the environment when omitted.
        clock: The business-date source; built from configuration when omitted.
        checkpointer: Conversation store; an in-memory one is created when omitted.
        extra_middleware: Additional middleware, appended after the built-in ones.

    Returns:
        The compiled agent.

    Raises:
        FileNotFoundError: If the vector store has not been built yet.
    """
    settings = settings or get_settings()
    clock = clock or settings.clock()

    if not settings.vector_store_dir.exists():
        raise FileNotFoundError(
            f"Indice non trovato in {settings.vector_store_dir}. Eseguire `make index`."
        )

    tools = build_tools(
        settings=settings,
        clock=clock,
        orders=OrdersRepository.from_file(settings.orders_path),
        escalations=EscalationsRepository(settings.escalations_path),
        store=open_index(settings.vector_store_dir, settings.embedding_model),
    )
    return build_agent(
        model=build_chat_model(settings),
        tools=tools,
        clock=clock,
        max_iterations=settings.agent_max_iterations,
        checkpointer=checkpointer,
        extra_middleware=extra_middleware,
    )
