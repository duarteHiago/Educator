"""
Entry point do Educator.

Fluxo de inicialização (ordem importa):
  1. Parsear args (sem imports de backend)
  2. Tela de boas-vindas (só no primeiro uso)
  3. init_user_config() — injeta env vars antes de Settings() ser criado
  4. Importar e executar o menu principal

Flags:
  --install-browser   Instala o Chromium via Playwright (rodar uma vez após setup.bat)
  --reset-config      Apaga config.enc e solicita novas credenciais
  (nenhuma flag)      Abre o menu principal
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="educator",
        description="Educator — automação acadêmica",
    )
    parser.add_argument(
        "--install-browser",
        action="store_true",
        help="Instala o navegador Chromium (necessário apenas na primeira vez)",
    )
    parser.add_argument(
        "--reset-config",
        action="store_true",
        help="Apaga as credenciais salvas e solicita novas",
    )
    return parser.parse_args()


def _chromium_exe_path() -> Path | None:
    """Retorna o caminho esperado do executável Chromium ou None se não detectável."""
    try:
        if getattr(sys, "frozen", False):
            local_browsers = (
                Path(sys._MEIPASS)
                / "playwright" / "driver" / "package" / ".local-browsers"
            )
            if local_browsers.exists():
                for entry in local_browsers.iterdir():
                    if entry.name.startswith("chromium"):
                        exe = entry / "chrome-win64" / "chrome.exe"
                        if exe.exists():
                            return exe
            return None  # pasta não existe ou sem chromium instalado
        else:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                return Path(p.chromium.executable_path)
    except Exception:
        return None


def _install_browser(exit_after: bool = True) -> None:
    print("Instalando Chromium (pode demorar alguns minutos)...")

    if getattr(sys, "frozen", False):
        driver_dir = Path(sys._MEIPASS) / "playwright" / "driver"
        node = driver_dir / "node.exe"
        cli  = driver_dir / "package" / "cli.js"
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = "0"  # instala em .local-browsers dentro do bundle
        result = subprocess.run([str(node), str(cli), "install", "chromium"], env=env, check=False)
    else:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False,
        )

    if result.returncode == 0:
        print("Chromium instalado com sucesso.\n")
    else:
        print("Erro na instalação. Tente executar novamente.")
        sys.exit(1)

    if exit_after:
        sys.exit(0)


def _show_welcome_screen() -> None:
    """Exibe onboarding completo. Chamado apenas no primeiro uso (sem config.enc)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    console = Console(highlight=False, legacy_windows=False)

    console.print()
    console.print(Rule(style="dim"))

    titulo = Text()
    titulo.append("  EDUCATOR", style="bold white")
    titulo.append("  —  Automação de Atividades AVA", style="dim")
    console.print(titulo)

    console.print(Rule(style="dim"))
    console.print()

    # Bloco de boas-vindas
    bv = Text()
    bv.append("  Bem-vindo!\n\n", style="bold white")
    bv.append(
        "  Este programa acessa o AVA Educ automaticamente e responde\n"
        "  as atividades usando inteligência artificial.\n",
        style="white",
    )
    console.print(Panel(bv, border_style="blue", expand=False))
    console.print()

    # Passo a passo
    console.print("  [bold cyan]O que vai acontecer agora:[/bold cyan]\n")

    passos = [
        (
            "1  Configuração inicial",
            "Vamos pedir 3 informações para configurar o sistema:",
            [
                ("CPF",             "seu CPF cadastrado na instituição (só números)"),
                ("Senha do AVA",    "a mesma que você usa para entrar no AVA Educ"),
                ("Token de acesso", "código fornecido pelo desenvolvedor para usar a IA"),
            ],
        ),
        (
            "2  Mapeamento das disciplinas",
            "Na primeira vez, o sistema abre o navegador e mapeia automaticamente\n"
            "  todas as suas disciplinas e atividades no AVA Educ.",
            [],
        ),
        (
            "3  Menu principal",
            "Depois do mapeamento, o menu aparece e você escolhe\n"
            "  quais disciplinas e atividades quer executar.",
            [],
        ),
    ]

    for titulo_passo, descricao, detalhes in passos:
        t = Text()
        t.append(f"  [{titulo_passo}]\n", style="bold yellow")
        t.append(f"  {descricao}\n", style="white")
        for campo, explicacao in detalhes:
            t.append(f"    • {campo:<18}", style="bold cyan")
            t.append(f"{explicacao}\n", style="dim")
        console.print(t)
        if titulo_passo.startswith("2"):
            console.print("  [dim]  Isso leva entre 2 e 5 minutos — só é necessário uma vez.[/dim]")
            console.print()

    # Aviso sobre o navegador
    aviso = Text()
    aviso.append("  Atenção: ", style="bold yellow")
    aviso.append(
        "durante o mapeamento um navegador será aberto automaticamente.\n"
        "  Não feche nem interaja com ele — o sistema opera sozinho.",
        style="white",
    )
    console.print(Panel(aviso, border_style="yellow", expand=False))
    console.print()

    input("  Pressione ENTER para começar a configuração...")
    console.print()


def _ensure_logs_dir() -> None:
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    (logs / "cache").mkdir(exist_ok=True)
    (logs / "quizzes").mkdir(exist_ok=True)
    (logs / "reports").mkdir(exist_ok=True)

    map_file = logs / "activity_map.json"
    if not map_file.exists():
        map_file.write_text("[]", encoding="utf-8")


def main() -> None:
    args = _parse_args()

    if args.install_browser:
        _install_browser(exit_after=True)
        return

    # Auto-instala Chromium se ainda não existir (atualização de versão do Playwright)
    if _chromium_exe_path() is None:
        print("Chromium não encontrado. Instalando automaticamente...")
        _install_browser(exit_after=False)

    # Deve rodar ANTES de qualquer import de backend.*
    from backend.core.user_config import init_user_config, load, reset

    if args.reset_config:
        reset()
        print("Credenciais apagadas. Será solicitado novo cadastro.\n")

    # Mostra boas-vindas apenas se não houver config salvo (primeiro uso)
    # frozen=False em dev — welcome screen só aparece no .exe distribuído
    is_first_run = load() is None
    if is_first_run and getattr(sys, "frozen", False):
        _show_welcome_screen()

    init_user_config()

    _ensure_logs_dir()

    # Configura logging — no .exe, apenas arquivo (sem poluir o terminal)
    from backend.core.config import settings
    from backend.core.logging import configure_logging
    configure_logging(
        log_level=settings.log_level,
        log_file=settings.log_file,
        silent_console=getattr(sys, "frozen", False),
    )

    # Agora é seguro importar o restante do backend
    from scripts.menu import main as run_menu
    run_menu()


if __name__ == "__main__":
    main()
