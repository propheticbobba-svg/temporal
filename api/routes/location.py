from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import Location
from db.session import get_session
from ingestion.base import BaseIngester
from ingestion.geocode import GeocodeIngester
from ingestion.schema import LocationInput
from ingestion.service import LocationResolutionError, resolve_location

router = APIRouter(prefix="/location", tags=["location"])


class LocationRead(BaseModel):
    id: int
    address: str = Field(min_length=1)
    latitude: float | None
    longitude: float | None
    confidence: float | None


def get_geocode_ingester() -> BaseIngester:
    return GeocodeIngester()


@router.post("", response_model=LocationRead)
async def create_location(
    request: LocationInput,
    session: Annotated[Session, Depends(get_session)],
    ingester: Annotated[BaseIngester, Depends(get_geocode_ingester)],
) -> LocationRead:
    try:
        location, confidence = await resolve_location(session, request, ingester)
    except LocationResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _to_location_read(location, confidence)


def _to_location_read(location: Location, confidence: float | None) -> LocationRead:
    return LocationRead(
        id=location.id,
        address=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
        confidence=confidence,
    )
