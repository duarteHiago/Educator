"""
ExecutionReporter — aggregates QuizMetrics from one or many manifests.

Usage:
  reporter = ExecutionReporter()
  batch    = reporter.from_logs_dir(Path("logs/quizzes"))
  reporter.print_summary(batch)
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from backend.core.logging import get_logger
from backend.metrics.evaluator import QuizEvaluator
from backend.schemas.metrics import BatchMetrics, QuizMetrics

logger = get_logger(__name__)


class ExecutionReporter:
    def __init__(self) -> None:
        self._ev = QuizEvaluator()

    # ── Loading ───────────────────────────────────────────────────────────────

    def from_manifest(self, path: Path) -> QuizMetrics:
        return self._ev.from_manifest(path)

    def from_manifests(self, paths: list[Path]) -> BatchMetrics:
        metrics: list[QuizMetrics] = []
        for p in paths:
            try:
                metrics.append(self._ev.from_manifest(p))
            except Exception as exc:
                logger.warning("reporter.manifest_skipped", path=str(p), error=str(exc))
        return self._aggregate(metrics)

    def from_logs_dir(self, logs_dir: Path) -> BatchMetrics:
        manifests = sorted(logs_dir.glob("*/manifest.json"))
        logger.info("reporter.scanning", dir=str(logs_dir), found=len(manifests))
        return self.from_manifests(manifests)

    # ── Aggregation ───────────────────────────────────────────────────────────

    def _aggregate(self, metrics: list[QuizMetrics]) -> BatchMetrics:
        if not metrics:
            return BatchMetrics()

        successful = [m for m in metrics if m.status == "success"]
        failed     = [m for m in metrics if m.status == "failed"]
        skipped    = [m for m in metrics if m.status in ("dry_run", "skipped")]

        scores  = [m.score_percent for m in successful if m.score_percent is not None]
        confs   = [m.avg_confidence for m in metrics if m.avg_confidence is not None]
        times   = [m.execution_time_s for m in metrics if m.execution_time_s > 0]
        caches  = [m.cache_rate for m in metrics if m.total_questions > 0]

        return BatchMetrics(
            total_quizzes      = len(metrics),
            successful         = len(successful),
            failed             = len(failed),
            skipped            = len(skipped),
            avg_score_percent  = round(mean(scores), 1)  if scores  else None,
            avg_cache_rate     = round(mean(caches), 3)  if caches  else None,
            avg_confidence     = round(mean(confs),  3)  if confs   else None,
            avg_execution_time = round(mean(times),  1)  if times   else None,
            quiz_metrics       = metrics,
        )

    # ── Output ────────────────────────────────────────────────────────────────

    def print_summary(self, batch: BatchMetrics) -> None:
        W = 62
        print(f"\n{'='*W}")
        print(f"  EXECUTION REPORT — {batch.generated_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*W}")
        print(f"  Total quizzes   : {batch.total_quizzes}")
        print(f"  Successful      : {batch.successful}")
        print(f"  Failed          : {batch.failed}")
        print(f"  Dry-run/Skipped : {batch.skipped}")

        if batch.avg_score_percent is not None:
            print(f"  Avg score       : {batch.avg_score_percent:.1f}%")
        if batch.avg_cache_rate is not None:
            print(f"  Cache hit rate  : {batch.avg_cache_rate:.1%}")
        if batch.avg_confidence is not None:
            print(f"  Avg confidence  : {batch.avg_confidence:.1%}")
        if batch.avg_execution_time is not None:
            print(f"  Avg time/quiz   : {batch.avg_execution_time:.1f}s")

        if batch.quiz_metrics:
            print(f"\n  {'ID':>12}  {'cmid':>8}  {'status':>7}  {'score':>6}  {'cache':>7}  {'time':>5}")
            print(f"  {'-'*12}  {'-'*8}  {'-'*7}  {'-'*6}  {'-'*7}  {'-'*5}")
            for m in batch.quiz_metrics:
                score_s = f"{m.score_percent:.0f}%" if m.score_percent is not None else "  N/A"
                cache_s = f"{m.cache_hits}/{m.total_questions}"
                print(
                    f"  {m.execution_id:>12}  {m.cmid:>8}  "
                    f"{m.status:>7}  {score_s:>6}  {cache_s:>7}  {m.execution_time_s:>4.0f}s"
                )

        print(f"{'='*W}\n")

    def save_report(self, batch: BatchMetrics, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            batch.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("reporter.saved", path=str(path), total=batch.total_quizzes)
