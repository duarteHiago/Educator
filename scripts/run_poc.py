"""
PoC runner — Phase 1.

Executes: login → list subjects → print results.
Run ONLY after completing discovery and updating selectors in:
  - backend/automation/flows/login.py
  - backend/automation/flows/navigation.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.flows.login import ensure_authenticated
from backend.automation.flows.navigation import list_subjects
from backend.automation.utils.browser import get_browser_context
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level, settings.log_file)
logger = get_logger("poc")


async def main() -> None:
    logger.info("poc.started")

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        page = await ensure_authenticated(context)
        subjects = await list_subjects(page)

        print("\n" + "=" * 50)
        print(f"Found {len(subjects)} subject(s):")
        for s in subjects:
            print(f"  • {s.name}")
            print(f"    {s.url}")
        print("=" * 50 + "\n")

        logger.info("poc.completed", subjects_found=len(subjects))


if __name__ == "__main__":
    asyncio.run(main())
