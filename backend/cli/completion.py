"""
CompletionTracker — constrói um mapa de quais cmids já foram concluídos.

Fontes (mescladas, em ordem de prioridade):
  1. logs/quizzes/*/manifest.json  — execuções feitas pelo Educator (tem nota exata)
  2. logs/activity_map.json        — completion tracking do Moodle (atividades feitas
                                     diretamente no AVA, detectadas no discovery)

Usado pelo menu para marcar atividades e matérias como concluídas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompletionInfo:
    cmid: int
    score_percent: float | None
    grade_string: str | None
    source: str = "manifest"  # "manifest" | "moodle"

    @property
    def done(self) -> bool:
        return True

    @property
    def score_label(self) -> str:
        if self.score_percent is not None:
            return f"{self.score_percent:.0f}%"
        if self.grade_string:
            return self.grade_string[:20]
        return "✓"


class CompletionTracker:
    def __init__(
        self,
        quizzes_dir: Path | None = None,
        activity_map: Path | None = None,
    ) -> None:
        self._dir = quizzes_dir or Path("logs/quizzes")
        self._map = activity_map or Path("logs/activity_map.json")
        self._data: dict[int, CompletionInfo] = self._load()

    def _load(self) -> dict[int, CompletionInfo]:
        result: dict[int, CompletionInfo] = {}

        # ── Fonte 1: activity_map.json (Moodle completion tracking) ──────────
        if self._map.exists():
            try:
                activities = json.loads(self._map.read_text(encoding="utf-8"))
                for act in activities:
                    if not act.get("completed"):
                        continue
                    cmid = int(act["cmid"])
                    if cmid not in result:
                        result[cmid] = CompletionInfo(
                            cmid=cmid,
                            score_percent=None,
                            grade_string=act.get("grade_string"),
                            source="moodle",
                        )
            except Exception:
                pass

        # ── Fonte 2: manifests locais (execuções via Educator — têm nota exata) ──
        if self._dir.exists():
            for manifest in self._dir.glob("*/manifest.json"):
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    sub = data.get("submission")
                    if not sub or sub.get("status") != "success":
                        continue
                    cmid = int(data["cmid"])
                    score = sub.get("score_percent")
                    grade = sub.get("grade_string")
                    # Manifests têm prioridade e mantém a melhor nota
                    existing = result.get(cmid)
                    if existing is None or (score or 0) > (existing.score_percent or 0):
                        result[cmid] = CompletionInfo(
                            cmid=cmid,
                            score_percent=score,
                            grade_string=grade,
                            source="manifest",
                        )
                except Exception:
                    pass

        return result

    def is_done(self, cmid: int) -> bool:
        return cmid in self._data

    def get(self, cmid: int) -> CompletionInfo | None:
        return self._data.get(cmid)

    def completed_cmids(self) -> set[int]:
        return set(self._data.keys())

    def course_progress(self, cmids: list[int]) -> tuple[int, int]:
        """Returns (done, total) for a list of cmids."""
        done = sum(1 for c in cmids if self.is_done(c))
        return done, len(cmids)
