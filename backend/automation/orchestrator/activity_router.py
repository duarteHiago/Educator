"""
Activity Router — dispatches each activity to its correct handler.

Keeps handlers fully decoupled: the router knows about types, not implementations.
"""
from __future__ import annotations

import time

from playwright.async_api import Page

from backend.automation.execution.modes import ExecutionContext
from backend.automation.handlers.material_handler import open_material
from backend.core.logging import get_logger
from backend.schemas.activity import ActivityInfo, ActivityResult, ActivityType

logger = get_logger(__name__)


async def route_activity(
    page: Page,
    activity: ActivityInfo,
    ctx: ExecutionContext | None = None,
) -> ActivityResult:
    """
    Dispatch an activity to the appropriate handler.
    ctx is required only for QUIZ type.
    """
    logger.info(
        "router.dispatch",
        cmid=activity.cmid,
        type=activity.type.value,
        title=activity.title[:60],
    )

    if activity.type == ActivityType.QUIZ:
        if ctx is None:
            raise ValueError("ExecutionContext required for quiz activities.")
        return await _handle_quiz(page, activity, ctx)

    if activity.type in (ActivityType.MATERIAL, ActivityType.OPEN_ONLY):
        return await open_material(page, activity)

    logger.warning("router.no_handler", cmid=activity.cmid, type=activity.type.value)
    return ActivityResult(
        cmid=activity.cmid,
        course_id=activity.course_id,
        type=activity.type,
        title=activity.title,
        success=False,
        error=f"No handler registered for type: {activity.type.value}",
    )


async def _handle_quiz(
    page: Page,
    activity: ActivityInfo,
    ctx: ExecutionContext,
) -> ActivityResult:
    # Import here to keep module-level imports clean and avoid circular refs
    from backend.automation.execution.runner import run_quiz
    from backend.llm.orchestrator import LLMOrchestrator

    started = time.monotonic()
    orc     = LLMOrchestrator()

    try:
        result  = await run_quiz(page, ctx, orchestrator=orc)
        duration = round(time.monotonic() - started, 1)

        success = result is not None and result.status.value in ("success", "dry_run")
        extra: dict = {}
        if result:
            extra = {
                "status":        result.status.value,
                "score_percent": result.score_percent,
                "grade_string":  result.grade_string,
                "attempt_id":    result.attempt_id,
            }

        return ActivityResult(
            cmid=activity.cmid,
            course_id=activity.course_id,
            type=activity.type,
            title=activity.title,
            success=success,
            duration_s=duration,
            extra=extra,
            error=result.error if result else None,
        )

    except Exception as exc:
        duration = round(time.monotonic() - started, 1)
        logger.error("router.quiz_exception", cmid=activity.cmid, error=str(exc))
        return ActivityResult(
            cmid=activity.cmid,
            course_id=activity.course_id,
            type=activity.type,
            title=activity.title,
            success=False,
            error=str(exc),
            duration_s=duration,
        )
