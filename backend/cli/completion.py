"""
CompletionTracker — lê todos os manifests de logs/quizzes/ e constrói
um mapa de quais cmids já foram submetidos com sucesso.

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

    @property
    def done(self) -> bool:
        return True  # se está no tracker, foi submetido com sucesso

    @property
    def score_label(self) -> str:
        if self.score_percent is not None:
            return f"{self.score_percent:.0f}%"
        return "OK"


class CompletionTracker:
    def __init__(self, quizzes_dir: Path | None = None) -> None:
        self._dir = quizzes_dir or Path("logs/quizzes")
        self._data: dict[int, CompletionInfo] = self._load()

    def _load(self) -> dict[int, CompletionInfo]:
        result: dict[int, CompletionInfo] = {}
        if not self._dir.exists():
            return result

        for manifest in self._dir.glob("*/manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                sub = data.get("submission")
                if not sub or sub.get("status") != "success":
                    continue
                cmid = int(data["cmid"])
                score = sub.get("score_percent")
                grade = sub.get("grade_string")
                # Mantém a melhor nota se houver múltiplas execuções
                if cmid not in result or (score or 0) > (result[cmid].score_percent or 0):
                    result[cmid] = CompletionInfo(cmid=cmid, score_percent=score, grade_string=grade)
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
