
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import QuizExecution, User
from app.schemas import RunOut

router = APIRouter(tags=["runs"])


@router.get("", response_model=list[RunOut])
async def list_runs(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunOut]:
    result = await db.execute(
        select(QuizExecution)
        .where(QuizExecution.user_id == user.id)
        .order_by(QuizExecution.started_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{execution_id}", response_model=RunOut)
async def get_run(
    execution_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunOut:
    result = await db.execute(
        select(QuizExecution).where(
            QuizExecution.execution_id == execution_id,
            QuizExecution.user_id == user.id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    return run
