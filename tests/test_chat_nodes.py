"""Tests for graph nodes (classify_and_route, handle_search, handle_popular, etc.)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from travelmind_ai.chat.nodes import (
    classify_and_route,
    handle_general,
    handle_popular,
    handle_search,
    respond,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(user_msg: str, **extra) -> dict:
    """Create a minimal AgentState dict."""
    return {"messages": [HumanMessage(content=user_msg)], "intent": "", "tool_result": "", **extra}


# ---------------------------------------------------------------------------
# classify_and_route
# ---------------------------------------------------------------------------

class TestClassifyAndRoute:
    @pytest.mark.asyncio
    async def test_rule_based_search(self):
        state = _make_state("tìm khách sạn ở Đà Nẵng")
        result = await classify_and_route(state)
        assert result["intent"] == "search"

    @pytest.mark.asyncio
    async def test_rule_based_popular(self):
        state = _make_state("top khách sạn Hà Nội")
        result = await classify_and_route(state)
        assert result["intent"] == "popular"

    @pytest.mark.asyncio
    async def test_rule_based_availability(self):
        state = _make_state("còn phòng trống không")
        result = await classify_and_route(state)
        assert result["intent"] == "availability"

    @pytest.mark.asyncio
    async def test_rule_based_details(self):
        state = _make_state("cho tôi xem chi tiết khách sạn đó")
        result = await classify_and_route(state)
        assert result["intent"] == "details"

    @pytest.mark.asyncio
    async def test_llm_fallback_when_uncertain(self):
        """When rules return None, LLM should classify."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="general")

        state = _make_state("xin chào bạn")
        result = await classify_and_route(state, llm=mock_llm)

        assert result["intent"] == "general"
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_fallback_returns_search(self):
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="search")

        state = _make_state("tôi muốn đi biển")
        result = await classify_and_route(state, llm=mock_llm)

        assert result["intent"] == "search"

    @pytest.mark.asyncio
    async def test_llm_fallback_invalid_response(self):
        """If LLM returns invalid intent, default to general."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="invalid_intent_xyz")

        state = _make_state("something weird")
        result = await classify_and_route(state, llm=mock_llm)

        assert result["intent"] == "general"

    @pytest.mark.asyncio
    async def test_no_llm_fallback_to_general(self):
        """When rules return None and no LLM → default to general."""
        state = _make_state("xin chào")
        result = await classify_and_route(state, llm=None)
        assert result["intent"] == "general"


# ---------------------------------------------------------------------------
# handle_search
# ---------------------------------------------------------------------------

class TestHandleSearch:
    @pytest.mark.asyncio
    async def test_calls_search_hotels(self):
        mock_result = "Tìm thấy 3 khách sạn phù hợp với 'beach resort'..."
        state = _make_state("tìm khách sạn ở Đà Nẵng")

        with patch(
            "travelmind_ai.chat.nodes.search_hotels"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value=mock_result)
            result = await handle_search(state)

        assert result["tool_result"] == mock_result
        mock_tool.ainvoke.assert_called_once()
        call_args = mock_tool.ainvoke.call_args[0][0]
        assert call_args["city"] == "Đà Nẵng"

    @pytest.mark.asyncio
    async def test_extracts_min_stars(self):
        state = _make_state("tìm khách sạn 4 sao ở Hà Nội")

        with patch(
            "travelmind_ai.chat.nodes.search_hotels"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="results")
            await handle_search(state)

        call_args = mock_tool.ainvoke.call_args[0][0]
        assert call_args["min_stars"] == 4
        assert call_args["city"] == "Hà Nội"

    @pytest.mark.asyncio
    async def test_no_city_extraction(self):
        state = _make_state("tìm khách sạn gần biển")

        with patch(
            "travelmind_ai.chat.nodes.search_hotels"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="results")
            await handle_search(state)

        call_args = mock_tool.ainvoke.call_args[0][0]
        assert call_args["city"] is None


# ---------------------------------------------------------------------------
# handle_popular
# ---------------------------------------------------------------------------

class TestHandlePopular:
    @pytest.mark.asyncio
    async def test_calls_get_popular_hotels(self):
        mock_result = "Top 5 khách sạn tại Đà Nẵng..."
        state = _make_state("top khách sạn Đà Nẵng")

        with patch(
            "travelmind_ai.chat.nodes.get_popular_hotels"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value=mock_result)
            result = await handle_popular(state)

        assert result["tool_result"] == mock_result
        mock_tool.ainvoke.assert_called_once()
        call_args = mock_tool.ainvoke.call_args[0][0]
        assert call_args["city"] == "Đà Nẵng"

    @pytest.mark.asyncio
    async def test_no_city(self):
        state = _make_state("top khách sạn tốt nhất")

        with patch(
            "travelmind_ai.chat.nodes.get_popular_hotels"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="results")
            await handle_popular(state)

        call_args = mock_tool.ainvoke.call_args[0][0]
        assert call_args["city"] is None


# ---------------------------------------------------------------------------
# handle_general
# ---------------------------------------------------------------------------

class TestHandleGeneral:
    @pytest.mark.asyncio
    async def test_delegates_to_react_agent(self):
        mock_llm = MagicMock()
        state = _make_state("xin chào, bạn có thể giúp gì")

        mock_react_result = {
            "messages": [
                HumanMessage(content="xin chào"),
                AIMessage(content="Xin chào! Tôi là TravelMind."),
            ]
        }

        with patch("travelmind_ai.chat.nodes.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_react_result
            mock_create.return_value = mock_agent

            result = await handle_general(state, llm=mock_llm)

        assert len(result["messages"]) == 2
        assert "TravelMind" in result["messages"][-1].content

    @pytest.mark.asyncio
    async def test_no_llm_returns_error(self):
        state = _make_state("hello")
        result = await handle_general(state, llm=None)

        assert len(result["messages"]) == 1
        assert "không thể xử lý" in result["messages"][0].content


# ---------------------------------------------------------------------------
# respond
# ---------------------------------------------------------------------------

class TestRespond:
    @pytest.mark.asyncio
    async def test_formats_tool_result_with_llm(self):
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(
            content="## Kết quả tìm kiếm\n\nĐây là 3 khách sạn..."
        )

        state = _make_state("tìm khách sạn Đà Nẵng")
        state["tool_result"] = "Tìm thấy 3 khách sạn..."

        result = await respond(state, llm=mock_llm)

        assert len(result["messages"]) == 1
        assert "Kết quả" in result["messages"][0].content
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_tool_result(self):
        state = _make_state("tìm khách sạn")
        state["tool_result"] = ""

        result = await respond(state, llm=None)

        assert "không tìm thấy" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_no_llm_returns_raw_result(self):
        state = _make_state("tìm khách sạn")
        state["tool_result"] = "Raw tool output here"

        result = await respond(state, llm=None)

        assert result["messages"][0].content == "Raw tool output here"
