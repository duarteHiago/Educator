"""
Quiz Execution Runner — single-pass pipeline.

  Por página: Navigate → Parse → LLM → Fill DOM → Next
  Ao final:   Summary → Finish → Confirm → Score

Passe único elimina o problema de navegação sequencial do Moodle:
preenchemos cada página ANTES de clicar Next, então nunca precisamos
voltar atrás.
"""
import asyncio
import base64
import re

from playwright.async_api import Page

from backend.automation.artifacts.artifact_logger import ArtifactLogger
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.flows.quiz_flow import (
    dismiss_overlays, js_click, get_sesskey_from_ava, AVA_BASE,
)
from backend.automation.parsers.moodle import quiz_parser, selectors as sel
from backend.automation.review.review_engine import review_quiz
from backend.automation.submitters import moodle_submitter
from backend.automation.utils.screenshot import capture_on_error
from backend.core.logging import get_logger
from backend.llm.orchestrator import LLMOrchestrator
from backend.schemas.quiz import (
    LLMResponse, ParsedQuiz, QuizMeta, ReviewedAnswer, ReviewStatus,
    SubmissionResult, SubmissionStatus,
)

logger = get_logger(__name__)

_LLM_MAX_ATTEMPTS = 3


async def _answer_with_retry(orc: LLMOrchestrator, question) -> LLMResponse:
    """Wraps answer_question with up to _LLM_MAX_ATTEMPTS retries on failure."""
    last_exc: Exception | None = None
    for attempt in range(1, _LLM_MAX_ATTEMPTS + 1):
        try:
            return await orc.answer_question(question)
        except Exception as exc:
            last_exc = exc
            if attempt < _LLM_MAX_ATTEMPTS:
                logger.warning(
                    "runner.llm_retry",
                    slot=question.slot,
                    attempt=attempt,
                    error=str(exc)[:120],
                )
                await asyncio.sleep(2.0 * attempt)

    logger.error(
        "runner.llm_all_retries_failed",
        slot=question.slot,
        error=str(last_exc)[:120],
    )
    return LLMResponse(
        question_hash=question.question_hash,
        answer="A",
        confidence=0.0,
        reasoning=f"Fallback após {_LLM_MAX_ATTEMPTS} tentativas: {last_exc}",
        model="fallback",
        provider="fallback",
    )


def _quiz_view_url(cmid: int) -> str:
    return f"{AVA_BASE}/mod/quiz/view.php?id={cmid}"


async def _start_attempt(page: Page, cmid: int) -> None:
    """Navega para a página do quiz e inicia/retoma a tentativa."""
    view_url = _quiz_view_url(cmid)
    logger.info("runner.navigating_to_quiz", url=view_url)
    await page.goto(view_url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.5)
    await dismiss_overlays(page)

    if "attempt.php" in page.url:
        logger.info("runner.attempt_already_open", url=page.url[:80])
        return

    start_btn = None
    for s in sel.START_ATTEMPT_BTN.split(", "):
        candidate = page.locator(s.strip()).first
        if await candidate.count() > 0:
            start_btn = candidate
            break

    if not start_btn:
        await capture_on_error(page, label="no_start_button")
        raise RuntimeError(f"Botão de início não encontrado em {page.url}")

    logger.info("runner.clicking_start")
    async with page.expect_navigation(wait_until="networkidle", timeout=20_000):
        await js_click(page, start_btn)
    await asyncio.sleep(1.5)
    await dismiss_overlays(page)

    # Sempre navega para page=0 para garantir que todas as páginas sejam processadas
    # (Moodle retoma na última página visitada, o que causaria skip das páginas anteriores)
    m = re.search(r'attempt=(\d+)', page.url)
    if m and "attempt.php" in page.url:
        attempt_id = m.group(1)
        page0_url = f"{AVA_BASE}/mod/quiz/attempt.php?attempt={attempt_id}&page=0"
        if f"page=0" not in page.url:
            logger.info("runner.navigating_to_page0", url=page0_url)
            await page.goto(page0_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.8)

    logger.info("runner.attempt_started", url=page.url[:80])


async def _fill_page_answers(
    page: Page,
    questions: list,
    reviewed_map: dict,
) -> list[int]:
    """Clica nas alternativas de todas as questões da página atual.
    Retorna lista de slots que falharam."""
    failed = []
    for q in questions:
        rev = reviewed_map.get(q.slot)
        if not rev:
            logger.warning("runner.no_reviewed_answer", slot=q.slot)
            continue

        chosen = rev.final_answer
        target = next((a for a in q.alternatives if a.id == chosen), None)
        if not target:
            logger.error("runner.alt_not_found", slot=q.slot, letter=chosen)
            failed.append(q.slot)
            continue

        radio_sel = f"input[name='{target.input_name}'][value='{target.input_value}']"
        locator = page.locator(radio_sel).first

        logger.info("runner.filling_radio",
                    slot=q.slot, letter=chosen, selector=radio_sel)

        if await locator.count() == 0:
            all_radios = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('input[type=radio]'))
                    .map(r => ({name: r.name, value: r.value}))
            """)
            logger.error("runner.radio_not_found",
                         slot=q.slot, letter=chosen,
                         selector=radio_sel,
                         radios_on_page=all_radios[:10])
            await capture_on_error(page, label=f"radio_not_found_slot{q.slot}")
            failed.append(q.slot)
            continue

        # Tenta click normal; fallback JS se falhar
        try:
            await locator.click(force=True, timeout=5_000)
        except Exception as e:
            logger.warning("runner.click_fallback_js", slot=q.slot, error=str(e))
            await locator.evaluate("el => el.click()")
        await asyncio.sleep(0.4)

        if not await locator.is_checked():
            # Último recurso: força via JS no DOM
            await page.evaluate(
                """([name, value]) => {
                    const el = document.querySelector(
                        `input[name='${name}'][value='${value}']`
                    );
                    if (el) {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
                [target.input_name, target.input_value],
            )
            await asyncio.sleep(0.3)

        if await locator.is_checked():
            logger.info("runner.radio_filled", slot=q.slot, letter=chosen)
        else:
            await capture_on_error(page, label=f"radio_fail_slot{q.slot}")
            logger.error("runner.radio_not_checked", slot=q.slot)
            failed.append(q.slot)

    return failed


async def run_quiz(
    page: Page,
    ctx: ExecutionContext,
    orchestrator: LLMOrchestrator | None = None,
) -> SubmissionResult | None:
    """
    Pipeline single-pass. Retorna SubmissionResult ou None (DRY_RUN).
    `page` já deve estar autenticado no AVA.
    """
    logger.info("runner.start", **{"ctx": ctx.summary()})
    artifact = ArtifactLogger(ctx)
    orc = orchestrator or LLMOrchestrator()

    # ── 1. Iniciar tentativa ──────────────────────────────────────────────────
    await _start_attempt(page, ctx.cmid)

    # ── 2. Single-pass: por página → parse → LLM → fill → Next ───────────────
    all_questions:  list = []
    all_responses:  list[LLMResponse] = []
    all_reviewed:   list[ReviewedAnswer] = []
    all_failed:     list[int] = []
    meta:           QuizMeta | None = None
    page_num = 0
    slot_offset = 0

    while True:
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(0.8)
        await dismiss_overlays(page)

        html = await page.content()
        artifact.save_raw_html(html, page=page_num)

        # Extrai meta só na primeira página
        if meta is None:
            sesskey = await get_sesskey_from_ava(page)
            meta = quiz_parser.extract_meta_from_html(html, ctx.cmid, ctx.course_id)
            if sesskey:
                meta = meta.model_copy(update={"sesskey": sesskey})
            logger.info("runner.meta", attempt_id=meta.attempt_id, title=meta.title)

        # Parse desta página
        qs, _ = quiz_parser.parse_attempt_page(
            html, meta, page=page_num, slot_offset=slot_offset
        )
        logger.info("runner.page_parsed",
                    page=page_num, questions=len(qs), url=page.url[:80])

        if qs:
            # Enrich image questions with screenshots before calling LLM
            enriched_qs = []
            for q in qs:
                if q.has_image:
                    try:
                        el = page.locator(f"#{q.question_id}").first
                        if await el.count() > 0:
                            img_bytes = await el.screenshot()
                            q = q.model_copy(update={"image_b64": base64.b64encode(img_bytes).decode()})
                    except Exception:
                        pass
                enriched_qs.append(q)
            qs = enriched_qs

            all_questions.extend(qs)
            slot_offset = len(all_questions)

            # LLM para as questões desta página (com retry em caso de falha)
            page_responses = []
            for q in qs:
                resp = await _answer_with_retry(orc, q)
                page_responses.append(resp)
                all_responses.append(resp)
                artifact.append_llm_response(resp)

            # DRY_RUN: só coleta, não preenche
            if ctx.mode == ExecutionMode.DRY_RUN:
                pass
            else:
                # Monta mapa slot → ReviewedAnswer para esta página
                reviewed_map: dict[int, ReviewedAnswer] = {}
                for q, resp in zip(qs, page_responses):
                    rev = ReviewedAnswer(
                        slot=q.slot,
                        question_hash=q.question_hash,
                        llm_answer=resp.answer,
                        final_answer=resp.answer,
                        confidence=resp.confidence,
                        reasoning=resp.reasoning,
                        status=ReviewStatus.APPROVED,
                    )
                    reviewed_map[q.slot] = rev
                    all_reviewed.append(rev)

                # Screenshot antes de preencher
                await capture_on_error(page, label=f"before_fill_page{page_num}")

                # Preenche alternativas desta página
                failed = await _fill_page_answers(page, qs, reviewed_map)
                all_failed.extend(failed)

                # Screenshot após preencher
                await capture_on_error(page, label=f"after_fill_page{page_num}")

        if page_num >= 50:
            logger.warning("runner.page_cap")
            break

        if ctx.mode == ExecutionMode.DRY_RUN:
            # Navega via URL direta — não clica Next para não salvar formulário vazio
            m_url = re.search(r'attempt=(\d+)(?:&page=(\d+))?', page.url)
            if not m_url:
                break
            aid = m_url.group(1)
            cur_moodle_page = int(m_url.group(2) or 0)
            next_url = f"{AVA_BASE}/mod/quiz/attempt.php?attempt={aid}&page={cur_moodle_page + 1}"
            logger.info("runner.dry_run_next_page", page=page_num, url=next_url)
            await page.goto(next_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.8)
            # Se caiu na summary, encerra
            if "summary.php" in page.url:
                logger.info("runner.last_page", total_pages=page_num + 1)
                break
        else:
            # Verifica se há próxima página
            next_btn = page.locator(sel.SUBMIT_NEXT).first
            has_next = await next_btn.count() > 0 and await next_btn.is_visible()

            if not has_next:
                logger.info("runner.last_page", total_pages=page_num + 1)
                break

            # Clica Next (salva respostas desta página no servidor)
            logger.info("runner.clicking_next", page=page_num)
            try:
                async with page.expect_navigation(wait_until="networkidle", timeout=15_000):
                    await js_click(page, next_btn)
            except Exception:
                await js_click(page, next_btn)
                await asyncio.sleep(3.0)

        page_num += 1

    # ── 3. DRY_RUN encerra aqui ───────────────────────────────────────────────
    if ctx.mode == ExecutionMode.DRY_RUN or meta is None:
        _print_dry_run_summary(all_questions, all_responses)
        artifact.finalize()
        return None

    # Reconstrói ParsedQuiz para compatibilidade com submitter
    quiz = ParsedQuiz(meta=meta, questions=all_questions, raw_html_pages=[])
    artifact.save_parsed_quiz(quiz)
    artifact.save_reviewed_answers(all_reviewed)

    # ── 4. Aborta se algum radio não foi marcado ──────────────────────────────
    if all_failed:
        logger.error("runner.fill_failed_aborting", failed_slots=all_failed)
        print(f"\nABORTADO: slots {all_failed} não preenchidos. Tentativa preservada.")
        result = SubmissionResult(
            attempt_id=meta.attempt_id,
            status=SubmissionStatus.FAILED,
            error=f"Fill failed: {all_failed}",
        )
        artifact.save_submission_result(result)
        artifact.finalize()
        return result

    logger.info("runner.all_filled", total=len(all_reviewed))

    # ── 5. Submit ─────────────────────────────────────────────────────────────
    if ctx.mode == ExecutionMode.AUTO_MODE:
        ctx.assert_submit_safe()
        result = await moodle_submitter.submit_attempt(page, quiz, all_reviewed, artifact)
        artifact.save_submission_result(result)
        artifact.finalize()
        return result

    # REVIEW_MODE — preenchido mas não enviado
    logger.info("runner.review_mode_not_submitted")
    dry = SubmissionResult(attempt_id=meta.attempt_id, status=SubmissionStatus.DRY_RUN)
    artifact.save_submission_result(dry)
    artifact.finalize()
    return dry


def _print_dry_run_summary(questions: list, responses: list[LLMResponse]) -> None:
    resp_map = {r.question_hash: r for r in responses}
    print(f"\n{'='*65}")
    print("DRY RUN")
    print(f"{'='*65}")
    for q in questions:
        resp = resp_map.get(q.question_hash)
        if not resp:
            continue
        print(f"\n[Slot {q.slot}] {q.text[:80]}")
        for alt in q.alternatives:
            marker = "  <-- IA" if alt.id == resp.answer else ""
            print(f"  {alt.id}) {alt.text[:80]}{marker}")
        print(f"  Confiança: {resp.confidence:.0%}")
    print(f"\n{'='*65}")
    print("Nenhuma ação realizada (DRY_RUN).")
