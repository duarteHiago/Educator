import asyncio
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from backend.core.logging import get_logger

logger = get_logger(__name__)

SCREENSHOT_DIR = Path("./logs/screenshots")


async def capture_on_error(page: Page, label: str = "error") -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"{label}_{ts}.png"
    await page.screenshot(path=str(path), full_page=True)
    logger.info("screenshot.captured", path=str(path), label=label)
    return path


def on_error_screenshot(label: str = "error"):
    """
    Decorator for async functions receiving `page` as first positional arg.
    Captures screenshot if an exception is raised.
    """
    def decorator(func):
        async def wrapper(page: Page, *args, **kwargs):
            try:
                return await func(page, *args, **kwargs)
            except Exception as exc:
                await capture_on_error(page, label=f"{label}_{func.__name__}")
                raise
        return wrapper
    return decorator
