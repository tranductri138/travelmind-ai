from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = Field(default=True)
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Conversation ID for stateful chat. When provided, LangGraph loads the "
            "full agent state (including previous tool results) from its checkpoint. "
            "Only send the NEW user message — the checkpoint has the rest."
        ),
    )


class ChatResponse(BaseModel):
    content: str
