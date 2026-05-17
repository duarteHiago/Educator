"""
Course Runner — executes activities for a course in controlled sequence.

Responsibilities:
  - Load activity inventory for the course
  - Filter by allowed types and profile rules
  - Execute each activity via the router
  - Apply cooldowns between activities
  - Safety-stop on consecutive failures
  - Return a structured CourseRunResult
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

from playwright.async_api import Page

from backend.automation.discovery.activity_discovery import ActivityDiscovery
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.orchestrator.activity_router import route_activity
from backend.automation.profiles.course_profiles import get_profile, is_safe, CourseProfile
from backend.core.logging import get_logger
from backend.schemas.activity import ActivityInfo, ActivityResult, ActivityType

logger = get_logger(__name__)


@dataclass
class CourseRunConfig:
    mode:             ExecutionMode     = ExecutionMode.DRY_RUN
    activity_types:   list[ActivityType] = field(
        default_factory=lambda: [ActivityType.QUIZ]
    )
    max_activities:   int   = 100
    cooldown_min_s:   float = 30.0
    cooldown_max_s:   float = 90.0
    max_failures:     int   = 3      # consecutive failures before safety stop
    force_submit:     bool  = False  # explicit override for HIGH_VALUE (dangerous)


@dataclass
class CourseRunResult:
    course_id:    int
    course_name:  str
    results:      list[ActivityResult] = field(default_factory=list)
    stopped_early: bool     = False
    stop_reason:   str | None = None
    started_at:    float = field(default_factory=time.monotonic)
    finished_at:   float = 0.0

    @property
    def successful(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def duration_s(self) -> float:
        return round(self.finished_at - self.started_at, 1) if self.finished_at else 0.0


async def run_course(
    page: Page,
    course_id: int,
    config: CourseRunConfig,
    discovery: ActivityDiscovery,
) -> CourseRunResult:
    """
    Run all matching activities for a course sequentially.
    Enforces SAFE_TEST/HIGH_VALUE guards regardless of config.
    """
    inventory  = discovery.for_course(course_id)
    activities = [
        a for a in inventory.activities
        if a.type in config.activity_types
    ][:config.max_activities]

    profile = get_profile(course_id)

    logger.info(
        "course_runner.start",
        course_id=course_id,
        course_name=inventory.course_name,
        profile=profile.value,
        queued=len(activities),
        types=[t.value for t in config.activity_types],
    )

    run = CourseRunResult(
        course_id=course_id,
        course_name=inventory.course_name,
    )
    consecutive_failures = 0

    for idx, activity in enumerate(activities):

        # ── Safety gate ────────────────────────────────────────────────────────
        if consecutive_failures >= config.max_failures:
            run.stopped_early = True
            run.stop_reason   = f"{consecutive_failures} consecutive failures"
            logger.warning("course_runner.safety_stop", **{
                "course_id": course_id,
                "reason": run.stop_reason,
            })
            break

        # ── Build context for quiz activities ──────────────────────────────────
        ctx: ExecutionContext | None = None
        if activity.type == ActivityType.QUIZ:
            if profile == CourseProfile.HIGH_VALUE and not config.force_submit:
                logger.warning(
                    "course_runner.skipping_high_value",
                    cmid=activity.cmid,
                    course_id=course_id,
                )
                run.results.append(ActivityResult(
                    cmid=activity.cmid,
                    course_id=course_id,
                    type=activity.type,
                    title=activity.title,
                    success=False,
                    error="HIGH_VALUE course — auto-submit blocked",
                ))
                continue

            ctx = ExecutionContext(
                course_id=course_id,
                cmid=activity.cmid,
                mode=config.mode,
                force_submit=config.force_submit,
            )

        # ── Execute ────────────────────────────────────────────────────────────
        result = await route_activity(page, activity, ctx=ctx)
        run.results.append(result)

        if result.success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning(
                "course_runner.activity_failed",
                cmid=activity.cmid,
                consecutive=consecutive_failures,
                error=result.error,
            )

        # ── Cooldown between activities (skip after last) ─────────────────────
        if idx < len(activities) - 1:
            delay = random.uniform(config.cooldown_min_s, config.cooldown_max_s)
            next_cmid = activities[idx + 1].cmid
            logger.info("course_runner.cooldown", seconds=round(delay, 1), next_cmid=next_cmid)
            await asyncio.sleep(delay)

    run.finished_at = time.monotonic()
    logger.info(
        "course_runner.complete",
        course_id=course_id,
        successful=run.successful,
        failed=run.failed,
        stopped_early=run.stopped_early,
        duration_s=run.duration_s,
    )
    return run
