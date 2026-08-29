from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from core.config import get_settings
from ingestion.base import BaseIngester
from ingestion.schema import LocationInput, SignalCreate

logger = logging.getLogger(__name__)

UNUSUAL_LICENSE_STATUSES = {"REV", "EXP", "RVO", "REA"}
BOUNDING_BOX_DEGREES = 0.001
DEFAULT_SOURCE_REGISTRY_PATH = Path(__file__).with_name("biz_license_sources.json")
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
            if city in {candidate.upper() for candidate in source.cities}
            and state in {candidate.upper() for candidate in source.states}
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
    registry_path: Path = DEFAULT_SOURCE_REGISTRY_PATH,
) -> list[BizLicenseSource]:
    payload = json.loads(registry_path.read_text())
    return TypeAdapter(list[BizLicenseSource]).validate_python(payload)
