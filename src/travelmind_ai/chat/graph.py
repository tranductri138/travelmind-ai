"""LangGraph ReAct agent for TravelMind chat.

Uses create_react_agent with a **checkpointer** so the agent remembers
full conversation state (messages + tool calls + tool results) between turns.

With checkpointing:
  Turn 1: "find hotels in Danang" → agent calls search_hotels → returns 5 results (with IDs)
  Turn 2: "tell me about the 2nd one" → agent loads checkpoint → sees tool_result with IDs
           → calls get_hotel_details(id) directly — no re-search needed
"""

from __future__ import annotations

import logging
import warnings

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langgraph.prebuilt import create_react_agent

from travelmind_ai.chat.prompts import build_system_prompt
from travelmind_ai.chat.tools import ALL_TOOLS
from travelmind_ai.config import settings

logger = logging.getLogger(__name__)

# Singletons
_agent = None
_checkpointer: MemorySaver | None = None


def _create_llm() -> ChatOpenAI:
    """Create a ChatOpenAI instance for either OpenAI or Ollama."""
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
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

    The MemorySaver checkpointer stores agent state in-memory, keyed by thread_id.
    For persistent storage across restarts, swap MemorySaver with PostgresSaver::

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        checkpointer = AsyncPostgresSaver.from_conn_string("postgresql://...")
        await checkpointer.setup()
    """
    global _agent, _checkpointer
    if _agent is None:
        llm = _create_llm()
        _checkpointer = MemorySaver()
        _agent = create_react_agent(
            model=llm,
            tools=ALL_TOOLS,
            prompt=build_system_prompt(),
            checkpointer=_checkpointer,
        )
        logger.info(
            "LangGraph ReAct agent initialized (provider=%s, checkpointer=MemorySaver)",
            settings.llm_provider,
        )
    return _agent


def reset_agent() -> None:
    """Reset the agent (e.g. on config change). Next call to get_agent() recreates it."""
    global _agent, _checkpointer
    _agent = None
    _checkpointer = None
