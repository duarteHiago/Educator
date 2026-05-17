"""
Mapeia atividades das disciplinas academicas principais.
Salva HTML e links de atividades de cada disciplina.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright, Page
from backend.core.config import settings

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
AVA_BASE    = "https://www.avaeduc.com.br"

# Disciplinas academicas com maior chance de ter avaliações
TARGET_COURSES = [
    {"id": 10180, "name": "Algoritmos e Estrutura de Dados Avancado"},
    {"id": 11074, "name": "Seguranca da Informacao e de Redes"},
    {"id": 10457, "name": "Sistemas Digitais e Microprocessadores"},
    {"id": 10741, "name": "Desenvolvimento com Low Code"},
    {"id": 5008,  "name": "Projeto de Software"},
]


async def wait_for_ava(context, timeout: float = 25.0) -> Page:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for p in context.pages:
            if "avaeduc.com.br" in p.url:
                return p
        await asyncio.sleep(0.5)
    raise TimeoutError("AVA nao abriu.")


async def map_course(page: Page, course_id: int, out_dir: Path) -> dict:
    url = f"{AVA_BASE}/course/view.php?id={course_id}"
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    # Salva HTML para analise posterior
    html = await page.content()
    (out_dir / f"course_{course_id}.html").write_text(html, encoding="utf-8", errors="replace")

    # Extrai links de atividades
    activities = await page.evaluate(r"""() => {
        const items = [];
        const seen  = new Set();

        // Links /mod/*/view.php
        document.querySelectorAll('a[href*="/mod/"]').forEach(a => {
            const m = a.href.match(/\/mod\/(\w+)\/(?:view|index)\.php\?(?:id|cm)=(\d+)/);
            if (m && !seen.has(a.href)) {
                seen.add(a.href);
                const name = (a.innerText || a.title || a.getAttribute('aria-label') || '').trim();
                items.push({ type: m[1], cmid: parseInt(m[2]), name: name.slice(0,100), url: a.href });
            }
        });

        // Secoes da pagina
        const sections = [];
        document.querySelectorAll('.section-modchooser, .section, [data-sectionid], .topics > li, .weeks > li').forEach(sec => {
            const title = (
                sec.querySelector('h3.sectionname, .sectionname, h2, .section-title')?.innerText ||
                sec.getAttribute('aria-label') || ''
            ).trim();
            const mods = [];
            sec.querySelectorAll('a[href*="/mod/"]').forEach(a => {
                const m = a.href.match(/\/mod\/(\w+)\/(?:view|index)\.php\?(?:id|cm)=(\d+)/);
                if (m) mods.push({ type: m[1], cmid: parseInt(m[2]), name: (a.innerText||'').trim().slice(0,80) });
            });
            if (title || mods.length) sections.push({ title, modules: mods });
        });

        return { activities: items, sections };
    }""")

    return {
        "course_id":  course_id,
        "url":        page.url,
        "activities": activities["activities"],
        "sections":   activities["sections"],
    }


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out_dir = Path("./logs/discovery/courses")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        context = await browser.new_context(
            storage_state=str(settings.session_file_path),
            viewport={"width": 1280, "height": 800},
        )

        # Abre o AVA
        portal = await context.new_page()
        await portal.goto(settings.portal_url)
        await portal.wait_for_load_state("networkidle")
        await portal.goto(ESTUDAR_URL)
        await portal.wait_for_load_state("networkidle")

        try:
            ava = await wait_for_ava(context)
        except TimeoutError:
            ava = await context.new_page()
            await ava.goto("https://www.avaeduc.com.br/")

        await ava.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        print(f"AVA: {ava.url}")

        all_results = []

        for course in TARGET_COURSES:
            print(f"\n--- [{course['id']}] {course['name']} ---")
            result = await map_course(ava, course["id"], out_dir)

            acts = result["activities"]
            type_counts = {}
            for a in acts:
                type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1

            print(f"  Atividades: {len(acts)}  |  Tipos: {type_counts}")
            for a in acts[:10]:
                print(f"    [{a['type']:15}] id={a['cmid']} {a['name'][:55]}")
            if len(acts) > 10:
                print(f"    ... e mais {len(acts)-10}")

            all_results.append(result)

        out_file = Path("./logs/discovery/all_courses_map.json")
        out_file.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nMapa completo salvo em: {out_file}")

        await browser.close()


asyncio.run(main())
