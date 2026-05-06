from fastapi import FastAPI

from api.routes.brief import router as brief_router
from api.routes.location import router as location_router

app = FastAPI(title="Temporal Project")
app.include_router(brief_router)
app.include_router(location_router)
