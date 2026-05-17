"""
Mapeia TODAS as atividades das matérias no AVA Educ.

Para matérias com estrutura de tópicos (?topic=XXXX), entra em cada
tópico para descobrir os cmids reais dos quizzes.

Classifica cada atividade:
  quiz      → responder questões (pipeline LLM)
  material  → abrir uma vez (marca completo)
  assign    → enviar arquivo
  open_only → abrir no AVA já registra nota

Salva resultado em logs/activity_map.json.

Uso:
    python scripts/discover_quiz_cmids.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.flows.login import ensure_authenticated
from backend.automation.utils.browser import get_browser_context
from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level, settings.log_file)
logger = get_logger("discover_activities")

ESTUDAR_URL = "https://alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle"
AVA_BASE    = "https://www.avaeduc.com.br"

MATERIAL_MODS  = {"resource", "book", "page", "folder", "label"}
OPEN_ONLY_MODS = {"url", "lti", "scorm", "hvp"}

COURSES = {
    # SAFE_TEST
    7136: "Ciencias Biologicas",
    7137: "Matematica",
    7138: "Portugues",
    8339: "Competencias para a Vida",
    # HIGH_VALUE
    10180: "Algoritmos e Estrutura de Dados Avancado",
    11074: "Seguranca da Informacao e de Redes",
    10457: "Sistemas Digitais e Microprocessadores",
    10741: "Desenvolvimento com Low Code",
}


def _classify(mod: str) -> str:
    if mod == "quiz":    return "quiz"
    if mod == "assign":  return "assign"
    if mod in MATERIAL_MODS:  return "material"
    if mod in OPEN_ONLY_MODS: return "open_only"
    return "unknown"


async def wait_for_ava_page(context, timeout: float = 30.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for p in context.pages:
            if "avaeduc.com.br" in p.url:
                await p.wait_for_load_state("networkidle")
                return p
        await asyncio.sleep(0.5)
    raise TimeoutError("AVA Educ nao abriu dentro do tempo limite.")


async def _extract_mod_links(page) -> list[dict]:
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


async def _extract_topic_ids(page, course_id: int) -> list[str]:
    """Extrai IDs de tópicos com Atividade Avaliativa ou Questões de Fixação."""
    html = await page.content()
    return re.findall(rf'course/view\.php\?id={course_id}&(?:amp;)?topic=(\d+)', html)


async def discover_activities(page, course_id: int, course_name: str) -> list[dict]:
    url = f"{AVA_BASE}/course/view.php?id={course_id}"
    logger.info("discover.navigating", course=course_name, url=url)

    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)

    # Tenta direto na página do curso
    direct_links = await _extract_mod_links(page)

    # Verifica se tem estrutura de tópicos
    topic_ids = await _extract_topic_ids(page, course_id)
    unique_topics = list(dict.fromkeys(topic_ids))  # preserva ordem, remove dupes

    activities: list[dict] = []
    seen_cmids: set[int] = set()

    def _add(mod, cmid, text, href, source="direct"):
        if cmid in seen_cmids or cmid == 1:
            return
        seen_cmids.add(cmid)
        cat = _classify(mod)
        activities.append({
            "cmid":        cmid,
            "course_id":   course_id,
            "course_name": course_name,
            "mod":         mod,
            "category":    cat,
            "title":       text or "(sem titulo)",
            "url":         href,
            "source":      source,
        })
        icon = {"quiz": "?", "assign": "=", "material": "~", "open_only": "o"}.get(cat, " ")
        print(f"  [{icon}] {mod:10s}  cmid={cmid:7d}  {text[:55]}")

    for l in direct_links:
        _add(l["mod"], l["cmid"], l["text"], l["href"])

    # Entra em cada tópico para achar quizzes escondidos
    if unique_topics:
        print(f"  -> {len(unique_topics)} topicos encontrados, entrando em cada um...")
        for topic_id in unique_topics:
            topic_url = f"{AVA_BASE}/course/view.php?id={course_id}&topic={topic_id}"
            await page.goto(topic_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.8)
            topic_links = await _extract_mod_links(page)
            for l in topic_links:
                _add(l["mod"], l["cmid"], l["text"], l["href"], source=f"topic_{topic_id}")

    return activities


async def main() -> None:
    all_activities: list[dict] = []

    async with get_browser_context(restore_session=True) as (context, browser, pw):
        portal_page = await ensure_authenticated(context)

        logger.info("discover.triggering_sso", url=ESTUDAR_URL)
        await portal_page.goto(ESTUDAR_URL)
        page = await wait_for_ava_page(context)
        logger.info("discover.ava_ready", url=page.url[:80])
        await asyncio.sleep(2)

        for course_id, course_name in COURSES.items():
            print(f"\n{'='*65}")
            print(f"{course_name}  (course_id={course_id})")
            print(f"{'='*65}")
            acts = await discover_activities(page, course_id, course_name)
            all_activities.extend(acts)
            if not acts:
                print("  Nenhuma atividade encontrada.")

    out = Path("logs/activity_map.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_activities, ensure_ascii=False, indent=2), encoding="utf-8")

    by_cat: dict[str, list] = {}
    for a in all_activities:
        by_cat.setdefault(a["category"], []).append(a)

    quizzes = by_cat.get("quiz", [])

    print(f"\n{'='*65}")
    print("RESUMO")
    print(f"{'='*65}")
    for cat, items in sorted(by_cat.items()):
        print(f"  [{cat:10s}]  {len(items):3d} atividades")
    print(f"  {'TOTAL':10s}  {len(all_activities):3d} atividades")

    if quizzes:
        print(f"\nQUIZZES encontrados ({len(quizzes)}):")
        for q in quizzes:
            print(f"  cmid={q['cmid']:7d}  [{q['course_name']}]  {q['title'][:55]}")

    print(f"\nSalvo em: {out}")
    logger.info("discover.done", total=len(all_activities), quizzes=len(quizzes), output=str(out))


if __name__ == "__main__":
    asyncio.run(main())
