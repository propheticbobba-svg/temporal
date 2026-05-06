from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

SignalType = Literal["activity", "anomaly", "baseline", "trend"]


class Base(DeclarativeBase):
    pass


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    signals: Mapped[list[Signal]] = relationship(back_populates="location")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "signal_type in ('activity', 'anomaly', 'baseline', 'trend')",
            name="ck_signals_signal_type",
        ),
        CheckConstraint("confidence >= 0.0 and confidence <= 1.0", name="ck_signals_confidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    location: Mapped[Location] = relationship(back_populates="signals")
