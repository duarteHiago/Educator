"""
Terminal display for the bulk quiz runner.
Uses `rich` for colored output, progress bars and evolution alerts.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

if TYPE_CHECKING:
    from backend.llm.performance.evolution_engine import ActiveConfig, EvolutionAction
    from backend.schemas.activity import ActivityInfo

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console(highlight=False, legacy_windows=False)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _score_color(pct: float) -> str:
    if pct >= 80:
        return "green"
    if pct >= 60:
        return "yellow"
    return "red"


# ── Per-course tracker ────────────────────────────────────────────────────────

@dataclass
class _CourseState:
    name: str
    total: int
    done: int = 0


# ── Main display class ────────────────────────────────────────────────────────

class RunDisplay:
    def __init__(
        self,
        total_quizzes: int,
        active_config: "ActiveConfig",
        mode: str,
    ) -> None:
        self._total = total_quizzes
        self._done  = 0
        self._cfg   = active_config
        self._mode  = mode
        self._courses: dict[int, _CourseState] = {}
        self._started_at = time.monotonic()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def show_header(self) -> None:
        console.print()
        console.print(Rule(style="dim"))

        t = Text()
        t.append("  EDUCATOR  ", style="bold white")
        t.append("•  Quiz Runner  ", style="dim")
        t.append(f"•  {self._mode}", style="cyan")
        console.print(t)

        m = Text()
        m.append("  Modelo ativo: ", style="dim")
        m.append(f"{self._cfg.provider} / {self._cfg.model}", style="bold cyan")
        m.append("  •  Prompt: ", style="dim")
        m.append(self._cfg.prompt_version, style="bold magenta")
        m.append("  •  Threshold: 70%  •  Janela: 5 quizzes", style="dim")
        console.print(m)

        console.print(Rule(style="dim"))
        console.print()

    def register_courses(self, activities: list["ActivityInfo"]) -> None:
        counts: dict[int, tuple[str, int]] = {}
        for a in activities:
            cid = a.course_id
            if cid not in counts:
                counts[cid] = (a.course_name, 0)
            counts[cid] = (counts[cid][0], counts[cid][1] + 1)
        for cid, (name, total) in counts.items():
            self._courses[cid] = _CourseState(name=name, total=total)

    # ── Per-activity display ──────────────────────────────────────────────────

    def show_activity_start(self, idx: int, activity: "ActivityInfo") -> None:
        state = self._courses.get(activity.course_id)

        console.print()

        # Index + overall progress
        overall_pct = self._done / self._total * 100 if self._total else 0
        idx_text = Text()
        idx_text.append(f"[{idx:>3}/{self._total}]", style="bold white")
        idx_text.append(f"  {_bar(overall_pct, 16)}", style="blue")
        idx_text.append(f"  {overall_pct:4.0f}% total", style="dim")
        console.print(idx_text)

        # Course + course progress
        if state:
            course_pct = state.done / state.total * 100 if state.total else 0
            c = Text()
            c.append("         Matéria: ", style="dim")
            c.append(state.name, style="bold yellow")
            c.append("  ")
            c.append(f"{_bar(course_pct, 12)}", style="yellow")
            c.append(f"  {state.done}/{state.total}", style="dim")
            console.print(c)

        # Activity title
        a = Text()
        a.append("         Quiz:    ", style="dim")
        a.append(activity.title, style="white")
        console.print(a)

        # Current model
        m = Text()
        m.append("         Modelo:  ", style="dim")
        m.append(f"{self._cfg.provider}/{self._cfg.model}", style="cyan")
        m.append(f"@{self._cfg.prompt_version}", style="magenta")
        console.print(m)

    def show_activity_result(
        self,
        activity: "ActivityInfo",
        score_pct: float | None,
        status: str,
        elapsed_s: float,
    ) -> None:
        state = self._courses.get(activity.course_id)
        if state:
            state.done += 1
        self._done += 1

        r = Text()
        if score_pct is not None:
            color  = _score_color(score_pct)
            symbol = "✓" if score_pct >= 70 else "✗"
            r.append(f"         {symbol} ", style=f"bold {color}")
            r.append(f"{score_pct:5.1f}%  ", style=f"bold {color}")
            r.append(_bar(score_pct), style=color)
            r.append(f"  ({elapsed_s:.1f}s)", style="dim")
        else:
            r.append(f"         → {status}", style="dim")
            r.append(f"  ({elapsed_s:.1f}s)", style="dim")

        console.print(r)

    def show_model_evolution(self, action: "EvolutionAction") -> None:
        old = action.old_config
        new = action.new_config
        self._cfg = new  # update local ref for subsequent show_activity_start calls

        lines = Text()
        lines.append("  ⚠  EVOLUÇÃO — Modelo alterado\n\n", style="bold yellow")
        lines.append(f"  Antes: ", style="dim")
        lines.append(f"{old.provider}/{old.model}@{old.prompt_version}\n", style="red")
        lines.append(f"  Agora: ", style="dim")
        lines.append(f"{new.provider}/{new.model}@{new.prompt_version}\n", style="bold green")
        lines.append(f"\n  {action.reason}", style="dim italic")

        console.print()
        console.print(Panel(lines, border_style="yellow", expand=False))
        console.print()

    def show_cooldown(self, seconds: float) -> None:
        console.print(
            Text(f"         ⏱  cooldown {seconds:.0f}s…", style="dim")
        )

    def show_safety_stop(self, reason: str) -> None:
        console.print()
        console.print(
            Panel(
                Text(f"  [SAFETY STOP]  {reason}", style="bold red"),
                border_style="red",
                expand=False,
            )
        )

    def show_final_summary(
        self,
        successful: int,
        failed: int,
        avg_score: float | None,
    ) -> None:
        elapsed = time.monotonic() - self._started_at
        minutes, seconds = divmod(int(elapsed), 60)

        t = Text()
        t.append("\n  Execução finalizada\n\n", style="bold white")
        t.append(f"  Quizzes: ", style="dim")
        t.append(f"{successful} ok", style="green")
        t.append(f"  /  {failed} falhas\n", style="dim")
        if avg_score is not None:
            color = _score_color(avg_score)
            t.append(f"  Acerto médio: ", style="dim")
            t.append(f"{avg_score:.1f}%\n", style=f"bold {color}")
        t.append(f"  Tempo total: {minutes}m {seconds}s\n", style="dim")
        t.append(f"  Modelo final: {self._cfg.provider}/{self._cfg.model}@{self._cfg.prompt_version}", style="cyan")

        console.print()
        console.print(Panel(t, border_style="dim", expand=False))
        console.print()
