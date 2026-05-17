"""
Mapeia o SSO do portal UNIC para o AVA Educ (avaeduc.com.br).
Rastreia o fluxo de redirect, captura cookies e estrutura do AVA.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright, Page
from backend.core.config import settings

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"


async def dump_page(page: Page, label: str, api_calls: list) -> dict:
    url = page.url
    try:
        links = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().slice(0,80),
                href: a.href
            })).filter(l => l.text).slice(0, 40)
        """)
    except Exception:
        links = []

    try:
        page_text = await page.evaluate("() => document.body.innerText.slice(0,2000)")
    except Exception:
        page_text = ""

    print(f"\n{'='*60}")
    print(f"{label} | URL: {url[:100]}")
    print(f"Links: {len(links)}  |  API calls ate agora: {len(api_calls)}")
    print(f"Texto (preview): {page_text[:300]}")
    return {"url": url, "links": links, "text_preview": page_text}


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    session_file = settings.session_file_path
    if not session_file.exists():
        print("Sessao nao encontrada. Rode run_poc.py primeiro.")
        return

    all_requests: list[str] = []
    api_calls:    list[dict] = []
    pages_data:   list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            storage_state=str(session_file),
            viewport={"width": 1280, "height": 800},
        )

        # Monitora TODAS as abas abertas
        all_pages: list[Page] = []

        async def handle_new_page(new_page: Page):
            all_pages.append(new_page)
            print(f"\n[NOVA ABA] {new_page.url}")

            async def on_resp(r):
                ct = r.headers.get("content-type", "")
                if "json" in ct and r.status < 400:
                    try:
                        body = await r.json()
                        api_calls.append({"url": r.url[:120], "status": r.status, "body": body})
                    except Exception:
                        pass
                all_requests.append(f"[{r.status}] {r.url[:120]}")

            new_page.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
            await new_page.wait_for_load_state("networkidle")
            data = await dump_page(new_page, "NOVA ABA", api_calls)
            pages_data.append(data)

        context.on("page", lambda p: asyncio.ensure_future(handle_new_page(p)))

        # Pagina principal
        page = await context.new_page()
        all_pages.append(page)

        async def on_resp_main(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct and r.status < 400:
                try:
                    body = await r.json()
                    api_calls.append({"url": r.url[:120], "status": r.status, "body": body})
                except Exception:
                    pass
            all_requests.append(f"[{r.status}] {r.url[:120]}")

        page.on("response", lambda r: asyncio.ensure_future(on_resp_main(r)))

        print(f"Navegando para Estudar: {ESTUDAR_URL}")
        await page.goto(ESTUDAR_URL)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(5)  # aguarda possivel nova aba ou redirect

        data = await dump_page(page, "ABA PRINCIPAL", api_calls)
        pages_data.append(data)

        # Se o link abriu nova aba, ela ja foi capturada por handle_new_page
        # Aguarda mais um pouco para garantir que tudo carregou
        await asyncio.sleep(3)

        print(f"\n{'='*60}")
        print(f"RESUMO DO SSO FLOW")
        print(f"Total requests: {len(all_requests)}")
        print(f"Total API JSON calls: {len(api_calls)}")
        print(f"Total abas abertas: {len(all_pages)}")

        print("\nRequests relevantes (kroton/ava):")
        for r in all_requests:
            if any(kw in r.lower() for kw in ["kroton", "ava", "educ", "token", "auth", "sso", "login"]):
                print(f"  {r}")

        print("\nAPI JSON calls:")
        for a in api_calls[:15]:
            print(f"  [{a['status']}] {a['url']}")

        out = {
            "sso_flow_requests": all_requests,
            "api_calls": api_calls,
            "pages": pages_data,
        }
        out_file = Path("./logs/discovery/ava_map.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSalvo em: {out_file}")

        await browser.close()


asyncio.run(main())
