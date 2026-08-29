from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agent.schema import Brief, BriefRequest
from api.brief_service import load_brief
from db.session import get_session
from ingestion.base import BaseIngester
from jobs.scheduler import get_registered_ingesters

router = APIRouter(prefix="/brief", tags=["brief"])


def get_signal_ingesters() -> tuple[BaseIngester, ...]:
    return tuple(
        registration.ingester
        for registration in get_registered_ingesters()
        if registration.source != "geocode"
    )


@router.post("", response_model=Brief)
async def create_brief(
    request: BriefRequest,
    session: Annotated[Session, Depends(get_session)],
    ingesters: Annotated[tuple[BaseIngester, ...], Depends(get_signal_ingesters)],
) -> Brief:
    return await load_brief(session, request, ingesters)
