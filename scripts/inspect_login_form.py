"""Script pontual — fluxo completo do login de dois passos (SPA progressivo)."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from backend.core.config import settings


async def dump_forms(page, label: str):
    data = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('input, button')).map(el => ({
            tag:          el.tagName,
            type:         el.type || '',
            name:         el.name || '',
            id:           el.id || '',
            placeholder:  el.placeholder || '',
            visible:      el.offsetParent !== null,
            class:        el.className.slice(0, 60),
        }));
    }""")
    print(f"\n{'='*60}")
    print(f"{label}  |  URL: {page.url[:80]}")
    print('='*60)
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()

        await page.goto(settings.portal_url)
        await page.wait_for_load_state("networkidle")
        await dump_forms(page, "PASSO 1 — ANTES DE PREENCHER CPF")

        # Preenche CPF e submete
        await page.fill("#username", settings.portal_username)
        await page.click('button[type="submit"]')

        # Aguarda campo de senha aparecer (SPA — sem page reload)
        try:
            await page.wait_for_selector('input[type="password"]', timeout=10000)
            print("\n[OK] Campo de senha apareceu!")
        except Exception:
            print("\n[WARN] Campo de senha nao apareceu. Verificar se houve navegacao.")

        await dump_forms(page, "PASSO 2 — APOS SUBMIT DO CPF")

        await asyncio.sleep(3)
        await browser.close()


asyncio.run(main())
