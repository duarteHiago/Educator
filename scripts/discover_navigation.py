"""
Descobre a estrutura de navegação do portal (matérias, links, API de widgets).
Usa a sessão já salva — não faz login novamente.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from backend.core.config import settings


async def main():
    session_file = settings.session_file_path
    if not session_file.exists():
        print("Sessão não encontrada. Rode run_poc.py primeiro.")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            storage_state=str(session_file),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        captured_api: list[dict] = []

        async def on_response(response):
            url = response.url
            if "unic.br" in url and "api" in url:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = await response.json()
                        captured_api.append({"url": url, "body": body})
                    except Exception:
                        pass

        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

        print("Navegando para a home do portal...")
        await page.goto(settings.portal_url)
        await page.wait_for_load_state("networkidle")
        print(f"URL atual: {page.url}")

        # Lista todos os links visíveis da home
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().slice(0, 80),
                href: a.href,
                class: a.className.slice(0, 50),
            })).filter(l => l.text && l.href.includes('unic.br'));
        }""")

        print(f"\nLinks encontrados na home ({len(links)}):")
        for l in links:
            print(f"  [{l['text'][:40]:40s}] -> {l['href'][:80]}")

        print("\n--- Aguardando você navegar pelas matérias (10s) ---")
        await asyncio.sleep(10)

        # Captura os links da página atual (pode ter mudado)
        links2 = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href], [ng-click], [data-id]')).map(el => ({
                text:    el.innerText.trim().slice(0, 80),
                href:    el.href || '',
                ngclick: el.getAttribute('ng-click') || '',
                dataid:  el.getAttribute('data-id') || '',
                class:   el.className.slice(0, 50),
            })).filter(l => l.text);
        }""")

        print(f"\nElementos clicáveis ({len(links2)}):")
        for l in links2[:30]:
            print(f"  [{l['text'][:35]:35s}] href={l['href'][:50]} ng={l['ngclick'][:30]}")

        print(f"\nAPI calls capturadas: {len(captured_api)}")
        for api in captured_api[:10]:
            print(f"  {api['url'][:100]}")

        out = Path("./logs/discovery/navigation_map.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "links_home": links,
            "elements": links2,
            "api_calls": captured_api,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"\nSalvo em: {out}")
        await browser.close()


asyncio.run(main())
