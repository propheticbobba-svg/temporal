from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.brief import router as brief_router
from api.routes.location import router as location_router
from db.models import Base
from db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Temporal Project", lifespan=lifespan)
app.include_router(brief_router)
app.include_router(location_router)
