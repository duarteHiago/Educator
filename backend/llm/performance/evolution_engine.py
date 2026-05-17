"""
EvolutionEngine — decides when and how to evolve the active model+prompt config.

State machine:
  For each (provider, model, prompt_version):
    - Wait until window_size quizzes recorded
    - If avg_score < accuracy_threshold (70%):
        Phase 1: cycle to next prompt version (v1 → v2 → v3)
        Phase 2: when all prompt versions exhausted, advance to next model in chain
    - If avg_score >= threshold: stay — no change

Model chain (in order of escalation):
  1. openai  / gpt-4o-mini          (cheap, fast)
  2. openai  / gpt-4o               (better OpenAI)
  3. anthropic / claude-haiku-4-5-20251001  (fast Claude)
  4. anthropic / claude-sonnet-4-6   (best available)

Prompt cycle per model: v1 → v2 → v3 → (escalate model, reset to v1)

Active config is persisted at logs/active_model_config.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.llm.performance.tracker import PerformanceTracker

logger = get_logger(__name__)

_MODEL_CHAIN: list[tuple[str, str]] = [
    ("openai",     "gpt-4o-mini"),
    ("openai",     "gpt-4o"),
    ("anthropic",  "claude-haiku-4-5-20251001"),
    ("anthropic",  "claude-sonnet-4-6"),
]

_PROMPT_VERSIONS = ["v1", "v2", "v3"]


@dataclass
class ActiveConfig:
    provider: str
    model: str
    prompt_version: str
    switched_at: str
    switch_reason: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ActiveConfig":
        return cls(**d)

    @classmethod
    def default(cls) -> "ActiveConfig":
        return cls(
            provider="openai",
            model=settings.llm_model_primary,
            prompt_version="v1",
            switched_at=datetime.now(timezone.utc).isoformat(),
            switch_reason="initial",
        )


@dataclass
class EvolutionAction:
    triggered: bool
    old_config: ActiveConfig
    new_config: ActiveConfig
    reason: str


class EvolutionEngine:
    def __init__(
        self,
        config_file: Path | None = None,
        tracker: PerformanceTracker | None = None,
    ) -> None:
        self._path = config_file or settings.perf_active_config_file
        self._tracker = tracker or PerformanceTracker()
        self._config = self._load_config()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def active_config(self) -> ActiveConfig:
        return self._config

    def record_and_evaluate(
        self,
        cmid: int,
        score_percent: float,
    ) -> EvolutionAction | None:
        """Record a quiz result and evaluate if evolution is needed."""
        cfg = self._config

        self._tracker.record(
            cmid=cmid,
            score_percent=score_percent,
            provider=cfg.provider,
            model=cfg.model,
            prompt_version=cfg.prompt_version,
        )

        accuracy, n = self._tracker.get_accuracy(
            cfg.provider, cfg.model, cfg.prompt_version
        )

        if n < settings.perf_window_size:
            logger.info(
                "perf.engine.waiting_for_window",
                n=n,
                needed=settings.perf_window_size,
            )
            return None

        threshold_pct = settings.perf_accuracy_threshold * 100

        if accuracy >= threshold_pct:
            logger.info(
                "perf.engine.healthy",
                accuracy=accuracy,
                threshold=threshold_pct,
                provider=cfg.provider,
                model=cfg.model,
                prompt_version=cfg.prompt_version,
            )
            return None

        logger.warning(
            "perf.engine.below_threshold",
            accuracy=accuracy,
            threshold=threshold_pct,
            provider=cfg.provider,
            model=cfg.model,
            prompt_version=cfg.prompt_version,
        )

        return self._evolve(accuracy, threshold_pct)

    # ── Internal evolution logic ──────────────────────────────────────────────

    def _evolve(self, accuracy: float, threshold: float) -> EvolutionAction:
        old = self._config
        new_cfg = self._next_config(old)

        reason = (
            f"accuracy={accuracy:.1f}% < threshold={threshold:.0f}% "
            f"over last {settings.perf_window_size} quizzes — "
            f"upgraded from {old.provider}/{old.model}@{old.prompt_version} "
            f"to {new_cfg.provider}/{new_cfg.model}@{new_cfg.prompt_version}"
        )

        new_cfg.switched_at = datetime.now(timezone.utc).isoformat()
        new_cfg.switch_reason = reason

        self._config = new_cfg
        self._save_config()

        logger.warning("perf.engine.evolved", reason=reason)

        return EvolutionAction(
            triggered=True,
            old_config=old,
            new_config=new_cfg,
            reason=reason,
        )

    def _next_config(self, current: ActiveConfig) -> ActiveConfig:
        curr_prompt_idx = _PROMPT_VERSIONS.index(current.prompt_version) if current.prompt_version in _PROMPT_VERSIONS else -1

        # Phase 1: cycle to next prompt version
        if curr_prompt_idx < len(_PROMPT_VERSIONS) - 1:
            return ActiveConfig(
                provider=current.provider,
                model=current.model,
                prompt_version=_PROMPT_VERSIONS[curr_prompt_idx + 1],
                switched_at="",
                switch_reason="",
            )

        # Phase 2: advance to next model, reset prompt to v1
        curr_model_idx = next(
            (i for i, (p, m) in enumerate(_MODEL_CHAIN)
             if p == current.provider and m == current.model),
            -1,
        )

        if curr_model_idx < len(_MODEL_CHAIN) - 1:
            next_provider, next_model = _MODEL_CHAIN[curr_model_idx + 1]
        else:
            # Chain exhausted — wrap around to best model but log warning
            logger.error("perf.engine.chain_exhausted", cycling_back=True)
            next_provider, next_model = _MODEL_CHAIN[-1]

        return ActiveConfig(
            provider=next_provider,
            model=next_model,
            prompt_version="v1",
            switched_at="",
            switch_reason="",
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_config(self) -> ActiveConfig:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                cfg = ActiveConfig.from_dict(data)
                logger.info(
                    "perf.engine.loaded_config",
                    provider=cfg.provider,
                    model=cfg.model,
                    prompt_version=cfg.prompt_version,
                )
                return cfg
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning("perf.engine.corrupted_config", path=str(self._path))

        default = ActiveConfig.default()
        self._save_config(default)
        return default

    def _save_config(self, cfg: ActiveConfig | None = None) -> None:
        target = cfg or self._config
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(target.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
