from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from travelmind_ai.config import settings

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Hotel(Base):
    """Read-only mapping of Prisma Hotel model."""

    __tablename__ = "hotels"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    amenities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    images: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    contact_email: Mapped[str | None] = mapped_column(String)
    contact_phone: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    rooms: Mapped[list[Room]] = relationship(back_populates="hotel", lazy="selectin")
    reviews: Mapped[list[Review]] = relationship(back_populates="hotel", lazy="selectin")


class Room(Base):
    """Read-only mapping of Prisma Room model."""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String, ForeignKey("hotels.id"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="USD")
    max_guests: Mapped[int] = mapped_column(Integer, default=2)
    amenities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    images: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    hotel: Mapped[Hotel] = relationship(back_populates="rooms")
    availability: Mapped[list[RoomAvailability]] = relationship(back_populates="room", lazy="selectin")


class Review(Base):
    """Read-only mapping of Prisma Review model."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String)
    hotel_id: Mapped[str] = mapped_column(String, ForeignKey("hotels.id"))
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    hotel: Mapped[Hotel] = relationship(back_populates="reviews")

    __table_args__ = (UniqueConstraint("user_id", "hotel_id"),)


class RoomAvailability(Base):
    """Read-only mapping of Prisma RoomAvailability model."""

    __tablename__ = "room_availability"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id: Mapped[str] = mapped_column(String, ForeignKey("rooms.id"))
    date: Mapped[date_type] = mapped_column(Date)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    price: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    room: Mapped[Room] = relationship(back_populates="availability")
