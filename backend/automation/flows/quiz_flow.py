"""
Quiz Flow — opens a Moodle quiz attempt and returns raw HTML pages.

Responsibilities:
  - Navigate to /mod/quiz/view.php?id={cmid}
  - Click "start attempt"
  - Collect HTML from all pages (navigating without filling answers)
  - Return list[str] of raw HTML pages for the parser

Does NOT parse, answer, or submit — that is handled by downstream components.
"""
import asyncio

from playwright.async_api import Page

from backend.automation.parsers.moodle import selectors as sel
from backend.automation.utils.retry import async_retry
from backend.automation.utils.screenshot import capture_on_error
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

AVA_BASE = "https://www.avaeduc.com.br"


async def dismiss_overlays(page: Page) -> None:
    """Hide cookie banners and overlays that intercept pointer events.
    Uses display:none instead of remove() so it survives web component re-mounts."""
    await page.evaluate("""
        () => {
            const selectors = [
                'cookie-police-bar',
                '.cookie-police-bar',
                '.cookie-bar',
                '#cookie-bar',
                '[class*="cookie"]',
                '[id*="cookie"]',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('pointer-events', 'none', 'important');
                    el.style.setProperty('visibility', 'hidden', 'important');
                });
            }
        }
    """)


async def js_click(page: Page, locator) -> None:
    """Click via JavaScript — bypasses Playwright's pointer-event interception check.
    Use when a fixed overlay blocks .click() even after dismiss_overlays."""
    await locator.evaluate("el => el.click()")


def _quiz_view_url(cmid: int) -> str:
    return f"{AVA_BASE}/mod/quiz/view.php?id={cmid}"


async def _get_sesskey(page: Page) -> str | None:
    return await page.evaluate(r"""() => {
        if (window.M?.cfg?.sesskey) return window.M.cfg.sesskey;
        const m = document.body.innerHTML.match(/"sesskey":"([^"]{5,})"/);
        return m ? m[1] : null;
    }""")


@async_retry(max_attempts=2, delay_seconds=3.0)
async def open_quiz_and_collect_pages(
    page: Page,
    cmid: int,
    artifact_dir=None,
) -> list[str]:
    """
    Opens the quiz view page, starts or continues an attempt,
    and returns raw HTML for each question page.
    """
    view_url = _quiz_view_url(cmid)
    logger.info("quiz_flow.navigating_to_view", url=view_url)

    await page.goto(view_url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)
    await dismiss_overlays(page)

    current_url = page.url
    logger.info("quiz_flow.view_loaded", url=current_url[:80])

    # ── Start / continue attempt ───────────────────────────────────────────────
    if "attempt.php" not in current_url:
        start_btn = None
        for s in sel.START_ATTEMPT_BTN.split(", "):
            start_btn = page.locator(s.strip()).first
            if await start_btn.count() > 0:
                break

        if not start_btn or await start_btn.count() == 0:
            html = await page.content()
            logger.error("quiz_flow.no_start_button", url=current_url)
            if artifact_dir:
                await capture_on_error(page, "quiz_no_start_btn")
            raise RuntimeError(
                f"Start attempt button not found on {current_url}. "
                "Quiz may be unavailable, locked, or already submitted."
            )

        logger.info("quiz_flow.clicking_start_attempt")

        async with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            await js_click(page, start_btn)
        await asyncio.sleep(1.5)

    # ── Ensure we start from page 0 (quiz may have resumed mid-way) ───────────
    current_url = page.url
    if "attempt.php" in current_url and "page=" in current_url:
        import re as _re
        attempt_id_m = _re.search(r"attempt=(\d+)", current_url)
        if attempt_id_m:
            attempt_id = attempt_id_m.group(1)
            page0_url = f"{AVA_BASE}/mod/quiz/attempt.php?attempt={attempt_id}&page=0"
            if current_url != page0_url:
                logger.info("quiz_flow.rewinding_to_page0", url=page0_url)
                await page.goto(page0_url)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1.0)

    # ── Collect all pages ─────────────────────────────────────────────────────
    html_pages: list[str] = []
    page_num = 0

    while True:
        current_url = page.url
        logger.info("quiz_flow.collecting_page", page=page_num, url=current_url[:80])

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(0.8)
        await dismiss_overlays(page)

        html = await page.content()
        html_pages.append(html)

        # Check if there is a "Next page" button
        next_btn = page.locator(sel.SUBMIT_NEXT).first
        has_next = await next_btn.count() > 0 and await next_btn.is_visible()

        if not has_next:
            logger.info("quiz_flow.last_page_reached", total_pages=len(html_pages))
            break

        if page_num >= 50:  # safety cap
            logger.warning("quiz_flow.page_cap_reached")
            break

        # Navigate to next page WITHOUT submitting answers
        logger.info("quiz_flow.navigating_to_next_page", from_page=page_num)
        async with page.expect_navigation(wait_until="networkidle", timeout=15_000):
            await js_click(page, next_btn)
        page_num += 1

    return html_pages


async def get_sesskey_from_ava(page: Page) -> str | None:
    """Utility — extracts Moodle sesskey from any AVA page."""
    return await _get_sesskey(page)
