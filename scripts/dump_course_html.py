"""
Salva o HTML completo de um curso para inspeção de estrutura.
Uso: python scripts/dump_course_html.py <course_id>
"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.flows.login import ensure_authenticated
from backend.automation.utils.browser import get_browser_context
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level, settings.log_file)
logger = get_logger("dump_html")

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
AVA_BASE    = "https://www.avaeduc.com.br"


async def wait_for_ava_page(context, timeout: float = 30.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for p in context.pages:
            if "avaeduc.com.br" in p.url:
                await p.wait_for_load_state("networkidle")
                return p
        await asyncio.sleep(0.5)
    raise TimeoutError("AVA Educ nao abriu.")


async def main(course_id: int) -> None:
    async with get_browser_context(restore_session=True) as (context, browser, pw):
        portal_page = await ensure_authenticated(context)
        await portal_page.goto(ESTUDAR_URL)
        page = await wait_for_ava_page(context)
        await asyncio.sleep(2)

        url = f"{AVA_BASE}/course/view.php?id={course_id}"
        print(f"Navegando para {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # Tenta expandir todas as seções colapsadas
        collapsed = await page.locator(".section-toggler, .collapsed, [data-toggle='collapse']").all()
        print(f"Secoes colapsadas encontradas: {len(collapsed)}")
        for el in collapsed:
            try:
                await el.click()
                await asyncio.sleep(0.3)
            except Exception:
                pass

        await asyncio.sleep(2)

        # Extrai todos os links /mod/
        links = await page.evaluate(r"""() => {
            const items = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/mod/"]').forEach(a => {
                if (!seen.has(a.href)) {
                    seen.add(a.href);
                    items.push({
                        href: a.href,
                        text: (a.innerText || a.title || '').trim().slice(0, 120),
                    });
                }
            });
            return items;
        }""")

        print(f"\nTodos os links /mod/ encontrados ({len(links)}):")
        for l in links:
            print(f"  {l['href']}")
            if l['text']:
                print(f"    -> {l['text']}")

        # Salva HTML
        html = await page.content()
        out = Path(f"logs/course_{course_id}.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8", errors="replace")
        print(f"\nHTML salvo em: {out}  ({len(html)} bytes)")


if __name__ == "__main__":
    cid = int(sys.argv[1]) if len(sys.argv) > 1 else 7138
    asyncio.run(main(cid))
