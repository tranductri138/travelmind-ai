from __future__ import annotations

from pydantic import BaseModel


class BookingEventData(BaseModel):
    """Data received from RabbitMQ booking events."""

    id: str
    user_id: str
    room_id: str
    check_in: str
    check_out: str
    guests: int
    total_price: float
    currency: str = "USD"
    status: str = "PENDING"
    special_requests: str | None = None
    hotel_name: str | None = None
    hotel_city: str | None = None
    hotel_country: str | None = None


class BookingAnalyticsEvent(BaseModel):
    """Published analytics event for booking actions."""

    booking_id: str
    action: str
    user_id: str
    room_id: str
    check_in: str
    check_out: str
    guests: int
    total_price: float
    currency: str
    status: str
    hotel_name: str | None = None
    hotel_city: str | None = None
    hotel_country: str | None = None
