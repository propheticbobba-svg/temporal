from fastapi import FastAPI

from api.routes.brief import router as brief_router

app = FastAPI(title="Temporal Project")
app.include_router(brief_router)
