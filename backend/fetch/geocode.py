from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter

from .base import BaseIngester, LocationInput, SignalCreate

logger = logging.getLogger(__name__)


DEFAULT_CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
DEFAULT_PHOTON_URL = "https://photon.komoot.io/api/"
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_BENCHMARK = "Public_AR_Current"
GEOCODER_USER_AGENT = "temporal-place-intelligence/0.1"
GEOCODER_HEADERS = {
    "User-Agent": GEOCODER_USER_AGENT,
    "Accept": "application/json",
}


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


class NominatimHit(BaseModel):
    display_name: str
    lat: float
    lon: float

    def to_census_match(self) -> CensusAddressMatch:
        return _osm_match(_short_osm_label(self.display_name), self.lat, self.lon, "nominatim")


class PhotonProperties(BaseModel):
    name: str | None = None
    housenumber: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    countrycode: str | None = None


class PhotonGeometry(BaseModel):
    coordinates: list[float]


class PhotonFeature(BaseModel):
    geometry: PhotonGeometry
    properties: PhotonProperties = Field(default_factory=PhotonProperties)

    def to_census_match(self) -> CensusAddressMatch | None:
        if len(self.geometry.coordinates) < 2:
            return None
        country = (self.properties.countrycode or "US").upper()
        if country and country != "US":
            return None
        longitude, latitude = self.geometry.coordinates[0], self.geometry.coordinates[1]
        return _osm_match(self._label(), latitude, longitude, "photon")

    def _label(self) -> str:
        props = self.properties
        street = " ".join(part for part in (props.housenumber, props.street) if part)
        parts = [
            part for part in (street or props.name, props.city, props.state, props.postcode) if part
        ]
        return ", ".join(parts) or "Resolved address"


class PhotonResponse(BaseModel):
    features: list[PhotonFeature] = Field(default_factory=list)


class GeocodeIngester(BaseIngester):
    source = "geocode"

    def __init__(
        self,
        api_url: str = DEFAULT_CENSUS_GEOCODER_URL,
        timeout_seconds: float = 10.0,
        benchmark: str = DEFAULT_BENCHMARK,
        nominatim_url: str = DEFAULT_NOMINATIM_URL,
        photon_url: str = DEFAULT_PHOTON_URL,
    ) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.benchmark = benchmark
        self.nominatim_url = nominatim_url
        self.photon_url = photon_url

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        try:
            matches = await self._fetch_matches(location)
        except Exception as exc:
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
        try:
            matches = await self._fetch_census(location)
            if matches:
                return matches
            logger.info("Census returned no matches for %s; trying fallbacks", location.address)
        except Exception as exc:
            logger.warning(
                "Census geocoder failed for %s: %s; trying fallbacks", location.address, exc
            )

        for name, fetch in (("photon", self._fetch_photon), ("nominatim", self._fetch_nominatim)):
            try:
                matches = await fetch(location)
            except Exception as exc:
                logger.warning("%s geocoder failed for %s: %s", name, location.address, exc)
                continue
            if matches:
                return matches
        return []

    async def _fetch_census(self, location: LocationInput) -> list[CensusAddressMatch]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=GEOCODER_HEADERS,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                self.api_url,
                params={
                    "address": compact_geocode_query(location.address),
                    "benchmark": self.benchmark,
                    "format": "json",
                },
            )
            response.raise_for_status()

        payload = CensusGeocoderResponse.model_validate(response.json())
        return payload.result.address_matches

    async def _fetch_photon(self, location: LocationInput) -> list[CensusAddressMatch]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=GEOCODER_HEADERS,
        ) as client:
            response = await client.get(
                self.photon_url,
                params={"q": compact_geocode_query(location.address), "limit": 1},
            )
            response.raise_for_status()
        payload = PhotonResponse.model_validate(response.json())
        matches = [match for feature in payload.features if (match := feature.to_census_match())]
        return matches

    async def _fetch_nominatim(self, location: LocationInput) -> list[CensusAddressMatch]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=GEOCODER_HEADERS,
        ) as client:
            response = await client.get(
                self.nominatim_url,
                params={
                    "q": compact_geocode_query(location.address),
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "us",
                },
            )
            response.raise_for_status()

        hits = TypeAdapter(list[NominatimHit]).validate_python(response.json())
        return [hit.to_census_match() for hit in hits]

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


def _osm_match(label: str, latitude: float, longitude: float, source: str) -> CensusAddressMatch:
    return CensusAddressMatch(
        matched_address=label,
        coordinates=CensusCoordinates(longitude=longitude, latitude=latitude),
        tiger_line=CensusTigerLine(tiger_line_id=source, side="N"),
        match_status="Non_Exact",
    )


def is_compact_address(address: str) -> bool:
    stripped = address.strip()
    return len(stripped) <= 80 and stripped.count(",") <= 4 and "United States" not in stripped


def compact_geocode_query(address: str) -> str:
    stripped = address.strip()
    if is_compact_address(stripped):
        return stripped

    parts = [part.strip() for part in stripped.split(",") if part.strip()]
    parts = [part for part in parts if part.lower() not in {"united states", "usa"}]
    street = next((part for part in parts if re.search(r"\d", part)), None)
    zip_part = next(
        (part for part in reversed(parts) if re.search(r"\b\d{5}(?:-\d{4})?\b", part)),
        None,
    )
    if street and zip_part and zip_part != street:
        return f"{street}, {zip_part}"
    if street:
        return street
    if len(parts) >= 2:
        return ", ".join(parts[: min(4, len(parts))])
    return parts[0] if parts else stripped


def _short_osm_label(display_name: str) -> str:
    compacted = compact_geocode_query(display_name)
    if is_compact_address(compacted):
        return compacted
    parts = [part.strip() for part in display_name.split(",") if part.strip()]
    parts = [part for part in parts if part.lower() not in {"united states", "usa"}]
    if len(parts) <= 4:
        return ", ".join(parts)
    return ", ".join([parts[0], *parts[-3:]])
