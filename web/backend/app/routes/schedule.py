
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import ScheduledRun, User
from app.schemas import ScheduleCreate, ScheduleOut

router = APIRouter(tags=["schedule"])


def _next_run(cron_expr: str) -> datetime:
    it = croniter(cron_expr, datetime.now(timezone.utc))
    return it.get_next(datetime)


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleOut:
    if not croniter.is_valid(body.cron_expr):
        raise HTTPException(status_code=400, detail="Expressão cron inválida.")

    schedule = ScheduledRun(
        user_id=user.id,
        course_id=body.course_id,
        cron_expr=body.cron_expr,
        mode=body.mode,
        next_run_at=_next_run(body.cron_expr),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleOut]:
    result = await db.execute(
        select(ScheduledRun)
        .where(ScheduledRun.user_id == user.id)
        .order_by(ScheduledRun.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def toggle_schedule(
    schedule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleOut:
    from uuid import UUID
    result = await db.execute(
        select(ScheduledRun).where(
            ScheduledRun.id == UUID(schedule_id),
            ScheduledRun.user_id == user.id,
        )
    )
    sched = result.scalar_one_or_none()
    if sched is None:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    sched.is_active = not sched.is_active
    await db.commit()
    await db.refresh(sched)
    return sched


@router.delete("/{schedule_id}", status_code=204, response_class=Response)
async def delete_schedule(
    schedule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    from uuid import UUID
    result = await db.execute(
        select(ScheduledRun).where(
            ScheduledRun.id == UUID(schedule_id),
            ScheduledRun.user_id == user.id,
        )
    )
    sched = result.scalar_one_or_none()
    if sched is None:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    await db.delete(sched)
    await db.commit()
