"""Graph nodes for the intent-based StateGraph.

Nodes:
- classify_and_route: rule-based first, LLM fallback for uncertain cases
- handle_search: extract query + city → call search_hotels directly
- handle_popular: extract city → call get_popular_hotels directly
- handle_general: delegate to inner ReAct agent for complex queries
- respond: LLM formats tool_result into natural language (Vietnamese, markdown)
"""

from __future__ import annotations

import logging
import re
import warnings

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langgraph.prebuilt import create_react_agent

from travelmind_ai.chat.intent import INTENT_CLASSIFICATION_PROMPT, classify_intent_rules
from travelmind_ai.chat.prompts import build_system_prompt
from travelmind_ai.chat.tools import (
    ALL_TOOLS,
    get_popular_hotels,
    search_hotels,
)

logger = logging.getLogger(__name__)

# Vietnamese city names for extraction
_CITIES = [
    "Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hội An", "Nha Trang",
    "Đà Lạt", "Phú Quốc", "Huế", "Sapa", "Sa Pa", "Hạ Long",
    "Vũng Tàu", "Quy Nhơn", "Phan Thiết", "Cần Thơ", "Ninh Bình",
    "Bắc Ninh", "Hải Phòng",
    # English variants
    "Hanoi", "Ho Chi Minh", "Da Nang", "Hoi An", "Nha Trang",
    "Da Lat", "Dalat", "Phu Quoc", "Hue", "Sapa", "Ha Long",
    "Halong", "Vung Tau", "Quy Nhon", "Phan Thiet", "Can Tho",
    # International
    "Paris", "Tokyo", "Bangkok", "Singapore", "Bali", "London",
    "New York", "Dubai", "Seoul", "Osaka",
]


def _extract_city(text: str) -> str | None:
    """Extract city name from text (case-insensitive)."""
    text_lower = text.lower()
    for city in _CITIES:
        if city.lower() in text_lower:
            return city
    return None


def _extract_search_query(text: str) -> str:
    """Extract the search query from a user message.

    Strips common prefixes like "tìm", "search for" etc. to get the core query.
    """
    # Remove common Vietnamese prefixes
    cleaned = re.sub(
        r"^(tìm|tìm kiếm|search|search for|gợi ý|giới thiệu|đề xuất)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    return cleaned if cleaned else text.strip()


def _extract_min_stars(text: str) -> int | None:
    """Extract minimum star rating from text."""
    match = re.search(r"(\d)\s*sao", text, re.IGNORECASE)
    if match:
        stars = int(match.group(1))
        if 1 <= stars <= 5:
            return stars
    match = re.search(r"(\d)\s*star", text, re.IGNORECASE)
    if match:
        stars = int(match.group(1))
        if 1 <= stars <= 5:
            return stars
    return None


# ---------------------------------------------------------------------------
# Node: classify_and_route
# ---------------------------------------------------------------------------

async def classify_and_route(state: dict, llm=None) -> dict:
    """Classify intent using rules first, LLM fallback if uncertain.

    Args:
        state: AgentState with messages list.
        llm: ChatOpenAI instance (injected by graph builder).

    Returns:
        Updated state with intent field set.
    """
    messages = state["messages"]
    last_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_msg = msg.content
            break

    # Rule-based classification
    intent = classify_intent_rules(last_msg)

    if intent is None and llm is not None:
        # LLM fallback
        prompt = INTENT_CLASSIFICATION_PROMPT.format(message=last_msg)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip().lower()
        if raw in ("search", "popular", "details", "availability", "general"):
            intent = raw
        else:
            intent = "general"
        logger.info("Intent classified by LLM: '%s' → %s", last_msg[:60], intent)
    elif intent is None:
        intent = "general"

    if intent != "general" or classify_intent_rules(last_msg) is not None:
        logger.info("Intent classified: '%s' → %s", last_msg[:60], intent)

    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node: handle_search
# ---------------------------------------------------------------------------

async def handle_search(state: dict) -> dict:
    """Extract query + city from message, call search_hotels directly."""
    messages = state["messages"]
    last_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_msg = msg.content
            break

    query = _extract_search_query(last_msg)
    city = _extract_city(last_msg)
    min_stars = _extract_min_stars(last_msg)

    result = await search_hotels.ainvoke({
        "query": query,
        "city": city,
        "min_stars": min_stars,
    })

    logger.info("handle_search: query='%s', city=%s → %d chars", query[:40], city, len(result))
    return {"tool_result": result}


# ---------------------------------------------------------------------------
# Node: handle_popular
# ---------------------------------------------------------------------------

async def handle_popular(state: dict) -> dict:
    """Extract city from message, call get_popular_hotels directly."""
    messages = state["messages"]
    last_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_msg = msg.content
            break

    city = _extract_city(last_msg)

    result = await get_popular_hotels.ainvoke({
        "city": city,
        "limit": 5,
    })

    logger.info("handle_popular: city=%s → %d chars", city, len(result))
    return {"tool_result": result}


# ---------------------------------------------------------------------------
# Node: handle_general (ReAct agent fallback)
# ---------------------------------------------------------------------------

async def handle_general(state: dict, llm=None, prompt_fn=None) -> dict:
    """Delegate to inner ReAct agent for complex queries.

    The inner ReAct agent has no checkpointer — parent StateGraph owns the checkpoint.
    """
    if llm is None:
        return {"messages": [AIMessage(content="Xin lỗi, tôi không thể xử lý yêu cầu này.")]}

    inner_agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=prompt_fn or _default_prompt_fn,
    )

    result = await inner_agent.ainvoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


def _default_prompt_fn(state: dict) -> list:
    """Default prompt function for inner ReAct agent."""
    return [SystemMessage(content=build_system_prompt())] + state["messages"]


# ---------------------------------------------------------------------------
# Node: respond
# ---------------------------------------------------------------------------

async def respond(state: dict, llm=None) -> dict:
    """Format tool_result into natural language using LLM."""
    tool_result = state.get("tool_result", "")
    messages = state["messages"]

    last_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_msg = msg.content
            break

    if not tool_result:
        return {"messages": [AIMessage(content="Xin lỗi, không tìm thấy kết quả phù hợp.")]}

    if llm is None:
        # No LLM available, return raw tool result
        return {"messages": [AIMessage(content=tool_result)]}

    format_prompt = (
        f"Bạn là TravelMind, một trợ lý du lịch AI. "
        f"Dựa trên câu hỏi và dữ liệu bên dưới, hãy trả lời bằng tiếng Việt, dùng markdown.\n\n"
        f"Câu hỏi: {last_msg}\n\n"
        f"Dữ liệu:\n{tool_result}"
    )

    response = await llm.ainvoke([
        SystemMessage(content=build_system_prompt()),
        HumanMessage(content=format_prompt),
    ])

    return {"messages": [AIMessage(content=response.content)]}
