from __future__ import annotations

import logging
from datetime import datetime

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..store import get_settings
from .base import BaseIngester, LocationInput, SignalCreate

logger = logging.getLogger(__name__)


class PermitRecord(BaseModel):
    permit_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    permit_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    issued_at: datetime
    valuation: float | None = Field(default=None, ge=0.0)


class PermitsApiResponse(BaseModel):
    permits: list[PermitRecord] = Field(default_factory=list)


class PermitsIngester(BaseIngester):
    source = "permits"

    def __init__(self, api_url: str | None = None, timeout_seconds: float = 10.0) -> None:
        settings = get_settings()
        self.api_url = api_url or settings.permits_api_url
        self.timeout_seconds = timeout_seconds

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        if self.api_url is None:
            logger.info("Permits API URL is not configured")
            return []

        try:
            records = await self._fetch_records(location)
        except (httpx.HTTPError, ValidationError) as exc:
            logger.warning("Unable to fetch permits for %s: %s", location.address, exc)
            return []

        return [self._to_signal(record) for record in records]

    async def _fetch_records(self, location: LocationInput) -> list[PermitRecord]:
        assert self.api_url is not None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.api_url, params={"address": location.address})
            response.raise_for_status()

        payload = PermitsApiResponse.model_validate(response.json())
        return payload.permits

    def _to_signal(self, record: PermitRecord) -> SignalCreate:
        is_anomaly = self._is_unusual(record)
        valuation_text = (
            f" valued at ${record.valuation:,.0f}" if record.valuation is not None else ""
        )

        return SignalCreate(
            source=self.source,
            signal_type="anomaly" if is_anomaly else "activity",
            observed_at=record.issued_at,
            value={
                "permit_id": record.permit_id,
                "status": record.status,
                "permit_type": record.permit_type,
                "description": record.description,
                "valuation": record.valuation,
            },
            summary=(
                f"A {record.permit_type.lower()} permit was issued with status "
                f"{record.status.lower()}{valuation_text}."
            ),
            is_anomaly=is_anomaly,
            confidence=1.0,
        )

    def _is_unusual(self, record: PermitRecord) -> bool:
        return record.status.lower() in {"stop work", "violation", "revoked"}
