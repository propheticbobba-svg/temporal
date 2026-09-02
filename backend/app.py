"""HTTP door. Address in, brief out.

fetch.py talks to public APIs. place.py identifies the pin and stores
signals. brief.py classifies, graphs, and snapshots. store.py is the DB.
"""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .brief import Brief, BriefRequest, load_brief
from .fetch import BaseIngester, GeocodeIngester, LocationInput
from .place import LocationResolutionError, get_registered_ingesters, resolve_location
from .store import ensure_schema, get_session

logger = logging.getLogger("temporal")
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class LocationRead(BaseModel):
    id: int
    address: str = Field(min_length=1)
    latitude: float | None
    longitude: float | None
    confidence: float | None


def get_geocode_ingester() -> BaseIngester:
    return GeocodeIngester()


def get_signal_ingesters() -> tuple[BaseIngester, ...]:
    return tuple(
        registration.ingester
        for registration in get_registered_ingesters()
        if registration.source != "geocode"
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ensure_schema()
    yield


app = FastAPI(title="Temporal", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path != "/health":
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/location", response_model=LocationRead)
async def create_location(
    request: LocationInput,
    session: Annotated[Session, Depends(get_session)],
    ingester: Annotated[BaseIngester, Depends(get_geocode_ingester)],
) -> LocationRead:
    try:
        location, confidence = await resolve_location(session, request, ingester)
    except LocationResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LocationRead(
        id=location.id,
        address=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
        confidence=confidence,
    )


@app.post("/brief", response_model=Brief)
async def create_brief(
    request: BriefRequest,
    session: Annotated[Session, Depends(get_session)],
    ingesters: Annotated[tuple[BaseIngester, ...], Depends(get_signal_ingesters)],
) -> Brief:
    return await load_brief(session, request, ingesters)


# Literal path so Vercel can promote the Vite build to the CDN.
# Hashed JS/CSS stay immutable; HTML must not be cached across deploys.
if FRONTEND_DIST.exists():
    app.frontend("/", directory="frontend/dist")
