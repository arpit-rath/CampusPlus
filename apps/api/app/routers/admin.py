"""Admin-only endpoints. Currently just "Ask CampusPluse" (build-plan.md §6/§7).

Wired at integration time — Track B built `app.pipeline.ask.answer_admin_question`
as a pure function over a list of complaint dicts; this router is the thin
DB-fetching wrapper around it that `apps/web/src/lib/api.ts`'s `askAdmin`
actually calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Complaint
from app.pipeline.ask import answer_admin_question
from app.routers.complaints import _LOAD_OPTS, _to_read_model

router = APIRouter()


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    cited_complaint_ids: list[str]


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    stmt = select(Complaint).options(*_LOAD_OPTS).order_by(Complaint.created_at.desc())
    complaints = (await db.execute(stmt)).scalars().all()

    # answer_admin_question only reads via .get() on plain dicts — reuse the
    # same read-model shape the frontend already sees so field names always
    # match (category_slug, department_name, priority_score, ...).
    complaint_dicts = [
        {**_to_read_model(c).model_dump(mode="json"), "id": str(c.id)} for c in complaints
    ]

    result = await answer_admin_question(payload.question, complaint_dicts)
    return AskResponse(**result)
