from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
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
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.types import JSON

SignalType = Literal["activity", "anomaly", "baseline", "trend"]

_STREET_ALIASES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "DRIVE": "DR",
    "ROAD": "RD",
    "BOULEVARD": "BLVD",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "SOUTH": "S",
    "NORTH": "N",
    "EAST": "E",
    "WEST": "W",
}
_DIRECTION = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})
_SUFFIXES = frozenset({"ST", "AVE", "DR", "RD", "BLVD", "LN", "CT", "PL", "WAY", "TER", "CIR"})
_SKIP = frozenset({"UNITED", "STATES", "TOWNSHIP", "COUNTY", "DISTRICT"})
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="sqlite:///./temporal_proj.db")
    permits_api_url: str | None = Field(default=None)
    socrata_app_token: str | None = Field(default=None)
    socrata_host: str = Field(default="data.sf.gov")
    socrata_api_version: str = Field(default="v2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _create_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


class Base(DeclarativeBase):
    pass


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    place_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
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
    __tablename__ = "source_watermarks"
    __table_args__ = (UniqueConstraint("location_id", "source", name="uq_source_watermarks"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BriefSnapshot(Base):
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


def encode_place_key(address: str) -> str | None:
    """House + direction + street + ZIP. Indexed equality, not a full-table scan."""
    tokens = [
        _STREET_ALIASES.get(token, token)
        for token in _NON_ALNUM.sub(" ", address.upper()).split()
        if token not in _SKIP
    ]
    if not tokens:
        return None

    zip_code = ""
    if tokens[-1].isdigit() and len(tokens[-1]) == 5:
        zip_code = tokens[-1]
        tokens = tokens[:-1]
        if tokens and len(tokens[-1]) == 2 and tokens[-1].isalpha():
            tokens = tokens[:-1]

    house = next((token for token in tokens if token.isdigit()), None)
    if house is None:
        return None
    index = tokens.index(house) + 1
    direction = ""
    if index < len(tokens) and tokens[index] in _DIRECTION:
        direction = tokens[index]
        index += 1

    street: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token in _SUFFIXES or token.isdigit():
            break
        street.append(token)
        index += 1
        if len(street) >= 4:
            break
    if not street:
        return None
    return f"{house}|{direction}|{' '.join(street)}|{zip_code}"


@event.listens_for(Location, "before_insert")
@event.listens_for(Location, "before_update")
def _stamp_place_key(_mapper: object, _connection: object, target: Location) -> None:
    target.place_key = encode_place_key(target.address)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    if "locations" not in inspect(engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(engine).get_columns("locations")}
    if "place_key" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE locations ADD COLUMN place_key VARCHAR(128)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_locations_place_key ON locations (place_key)")
            )
    with SessionLocal() as session:
        dirty = False
        for location in session.scalars(select(Location)).all():
            key = encode_place_key(location.address)
            if location.place_key != key:
                location.place_key = key
                dirty = True
        if dirty:
            session.commit()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
