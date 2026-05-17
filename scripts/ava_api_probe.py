"""
Proba AVA: lista cursos (DOM), testa core_course_get_contents via AJAX,
salva HTML do curso para inspecionar seletores reais.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright, Page
from backend.core.config import settings

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
AVA_AJAX    = "https://www.avaeduc.com.br/lib/ajax/service.php"
AVA_HOME    = "https://www.avaeduc.com.br/"
AVA_MY      = "https://www.avaeduc.com.br/my/"


async def wait_for_ava_page(context, timeout: float = 25.0) -> Page:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for p in context.pages:
            if "avaeduc.com.br" in p.url:
                return p
        await asyncio.sleep(0.5)
    raise TimeoutError("Pagina do AVA nao apareceu.")


async def moodle_ajax(page: Page, sesskey: str, calls: list[dict]) -> list:
    payload = [{"index": i, "methodname": c["method"], "args": c.get("args", {})}
               for i, c in enumerate(calls)]
    return await page.evaluate(f"""async () => {{
        const r = await fetch({json.dumps(AVA_AJAX + "?sesskey=" + sesskey)}, {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({json.dumps(payload)}),
        }});
        return await r.json();
    }}""")


async def get_sesskey(page: Page) -> str | None:
    for _ in range(8):
        v = await page.evaluate(r"""() => {
            if (window.M?.cfg?.sesskey) return window.M.cfg.sesskey;
            const m = document.body.innerHTML.match(/"sesskey":"([^"]{5,})"/);
            return m ? m[1] : null;
        }""")
        if v:
            return v
        await asyncio.sleep(1.5)
    return None


async def extract_courses_from_dom(page: Page) -> list[dict]:
    await page.goto(AVA_MY)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)
    return await page.evaluate(r"""() => {
        const courses = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/course/view.php"]').forEach(a => {
            const m = a.href.match(/\/course\/view\.php\?id=(\d+)/);
            if (m && !seen.has(m[1])) {
                seen.add(m[1]);
                courses.push({ id: parseInt(m[1]), name: a.innerText.trim() || a.title || '', url: a.href });
            }
        });
        return courses;
    }""")


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out_dir = Path("./logs/discovery")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        context = await browser.new_context(
            storage_state=str(settings.session_file_path),
            viewport={"width": 1280, "height": 800},
        )

        portal_page = await context.new_page()
        await portal_page.goto(settings.portal_url)
        await portal_page.wait_for_load_state("networkidle")

        await portal_page.goto(ESTUDAR_URL)
        await portal_page.wait_for_load_state("networkidle")

        try:
            ava_page = await wait_for_ava_page(context, timeout=25)
        except TimeoutError:
            ava_page = await context.new_page()
            await ava_page.goto(AVA_HOME)

        await ava_page.wait_for_load_state("networkidle")
        await asyncio.sleep(4)

        sesskey = await get_sesskey(ava_page)
        print(f"sesskey: {sesskey}")

        # ── Disciplinas via DOM ──────────────────────────────────────────
        courses = await extract_courses_from_dom(ava_page)
        (out_dir / "ava_courses_dom.json").write_text(
            json.dumps(courses, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nDisciplinas ({len(courses)}):")
        for c in courses:
            print(f"  [{c['id']:6}] {c['name'][:70]}")

        if not courses or not sesskey:
            await browser.close()
            return

        # ── Tenta core_course_get_contents para cada disciplina ─────────
        print(f"\n=== Testando core_course_get_contents ===")
        for course in courses[:3]:
            res = await moodle_ajax(ava_page, sesskey,
                [{"method": "core_course_get_contents", "args": {"courseid": course["id"]}}])
            ok = res and not res[0].get("error")
            print(f"  [{course['id']}] {'OK' if ok else 'ERR: ' + str(res[0].get('exception', {}).get('errorcode','?'))}")
            if ok:
                data = res[0].get("data", [])
                (out_dir / f"course_{course['id']}_contents.json").write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                for sec in data:
                    print(f"    Secao: {sec.get('name')}")
                    for mod in sec.get("modules", [])[:5]:
                        print(f"      [{mod.get('modname'):12}] {mod.get('name','')[:55]}")
                break  # basta o primeiro que funcionar

        # ── Salva HTML do curso para inspecionar seletores ───────────────
        print(f"\n=== Salvando HTML do primeiro curso para analise ===")
        first_course_url = courses[0]["url"]
        await ava_page.goto(first_course_url)
        await ava_page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        html = await ava_page.content()
        html_file = out_dir / "course_page.html"
        html_file.write_text(html, encoding="utf-8", errors="replace")
        print(f"HTML salvo: {html_file} ({len(html)//1024}KB)")

        # Extrai o que tem na pagina do curso via JS amplo
        page_data = await ava_page.evaluate(r"""() => {
            const links = [];
            document.querySelectorAll('a[href*="/mod/"]').forEach(a => {
                const m = a.href.match(/\/mod\/(\w+)\/(view|index)\.php\?(?:id|cm)=(\d+)/);
                if (m) links.push({ type: m[1], id: parseInt(m[3]), name: a.innerText.trim().slice(0,80), url: a.href });
            });
            return { url: window.location.href, activity_links: [...new Map(links.map(l=>[l.url,l])).values()] };
        }""")
        (out_dir / "course_activities_links.json").write_text(
            json.dumps(page_data, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"\nLinks de atividades encontrados: {len(page_data['activity_links'])}")
        for a in page_data["activity_links"]:
            print(f"  [{a['type']:12}] id={a['id']} {a['name'][:55]}")

        await browser.close()
        print("\nDone.")


asyncio.run(main())
