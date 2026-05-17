"""
Live Discovery — mapeia dinamicamente as atividades do aluno no AVA Educ.

Diferença do script original (discover_quiz_cmids.py):
  - Não depende de COURSES hardcoded: descobre os cursos matriculados via dashboard AVA
  - Pode ser chamado programaticamente pelo menu ou pelo CLI

Fluxo:
  1. portal_page (autenticado) → navega para ESTUDAR_URL → SSO abre AVA em nova aba
  2. Acessa /my/ no AVA → extrai todos os course/view.php?id=XXXX
  3. Para cada curso: extrai atividades (diretas + tópicos)
  4. Salva em logs/activity_map.json
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import Page

from backend.core.logging import get_logger

logger = get_logger(__name__)

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
AVA_BASE    = "https://www.avaeduc.com.br"
MAP_FILE    = Path("logs/activity_map.json")

_MATERIAL_MODS  = {"resource", "book", "page", "folder", "label"}
_OPEN_ONLY_MODS = {"url", "lti", "scorm", "hvp", "pde"}


def _classify(mod: str) -> str:
    if mod == "quiz":               return "quiz"
    if mod == "assign":             return "assign"
    if mod in _MATERIAL_MODS:       return "material"
    if mod in _OPEN_ONLY_MODS:      return "open_only"
    return "unknown"


# ── AVA navigation ────────────────────────────────────────────────────────────

async def _wait_for_ava_page(context, timeout: float = 30.0) -> Page:
    """Aguarda a aba do AVA Educ abrir após o SSO."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for p in context.pages:
            if "avaeduc.com.br" in p.url:
                await p.wait_for_load_state("networkidle")
                return p
        await asyncio.sleep(0.5)
    raise TimeoutError("AVA Educ não abriu dentro do tempo limite.")


# ── Curso discovery ───────────────────────────────────────────────────────────

async def discover_enrolled_courses(ava_page: Page) -> dict[int, str]:
    """
    Acessa o dashboard do Moodle (/my/) e extrai todos os cursos matriculados.
    Retorna {course_id: course_name}.
    """
    await ava_page.goto(f"{AVA_BASE}/my/")
    await ava_page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)

    raw: dict = await ava_page.evaluate("""() => {
        const result = {};
        document.querySelectorAll('a[href*="/course/view.php?id="]').forEach(a => {
            const m = a.href.match(/course\\/view\\.php\\?id=(\\d+)/);
            if (!m) return;
            const id = parseInt(m[1]);
            if (id <= 1) return;
            const name = (a.innerText || a.title || a.getAttribute('data-original-title') || '').trim();
            if (name && !result[id]) result[id] = name;
        });
        return result;
    }""")

    courses = {int(k): v for k, v in raw.items()}
    logger.info("live_discovery.courses_found", total=len(courses), ids=list(courses.keys()))
    return courses


# ── Activity extraction ───────────────────────────────────────────────────────

async def _extract_mod_links(page: Page) -> list[dict]:
    return await page.evaluate(r"""() => {
        const items = [];
        const seen  = new Set();
        document.querySelectorAll('a[href*="/mod/"]').forEach(a => {
            const m = a.href.match(/\/mod\/(\w+)\/(?:view|index)\.php\?(?:id|cm)=(\d+)/);
            if (m && !seen.has(a.href)) {
                seen.add(a.href);
                const text = (a.innerText || a.title || a.getAttribute('aria-label') || '').trim();
                items.push({ mod: m[1], cmid: parseInt(m[2]), text: text.slice(0, 120), href: a.href });
            }
        });
        return items;
    }""")


async def _extract_topic_ids(page: Page, course_id: int) -> list[str]:
    html = await page.content()
    return re.findall(rf'course/view\.php\?id={course_id}&(?:amp;)?topic=(\d+)', html)


async def discover_activities(
    page: Page,
    course_id: int,
    course_name: str,
    on_progress: callable | None = None,
) -> list[dict]:
    """
    Extrai todas as atividades de um curso (diretas + tópicos).
    on_progress(msg): callback opcional para exibir progresso.
    """
    url = f"{AVA_BASE}/course/view.php?id={course_id}"
    logger.info("live_discovery.course_start", course=course_name, url=url)

    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)

    direct_links = await _extract_mod_links(page)
    topic_ids    = await _extract_topic_ids(page, course_id)
    unique_topics = list(dict.fromkeys(topic_ids))

    activities: list[dict] = []
    seen_cmids: set[int] = set()

    def _add(mod: str, cmid: int, text: str, href: str, source: str = "direct") -> None:
        if cmid in seen_cmids or cmid <= 1:
            return
        seen_cmids.add(cmid)
        cat = _classify(mod)
        activities.append({
            "cmid":        cmid,
            "course_id":   course_id,
            "course_name": course_name,
            "mod":         mod,
            "category":    cat,
            "title":       text or "(sem título)",
            "url":         href,
            "source":      source,
        })

    for link in direct_links:
        _add(link["mod"], link["cmid"], link["text"], link["href"])

    if unique_topics:
        if on_progress:
            on_progress(f"{course_name}: {len(unique_topics)} tópicos encontrados")
        for topic_id in unique_topics:
            topic_url = f"{AVA_BASE}/course/view.php?id={course_id}&topic={topic_id}"
            await page.goto(topic_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.8)
            for link in await _extract_mod_links(page):
                _add(link["mod"], link["cmid"], link["text"], link["href"],
                     source=f"topic_{topic_id}")

    logger.info("live_discovery.course_done",
                course=course_name, total=len(activities))
    return activities


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_full_discovery(
    portal_page: Page,
    on_progress: callable | None = None,
) -> list[dict]:
    """
    Ponto de entrada principal. Recebe a portal_page já autenticada.
    Faz SSO → descobre cursos → extrai atividades → salva activity_map.json.
    """
    if on_progress:
        on_progress("Acessando AVA Educ...")

    await portal_page.goto(ESTUDAR_URL)
    ava_page = await _wait_for_ava_page(portal_page.context)

    if on_progress:
        on_progress("Buscando disciplinas matriculadas...")

    courses = await discover_enrolled_courses(ava_page)

    if not courses:
        logger.warning("live_discovery.no_courses_found")
        return []

    all_activities: list[dict] = []

    for course_id, course_name in courses.items():
        if on_progress:
            on_progress(f"Mapeando: {course_name}...")
        acts = await discover_activities(ava_page, course_id, course_name, on_progress)
        all_activities.extend(acts)

    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAP_FILE.write_text(
        json.dumps(all_activities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    by_cat: dict[str, int] = {}
    for a in all_activities:
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1

    logger.info("live_discovery.done",
                total=len(all_activities),
                by_category=by_cat,
                output=str(MAP_FILE))

    return all_activities
