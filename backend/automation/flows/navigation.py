"""
Navigation flow — list subjects/courses from the portal.

IMPORTANT: Selectors and URLs below are placeholders.
Populate PORTAL_MAP.md during discovery, then update this file.
"""
from dataclasses import dataclass

from playwright.async_api import Page

from backend.automation.utils.retry import async_retry
from backend.automation.utils.screenshot import on_error_screenshot
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

# ─── Configure after discovery ─────────────────────────────────────────────
SUBJECTS_URL    = f"{settings.portal_url}/meus-cursos"   # update after discovery
SUBJECT_CARD_SELECTOR = ".course-card"                   # update after discovery
SUBJECT_NAME_SELECTOR = ".course-card__title"            # update after discovery
SUBJECT_LINK_SELECTOR = ".course-card a"                 # update after discovery
# ───────────────────────────────────────────────────────────────────────────


@dataclass
class Subject:
    name: str
    url: str


@async_retry(max_attempts=3, delay_seconds=2.0)
@on_error_screenshot(label="navigation")
async def list_subjects(page: Page) -> list[Subject]:
    logger.info("navigation.list_subjects.started", url=SUBJECTS_URL)

    await page.goto(SUBJECTS_URL)
    await page.wait_for_load_state("networkidle")

    cards = await page.query_selector_all(SUBJECT_CARD_SELECTOR)
    subjects: list[Subject] = []

    for card in cards:
        name_el = await card.query_selector(SUBJECT_NAME_SELECTOR)
        link_el = await card.query_selector(SUBJECT_LINK_SELECTOR)

        name = (await name_el.inner_text()).strip() if name_el else "unknown"
        href = await link_el.get_attribute("href") if link_el else None
        url  = f"{settings.portal_url}{href}" if href and href.startswith("/") else (href or "")

        subjects.append(Subject(name=name, url=url))
        logger.debug("navigation.subject_found", name=name, url=url)

    logger.info("navigation.list_subjects.done", count=len(subjects))
    return subjects
