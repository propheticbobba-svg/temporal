from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, TypeAlias

import httpx
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from .catalog import LICENSE_SOURCES_PATH
from .store import get_settings

logger = logging.getLogger(__name__)

JsonObject: TypeAlias = dict[str, JsonValue]
SignalType: TypeAlias = Literal["activity", "anomaly", "baseline", "trend"]


class LocationInput(BaseModel):
    address: str = Field(min_length=1)
    latitude: float | None = None
    longitude: float | None = None


class SignalCreate(BaseModel):
    source: str = Field(min_length=1)
    signal_type: SignalType
    observed_at: datetime
    value: JsonObject
    summary: str = Field(min_length=1)
    is_anomaly: bool
    confidence: float = Field(ge=0.0, le=1.0)


class BaseIngester(ABC):
    source: str

    @abstractmethod
    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        raise NotImplementedError


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
        unusual_statuses = {"stop work", "violation", "revoked", "expired"}
        return record.status.lower() in unusual_statuses or (
            record.valuation is not None and record.valuation >= 500_000
        )


UNUSUAL_LICENSE_STATUSES = {"REV", "EXP", "RVO", "REA"}
BOUNDING_BOX_DEGREES = 0.001
RawRow: TypeAlias = Mapping[str, object]


class ParsedAddress(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


class BizLicenseFields(BaseModel):
    license_id: str
    account_number: str | None = None
    legal_name: str
    doing_business_as: str | None = None
    license_type: str | None = None
    license_status: str | None = None
    license_start_date: str
    expiration_date: str | None = None


class BizLicenseDefaults(BaseModel):
    account_number: str | None = None
    doing_business_as: str | None = None
    license_type: str | None = None
    license_status: str | None = None
    expiration_date: str | None = None


class BizLicenseQuery(BaseModel):
    strategy: Literal["coordinate_columns", "address_fields"]
    latitude_field: str | None = None
    longitude_field: str | None = None
    address_field: str | None = None
    city_field: str | None = None
    state_field: str | None = None
    zip_field: str | None = None
    date_field: str | None = None
    order_field: str | None = None
    required_non_null: list[str] = Field(default_factory=list)


class BizLicenseSource(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    api_url: str = Field(min_length=1)
    cities: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    query: BizLicenseQuery
    fields: BizLicenseFields
    defaults: BizLicenseDefaults = Field(default_factory=BizLicenseDefaults)
    status_from_expiration: bool = False
    cities_upper: frozenset[str] = Field(default_factory=frozenset, exclude=True)
    states_upper: frozenset[str] = Field(default_factory=frozenset, exclude=True)

    @model_validator(mode="after")
    def index_coverage(self) -> BizLicenseSource:
        object.__setattr__(self, "cities_upper", frozenset(city.upper() for city in self.cities))
        object.__setattr__(self, "states_upper", frozenset(state.upper() for state in self.states))
        return self


class BizLicenseRecord(BaseModel):
    license_id: str
    account_number: str
    legal_name: str
    doing_business_as: str | None = None
    license_type: str
    license_status: str
    license_start_date: datetime
    expiration_date: datetime | None = None
    source_dataset_id: str
    source_name: str

    @field_validator("license_start_date", "expiration_date", mode="before")
    @classmethod
    def parse_socrata_datetime(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, str) and re.fullmatch(r"\d{8}", value):
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
        return value


class BizLicensesIngester(BaseIngester):
    source = "biz_licenses"

    def __init__(
        self,
        api_url: str | None = None,
        timeout_seconds: float = 10.0,
        sources: list[BizLicenseSource] | None = None,
    ) -> None:
        settings = get_settings()
        self.timeout_seconds = timeout_seconds
        self.sources = sources or (
            [self._legacy_source(api_url)] if api_url is not None else load_license_sources()
        )

        self.socrata_app_token = settings.socrata_app_token

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        try:
            records = await self._fetch_records(location)
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("Unable to fetch business licenses for %s: %s", location.address, exc)
            return []

        return [self._to_signal(record) for record in records]

    def matching_sources(self, location: LocationInput) -> list[BizLicenseSource]:
        parsed_address = self._parse_address(location.address)
        city = parsed_address.city.upper() if parsed_address.city is not None else None
        state = parsed_address.state.upper() if parsed_address.state is not None else None
        if city is None or state is None:
            return []

        return [
            source
            for source in self.sources
            if city in source.cities_upper and state in source.states_upper
        ]

    async def _fetch_records(self, location: LocationInput) -> list[BizLicenseRecord]:
        matching_sources = self.matching_sources(location)
        if not matching_sources:
            parsed_address = self._parse_address(location.address)
            logger.info(
                "No business license source configured for %s, %s",
                parsed_address.city or location.address,
                parsed_address.state or "unknown",
            )
            return []

        headers: dict[str, str] = {}
        if self.socrata_app_token is not None:
            headers["X-App-Token"] = self.socrata_app_token

        records: list[BizLicenseRecord] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for source in matching_sources:
                try:
                    records.extend(
                        await self._fetch_records_for_source(client, source, location, headers)
                    )
                except (httpx.HTTPError, ValidationError, ValueError) as exc:
                    logger.warning(
                        "Unable to fetch business licenses from %s for %s: %s",
                        source.id,
                        location.address,
                        exc,
                    )

        return records

    async def _fetch_records_for_source(
        self,
        client: httpx.AsyncClient,
        source: BizLicenseSource,
        location: LocationInput,
        headers: dict[str, str],
    ) -> list[BizLicenseRecord]:
        response = await client.get(
            source.api_url,
            params=self._query_params(source, location),
            headers=headers,
        )
        response.raise_for_status()

        rows = TypeAdapter(list[RawRow]).validate_python(response.json())
        return [self._normalize_row(source, row) for row in rows]

    def _query_params(self, source: BizLicenseSource, location: LocationInput) -> dict[str, str]:
        query = source.query
        params = {"$limit": "50"}
        if query.order_field is not None:
            params["$order"] = f"{query.order_field} DESC"

        where_clauses = self._required_where_clauses(query)
        if query.strategy == "coordinate_columns":
            coordinate_where = self._coordinate_where_clause(source, location)
            if coordinate_where is not None:
                where_clauses.append(coordinate_where)
        elif query.strategy == "address_fields":
            where_clauses.extend(self._address_where_clauses(source, location))

        if where_clauses:
            params["$where"] = " and ".join(where_clauses)
        return params

    def _required_where_clauses(self, query: BizLicenseQuery) -> list[str]:
        return [f"{field} IS NOT NULL" for field in query.required_non_null]

    def _coordinate_where_clause(
        self,
        source: BizLicenseSource,
        location: LocationInput,
    ) -> str | None:
        query = source.query
        if (
            location.latitude is None
            or location.longitude is None
            or query.latitude_field is None
            or query.longitude_field is None
        ):
            return None

        min_latitude = location.latitude - BOUNDING_BOX_DEGREES
        max_latitude = location.latitude + BOUNDING_BOX_DEGREES
        min_longitude = location.longitude - BOUNDING_BOX_DEGREES
        max_longitude = location.longitude + BOUNDING_BOX_DEGREES
        return (
            f"{query.latitude_field} between {min_latitude} and {max_latitude} "
            f"and {query.longitude_field} between {min_longitude} and {max_longitude}"
        )

    def _address_where_clauses(
        self,
        source: BizLicenseSource,
        location: LocationInput,
    ) -> list[str]:
        parsed_address = self._parse_address(location.address)
        query = source.query
        clauses: list[str] = []
        if query.address_field is not None and parsed_address.street is not None:
            clauses.append(
                f"upper({query.address_field}) = {self._soql_string(parsed_address.street)}"
            )
        if query.city_field is not None and parsed_address.city is not None:
            clauses.append(f"upper({query.city_field}) = {self._soql_string(parsed_address.city)}")
        if query.state_field is not None and parsed_address.state is not None:
            clauses.append(
                f"upper({query.state_field}) = {self._soql_string(parsed_address.state)}"
            )
        if query.zip_field is not None and parsed_address.zip_code is not None:
            zip_pattern = self._soql_string(parsed_address.zip_code + "%")
            clauses.append(f"{query.zip_field} like {zip_pattern}")
        return clauses

    def _normalize_row(self, source: BizLicenseSource, row: RawRow) -> BizLicenseRecord:
        fields = source.fields
        expiration_date = (
            self._get_str(row, fields.expiration_date) or source.defaults.expiration_date
        )
        license_status = self._get_str(row, fields.license_status) or source.defaults.license_status
        if source.status_from_expiration and expiration_date:
            license_status = "EXP"

        license_id = self._required_str(row, fields.license_id)
        account_number = (
            self._get_str(row, fields.account_number)
            or source.defaults.account_number
            or license_id
        )
        license_type = (
            self._get_str(row, fields.license_type)
            or source.defaults.license_type
            or "Business License"
        )

        return BizLicenseRecord.model_validate(
            {
                "license_id": license_id,
                "account_number": account_number,
                "legal_name": self._required_str(row, fields.legal_name),
                "doing_business_as": (
                    self._get_str(row, fields.doing_business_as)
                    or source.defaults.doing_business_as
                ),
                "license_type": license_type,
                "license_status": license_status or "Active",
                "license_start_date": self._required_str(row, fields.license_start_date),
                "expiration_date": expiration_date,
                "source_dataset_id": source.id,
                "source_name": source.name,
            }
        )

    def _to_signal(self, record: BizLicenseRecord) -> SignalCreate:
        is_anomaly = self._is_unusual(record)

        return SignalCreate(
            source=self.source,
            signal_type="anomaly" if is_anomaly else "activity",
            observed_at=record.license_start_date,
            value={
                "license_id": record.license_id,
                "account_number": record.account_number,
                "legal_name": record.legal_name,
                "doing_business_as": record.doing_business_as,
                "license_type": record.license_type,
                "license_status": record.license_status,
                "expiration_date": self._isoformat_utc(record.expiration_date),
                "source_dataset_id": record.source_dataset_id,
                "source_name": record.source_name,
            },
            summary=self._summary(record),
            is_anomaly=is_anomaly,
            confidence=1.0,
        )

    def _summary(self, record: BizLicenseRecord) -> str:
        business_name = record.doing_business_as or record.legal_name
        license_label = self._license_label(record.license_type)
        expiration_text = (
            f"expiring {self._date_string(record.expiration_date)}"
            if record.expiration_date is not None
            else "with no expiration date on record"
        )
        return (
            f"A {license_label} for {business_name} was issued, "
            f"currently {self._status_text(record.license_status)}, {expiration_text}."
        )

    def _is_unusual(self, record: BizLicenseRecord) -> bool:
        if record.license_status.upper() in UNUSUAL_LICENSE_STATUSES:
            return True
        if record.expiration_date is None:
            return False

        return self._ensure_utc(record.expiration_date) < datetime.now(tz=UTC)

    def _status_text(self, license_status: str) -> str:
        return {
            "AAI": "active",
            "AAC": "active",
            "REV": "revoked",
            "EXP": "expired",
            "RVO": "revoked",
            "REA": "revocation appealed",
        }.get(license_status.upper(), license_status.lower())

    def _license_label(self, license_type: str) -> str:
        label = license_type.lower()
        if label.endswith("license"):
            return label

        return f"{label} license"

    def _date_string(self, value: datetime) -> str:
        return self._ensure_utc(value).date().isoformat()

    def _isoformat_utc(self, value: datetime | None) -> str | None:
        if value is None:
            return None

        return self._ensure_utc(value).isoformat().replace("+00:00", "Z")

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)

    def _legacy_source(self, api_url: str) -> BizLicenseSource:
        return BizLicenseSource.model_validate(
            {
                "id": "custom_business_licenses",
                "name": "Custom Business Licenses",
                "api_url": api_url,
                "cities": ["CHICAGO"],
                "states": ["IL"],
                "query": {
                    "strategy": "coordinate_columns",
                    "latitude_field": "latitude",
                    "longitude_field": "longitude",
                    "date_field": "license_start_date",
                    "order_field": "license_start_date",
                    "required_non_null": ["license_start_date"],
                },
                "fields": {
                    "license_id": "license_id",
                    "account_number": "account_number",
                    "legal_name": "legal_name",
                    "doing_business_as": "doing_business_as_name",
                    "license_type": "license_description",
                    "license_status": "license_status",
                    "license_start_date": "license_start_date",
                    "expiration_date": "expiration_date",
                },
            }
        )

    def _parse_address(self, address: str) -> ParsedAddress:
        parts = [part.strip().upper() for part in address.split(",") if part.strip()]
        if len(parts) >= 4:
            return ParsedAddress(
                street=parts[0],
                city=parts[-3],
                state=parts[-2],
                zip_code=self._zip_prefix(parts[-1]),
            )
        return ParsedAddress(street=address.strip().upper() or None)

    def _zip_prefix(self, value: str) -> str | None:
        match = re.search(r"\d{5}", value)
        return match.group(0) if match is not None else None

    def _soql_string(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _required_str(self, row: RawRow, field: str) -> str:
        value = self._get_str(row, field)
        if value is None:
            raise ValueError(f"Business license row is missing {field}")
        return value

    def _get_str(self, row: RawRow, field: str | None) -> str | None:
        if field is None:
            return None

        value: object = row
        for part in field.split("."):
            if not isinstance(value, Mapping):
                return None
            value = value.get(part)

        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        if isinstance(value, int | float):
            return str(value)
        return None


def load_license_sources(
    registry_path: Path = LICENSE_SOURCES_PATH,
) -> list[BizLicenseSource]:
    payload = json.loads(registry_path.read_text())
    return TypeAdapter(list[BizLicenseSource]).validate_python(payload)


SFPD_INCIDENTS_DATASET_ID = "wg3w-h783"
CRIME_RADIUS_METERS = 400
CRIME_LOOKBACK_DAYS = 365
MIN_DISTINCT_INTERSECTIONS = 8
SF_LAT_MIN = 37.70
SF_LAT_MAX = 37.84
SF_LNG_MIN = -122.55
SF_LNG_MAX = -122.35
CRIME_REPORT_TYPES = ("Initial", "Coplogic Initial", "Vehicle Initial")
CRIME_VEHICLE_CATEGORIES = ("Motor Vehicle Theft", "Motor Vehicle Theft?")
CRIME_LARCENY_VEHICLE_SUBCATEGORIES = (
    "Larceny - From Vehicle",
    "Theft From Vehicle",
    "Larceny - Auto Parts",
)
CRIME_VANDALISM_CATEGORIES = ("Malicious Mischief", "Vandalism")


class CrimeAggregateRow(BaseModel):
    total_incidents: int = 0
    distinct_intersections: int = 0
    burglary: int = 0
    robbery: int = 0
    vehicle: int = 0
    vandalism: int = 0
    data_as_of: str | None = None


class CrimeNearbyIngester(BaseIngester):
    source = "crime_nearby"

    def __init__(
        self,
        host: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        settings = get_settings()
        self.host = host if host is not None else settings.socrata_host
        self.api_version = api_version if api_version is not None else settings.socrata_api_version
        self.timeout_seconds = timeout_seconds
        self.socrata_app_token = settings.socrata_app_token
        self.api_url = socrata_resource_url(
            self.host,
            self.api_version,
            SFPD_INCIDENTS_DATASET_ID,
        )

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        if location.latitude is None or location.longitude is None:
            logger.info("Crime nearby skipped: no coordinates for %s", location.address)
            return []
        if not in_san_francisco(location.latitude, location.longitude):
            logger.info("Crime nearby skipped: %s is outside San Francisco", location.address)
            return []

        try:
            row = await self._fetch_aggregate(location)
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("Unable to fetch nearby crime for %s: %s", location.address, exc)
            return []

        if row is None or row.distinct_intersections < MIN_DISTINCT_INTERSECTIONS:
            logger.info("Crime nearby skipped: thin data for %s", location.address)
            return []

        return [self._to_signal(row)]

    async def _fetch_aggregate(self, location: LocationInput) -> CrimeAggregateRow | None:
        headers: dict[str, str] = {}
        if self.socrata_app_token is not None:
            headers["X-App-Token"] = self.socrata_app_token

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.api_url,
                params=self._query_params(location),
                headers=headers,
            )
            response.raise_for_status()

        rows = TypeAdapter(list[RawRow]).validate_python(response.json())
        if not rows:
            return None
        return CrimeAggregateRow.model_validate(rows[0])

    def _query_params(
        self,
        location: LocationInput,
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        if location.latitude is None or location.longitude is None:
            raise ValueError("Crime nearby query requires latitude and longitude")

        current = now or datetime.now(tz=UTC)
        since = (current - timedelta(days=CRIME_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        report_types = _soql_in(CRIME_REPORT_TYPES)
        vehicle_categories = _soql_in(CRIME_VEHICLE_CATEGORIES)
        larceny_subcategories = _soql_in(CRIME_LARCENY_VEHICLE_SUBCATEGORIES)
        vandalism_categories = _soql_in(CRIME_VANDALISM_CATEGORIES)
        vehicle_case = (
            f"incident_category in ({vehicle_categories}) OR "
            f"(incident_category = 'Larceny Theft' AND "
            f"incident_subcategory in ({larceny_subcategories}))"
        )
        category_filter = (
            f"incident_category in ('Burglary', 'Robbery', {vehicle_categories}, "
            f"{vandalism_categories}) OR "
            f"(incident_category = 'Larceny Theft' AND "
            f"incident_subcategory in ({larceny_subcategories}))"
        )
        return {
            "$select": (
                "count(distinct incident_id) as total_incidents, "
                "count(distinct intersection) as distinct_intersections, "
                "max(data_as_of) as data_as_of, "
                "count(distinct case(incident_category = 'Burglary', incident_id)) as burglary, "
                "count(distinct case(incident_category = 'Robbery', incident_id)) as robbery, "
                f"count(distinct case({vehicle_case}, incident_id)) as vehicle, "
                f"count(distinct case(incident_category in ({vandalism_categories}), "
                f"incident_id)) as vandalism"
            ),
            "$where": (
                f"within_circle(point, {location.latitude}, {location.longitude}, "
                f"{CRIME_RADIUS_METERS}) AND incident_datetime >= '{since}' AND "
                f"report_type_description in ({report_types}) AND "
                f"resolution != 'Unfounded' AND ({category_filter})"
            ),
        }

    def _to_signal(self, row: CrimeAggregateRow) -> SignalCreate:
        return SignalCreate(
            source=self.source,
            signal_type="trend",
            observed_at=datetime.now(tz=UTC),
            value={
                "burglary": row.burglary,
                "vehicle": row.vehicle,
                "robbery": row.robbery,
                "vandalism": row.vandalism,
                "total_incidents": row.total_incidents,
                "distinct_intersections": row.distinct_intersections,
                "radius_meters": CRIME_RADIUS_METERS,
                "window_days": CRIME_LOOKBACK_DAYS,
                "data_as_of": row.data_as_of,
            },
            summary=(
                f"{row.total_incidents} incidents within {CRIME_RADIUS_METERS}m in the last "
                f"12 months ({row.burglary} burglary, {row.vehicle} vehicle, "
                f"{row.robbery} robbery, {row.vandalism} vandalism)."
            ),
            is_anomaly=False,
            confidence=1.0,
        )


def socrata_resource_url(host: str, api_version: str, dataset_id: str) -> str:
    if api_version == "v3":
        return f"https://{host}/api/v3/views/{dataset_id}/query.json"
    return f"https://{host}/resource/{dataset_id}.json"


def in_san_francisco(latitude: float, longitude: float) -> bool:
    return SF_LAT_MIN <= latitude <= SF_LAT_MAX and SF_LNG_MIN <= longitude <= SF_LNG_MAX


def _soql_in(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)
