from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from travelmind_ai.chat.schemas import ChatRequest, ChatResponse
from travelmind_ai.chat.service import agent_chat, agent_chat_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["Chat"])


@router.post(
    "/chat",
    summary="Chat with TravelMind AI Agent",
    response_model=None,
    description=(
        "Send a message to the TravelMind AI agent. "
        "The agent uses function calling to search hotels, check availability, "
        "and retrieve real-time data before responding.\n\n"
        "**Stateful mode** (conversation_id provided): LangGraph loads full agent state "
        "from checkpoint — only send the NEW user message.\n\n"
        "**Stateless mode** (no conversation_id): pass all messages, uses CAG caching."
    ),
)
async def chat_endpoint(request: ChatRequest) -> StreamingResponse | ChatResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    conv_id = request.conversation_id

    if not request.stream:
        content = await agent_chat(messages, conversation_id=conv_id)
        return ChatResponse(content=content)

    async def event_generator():
        try:
            async for chunk in agent_chat_stream(messages, conversation_id=conv_id):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Agent streaming error")
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
