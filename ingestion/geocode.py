import logging
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from ingestion.base import BaseIngester
from ingestion.schema import LocationInput, SignalCreate

logger = logging.getLogger(__name__)

DEFAULT_CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
DEFAULT_BENCHMARK = "Public_AR_Current"


class CensusCoordinates(BaseModel):
    longitude: float = Field(validation_alias=AliasChoices("x", "longitude"))
    latitude: float = Field(validation_alias=AliasChoices("y", "latitude"))


class CensusTigerLine(BaseModel):
    tiger_line_id: str = Field(validation_alias=AliasChoices("tigerLineId", "tiger_line_id"))
    side: str


class CensusAddressMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    matched_address: str = Field(validation_alias=AliasChoices("matchedAddress", "matched_address"))
    coordinates: CensusCoordinates
    tiger_line: CensusTigerLine = Field(validation_alias=AliasChoices("tigerLine", "tiger_line"))
    match_status: Literal["Exact", "Non_Exact"] | None = Field(
        default=None,
        validation_alias=AliasChoices("matchStatus", "match_status"),
    )


class CensusGeocoderResult(BaseModel):
    address_matches: list[CensusAddressMatch] = Field(
        default_factory=list,
        validation_alias=AliasChoices("addressMatches", "address_matches"),
    )


class CensusGeocoderResponse(BaseModel):
    result: CensusGeocoderResult


class GeocodeIngester(BaseIngester):
    source = "geocode"

    def __init__(
        self,
        api_url: str = DEFAULT_CENSUS_GEOCODER_URL,
        timeout_seconds: float = 10.0,
        benchmark: str = DEFAULT_BENCHMARK,
    ) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.benchmark = benchmark

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        try:
            matches = await self._fetch_matches(location)
        except (httpx.HTTPError, ValidationError) as exc:
            logger.warning("Unable to geocode %s: %s", location.address, exc)
            return []

        if not matches:
            logger.warning("No geocode match found for %s", location.address)
            return []

        signal = self._to_signal(matches[0])
        if signal is None:
            logger.warning("No usable geocode match found for %s", location.address)
            return []

        return [signal]

    async def _fetch_matches(self, location: LocationInput) -> list[CensusAddressMatch]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "temporal-place-intelligence/0.1"},
        ) as client:
            response = await client.get(
                self.api_url,
                params={
                    "address": location.address,
                    "benchmark": self.benchmark,
                    "format": "json",
                },
            )
            response.raise_for_status()

        payload = CensusGeocoderResponse.model_validate(response.json())
        return payload.result.address_matches

    def _to_signal(self, match: CensusAddressMatch) -> SignalCreate | None:
        confidence = self._confidence_for_match(match.match_status)
        if confidence is None:
            return None

        return SignalCreate(
            source=self.source,
            signal_type="baseline",
            observed_at=datetime.now(tz=UTC),
            value={
                "matched_address": match.matched_address,
                "latitude": match.coordinates.latitude,
                "longitude": match.coordinates.longitude,
                "tiger_line_id": match.tiger_line.tiger_line_id,
                "side": match.tiger_line.side,
            },
            summary=(
                f"The address was resolved to {match.matched_address} at "
                f"{match.coordinates.latitude:.6f}, {match.coordinates.longitude:.6f}."
            ),
            is_anomaly=False,
            confidence=confidence,
        )

    def _confidence_for_match(
        self,
        match_status: Literal["Exact", "Non_Exact"] | None,
    ) -> float | None:
        if match_status == "Non_Exact":
            return 0.7
        if match_status == "Exact" or match_status is None:
            return 1.0
        return None
