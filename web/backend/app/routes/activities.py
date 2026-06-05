from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserActivity
from app.schemas import ActivityOut, CourseOut

router = APIRouter(tags=["activities"])


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    course_id: int | None = None,
    activity_type: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityOut]:
    stmt = select(UserActivity).where(UserActivity.user_id == user.id)
    if course_id is not None:
        stmt = stmt.where(UserActivity.course_id == course_id)
    if activity_type is not None:
        stmt = stmt.where(UserActivity.activity_type == activity_type)
    stmt = stmt.order_by(UserActivity.course_id, UserActivity.title)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CourseOut]:
    result = await db.execute(
        select(UserActivity)
        .where(UserActivity.user_id == user.id)
        .order_by(UserActivity.course_id, UserActivity.title)
    )
    activities = result.scalars().all()

    courses: dict[int, CourseOut] = {}
    for act in activities:
        if act.course_id not in courses:
            courses[act.course_id] = CourseOut(
                course_id=act.course_id,
                course_name=act.course_name,
                activities=[],
            )
        courses[act.course_id].activities.append(act)

    return list(courses.values())
