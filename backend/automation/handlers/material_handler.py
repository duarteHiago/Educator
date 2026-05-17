"""
Material Handler — marks study materials as complete by navigating to them.

Moodle semantics:
  mod/url          — external link; opening view.php triggers completion
  mod/page         — inline content page; same
  mod/book         — multi-chapter ebook; opening first page is enough
  mod/activityvideo — Kroton custom video; open = complete
  mod/pde          — Kroton extension activity; open = complete
"""
from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from backend.core.logging import get_logger
from backend.schemas.activity import ActivityInfo, ActivityResult, ActivityType

logger = get_logger(__name__)

# Seconds to linger on the page so Moodle registers the visit server-side
_DEFAULT_LINGER_S = 3.0


async def open_material(
    page: Page,
    activity: ActivityInfo,
    linger_s: float = _DEFAULT_LINGER_S,
) -> ActivityResult:
    """
    Navigate to the activity page to trigger completion marking.
    Does NOT follow external links — only the AVA view.php URL is visited.
    """
    started = time.monotonic()
    logger.info(
        "material.opening",
        cmid=activity.cmid,
        mod=activity.mod,
        type=activity.type.value,
        title=activity.title[:70],
    )

    try:
        await page.goto(activity.url, timeout=30_000)
        await page.wait_for_load_state("networkidle", timeout=15_000)
        await asyncio.sleep(linger_s)

        current_url = page.url

        # Session expired check
        if "login" in current_url and "avaeduc" not in current_url:
            raise RuntimeError(f"Session expired — redirected to: {current_url}")

        duration = round(time.monotonic() - started, 1)
        logger.info("material.opened", cmid=activity.cmid, duration_s=duration)

        return ActivityResult(
            cmid=activity.cmid,
            course_id=activity.course_id,
            type=activity.type,
            title=activity.title,
            success=True,
            duration_s=duration,
            extra={"final_url": current_url},
        )

    except Exception as exc:
        duration = round(time.monotonic() - started, 1)
        logger.error("material.failed", cmid=activity.cmid, error=str(exc))
        return ActivityResult(
            cmid=activity.cmid,
            course_id=activity.course_id,
            type=activity.type,
            title=activity.title,
            success=False,
            error=str(exc),
            duration_s=duration,
        )
