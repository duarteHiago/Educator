"""
Celery Beat task: process scheduled runs.

Runs every minute. Queries ScheduledRun rows where next_run_at <= now()
and is_active=True, then dispatches run_course_task for each.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from app.celery_app import celery
from app.models import ScheduledRun
from app.tasks.db import get_session

logger = logging.getLogger(__name__)


def _next_run(cron_expr: str, after: datetime) -> datetime:
    it = croniter(cron_expr, after)
    return it.get_next(datetime)


@celery.task
def process_scheduled_runs() -> dict:
    now = datetime.now(timezone.utc)
    dispatched = 0

    with get_session() as db:
        due = db.execute(
            select(ScheduledRun).where(
                ScheduledRun.is_active.is_(True),
                ScheduledRun.next_run_at <= now,
            )
        ).scalars().all()

        for sched in due:
            celery.send_task(
                "app.tasks.execution.run_course_task",
                args=[str(sched.user_id), sched.course_id, sched.mode],
            )
            sched.last_run_at = now
            sched.next_run_at = _next_run(sched.cron_expr, now)
            dispatched += 1
            logger.info(
                "scheduler.dispatched",
                extra={
                    "schedule_id": str(sched.id),
                    "user_id": str(sched.user_id),
                    "next_run": sched.next_run_at.isoformat(),
                },
            )

    return {"dispatched": dispatched}
