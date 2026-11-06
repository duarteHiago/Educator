"""
Editor de credenciais do .exe.

Permite corrigir CPF, senha do AVA ou token sem apagar o resto do config.enc
(ao contrário de --reset-config, que obriga a redigitar tudo).

Acessível por `educator.exe --config` ou pela opção "Configurações" do menu.
"""
from __future__ import annotations

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backend.core import user_config

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

def _mask(value: str, keep: int = 0) -> str:
    """Mascara um segredo, revelando opcionalmente os primeiros caracteres."""
    if not value:
        return "(vazio)"
    if keep <= 0 or len(value) <= keep:
        return "•" * min(len(value), 12)
    return value[:keep] + "•" * min(len(value) - keep, 12)


def _show_current(config: user_config.UserConfig) -> None:
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="dim")
    t.add_column(style="white")
    t.add_row("CPF",          f"{config.cpf[:3]}{'•' * 8}" if config.cpf else "(vazio)")
    t.add_row("Senha AVA",    _mask(config.ava_password))
    t.add_row("Token",        _mask(config.proxy_token, keep=8))
    t.add_row("Proxy",        config.proxy_url)
    console.print()
    console.print(Panel(t, title="[bold]Credenciais salvas[/bold]",
                        border_style="dim", expand=False))
    console.print()


def _ask_ava_password() -> str | None:
    """Pede a senha duas vezes — o motivo de existir esta tela é erro de digitação."""
    while True:
        first = questionary.password("Nova senha do AVA:", style=_STYLE).ask()
        if first is None:
            return None
        if not first:
            console.print("  [yellow]A senha não pode ficar vazia.[/yellow]")
            continue

        again = questionary.password("Repita a senha:", style=_STYLE).ask()
        if again is None:
            return None
        if first != again:
            console.print("  [yellow]As senhas não coincidem. Tente de novo.[/yellow]")
            continue

        return first


def _ask_cpf(current: str) -> str | None:
    while True:
        answer = questionary.text(
            "CPF (11 dígitos):",
            default=current,
            style=_STYLE,
        ).ask()
        if answer is None:
            return None

        cpf = "".join(c for c in answer if c.isdigit())
        if len(cpf) != 11:
            console.print("  [yellow]CPF inválido — precisa ter 11 dígitos.[/yellow]")
            continue
        return cpf


def _ask_token() -> str | None:
    while True:
        token = questionary.text(
            "Token de acesso (gerado no painel web):",
            style=_STYLE,
        ).ask()
        if token is None:
            return None
        token = token.strip()
        if not token:
            console.print("  [yellow]O token não pode ficar vazio.[/yellow]")
            continue
        return token


# ── Teste de credenciais ──────────────────────────────────────────────────────

def _test_credentials(config: user_config.UserConfig) -> None:
    """
    Faz um login real no AVA com as credenciais salvas.

    Usa UserRunContext em vez das env vars porque o Settings() global já pode
    ter sido instanciado com os valores antigos quando chamado pelo menu.
    """
    import asyncio

    console.print()
    console.print(Panel(
        Text("  Abrindo o AVA para testar o login... aguarde.", style="cyan"),
        border_style="cyan", expand=False,
    ))
    console.print()

    async def _probe() -> str | None:
        from backend.automation.execution.modes import UserRunContext
        from backend.automation.flows.login import do_login
        from backend.automation.utils.browser import get_browser_context

        user_ctx = UserRunContext(
            user_id="config-test",
            cpf=config.cpf,
            ava_password=config.ava_password,
            proxy_token=config.proxy_token,
            proxy_url=config.proxy_url,
        )

        # restore_session=False força o login completo em vez de reaproveitar
        # uma sessão antiga, que passaria mesmo com a senha errada.
        async with get_browser_context(
            restore_session=False,
            session_dir=user_ctx.session_dir,
        ) as (context, _browser, _pw):
            page = await context.new_page()
            await do_login(page, user_ctx=user_ctx)
        return None

    try:
        asyncio.run(_probe())
    except Exception as exc:
        console.print(f"  [bold red]Login falhou.[/bold red] [dim]{exc}[/dim]")
        console.print("  [yellow]Confira o CPF e a senha e tente novamente.[/yellow]")
        console.print()
        return

    console.print("  [bold green]Login bem-sucedido.[/bold green] "
                  "[dim]As credenciais estão corretas.[/dim]")
    console.print()


# ── Menu ──────────────────────────────────────────────────────────────────────

def run_config_menu() -> None:
    """Loop do editor. Retorna quando o usuário escolhe voltar."""
    config = user_config.load()

    if config is None:
        console.print()
        console.print("  [yellow]Nenhuma credencial salva ainda.[/yellow]")
        console.print("  [dim]Ela é pedida automaticamente no primeiro uso.[/dim]")
        console.print()
        return

    while True:
        _show_current(config)

        action = questionary.select(
            "Configurações:",
            choices=[
                questionary.Choice("Trocar a senha do AVA",     value="senha"),
                questionary.Choice("Corrigir o CPF",            value="cpf"),
                questionary.Choice("Trocar o token de acesso",  value="token"),
                questionary.Choice("Testar login no AVA agora", value="testar"),
                questionary.Separator(),
                questionary.Choice("Voltar",                    value="voltar"),
            ],
            style=_STYLE,
        ).ask()

        if action in (None, "voltar"):
            return

        if action == "senha":
            senha = _ask_ava_password()
            if senha is not None:
                config = user_config.update(ava_password=senha) or config
                console.print("  [green]Senha do AVA atualizada.[/green]")

        elif action == "cpf":
            cpf = _ask_cpf(config.cpf)
            if cpf is not None:
                config = user_config.update(cpf=cpf) or config
                console.print("  [green]CPF atualizado.[/green]")

        elif action == "token":
            token = _ask_token()
            if token is not None:
                config = user_config.update(proxy_token=token) or config
                console.print("  [green]Token atualizado.[/green]")

        elif action == "testar":
            _test_credentials(config)
