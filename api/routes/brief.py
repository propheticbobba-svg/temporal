from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agent.brief import build_brief
from agent.schema import Brief, BriefRequest
from db.session import get_session

router = APIRouter(prefix="/brief", tags=["brief"])


@router.post("", response_model=Brief)
async def create_brief(
    request: BriefRequest,
    session: Annotated[Session, Depends(get_session)],
) -> Brief:
    return build_brief(session, request)
