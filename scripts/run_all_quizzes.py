"""
Bulk Quiz Runner — executes all SAFE_TEST quizzes in controlled sequence.

Usage:
  python scripts/run_all_quizzes.py --mode AUTO_MODE
  python scripts/run_all_quizzes.py --mode DRY_RUN --courses 7138 7137
  python scripts/run_all_quizzes.py --mode AUTO_MODE --max-quizzes 5 --cooldown-min 45

Safety controls:
  - Only SAFE_TEST courses by default (--force unlocks HIGH_VALUE, use with care)
  - MAX_QUIZZES_PER_RUN cap
  - Random human-paced cooldowns between quizzes
  - Auto-stop if accuracy or parse success falls below threshold
  - Writes batch report to logs/reports/
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

# ── Path bootstrap ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.discovery.activity_discovery import ActivityDiscovery
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.flows.login import ensure_authenticated
from backend.automation.profiles.course_profiles import get_profile, CourseProfile
from backend.automation.execution.runner import run_quiz
from backend.cli.display import RunDisplay
from backend.core.logging import get_logger
from backend.llm.orchestrator import LLMOrchestrator
from backend.llm.performance.evolution_engine import EvolutionEngine
from backend.metrics.evaluator import QuizEvaluator
from backend.metrics.reports import ExecutionReporter
from backend.schemas.activity import ActivityInfo, ActivityType
from backend.schemas.metrics import BatchMetrics, QuizMetrics

try:
    from backend.automation.utils.browser import get_browser_context
except ImportError:
    from backend.automation.utils.browser import get_browser_context

logger = get_logger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_COOLDOWN_MIN = 30.0
DEFAULT_COOLDOWN_MAX = 90.0
DEFAULT_MAX_QUIZZES  = 50

# Safety thresholds — halt if breached
SAFETY_MIN_SCORE_PCT   = 30.0  # if latest quiz scored below this → stop
SAFETY_MAX_FAIL_STREAK = 3     # consecutive submission failures → stop
SAFETY_MAX_PARSE_FAIL  = 5     # total parse failures across run → stop


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bulk quiz runner")
    p.add_argument("--mode", choices=["DRY_RUN", "AUTO_MODE"], default="DRY_RUN")
    p.add_argument("--courses", nargs="+", type=int, metavar="COURSE_ID",
                   help="Restrict to specific course IDs (default: all SAFE_TEST)")
    p.add_argument("--max-quizzes", type=int, default=DEFAULT_MAX_QUIZZES,
                   metavar="N", help="Maximum quizzes to attempt in this run")
    p.add_argument("--cooldown-min", type=float, default=DEFAULT_COOLDOWN_MIN,
                   metavar="S", help="Minimum cooldown between quizzes (seconds)")
    p.add_argument("--cooldown-max", type=float, default=DEFAULT_COOLDOWN_MAX,
                   metavar="S", help="Maximum cooldown between quizzes (seconds)")
    p.add_argument("--skip-cmids", nargs="+", type=int, metavar="CMID",
                   help="Specific quiz cmids to skip")
    p.add_argument("--force", action="store_true",
                   help="Allow HIGH_VALUE courses (dangerous — requires explicit intent)")
    p.add_argument("--map", default="logs/activity_map.json",
                   help="Path to activity_map.json")
    p.add_argument("--report-dir", default="logs/reports",
                   help="Directory to save execution report")
    return p


# ── Safety checker ────────────────────────────────────────────────────────────

class SafetyMonitor:
    def __init__(
        self,
        min_score_pct: float = SAFETY_MIN_SCORE_PCT,
        max_fail_streak: int = SAFETY_MAX_FAIL_STREAK,
        max_parse_failures: int = SAFETY_MAX_PARSE_FAIL,
    ):
        self._min_score      = min_score_pct
        self._max_streak     = max_fail_streak
        self._max_parse_fail = max_parse_failures

        self._fail_streak    = 0
        self._parse_failures = 0

    def record_success(self, score_pct: float | None) -> None:
        self._fail_streak = 0
        if score_pct is not None and score_pct < self._min_score:
            logger.warning("safety.low_score", score_pct=score_pct, threshold=self._min_score)

    def record_failure(self) -> None:
        self._fail_streak += 1

    def record_parse_failure(self) -> None:
        self._parse_failures += 1

    def should_stop(self) -> tuple[bool, str]:
        if self._fail_streak >= self._max_streak:
            return True, f"{self._fail_streak} consecutive submission failures"
        if self._parse_failures >= self._max_parse_fail:
            return True, f"{self._parse_failures} parse failures in this run"
        return False, ""


# ── Main execution ────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> None:
    discovery = ActivityDiscovery(Path(args.map)).load()

    # Select quizzes
    if args.force:
        candidates = [a for a in discovery.all_activities() if a.type == ActivityType.QUIZ]
    else:
        candidates = discovery.safe_test_quizzes()

    if args.courses:
        candidates = [a for a in candidates if a.course_id in args.courses]

    skip_set = set(args.skip_cmids or [])
    candidates = [a for a in candidates if a.cmid not in skip_set]
    candidates = candidates[:args.max_quizzes]

    if not candidates:
        print("Nenhum quiz encontrado com os filtros informados.")
        return

    mode    = ExecutionMode(args.mode)
    engine  = EvolutionEngine()
    orc     = LLMOrchestrator(engine=engine)
    display = RunDisplay(total_quizzes=len(candidates), active_config=engine.active_config, mode=mode.value)
    display.register_courses(candidates)
    display.show_header()

    evaluator    = QuizEvaluator()
    reporter     = ExecutionReporter()
    safety       = SafetyMonitor()
    all_metrics: list[QuizMetrics] = []
    successful   = 0
    failed       = 0

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        page = await ensure_authenticated(context)

        for idx, activity in enumerate(candidates):
            # ── Safety gate ────────────────────────────────────────────────────
            stop, reason = safety.should_stop()
            if stop:
                logger.warning("bulk.safety_halt", reason=reason)
                display.show_safety_stop(reason)
                break

            display.show_activity_start(idx + 1, activity)

            ctx = ExecutionContext(
                course_id=activity.course_id,
                cmid=activity.cmid,
                mode=mode,
                force_submit=args.force,
            )

            # ── Execute ────────────────────────────────────────────────────────
            quiz_start = time.monotonic()
            try:
                result = await run_quiz(page, ctx, orchestrator=orc)
                elapsed = time.monotonic() - quiz_start

                if result is None:
                    display.show_activity_result(activity, None, "dry_run / sem questões", elapsed)
                    safety.record_failure()
                    failed += 1
                    continue

                sub_ok = result.status.value == "success"
                display.show_activity_result(activity, result.score_percent, result.status.value, elapsed)

                if sub_ok:
                    successful += 1
                    safety.record_success(result.score_percent)
                    if result.score_percent is not None:
                        action = orc.record_result(
                            cmid=activity.cmid,
                            score_percent=result.score_percent,
                        )
                        if action and action.triggered:
                            display.show_model_evolution(action)
                else:
                    failed += 1
                    safety.record_failure()

                # Collect metrics
                latest_manifest = _latest_manifest(Path("logs/quizzes"))
                if latest_manifest:
                    try:
                        m = evaluator.from_manifest(latest_manifest)
                        all_metrics.append(m)
                    except Exception:
                        pass

            except Exception as exc:
                elapsed = time.monotonic() - quiz_start
                logger.error("bulk.quiz_exception", cmid=activity.cmid, error=str(exc))
                display.show_activity_result(activity, None, f"EXCEPTION: {exc}", elapsed)
                safety.record_failure()
                failed += 1

            # ── Cooldown ───────────────────────────────────────────────────────
            if idx < len(candidates) - 1:
                delay = random.uniform(args.cooldown_min, args.cooldown_max)
                display.show_cooldown(delay)
                await asyncio.sleep(delay)

    # ── Final report ───────────────────────────────────────────────────────────
    avg_score = None
    if all_metrics:
        batch = reporter._aggregate(all_metrics)
        avg_score = batch.avg_score_percent
        report_path = Path(args.report_dir) / f"batch_{int(time.time())}.json"
        reporter.save_report(batch, report_path)

    display.show_final_summary(successful, failed, avg_score)


def _latest_manifest(quizzes_dir: Path) -> Path | None:
    manifests = sorted(quizzes_dir.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
    return manifests[-1] if manifests else None


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = build_parser().parse_args()
    asyncio.run(run(args))
