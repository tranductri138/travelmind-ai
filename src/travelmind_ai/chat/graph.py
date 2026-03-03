"""LangGraph custom StateGraph with intent-based routing.

Architecture:
    START → classify_and_route (rule-based, LLM fallback)
      ├─ "search"       → handle_search       → respond → END
      ├─ "popular"      → handle_popular       → respond → END
      ├─ "details"      ──┐
      ├─ "availability" ──┼─→ handle_general (inner ReAct agent) → END
      └─ "general"      ──┘

- search/popular: extract params with regex → call tool directly → save tokens
- details/availability/general: fall back to ReAct agent for complex extraction

Checkpoint is persisted to PostgreSQL via AsyncPostgresSaver so conversations
survive service restarts.
"""

from __future__ import annotations

import functools
import logging
from typing import Annotated

import psycopg
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg_pool import AsyncConnectionPool
from typing_extensions import TypedDict

from travelmind_ai.chat.nodes import (
    classify_and_route,
    handle_general,
    handle_popular,
    handle_search,
    respond,
)
from travelmind_ai.chat.prompts import build_system_prompt
from travelmind_ai.config import settings

logger = logging.getLogger(__name__)

# Singletons
_agent = None
_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """State for the intent-based StateGraph.

    Extends LangGraph's message handling with intent classification
    and direct tool result storage.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
    tool_result: str


# ---------------------------------------------------------------------------
# Checkpointer lifecycle
# ---------------------------------------------------------------------------

async def setup_checkpointer() -> None:
    """Create connection pool and initialise PostgreSQL checkpoint tables."""
    global _pool, _checkpointer
    _pool = AsyncConnectionPool(conninfo=settings.checkpoint_database_url)
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    # setup() uses CREATE INDEX CONCURRENTLY which cannot run inside a transaction.
    # Use a dedicated autocommit connection for the migration DDL.
    async with await psycopg.AsyncConnection.connect(
        settings.checkpoint_database_url, autocommit=True
    ) as conn:
        _tmp = AsyncPostgresSaver(conn)
        await _tmp.setup()
    logger.info("LangGraph checkpointer ready (AsyncPostgresSaver → PostgreSQL)")


async def shutdown_checkpointer() -> None:
    """Close the checkpoint connection pool."""
    global _pool, _checkpointer
    if _pool:
        await _pool.close()
        logger.info("LangGraph checkpoint connection pool closed")
    _pool = None
    _checkpointer = None


# ---------------------------------------------------------------------------
# LLM + Prompt
# ---------------------------------------------------------------------------

def _build_prompt(state: dict) -> list:
    """Build prompt with system message + trimmed conversation history.

    Checkpoint stores ALL messages, but we only send the last N to the LLM
    to save tokens and avoid latency on long conversations.
    Ensures we never cut mid-tool-call by starting from a HumanMessage.
    """
    system = SystemMessage(content=build_system_prompt())
    messages = state["messages"]
    limit = settings.checkpoint_messages_limit
    if len(messages) > limit:
        messages = messages[-limit:]
        # Don't start mid-tool-call — skip forward to first HumanMessage
        while messages and not isinstance(messages[0], HumanMessage):
            messages = messages[1:]
    return [system] + messages


def _create_llm() -> ChatOpenAI:
    """Create a ChatOpenAI instance for OpenAI, Ollama, or Alibaba Cloud (Qwen)."""
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.7,
            max_tokens=2048,
            streaming=True,
        )
    elif settings.llm_provider == "alibaba":
        return ChatOpenAI(
            model=settings.alibaba_model,
            base_url=settings.alibaba_base_url,
            api_key=settings.alibaba_api_key,
            temperature=0.7,
            max_tokens=2048,
            streaming=True,
        )
    else:
        return ChatOpenAI(
            model=settings.ollama_model,
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
            temperature=0.7,
            max_tokens=2048,
            streaming=True,
        )


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_by_intent(state: dict) -> str:
    """Route to the appropriate handler based on classified intent."""
    intent = state.get("intent", "general")
    if intent == "search":
        return "handle_search"
    elif intent == "popular":
        return "handle_popular"
    else:
        # details, availability, general → ReAct agent
        return "handle_general"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph(llm: ChatOpenAI) -> StateGraph:
    """Construct the intent-based StateGraph.

    Nodes use functools.partial to inject the LLM instance.
    """
    graph = StateGraph(AgentState)

    # Add nodes with LLM injected via partial
    graph.add_node("classify_and_route", functools.partial(classify_and_route, llm=llm))
    graph.add_node("handle_search", handle_search)
    graph.add_node("handle_popular", handle_popular)
    graph.add_node(
        "handle_general",
        functools.partial(handle_general, llm=llm, prompt_fn=_build_prompt),
    )
    graph.add_node("respond", functools.partial(respond, llm=llm))

    # Edges
    graph.add_edge(START, "classify_and_route")
    graph.add_conditional_edges("classify_and_route", route_by_intent)
    graph.add_edge("handle_search", "respond")
    graph.add_edge("handle_popular", "respond")
    graph.add_edge("handle_general", END)
    graph.add_edge("respond", END)

    return graph


# ---------------------------------------------------------------------------
# Agent singleton
# ---------------------------------------------------------------------------

def get_agent():
    """Get or create the singleton StateGraph agent with checkpointing.

    The AsyncPostgresSaver checkpointer persists agent state to PostgreSQL,
    keyed by thread_id. Conversations survive service restarts.

    setup_checkpointer() must be called before this function (done in lifespan).
    """
    global _agent
    if _agent is None:
        if _checkpointer is None:
            raise RuntimeError(
                "Checkpointer not initialised. Call setup_checkpointer() first."
            )
        llm = _create_llm()
        graph = _build_graph(llm)
        _agent = graph.compile(checkpointer=_checkpointer)
        logger.info(
            "LangGraph StateGraph agent initialized "
            "(provider=%s, messages_limit=%d, intents=search/popular/details/availability/general)",
            settings.llm_provider,
            settings.checkpoint_messages_limit,
        )
    return _agent


def reset_agent() -> None:
    """Reset the agent (e.g. on config change). Next call to get_agent() recreates it."""
    global _agent
    _agent = None
