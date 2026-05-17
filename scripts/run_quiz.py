"""
Quiz Automation CLI — Phase 2 entry point.

Modes:
  --mode DRY_RUN      Parse + LLM, print answers, no browser interaction
  --mode REVIEW_MODE  Fill DOM, show each answer for human approval, no submit
  --mode AUTO_MODE    Full auto (blocked for HIGH_VALUE courses)

Replay (offline, no browser):
  --replay logs/quizzes/<id>/parsed/quiz_data.json

Examples:
  python scripts/run_quiz.py --cmid 12345 --course-id 7137 --mode DRY_RUN
  python scripts/run_quiz.py --cmid 12345 --course-id 7137 --mode REVIEW_MODE
  python scripts/run_quiz.py --replay logs/quizzes/abc123/parsed/quiz_data.json
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.replay.replay_runner import replay
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level, settings.log_file)
logger = get_logger("run_quiz")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Educator Quiz Automation")
    p.add_argument("--cmid",      type=int, help="Moodle activity ID (mod_quiz)")
    p.add_argument("--course-id", type=int, dest="course_id", help="Moodle course ID")
    p.add_argument(
        "--mode",
        choices=["DRY_RUN", "REVIEW_MODE", "AUTO_MODE"],
        default="DRY_RUN",
    )
    p.add_argument("--force",  action="store_true", help="Force submit on HIGH_VALUE courses")
    p.add_argument("--replay", type=str, metavar="PATH", help="Offline replay from saved quiz JSON")
    return p.parse_args()


async def run_live(args: argparse.Namespace) -> None:
    from backend.automation.execution.runner import run_quiz
    from backend.automation.flows.login import ensure_authenticated
    from backend.automation.utils.browser import get_browser_context
    from backend.llm.orchestrator import LLMOrchestrator

    ctx = ExecutionContext(
        course_id    = args.course_id,
        cmid         = args.cmid,
        mode         = ExecutionMode(args.mode),
        force_submit = args.force,
    )

    logger.info("run_quiz.starting",
                cmid=ctx.cmid,
                course_id=ctx.course_id,
                mode=ctx.mode.value,
                execution_id=ctx.execution_id)

    orc = LLMOrchestrator()

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        page = await ensure_authenticated(context)
        result = await run_quiz(page, ctx, orchestrator=orc)

    if result:
        print(f"\nResult: {result.status.value}")
        if result.score_percent is not None:
            print(f"Score:  {result.score_percent}% ({result.score_raw}/{result.score_max})")
            if result.status.value == "success":
                action = orc.record_result(cmid=args.cmid, score_percent=result.score_percent)
                if action and action.triggered:
                    print(f"\n[EVOLUTION] modelo alterado: {action.new_config.provider}/{action.new_config.model}@{action.new_config.prompt_version}")
    else:
        print("\nDRY_RUN complete — no submission made.")


def main() -> None:
    args = _parse_args()

    if args.replay:
        mode = ExecutionMode(args.mode)
        asyncio.run(replay(args.replay, mode=mode))
        return

    if not args.cmid or not args.course_id:
        print("Error: --cmid and --course-id are required for live mode.")
        print("       Use --replay <path> for offline mode.")
        sys.exit(1)

    asyncio.run(run_live(args))


if __name__ == "__main__":
    main()
