"""
Quiz Execution Runner — orchestrates the full pipeline.

  Browser → Parser → LLM → Fill DOM → Safety check → Submit

Respects ExecutionMode and CourseProfile at every step.
SAFETY: aborts submission if ANY question failed to be filled in the DOM.
"""
from playwright.async_api import Page

from backend.automation.artifacts.artifact_logger import ArtifactLogger
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.flows.quiz_flow import open_quiz_and_collect_pages, get_sesskey_from_ava
from backend.automation.parsers.moodle import quiz_parser
from backend.automation.review.review_engine import review_quiz
from backend.automation.submitters import moodle_submitter
from backend.core.logging import get_logger
from backend.llm.orchestrator import LLMOrchestrator
from backend.schemas.quiz import (
    LLMResponse, ParsedQuiz, ReviewedAnswer, ReviewStatus,
    SubmissionResult, SubmissionStatus,
)

logger = get_logger(__name__)


def _auto_approve(quiz: ParsedQuiz, responses: list[LLMResponse]) -> list[ReviewedAnswer]:
    """Convert LLM responses directly to ReviewedAnswers without human input."""
    resp_map = {r.question_hash: r for r in responses}
    reviewed = []
    for q in quiz.questions:
        resp = resp_map.get(q.question_hash)
        if resp:
            reviewed.append(ReviewedAnswer(
                slot          = q.slot,
                question_hash = q.question_hash,
                llm_answer    = resp.answer,
                final_answer  = resp.answer,
                confidence    = resp.confidence,
                reasoning     = resp.reasoning,
                status        = ReviewStatus.APPROVED,
            ))
        else:
            logger.warning("runner.no_llm_response_for_slot", slot=q.slot)
    return reviewed


async def run_quiz(
    page: Page,
    ctx: ExecutionContext,
    orchestrator: LLMOrchestrator | None = None,
) -> SubmissionResult | None:
    """
    Full quiz pipeline. Returns SubmissionResult or None (DRY_RUN).
    `page` must already be authenticated on www.avaeduc.com.br.
    """
    logger.info("runner.start", **{"ctx": ctx.summary()})

    artifact = ArtifactLogger(ctx)
    orc      = orchestrator or LLMOrchestrator()

    # ── 1. Collect HTML pages from Moodle ────────────────────────────────────
    html_pages = await open_quiz_and_collect_pages(
        page, ctx.cmid, artifact_dir=ctx.artifact_dir
    )

    for i, html in enumerate(html_pages):
        artifact.save_raw_html(html, page=i)

    # ── 2. Parse ──────────────────────────────────────────────────────────────
    sesskey = await get_sesskey_from_ava(page)
    first_html = html_pages[0] if html_pages else ""
    meta = quiz_parser.extract_meta_from_html(first_html, ctx.cmid, ctx.course_id)
    if sesskey:
        meta = meta.model_copy(update={"sesskey": sesskey})

    quiz: ParsedQuiz = quiz_parser.parse_quiz_pages(html_pages, meta)
    artifact.save_parsed_quiz(quiz)

    logger.info("runner.parsed",
                title=quiz.meta.title,
                questions=len(quiz.questions),
                pages=len(html_pages))

    if not quiz.questions:
        logger.warning("runner.no_questions_found")
        artifact.finalize()
        return None

    # ── 3. LLM ────────────────────────────────────────────────────────────────
    responses = await orc.answer_quiz(quiz)
    for resp in responses:
        artifact.append_llm_response(resp)

    # ── DRY_RUN ends here ─────────────────────────────────────────────────────
    if ctx.mode == ExecutionMode.DRY_RUN:
        _print_dry_run_summary(quiz, responses)
        artifact.finalize()
        return None

    # ── 4. Review (human or auto) ─────────────────────────────────────────────
    if ctx.mode == ExecutionMode.REVIEW_MODE:
        reviewed = await review_quiz(quiz, responses)
    else:
        reviewed = _auto_approve(quiz, responses)

    artifact.save_reviewed_answers(reviewed)

    # ── 5. Fill DOM ───────────────────────────────────────────────────────────
    failed_slots = await moodle_submitter.fill_answers(page, quiz, reviewed, artifact)

    if failed_slots:
        logger.error("runner.fill_failed_aborting",
                     failed_slots=failed_slots,
                     total=len(quiz.questions))
        print(f"\nABORTADO: {len(failed_slots)} questao(oes) nao preenchida(s) no DOM: slots {failed_slots}")
        print("Tentativa preservada — nenhum envio realizado.")
        abort_result = SubmissionResult(
            attempt_id = quiz.meta.attempt_id,
            status     = SubmissionStatus.FAILED,
            error      = f"Fill failed for slots: {failed_slots}",
        )
        artifact.save_submission_result(abort_result)
        artifact.finalize()
        return abort_result

    logger.info("runner.dom_filled_all_verified", total=len(reviewed))

    # ── 6. Submit (AUTO_MODE only, after profile guard) ───────────────────────
    if ctx.mode == ExecutionMode.AUTO_MODE:
        ctx.assert_submit_safe()
        result = await moodle_submitter.submit_attempt(page, quiz, reviewed, artifact)
        artifact.save_submission_result(result)
        artifact.finalize()
        return result

    # REVIEW_MODE — filled but not submitted
    logger.info("runner.review_mode_complete_not_submitted")
    dry_result = SubmissionResult(
        attempt_id = quiz.meta.attempt_id,
        status     = SubmissionStatus.DRY_RUN,
    )
    artifact.save_submission_result(dry_result)
    artifact.finalize()
    return dry_result


def _print_dry_run_summary(quiz: ParsedQuiz, responses: list) -> None:
    resp_map = {r.question_hash: r for r in responses}
    print(f"\n{'='*65}")
    print(f"DRY RUN — {quiz.meta.title}")
    print(f"{'='*65}")
    for q in quiz.questions:
        resp = resp_map.get(q.question_hash)
        if not resp:
            continue
        print(f"\n[Slot {q.slot}] {q.text[:80]}")
        for alt in q.alternatives:
            marker = "  <-- IA" if alt.id == resp.answer else ""
            print(f"  {alt.id}) {alt.text[:80]}{marker}")
        print(f"  Confiança: {resp.confidence:.0%} | {resp.reasoning[:80]}")
        if resp.from_cache:
            print("  (cache hit)")
    print(f"\n{'='*65}")
    print("Nenhuma ação realizada no browser (DRY_RUN).")
