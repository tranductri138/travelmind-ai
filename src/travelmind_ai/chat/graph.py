"""LangGraph ReAct agent for TravelMind chat.

Uses create_react_agent with a **checkpointer** so the agent remembers
full conversation state (messages + tool calls + tool results) between turns.

Checkpoint is persisted to PostgreSQL via AsyncPostgresSaver so conversations
survive service restarts.

With checkpointing:
  Turn 1: "find hotels in Danang" → agent calls search_hotels → returns 5 results (with IDs)
  Turn 2: "tell me about the 2nd one" → agent loads checkpoint → sees tool_result with IDs
           → calls get_hotel_details(id) directly — no re-search needed
"""

from __future__ import annotations

import logging
import warnings

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langgraph.prebuilt import create_react_agent

from travelmind_ai.chat.prompts import build_system_prompt
from travelmind_ai.chat.tools import ALL_TOOLS
from travelmind_ai.config import settings

logger = logging.getLogger(__name__)

# Singletons
_agent = None
_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def setup_checkpointer() -> None:
    """Create connection pool and initialise PostgreSQL checkpoint tables."""
    global _pool, _checkpointer
    _pool = AsyncConnectionPool(conninfo=settings.checkpoint_database_url)
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    logger.info("LangGraph checkpointer ready (AsyncPostgresSaver → PostgreSQL)")


async def shutdown_checkpointer() -> None:
    """Close the checkpoint connection pool."""
    global _pool, _checkpointer
    if _pool:
        await _pool.close()
        logger.info("LangGraph checkpoint connection pool closed")
    _pool = None
    _checkpointer = None


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


def get_agent():
    """Get or create the singleton ReAct agent with checkpointing.

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
        _agent = create_react_agent(
            model=llm,
            tools=ALL_TOOLS,
            prompt=_build_prompt,
            checkpointer=_checkpointer,
        )
        logger.info(
            "LangGraph ReAct agent initialized (provider=%s, messages_limit=%d)",
            settings.llm_provider,
            settings.checkpoint_messages_limit,
        )
    return _agent


def reset_agent() -> None:
    """Reset the agent (e.g. on config change). Next call to get_agent() recreates it."""
    global _agent
    _agent = None
