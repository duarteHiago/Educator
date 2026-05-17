"""
PerformanceTracker — persists quiz results and computes rolling accuracy.

Record format (logs/performance_history.json):
  [{recorded_at, cmid, score_percent, provider, model, prompt_version}, ...]

score_percent is the actual grade: e.g. 100.0 = acertou tudo, 0.0 = nenhuma.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import TypedDict

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class PerformanceRecord(TypedDict):
    recorded_at: str
    cmid: int
    score_percent: float
    provider: str
    model: str
    prompt_version: str


class PerformanceTracker:
    def __init__(self, history_file: Path | None = None) -> None:
        self._path = history_file or settings.perf_history_file
        self._records: list[PerformanceRecord] = self._load()

    def _load(self) -> list[PerformanceRecord]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("perf.tracker.corrupted_history", path=str(self._path))
        return []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def record(
        self,
        cmid: int,
        score_percent: float,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> None:
        rec: PerformanceRecord = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "cmid": cmid,
            "score_percent": round(score_percent, 2),
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
        }
        self._records.append(rec)
        self._save()
        logger.info(
            "perf.tracker.recorded",
            cmid=cmid,
            score_percent=score_percent,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
        )

    def get_accuracy(
        self,
        provider: str,
        model: str,
        prompt_version: str,
        window: int | None = None,
    ) -> tuple[float | None, int]:
        """Returns (avg_score_percent, n_records) for the given config window."""
        w = window or settings.perf_window_size
        matching = [
            r for r in self._records
            if r["provider"] == provider
            and r["model"] == model
            and r["prompt_version"] == prompt_version
        ]
        recent = matching[-w:]
        if not recent:
            return None, 0
        return round(mean(r["score_percent"] for r in recent), 2), len(recent)

    def all_records(self) -> list[PerformanceRecord]:
        return list(self._records)
