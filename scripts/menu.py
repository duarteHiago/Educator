"""
Menu interativo — seleciona matéria / unidade / atividades e executa o runner.

Uso:
  python scripts/menu.py
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from backend.cli.completion import CompletionTracker
from backend.automation.discovery.activity_discovery import ActivityDiscovery
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.flows.login import ensure_authenticated
from backend.automation.profiles.course_profiles import get_profile, CourseProfile
from backend.automation.execution.runner import run_quiz
from backend.cli.display import RunDisplay
from backend.llm.orchestrator import LLMOrchestrator
from backend.llm.performance.evolution_engine import EvolutionEngine
from backend.metrics.evaluator import QuizEvaluator
from backend.metrics.reports import ExecutionReporter
from backend.schemas.activity import ActivityInfo, ActivityType
from backend.schemas.metrics import QuizMetrics

try:
    from backend.automation.utils.browser import get_browser_context
except ImportError:
    from backend.automation.utils.browser import get_browser_context

console = Console(legacy_windows=False, highlight=False)

_STYLE = Style([
    ("qmark",        "fg:#00bfff bold"),
    ("question",     "bold"),
    ("answer",       "fg:#00ff99 bold"),
    ("pointer",      "fg:#00bfff bold"),
    ("highlighted",  "fg:#00bfff bold"),
    ("selected",     "fg:#00ff99"),
    ("separator",    "fg:#555555"),
    ("instruction",  "fg:#555555 italic"),
])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _topic_label(source: str, idx: int) -> str:
    if source == "direct" or not source.startswith("topic_"):
        return "Geral"
    return f"Unidade {idx + 1}"


def _group_by_topic(activities: list[ActivityInfo]) -> dict[str, list[ActivityInfo]]:
    """Groups activities by source topic, numbering them sequentially."""
    raw: dict[str, list[ActivityInfo]] = defaultdict(list)
    for a in activities:
        raw[a.source].append(a)

    # Sort topics: direct first, then topic_XXXXX numerically
    def sort_key(s: str) -> tuple:
        if s == "direct":
            return (0, 0)
        try:
            return (1, int(s.split("_")[1]))
        except (IndexError, ValueError):
            return (1, 0)

    sorted_keys = sorted(raw.keys(), key=sort_key)
    result: dict[str, list[ActivityInfo]] = {}
    for idx, key in enumerate(sorted_keys):
        label = _topic_label(key, idx if key != "direct" else -1)
        result[label] = raw[key]
    return result


def _print_header(active_model: str, prompt_version: str) -> None:
    console.print()
    console.print(Rule(style="dim"))
    t = Text()
    t.append("  EDUCATOR  ", style="bold white")
    t.append("•  Menu Interativo\n", style="dim")
    t.append("  Modelo ativo: ", style="dim")
    t.append(f"{active_model}", style="bold cyan")
    t.append("  •  Prompt: ", style="dim")
    t.append(prompt_version, style="bold magenta")
    console.print(t)
    console.print(Rule(style="dim"))
    console.print()


def _latest_manifest(quizzes_dir: Path) -> Path | None:
    manifests = sorted(quizzes_dir.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
    return manifests[-1] if manifests else None


# ── Selection flow ────────────────────────────────────────────────────────────

def select_activities(all_quizzes: list[ActivityInfo], tracker: CompletionTracker) -> list[ActivityInfo] | None:
    """Interactive selection: matéria → unidade(s) → confirmação."""

    # ── 1. Matéria ────────────────────────────────────────────────────────────
    courses: dict[str, list[ActivityInfo]] = defaultdict(list)
    for a in all_quizzes:
        courses[a.course_name].append(a)

    course_choices = []
    for name, acts in sorted(courses.items()):
        done, total = tracker.course_progress([a.cmid for a in acts])
        if done == total:
            badge = f"[green]✓ {done}/{total}[/green]"
            status = " ✓ COMPLETA"
        elif done > 0:
            badge = f"[yellow]{done}/{total}[/yellow]"
            status = f" {done}/{total}"
        else:
            badge = f"[dim]{done}/{total}[/dim]"
            status = ""

        course_choices.append(questionary.Choice(
            title=f"{name}{status}  ({total} quizzes)",
            value=name,
        ))
        _ = badge  # usado apenas no rich print abaixo

    course_choices.append(questionary.Choice(title="── Todas as matérias ──", value="__all__"))

    # Mostra legenda de progresso antes do select
    console.print("  [dim]Progresso das matérias:[/dim]")
    for name, acts in sorted(courses.items()):
        done, total = tracker.course_progress([a.cmid for a in acts])
        bar_filled = round(done / total * 12) if total else 0
        bar = "█" * bar_filled + "░" * (12 - bar_filled)
        color = "green" if done == total else ("yellow" if done > 0 else "dim")
        t = Text(f"    {name:<40}", style="white")
        t.append(f" {bar} ", style=color)
        t.append(f"{done}/{total}", style=f"bold {color}")
        if done == total:
            t.append("  ✓", style="bold green")
        console.print(t)
    console.print()

    materia = questionary.select(
        "Selecione a Matéria:",
        choices=course_choices,
        style=_STYLE,
    ).ask()

    if materia is None:
        return None

    selected_pool = all_quizzes if materia == "__all__" else courses[materia]

    # ── 2. Unidade(s) — checkbox, Enter sem espaço = todas ───────────────────
    grouped = _group_by_topic(selected_pool)

    unit_choices = []
    for unit_name, acts in grouped.items():
        done, total = tracker.course_progress([a.cmid for a in acts])
        if done == total and total > 0:
            label = f"{unit_name}  ✓ completa"
        elif done > 0:
            label = f"{unit_name}  ({done}/{total} feitos)"
        else:
            label = f"{unit_name}  ({total} quiz{'zes' if total > 1 else ''})"
        unit_choices.append(questionary.Choice(title=label, value=unit_name, checked=True))

    if len(unit_choices) > 1:
        console.print(
            "\n  [dim]Dica: [space] marca/desmarca  •  [a] seleciona tudo  •  [enter] confirma[/dim]\n"
        )
        selected_units = questionary.checkbox(
            "Selecione as Unidades:",
            choices=unit_choices,
            style=_STYLE,
        ).ask()

        if selected_units is None:
            return None
        if not selected_units:
            selected_units = list(grouped.keys())
    else:
        selected_units = list(grouped.keys())

    # ── 3. Resumo do que vai rodar ────────────────────────────────────────────
    final: list[ActivityInfo] = []
    for unit in selected_units:
        final.extend(grouped[unit])

    pending  = [a for a in final if not tracker.is_done(a.cmid)]
    done_lst = [a for a in final if tracker.is_done(a.cmid)]

    console.print()
    console.print(f"  [bold white]{len(final)}[/bold white] [dim]quiz(zes) selecionados:[/dim]")
    if done_lst:
        console.print(f"  [green]  ✓ {len(done_lst)} já concluídos[/green]")
    if pending:
        console.print(f"  [cyan]  ○ {len(pending)} pendentes[/cyan]")
    console.print()

    return final if final else None


def select_mode() -> ExecutionMode | None:
    mode_str = questionary.select(
        "Modo de execução:",
        choices=[
            questionary.Choice("AUTO_MODE  — submete de verdade", value="AUTO_MODE"),
            questionary.Choice("DRY_RUN    — só mostra respostas da IA, sem submeter", value="DRY_RUN"),
        ],
        style=_STYLE,
    ).ask()
    return ExecutionMode(mode_str) if mode_str else None


# ── Runner ────────────────────────────────────────────────────────────────────

async def execute(candidates: list[ActivityInfo], mode: ExecutionMode, force: bool = False) -> None:
    engine  = EvolutionEngine()
    orc     = LLMOrchestrator(engine=engine)
    tracker = CompletionTracker()
    display = RunDisplay(
        total_quizzes=len(candidates),
        active_config=engine.active_config,
        mode=mode.value,
    )
    display.register_courses(candidates)
    display.show_header()

    evaluator   = QuizEvaluator()
    reporter    = ExecutionReporter()
    all_metrics: list[QuizMetrics] = []
    successful = failed = skipped = 0

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        page = await ensure_authenticated(context)

        for idx, activity in enumerate(candidates):
            display.show_activity_start(idx + 1, activity)

            # Pula atividades já concluídas com sucesso em modo AUTO
            if mode == ExecutionMode.AUTO_MODE and tracker.is_done(activity.cmid):
                info = tracker.get(activity.cmid)
                display.show_activity_skipped(activity, info.score_percent if info else None)
                successful += 1
                skipped += 1
                continue

            # Atualiza contexto de curso no orquestrador (persona por matéria)
            orc.set_course(activity.course_id, activity.course_name)

            ctx = ExecutionContext(
                course_id    = activity.course_id,
                cmid         = activity.cmid,
                mode         = mode,
                force_submit = force,
            )

            quiz_start = time.monotonic()
            try:
                result = await run_quiz(page, ctx, orchestrator=orc)
                elapsed = time.monotonic() - quiz_start

                if result is None:
                    display.show_activity_result(activity, None, "dry_run", elapsed)
                    failed += 1
                    continue

                display.show_activity_result(activity, result.score_percent, result.status.value, elapsed)

                if result.status.value == "success":
                    successful += 1
                    if result.score_percent is not None:
                        action = orc.record_result(
                            cmid=activity.cmid,
                            score_percent=result.score_percent,
                        )
                        if action and action.triggered:
                            display.show_model_evolution(action)
                else:
                    failed += 1

                latest = _latest_manifest(Path("logs/quizzes"))
                if latest:
                    try:
                        all_metrics.append(evaluator.from_manifest(latest))
                    except Exception:
                        pass

            except Exception as exc:
                elapsed = time.monotonic() - quiz_start
                display.show_activity_result(activity, None, f"ERRO: {exc}", elapsed)
                failed += 1

            if idx < len(candidates) - 1:
                delay = random.uniform(15, 35)
                display.show_cooldown(delay)
                await asyncio.sleep(delay)

    avg_score = None
    if all_metrics:
        batch = reporter._aggregate(all_metrics)
        avg_score = batch.avg_score_percent
        report_path = Path("logs/reports") / f"batch_{int(time.time())}.json"
        reporter.save_report(batch, report_path)

    display.show_final_summary(successful, failed, avg_score, skipped=skipped)


# ── Live Discovery ────────────────────────────────────────────────────────────

def _map_is_empty() -> bool:
    path = Path("logs/activity_map.json")
    if not path.exists():
        return True
    try:
        return json.loads(path.read_text(encoding="utf-8")) == []
    except Exception:
        return True


async def _run_discovery_async() -> int:
    from backend.automation.discovery.live_discovery import run_full_discovery

    def _on_progress(msg: str) -> None:
        console.print(f"  [cyan]  {msg}[/cyan]")

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        page = await ensure_authenticated(context)
        activities = await run_full_discovery(page, on_progress=_on_progress)

    return len(activities)


def _prompt_and_run_discovery() -> bool:
    """Exibe aviso, pergunta confirmação e executa o discovery. Retorna True se concluído."""
    console.print()
    console.print(Panel(
        Text(
            "  Nenhuma atividade mapeada.\n\n"
            "  O sistema precisa mapear suas disciplinas no AVA Educ.\n"
            "  Isso leva cerca de 2-4 minutos e só é necessário uma vez\n"
            "  (ou quando novas disciplinas forem adicionadas).",
            style="yellow",
        ),
        border_style="yellow",
        expand=False,
    ))
    console.print()

    confirm = questionary.confirm(
        "Mapear atividades agora?",
        default=True,
        style=_STYLE,
    ).ask()

    if not confirm:
        return False

    console.print()
    console.print(Panel(
        Text("  Mapeando disciplinas... aguarde.", style="cyan"),
        border_style="cyan",
        expand=False,
    ))
    console.print()

    total = asyncio.run(_run_discovery_async())

    console.print()
    if total > 0:
        console.print(
            f"  [bold green]Mapeamento concluído:[/bold green] "
            f"[white]{total}[/white] atividades encontradas."
        )
    else:
        console.print(
            "  [yellow]Nenhuma atividade encontrada. "
            "Verifique se está matriculado em disciplinas no AVA.[/yellow]"
        )
    console.print()
    return total > 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if _map_is_empty():
        ok = _prompt_and_run_discovery()
        if not ok:
            console.print("\n[dim]  Saindo.[/dim]\n")
            return

    discovery  = ActivityDiscovery(Path("logs/activity_map.json")).load()
    all_quizzes = [
        a for a in discovery.all_activities()
        if a.type == ActivityType.QUIZ
    ]

    engine  = EvolutionEngine()
    cfg     = engine.active_config
    tracker = CompletionTracker()
    _print_header(f"{cfg.provider}/{cfg.model}", cfg.prompt_version)

    candidates = select_activities(all_quizzes, tracker)
    if not candidates:
        console.print("\n[dim]  Nenhuma atividade selecionada. Saindo.[/dim]\n")
        return

    mode = select_mode()
    if not mode:
        return

    # ── Detecta HIGH_VALUE ────────────────────────────────────────────────────
    high_value = [a for a in candidates if get_profile(a.course_id) == CourseProfile.HIGH_VALUE]
    force = False

    if high_value and mode == ExecutionMode.AUTO_MODE:
        console.print()
        warn = Text()
        warn.append("  ⚠  ATENÇÃO — ", style="bold yellow")
        warn.append(f"{len(high_value)} atividade(s) são HIGH_VALUE ", style="yellow")
        warn.append("(matérias com nota real na grade):\n", style="dim")
        for a in high_value:
            warn.append(f"     • {a.course_name}  —  {a.title}\n", style="dim")
        console.print(Panel(warn, border_style="yellow", expand=False))
        console.print()

        force = questionary.confirm(
            "Confirma AUTO_MODE com submissão real nessas matérias?",
            default=False,
            style=_STYLE,
        ).ask()

        if not force:
            console.print("\n[dim]  Operação cancelada. Use DRY_RUN para testar sem risco.[/dim]\n")
            return

    # ── Confirmação final ─────────────────────────────────────────────────────
    console.print()
    confirm = questionary.confirm(
        f"Executar {len(candidates)} quiz(zes) em {mode.value}?",
        default=True,
        style=_STYLE,
    ).ask()

    if not confirm:
        console.print("\n[dim]  Cancelado.[/dim]\n")
        return

    asyncio.run(execute(candidates, mode, force=force))


if __name__ == "__main__":
    main()
