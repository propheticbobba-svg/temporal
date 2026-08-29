from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
        Index("ix_signals_location_source", "location_id", "source"),
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


class SourceWatermark(Base):
    """Last successful ingest time per location and source.

    Signals are the source of truth. Watermarks decide whether a source is
    stale enough to fetch again (DDIA: derived freshness, not request-path
    recomputation).
    """

    __tablename__ = "source_watermarks"
    __table_args__ = (UniqueConstraint("location_id", "source", name="uq_source_watermarks"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BriefSnapshot(Base):
    """Materialized brief for a location. Rebuilt when source facts change."""

    __tablename__ = "brief_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
