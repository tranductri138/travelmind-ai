"""Chat service: LangGraph agent + Checkpointing + CAG.

Two modes based on whether conversation_id is provided:

**Stateful (conversation_id provided):**
  - LangGraph loads full agent state from checkpoint (messages + tool results)
  - Only the NEW user message is sent — checkpoint has the history
  - After response, state is auto-saved to checkpoint
  - CAG is skipped (context-dependent responses shouldn't be cached)

**Stateless (no conversation_id):**
  - All messages passed as-is to the agent (one-shot)
  - CAG is used: check cache first, cache response after
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage

from travelmind_ai.chat.graph import get_agent
from travelmind_ai.dependencies import get_cache_layer

logger = logging.getLogger(__name__)

# Nodes whose LLM output should be streamed to the user.
# classify_and_route LLM output is internal (intent classification) — not for user.
_STREAMABLE_NODES = {"respond", "handle_general"}


def _to_langchain_messages(
    messages: list[dict[str, str]],
) -> list[HumanMessage | AIMessage]:
    """Convert raw dicts to LangChain message objects."""
    lc_messages: list[HumanMessage | AIMessage] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
    return lc_messages


def _get_last_user_message(messages: list[dict[str, str]]) -> str:
    """Extract the last user message for cache key."""
    for msg in reversed(messages):
        if msg["role"] == "user":
            return msg["content"]
    return ""


# ---------------------------------------------------------------------------
# Stateful mode (with checkpointing)
# ---------------------------------------------------------------------------

async def agent_chat_stream(
    messages: list[dict[str, str]],
    conversation_id: str | None = None,
) -> AsyncGenerator[str]:
    """Stream the agent's response.

    If conversation_id is provided → stateful with checkpoint (no CAG).
    If not → stateless with CAG.
    """
    if conversation_id:
        async for chunk in _stream_stateful(messages, conversation_id):
            yield chunk
    else:
        async for chunk in _stream_stateless(messages):
            yield chunk


async def agent_chat(
    messages: list[dict[str, str]],
    conversation_id: str | None = None,
) -> str:
    """Non-streaming agent chat.

    If conversation_id is provided → stateful with checkpoint (no CAG).
    If not → stateless with CAG.
    """
    if conversation_id:
        return await _invoke_stateful(messages, conversation_id)
    else:
        return await _invoke_stateless(messages)


# ---------------------------------------------------------------------------
# Stateful helpers (checkpoint-backed)
# ---------------------------------------------------------------------------

async def _stream_stateful(
    messages: list[dict[str, str]],
    conversation_id: str,
) -> AsyncGenerator[str]:
    """Stream with LangGraph checkpointing. Agent remembers full state."""
    agent = get_agent()
    lc_messages = _to_langchain_messages(messages)
    config = {"configurable": {"thread_id": conversation_id}}

    async for event in agent.astream_events(
        {"messages": lc_messages},
        config=config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            node = event.get("metadata", {}).get("langgraph_node", "")
            if node not in _STREAMABLE_NODES:
                continue
            chunk = event["data"]["chunk"]
            if chunk.content and not getattr(chunk, "tool_call_chunks", None):
                yield chunk.content


async def _invoke_stateful(
    messages: list[dict[str, str]],
    conversation_id: str,
) -> str:
    """Non-streaming with checkpointing."""
    agent = get_agent()
    lc_messages = _to_langchain_messages(messages)
    config = {"configurable": {"thread_id": conversation_id}}

    result = await agent.ainvoke({"messages": lc_messages}, config=config)

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
    if ai_messages:
        return ai_messages[-1].content
    return "Xin lỗi, tôi không thể tạo phản hồi. Vui lòng thử lại."


# ---------------------------------------------------------------------------
# Stateless helpers (CAG-backed, no checkpoint)
# ---------------------------------------------------------------------------

async def _stream_stateless(
    messages: list[dict[str, str]],
) -> AsyncGenerator[str]:
    """Stream without checkpointing. Uses CAG for caching."""
    last_msg = _get_last_user_message(messages)
    cache = get_cache_layer()

    # CAG: check cache
    if cache and last_msg:
        cached_response, status = await cache.get(last_msg)
        if cached_response is not None:
            logger.info("CAG %s for stream: '%s'", status, last_msg[:60])
            yield cached_response
            return

    # Cache miss → run agent (ephemeral thread_id for stateless)
    agent = get_agent()
    lc_messages = _to_langchain_messages(messages)
    config = {"configurable": {"thread_id": f"stateless-{uuid.uuid4().hex}"}}
    full_response = ""

    async for event in agent.astream_events(
        {"messages": lc_messages},
        config=config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            node = event.get("metadata", {}).get("langgraph_node", "")
            if node not in _STREAMABLE_NODES:
                continue
            chunk = event["data"]["chunk"]
            if chunk.content and not getattr(chunk, "tool_call_chunks", None):
                full_response += chunk.content
                yield chunk.content

    # CAG: write cache
    if cache and last_msg and full_response:
        await cache.set(last_msg, full_response)


async def _invoke_stateless(
    messages: list[dict[str, str]],
) -> str:
    """Non-streaming without checkpointing. Uses CAG."""
    last_msg = _get_last_user_message(messages)
    cache = get_cache_layer()

    # CAG: check cache
    if cache and last_msg:
        cached_response, status = await cache.get(last_msg)
        if cached_response is not None:
            logger.info("CAG %s for chat: '%s'", status, last_msg[:60])
            return cached_response

    # Cache miss → run agent (ephemeral thread_id for stateless)
    agent = get_agent()
    lc_messages = _to_langchain_messages(messages)
    config = {"configurable": {"thread_id": f"stateless-{uuid.uuid4().hex}"}}
    result = await agent.ainvoke({"messages": lc_messages}, config=config)

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
    response = (
        ai_messages[-1].content
        if ai_messages
        else "Xin lỗi, tôi không thể tạo phản hồi. Vui lòng thử lại."
    )

    # CAG: write cache
    if cache and last_msg and response:
        await cache.set(last_msg, response)

    return response
