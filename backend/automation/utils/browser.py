from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def get_browser_context(
    restore_session: bool = True,
    session_dir: Path | None = None,
) -> AsyncGenerator[tuple[BrowserContext, Browser, Playwright], None]:
    """
    Yields (context, browser, playwright).
    If restore_session=True and session file exists, restores cookies/storage.
    Always saves session state on exit.
    session_dir: per-user directory; if None uses settings.session_file_path.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,   # sempre headless no cloud; ignorado no .exe via settings
            slow_mo=0,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        session_file = (session_dir / "session.json") if session_dir else settings.session_file_path
        storage_state = str(session_file) if (restore_session and session_file.exists()) else None

        if storage_state:
            logger.info("browser.session_restored", file=str(session_file))
        else:
            logger.info("browser.new_session")

        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )

        context.set_default_timeout(settings.browser_timeout)
        context.set_default_navigation_timeout(settings.browser_timeout)

        try:
            yield context, browser, pw
        finally:
            session_file.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(session_file))
            logger.info("browser.session_saved", file=str(session_file))
            await browser.close()
