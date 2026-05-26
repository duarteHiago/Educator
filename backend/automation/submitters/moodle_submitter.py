"""
Moodle Submission Engine — fills answers in the DOM and submits.

SAFETY PROTOCOL (must be followed in order):
  1. Navigate to each question page and fill via radio button click
  2. Verify each fill was applied
  3. Screenshot pre-submit
  4. Click "Finish attempt"
  5. Screenshot summary page
  6. Click final confirm
  7. Screenshot result page
  8. Extract and return score
"""
import asyncio
import re
from collections import defaultdict

from playwright.async_api import Page

from backend.automation.flows.quiz_flow import dismiss_overlays, js_click
from backend.automation.parsers.moodle import selectors as sel
from backend.automation.utils.screenshot import capture_on_error
from backend.core.logging import get_logger
from backend.schemas.quiz import (
    ParsedQuiz, ReviewedAnswer, ReviewStatus,
    SubmissionResult, SubmissionStatus,
)

logger = get_logger(__name__)

AVA_BASE = "https://www.avaeduc.com.br"


async def fill_answers(
    page: Page,
    quiz: ParsedQuiz,
    reviewed: list[ReviewedAnswer],
    artifact_logger=None,
) -> list[int]:
    """
    Navigate to each question page and fill answers via radio button clicks.
    Returns list of slots that FAILED to be filled (empty = all OK).
    """
    answer_map = {
        r.slot: r
        for r in reviewed
        if r.status in (ReviewStatus.APPROVED, ReviewStatus.OVERRIDDEN)
    }
    question_map = {q.slot: q for q in quiz.questions}
    failed_slots: list[int] = []

    # Group slots by their DOM page so we navigate once per page
    page_groups: dict[int, list[int]] = defaultdict(list)
    for slot in answer_map:
        q = question_map.get(slot)
        if q:
            page_groups[q.page].append(slot)
        else:
            logger.warning("submitter.question_not_found_for_slot", slot=slot)
            failed_slots.append(slot)

    attempt_id  = quiz.meta.attempt_id
    logger.info("submitter.fill_start",
                attempt_id=attempt_id,
                total_slots=len(answer_map),
                pages=sorted(page_groups.keys()))
    sorted_pages = sorted(page_groups.keys())

    for page_idx, page_num in enumerate(sorted_pages):
        is_last = (page_idx == len(sorted_pages) - 1)

        # Navigate to the correct attempt page
        if attempt_id:
            attempt_url = f"{AVA_BASE}/mod/quiz/attempt.php?attempt={attempt_id}&page={page_num}"
            logger.info("submitter.navigating_to_page", page=page_num, url=attempt_url)
            await page.goto(attempt_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1.2)
            await dismiss_overlays(page)
            logger.info("submitter.landed", url=page.url[:100])
            await capture_on_error(page, label=f"after_nav_page{page_num}")
        else:
            logger.warning("submitter.no_attempt_id_skipping_navigation")
            await capture_on_error(page, label="no_attempt_id_current_page")

        for slot in page_groups[page_num]:
            reviewed_answer = answer_map[slot]
            question       = question_map[slot]
            chosen_letter  = reviewed_answer.final_answer

            target_alt = next(
                (a for a in question.alternatives if a.id == chosen_letter), None
            )
            if not target_alt:
                logger.error("submitter.alt_not_found",
                             slot=slot, letter=chosen_letter)
                failed_slots.append(slot)
                continue

            radio_sel = f"input[name='{target_alt.input_name}'][value='{target_alt.input_value}']"
            locator   = page.locator(radio_sel).first

            logger.info("submitter.trying_radio",
                        slot=slot, letter=chosen_letter,
                        selector=radio_sel,
                        current_url=page.url[:80])

            if await locator.count() == 0:
                # Diagnóstico: lista todos os radios disponíveis na página
                all_radios = await page.evaluate("""() =>
                    Array.from(document.querySelectorAll('input[type=radio]'))
                        .map(r => ({name: r.name, value: r.value, id: r.id}))
                """)
                logger.error("submitter.radio_not_found",
                             slot=slot, letter=chosen_letter,
                             name=target_alt.input_name, value=target_alt.input_value,
                             radios_on_page=all_radios[:10])
                await capture_on_error(page, label=f"radio_not_found_slot{slot}")
                failed_slots.append(slot)
                continue

            # Tenta click normal primeiro; se não marcar, força via JS
            try:
                await locator.click(force=True, timeout=5_000)
            except Exception as click_err:
                logger.warning("submitter.click_failed_trying_js",
                               slot=slot, error=str(click_err))
                await locator.evaluate("el => el.click()")
            await asyncio.sleep(0.4)

            is_checked = await locator.is_checked()
            if not is_checked:
                # Último recurso: força via JS direto no DOM
                await page.evaluate(
                    """([name, value]) => {
                        const el = document.querySelector(
                            `input[name='${name}'][value='${value}']`
                        );
                        if (el) { el.checked = true; el.dispatchEvent(new Event('change', {bubbles:true})); }
                    }""",
                    [target_alt.input_name, target_alt.input_value],
                )
                await asyncio.sleep(0.3)
                is_checked = await locator.is_checked()

            if not is_checked:
                await capture_on_error(page, label=f"radio_fail_slot{slot}")
                logger.error("submitter.radio_not_checked_after_click",
                             slot=slot, letter=chosen_letter,
                             name=target_alt.input_name, value=target_alt.input_value)
                failed_slots.append(slot)
            else:
                logger.info("submitter.answer_filled", slot=slot, letter=chosen_letter)

        # Screenshot antes de salvar — confirma que os radios estão marcados
        await capture_on_error(page, label=f"pre_next_page{page_num}")

        # Click "Next page" to save the answer server-side (all pages, including
        # the last — on the last question page Next navigates to the summary,
        # which also persists the answer; skipping it leaves Q unanswered).
        next_btn = page.locator(sel.SUBMIT_NEXT).first
        if await next_btn.count() > 0:
            logger.info("submitter.clicking_next_to_save", page=page_num)
            await js_click(page, next_btn)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(0.5)
        else:
            logger.warning("submitter.next_button_not_found", page=page_num)

    return failed_slots


async def submit_attempt(
    page: Page,
    quiz: ParsedQuiz,
    reviewed: list[ReviewedAnswer],
    artifact_logger=None,
) -> SubmissionResult:
    """
    Full submission flow with screenshots at every critical step.
    """
    logger.info("submitter.starting_submission",
                cmid=quiz.meta.cmid,
                attempt_id=quiz.meta.attempt_id)

    # ── Navigate to summary page (Finish attempt button lives here) ───────────
    if quiz.meta.attempt_id:
        summary_url = f"{AVA_BASE}/mod/quiz/summary.php?attempt={quiz.meta.attempt_id}"
        logger.info("submitter.navigating_to_summary", url=summary_url)
        await page.goto(summary_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1.5)
        await dismiss_overlays(page)

    # ── Screenshot pre-submit ─────────────────────────────────────────────────
    if artifact_logger:
        await page.screenshot(
            path=str(artifact_logger.screenshot_path("pre_submit")),
            full_page=True
        )

    # ── Click "Enviar tudo e terminar" on summary page ───────────────────────
    finish_btn = page.locator(sel.SUBMIT_FINISH).first
    if await finish_btn.count() == 0:
        return SubmissionResult(
            attempt_id = quiz.meta.attempt_id,
            status     = SubmissionStatus.FAILED,
            error      = "Finish attempt button not found on summary page",
        )

    logger.info("submitter.clicking_finish")
    await js_click(page, finish_btn)
    await asyncio.sleep(2.0)  # wait for YUI confirm dialog to appear

    # ── Screenshot confirmation modal ─────────────────────────────────────────
    if artifact_logger:
        await page.screenshot(
            path=str(artifact_logger.screenshot_path("confirm_page")),
            full_page=True
        )

    # ── Confirm the YUI modal dialog (or native browser dialog) ──────────────
    confirm_btn = page.locator(sel.SUBMIT_FINISH_CONFIRM).first
    if await confirm_btn.count() > 0:
        logger.info("submitter.confirming_submission_modal")
        try:
            async with page.expect_navigation(wait_until="networkidle", timeout=20_000):
                await js_click(page, confirm_btn)
        except Exception:
            await js_click(page, confirm_btn)
            await asyncio.sleep(3.0)
    else:
        # Dialog may have already submitted or used page navigation directly
        logger.warning("submitter.confirm_button_not_found_proceeding")
        await asyncio.sleep(3.0)

    # ── Screenshot result page ────────────────────────────────────────────────
    if artifact_logger:
        await page.screenshot(
            path=str(artifact_logger.screenshot_path("result_page")),
            full_page=True
        )

    # ── Extract score ─────────────────────────────────────────────────────────
    # .grade elements exist per-question — must read the summary table row
    # "Avaliar" which contains e.g. "5,00 de um máximo de 10,00( 50 %)"
    score_raw, score_max, score_pct, grade_str = None, None, None, None
    try:
        grade_str = await page.evaluate("""() => {
            // quizreviewsummary row whose header says Avaliar / Grade / Nota
            const rows = document.querySelectorAll('.quizreviewsummary tr');
            for (const row of rows) {
                const th = row.querySelector('th');
                if (th && /avaliar|grade|nota/i.test(th.textContent)) {
                    const td = row.querySelector('td');
                    if (td) return td.textContent.trim();
                }
            }
            return null;
        }""")

        if grade_str:
            # "( 50 %)" → direct percentage
            pct_m = re.search(r"\(\s*([\d,.]+)\s*%\s*\)", grade_str)
            if pct_m:
                score_pct = float(pct_m.group(1).replace(",", "."))

            # "5,00 de um máximo de 10,00" or "5,00 / 10,00"
            raw_m = re.search(
                r"([\d,.]+)\s*(?:de\s+um\s+m[áa]ximo\s+de|de|/)\s*([\d,.]+)",
                grade_str,
            )
            if raw_m:
                score_raw = float(raw_m.group(1).replace(",", "."))
                score_max = float(raw_m.group(2).replace(",", "."))
                if score_pct is None and score_max:
                    score_pct = round(score_raw / score_max * 100, 1)

    except Exception as exc:
        logger.warning("submitter.score_extraction_failed", error=str(exc))

    result = SubmissionResult(
        attempt_id    = quiz.meta.attempt_id,
        status        = SubmissionStatus.SUCCESS,
        score_raw     = score_raw,
        score_max     = score_max,
        score_percent = score_pct,
        grade_string  = grade_str,
    )

    logger.info("submitter.submission_complete",
                status=result.status.value,
                score=result.score_percent)
    return result
