"""
Login flow — UNIC Aluno Digital (Kroton Olimpo OAuth 2.0).

Fluxo completo:
  1. Navega para alunodigital.unic.br/pda_unic
  2. ServiceNow redireciona para login.unic.br (proxy do Kroton Olimpo)
  3. Passo 1 SPA: preenche CPF em #username → submit
  4. JavaScript revela campo de senha (sem page reload)
  5. Passo 2 SPA: preenche senha em #login-pass → submit
  6. Kroton valida → POST /loginapi/api/v2/Autenticacao → authorization code
  7. Redirect de volta para alunodigital.unic.br/krotonpda?code=...
  8. ServiceNow troca o code por sessão → cookies estabelecidos
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from playwright.async_api import BrowserContext, Page

from backend.automation.utils.retry import async_retry
from backend.automation.utils.screenshot import on_error_screenshot
from backend.automation.utils.session import is_session_valid, invalidate_session
from backend.core.config import settings
from backend.core.logging import get_logger

if TYPE_CHECKING:
    from backend.automation.execution.modes import UserRunContext

logger = get_logger(__name__)

# ─── Seletores confirmados pelo discovery ─────────────────────────────────
_CPF_SELECTOR      = "#username"
_PASS_SELECTOR     = "#login-pass"
_SUBMIT_SELECTOR   = 'button[type="submit"]'
_AUTH_DOMAIN       = "login.unic.br"
_PORTAL_DOMAIN     = "alunodigital.unic.br"
_AVA_SSO_URL       = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
_AVA_BASE          = "https://www.avaeduc.com.br"
# ──────────────────────────────────────────────────────────────────────────


@async_retry(max_attempts=3, delay_seconds=3.0)
@on_error_screenshot(label="login")
async def do_login(page: Page, user_ctx: UserRunContext | None = None) -> None:
    cpf      = user_ctx.cpf          if user_ctx else settings.portal_username
    password = user_ctx.ava_password if user_ctx else settings.portal_password

    logger.info("login.start", portal=settings.portal_url)
    await page.goto(settings.portal_url)
    await page.wait_for_load_state("networkidle")

    current = page.url
    if _AUTH_DOMAIN not in current:
        if _PORTAL_DOMAIN in current:
            logger.info("login.already_authenticated")
            return
        raise RuntimeError(f"URL inesperada após navegar ao portal: {current}")

    logger.info("login.on_auth_page", url=current[:80])

    # ── Passo 1: CPF ──────────────────────────────────────────────────────
    await page.wait_for_selector(_CPF_SELECTOR, state="visible")
    await page.fill(_CPF_SELECTOR, cpf)
    await asyncio.sleep(0.3)

    logger.info("login.step1_submit")
    await page.click(_SUBMIT_SELECTOR)

    # O JS revela o campo de senha sem reload — aguarda aparecer
    await page.wait_for_selector(_PASS_SELECTOR, state="visible", timeout=10_000)
    logger.info("login.password_field_visible")

    # ── Passo 2: Senha ────────────────────────────────────────────────────
    await page.fill(_PASS_SELECTOR, password)
    await asyncio.sleep(0.4)

    logger.info("login.step2_submit")

    # Aguarda sair do domínio de login (OAuth redirect de volta ao portal)
    async with page.expect_navigation(
        url=lambda url: _AUTH_DOMAIN not in url,
        timeout=settings.browser_timeout,
    ):
        await page.click(_SUBMIT_SELECTOR)

    await page.wait_for_load_state("networkidle")
    final_url = page.url
    logger.info("login.complete", landed_on=final_url[:80])

    if _AUTH_DOMAIN in final_url:
        error_msg = ""
        try:
            el = page.locator(".alert, .error, [class*='error']").first
            error_msg = await el.inner_text(timeout=2000)
        except Exception:
            pass
        raise RuntimeError(f"Login falhou — ainda em {_AUTH_DOMAIN}. Msg: '{error_msg}'")


async def _establish_ava_session(page: Page, context: BrowserContext) -> Page:
    """
    Navega pelo SSO do portal → AVA.
    O portal pode abrir o AVA como popup, nova aba ou redirecionar na mesma aba.
    Aguarda até 25s por qualquer página com avaeduc.com.br; se não aparecer,
    tenta clicar em botão "Estudar"/"Acessar" na página do portal.
    """
    logger.info("auth.establishing_ava_session")
    await page.goto(_AVA_SSO_URL)
    await page.wait_for_load_state("networkidle")

    deadline = asyncio.get_event_loop().time() + 25

    while asyncio.get_event_loop().time() < deadline:
        # Checa se a página atual já é o AVA
        if "avaeduc.com.br" in page.url:
            logger.info("auth.ava_session_ready_same_tab", url=page.url[:80])
            return page

        # Checa todas as abas abertas no contexto
        for p in context.pages:
            if "avaeduc.com.br" in p.url and p is not page:
                await p.wait_for_load_state("networkidle")
                logger.info("auth.ava_session_ready_new_tab", url=p.url[:80])
                return p

        # Tenta clicar num botão/link de acesso ao AVA na página atual
        for selector in [
            "text=Estudar",
            "text=Acessar AVA",
            "text=Entrar",
            "a[href*='avaeduc']",
            "a[href*='moodle']",
            "[id*='estudar']",
            "[class*='estudar']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=300):
                    logger.info("auth.clicking_ava_link", selector=selector)
                    await el.click()
                    await asyncio.sleep(3)
                    break
            except Exception:
                pass

        await asyncio.sleep(1)

    logger.warning("auth.ava_session_timeout_using_page_as_is", url=page.url[:80])
    return page


async def ensure_authenticated(
    context: BrowserContext,
    user_ctx: UserRunContext | None = None,
) -> Page:
    """
    Retorna Page autenticada no AVA. Reutiliza sessão do portal se válida,
    mas sempre reestabelece a sessão do AVA via SSO antes de retornar.
    user_ctx: quando fornecido, usa credenciais e session_file do usuário.
    """
    page = await context.new_page()

    session_file = user_ctx.session_file if user_ctx else None

    if not await is_session_valid(page, settings.portal_url, session_file=session_file):
        logger.info("auth.session_invalid_relogging")
        await invalidate_session(session_file=session_file)
        await do_login(page, user_ctx=user_ctx)

    return await _establish_ava_session(page, context)
