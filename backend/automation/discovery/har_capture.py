"""
Discovery — UNIC Aluno Digital.

Abre o portal real, intercepta toda a comunicação OAuth + APIs internas.
Navegue manualmente, faça login, acesse matérias. Pressione ENTER para salvar.

Usage:
    cd E:\\Documentos\\Estudos\\Programacao\\Educator
    python scripts/run_discovery.py
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, Request, Response, async_playwright

from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level, settings.log_file)
logger = get_logger(__name__)

OUTPUT_DIR = Path("./logs/discovery")

SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
                   ".ico", ".css", ".js", ".map", ".ttf", ".eot"}
SKIP_DOMAINS    = {"google-analytics.com", "googletagmanager.com", "hotjar.com",
                   "facebook.net", "doubleclick.net"}

INTERESTING_CONTENT_TYPES = {
    "application/json",
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/html",
}


def _should_capture(url: str, content_type: str | None) -> bool:
    lower = url.lower()
    path  = lower.split("?")[0]

    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if any(domain in lower for domain in SKIP_DOMAINS):
        return False

    # sempre captura domínios alvo
    if "unic.br" in lower:
        return True

    if content_type and any(ct in content_type for ct in INTERESTING_CONTENT_TYPES):
        return True

    return False


async def _extract_form_fields(page: Page, url: str) -> list[dict]:
    """Extrai campos de formulário da página atual."""
    try:
        fields = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('form')).map(form => ({
                action: form.action,
                method: form.method,
                fields: Array.from(form.querySelectorAll('input, select, textarea')).map(el => ({
                    tag:   el.tagName,
                    name:  el.name,
                    id:    el.id,
                    type:  el.type,
                    value: el.type === 'password' ? '[REDACTED]' : el.value,
                    placeholder: el.placeholder || '',
                    classes: el.className,
                }))
            }));
        }""")
        return fields
    except Exception:
        return []


async def run_discovery() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    requests_log: list[dict] = []
    form_snapshots: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        async def on_request(request: Request) -> None:
            if not _should_capture(request.url, request.headers.get("content-type")):
                return
            entry = {
                "type":          "request",
                "method":        request.method,
                "url":           request.url,
                "headers":       dict(request.headers),
                "post_data":     request.post_data,
                "resource_type": request.resource_type,
                "timestamp":     datetime.now().isoformat(),
            }
            requests_log.append(entry)
            marker = "<<< LOGIN POST >>>" if (
                request.method == "POST" and "login.unic.br" in request.url
            ) else ""
            logger.info("req", method=request.method, url=request.url[:120], note=marker)

        async def on_response(response: Response) -> None:
            ct = response.headers.get("content-type", "")
            if not _should_capture(response.url, ct):
                return
            body = None
            if "application/json" in ct:
                try:
                    body = await response.json()
                except Exception:
                    pass
            entry = {
                "type":         "response",
                "status":       response.status,
                "url":          response.url,
                "content_type": ct,
                "headers":      dict(response.headers),
                "body":         body,
                "timestamp":    datetime.now().isoformat(),
            }
            requests_log.append(entry)
            logger.info("res", status=response.status, url=response.url[:120])

        async def on_navigation(frame) -> None:
            if frame == page.main_frame:
                await asyncio.sleep(0.5)  # aguarda render
                url    = page.url
                fields = await _extract_form_fields(page, url)
                if fields:
                    snap = {"url": url, "forms": fields, "timestamp": datetime.now().isoformat()}
                    form_snapshots.append(snap)
                    logger.info("form.detected", url=url[:100], form_count=len(fields))

        page.on("request",  lambda r: asyncio.ensure_future(on_request(r)))
        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        page.on("framenavigated", lambda f: asyncio.ensure_future(on_navigation(f)))

        logger.info("discovery.started", target=settings.portal_url)
        await page.goto(settings.portal_url)

        print("\n" + "=" * 65)
        print("DISCOVERY MODE — UNIC Aluno Digital")
        print("=" * 65)
        print("O browser abrirá o portal. Faça:")
        print("  1. Login com CPF e senha")
        print("  2. Navegue pelas matérias/disciplinas")
        print("  3. Abra pelo menos uma atividade/questionário")
        print("  4. Volte aqui e pressione ENTER para salvar o mapeamento")
        print("=" * 65 + "\n")

        await asyncio.get_event_loop().run_in_executor(None, input)

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        net_file = OUTPUT_DIR / f"network_{ts}.json"
        frm_file = OUTPUT_DIR / f"forms_{ts}.json"

        net_file.write_text(
            json.dumps(requests_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        frm_file.write_text(
            json.dumps(form_snapshots, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info("discovery.saved",
                    network=str(net_file),
                    forms=str(frm_file),
                    total_requests=len(requests_log),
                    total_form_snapshots=len(form_snapshots))

        print(f"\nSalvo em:")
        print(f"  Network: {net_file}")
        print(f"  Forms:   {frm_file}")
        print(f"  Total requests capturados: {len(requests_log)}")
        print(f"  Formulários detectados:    {len(form_snapshots)}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_discovery())
