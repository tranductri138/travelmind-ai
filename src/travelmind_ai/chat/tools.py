"""LangChain tools for the TravelMind chat agent.

Each tool queries real data (Qdrant vector search or PostgreSQL) and returns
a formatted string that the LLM can use to compose its answer.
"""

from __future__ import annotations

import logging
from datetime import date

from langchain_core.tools import tool
from sqlalchemy import select

from travelmind_ai.config import settings
from travelmind_ai.core.database import (
    Hotel,
    Review,
    Room,
    RoomAvailability,
    async_session_factory,
)
from travelmind_ai.dependencies import get_embedding_client, get_qdrant_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_hotel(h: Hotel, include_rooms: bool = False) -> str:
    """Format a Hotel ORM object into a readable string for the LLM."""
    amenities = ", ".join(h.amenities[:8]) if h.amenities else "Không có"
    lines = [
        f"**{h.name}** (ID: {h.id})",
        f"  Thành phố: {h.city}, {h.country} | Sao: {'⭐' * h.stars} ({h.stars})",
        f"  Đánh giá: {h.rating}/5 ({h.review_count} đánh giá)",
        f"  Địa chỉ: {h.address}",
        f"  Tiện nghi: {amenities}",
    ]
    if h.description:
        desc = h.description[:200] + "..." if len(h.description) > 200 else h.description
        lines.append(f"  Mô tả: {desc}")

    if include_rooms and h.rooms:
        active_rooms = [r for r in h.rooms if r.is_active]
        if active_rooms:
            lines.append("  Phòng:")
            for r in active_rooms:
                r_amenities = ", ".join(r.amenities[:5]) if r.amenities else ""
                lines.append(
                    f"    - {r.name} ({r.type}): {r.price} {r.currency}/đêm, "
                    f"tối đa {r.max_guests} khách. {r_amenities}"
                )
    return "\n".join(lines)


def _format_review(r: Review) -> str:
    title = f" — {r.title}" if r.title else ""
    comment = r.comment[:150] + "..." if r.comment and len(r.comment) > 150 else (r.comment or "")
    return f"  ⭐ {r.rating}/5{title}: {comment}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
async def search_hotels(
    query: str,
    city: str | None = None,
    min_stars: int | None = None,
) -> str:
    """Search for hotels using natural language. Use this to discover hotels matching
    a description like 'beach resort with pool' or 'budget hotel near city center'.

    Args:
        query: Natural language description of what the user is looking for.
        city: Optional city name to filter results.
        min_stars: Optional minimum star rating (1-5).
    """
    try:
        embedding_client = get_embedding_client()
        qdrant_client = get_qdrant_client()
    except (AssertionError, RuntimeError):
        return "Tìm kiếm khách sạn tạm thời không khả dụng (vector database offline)."

    vectors = await embedding_client.embed([query])

    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    conditions = []
    if city:
        conditions.append(FieldCondition(key="city", match=MatchValue(value=city)))
    if min_stars is not None:
        conditions.append(FieldCondition(key="stars", range=Range(gte=min_stars)))
    query_filter = Filter(must=conditions) if conditions else None

    results_response = await qdrant_client.query_points(
        collection_name=settings.qdrant_collection_hotels,
        query=vectors[0],
        query_filter=query_filter,
        limit=20,
    )

    # Deduplicate by hotel_id, keep best score
    seen: dict[str, tuple[float, str]] = {}
    for hit in results_response.points:
        if hit.score < 0.25:
            continue
        hotel_id = hit.payload["hotel_id"]  # type: ignore[index]
        text = hit.payload.get("text", "")  # type: ignore[index]
        if hotel_id not in seen or hit.score > seen[hotel_id][0]:
            seen[hotel_id] = (hit.score, text)

    if not seen:
        return f"Không tìm thấy khách sạn phù hợp với '{query}'" + (f" tại {city}" if city else "") + "."

    # Fetch full hotel details from DB for top results
    top_ids = [hid for hid, _ in sorted(seen.items(), key=lambda x: x[1][0], reverse=True)[:5]]

    async with async_session_factory() as session:
        result = await session.execute(
            select(Hotel).where(Hotel.id.in_(top_ids), Hotel.is_active.is_(True))
        )
        hotels = result.scalars().all()

    if not hotels:
        return f"Không tìm thấy khách sạn đang hoạt động cho '{query}'."

    # Sort by relevance score
    score_map = {hid: score for hid, (score, _) in seen.items()}
    hotels_sorted = sorted(hotels, key=lambda h: score_map.get(h.id, 0), reverse=True)

    lines = [f"Tìm thấy {len(hotels_sorted)} khách sạn phù hợp với '{query}':"]
    for h in hotels_sorted:
        score = score_map.get(h.id, 0)
        lines.append(f"\n{_format_hotel(h)} (độ phù hợp: {score:.2f})")

    return "\n".join(lines)


@tool
async def get_hotel_details(hotel_id: str) -> str:
    """Get full details of a specific hotel including all rooms, prices, and recent reviews.
    Use this after search_hotels to get detailed info for a hotel the user is interested in.

    Args:
        hotel_id: The UUID of the hotel.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Hotel).where(Hotel.id == hotel_id)
        )
        hotel = result.scalar_one_or_none()

        if not hotel:
            return f"Không tìm thấy khách sạn với ID '{hotel_id}'."

        # Fetch reviews
        review_result = await session.execute(
            select(Review)
            .where(Review.hotel_id == hotel_id)
            .order_by(Review.created_at.desc())
            .limit(5)
        )
        reviews = review_result.scalars().all()

    lines = [_format_hotel(hotel, include_rooms=True)]

    if reviews:
        lines.append("\n  Đánh giá gần đây:")
        for r in reviews:
            lines.append(_format_review(r))
    else:
        lines.append("\n  Chưa có đánh giá.")

    return "\n".join(lines)


@tool
async def check_room_availability(
    hotel_id: str,
    check_in: str,
    check_out: str,
    guests: int = 2,
) -> str:
    """Check which rooms are available at a hotel for specific dates.
    Use this when the user mentions travel dates.

    Args:
        hotel_id: The UUID of the hotel.
        check_in: Check-in date in YYYY-MM-DD format.
        check_out: Check-out date in YYYY-MM-DD format.
        guests: Number of guests (default 2).
    """
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
    except ValueError:
        return "Định dạng ngày không hợp lệ. Vui lòng dùng YYYY-MM-DD."

    if co <= ci:
        return "Ngày check-out phải sau ngày check-in."

    async with async_session_factory() as session:
        # Get hotel
        hotel_result = await session.execute(select(Hotel).where(Hotel.id == hotel_id))
        hotel = hotel_result.scalar_one_or_none()
        if not hotel:
            return f"Không tìm thấy khách sạn '{hotel_id}'."

        # Get rooms that fit guest count
        room_result = await session.execute(
            select(Room).where(
                Room.hotel_id == hotel_id,
                Room.is_active.is_(True),
                Room.max_guests >= guests,
            )
        )
        rooms = room_result.scalars().all()

        if not rooms:
            return f"Không có phòng nào tại {hotel.name} phù hợp cho {guests} khách."

        # Check availability for each room
        available_rooms = []
        for room in rooms:
            avail_result = await session.execute(
                select(RoomAvailability).where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date >= ci,
                    RoomAvailability.date < co,
                    RoomAvailability.is_available.is_(False),
                )
            )
            unavailable_dates = avail_result.scalars().all()

            if not unavailable_dates:
                # Check for custom pricing
                price_result = await session.execute(
                    select(RoomAvailability).where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date >= ci,
                        RoomAvailability.date < co,
                        RoomAvailability.price.is_not(None),
                    )
                )
                custom_prices = price_result.scalars().all()
                avg_price = (
                    sum(p.price for p in custom_prices if p.price) / len(custom_prices)
                    if custom_prices
                    else room.price
                )
                nights = (co - ci).days
                available_rooms.append((room, avg_price, nights))

    if not available_rooms:
        return (
            f"Không có phòng trống tại {hotel.name} từ {check_in} đến {check_out} "
            f"({guests} khách)."
        )

    lines = [
        f"Phòng trống tại **{hotel.name}** ({check_in} → {check_out}, {guests} khách):"
    ]
    for room, price, nights in available_rooms:
        total = price * nights
        lines.append(
            f"  - **{room.name}** ({room.type}): ~{price:.0f} {room.currency}/night "
            f"× {nights} đêm = **{total:.0f} {room.currency}** tổng"
        )

    return "\n".join(lines)


@tool
async def get_popular_hotels(city: str | None = None, limit: int = 5) -> str:
    """Get top-rated popular hotels, optionally filtered by city.
    Use this when the user asks for 'best', 'top', or 'popular' hotels.

    Args:
        city: Optional city to filter by.
        limit: Number of results (default 5, max 10).
    """
    limit = min(limit, 10)

    async with async_session_factory() as session:
        query = select(Hotel).where(Hotel.is_active.is_(True))
        if city:
            query = query.where(Hotel.city.ilike(f"%{city}%"))
        query = query.order_by(Hotel.rating.desc(), Hotel.review_count.desc()).limit(limit)

        result = await session.execute(query)
        hotels = result.scalars().all()

    if not hotels:
        return "Không tìm thấy khách sạn" + (f" tại {city}" if city else "") + "."

    header = f"Top {len(hotels)} khách sạn" + (f" tại {city}" if city else "") + ":"
    lines = [header]
    for i, h in enumerate(hotels, 1):
        lines.append(f"\n{i}. {_format_hotel(h)}")

    return "\n".join(lines)


ALL_TOOLS = [search_hotels, get_hotel_details, check_room_availability, get_popular_hotels]
