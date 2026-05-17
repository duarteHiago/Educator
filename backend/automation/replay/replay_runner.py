"""
Replay Runner — offline testing without opening a browser.

Usage:
    python scripts/run_quiz.py --replay logs/quizzes/{execution_id}/parsed/quiz_data.json

Loads a saved ParsedQuiz, runs it through the LLM orchestrator,
and optionally runs the review engine. No Playwright involved.
"""
import asyncio
import json
from pathlib import Path

from backend.automation.artifacts.artifact_logger import ArtifactLogger
from backend.automation.execution.modes import ExecutionContext, ExecutionMode
from backend.automation.review.review_engine import review_quiz
from backend.core.logging import configure_logging, get_logger
from backend.llm.orchestrator import LLMOrchestrator
from backend.schemas.quiz import ParsedQuiz

logger = get_logger(__name__)


async def replay(quiz_json_path: str | Path, mode: ExecutionMode = ExecutionMode.DRY_RUN) -> None:
    path = Path(quiz_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Quiz JSON not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    quiz = ParsedQuiz(**data)

    logger.info("replay.loaded",
                title=quiz.meta.title,
                questions=len(quiz.questions),
                source=str(path))

    ctx = ExecutionContext(
        course_id = quiz.meta.course_id,
        cmid      = quiz.meta.cmid,
        mode      = mode,
    )
    artifact = ArtifactLogger(ctx)

    # ── LLM ───────────────────────────────────────────────────────────────────
    orchestrator = LLMOrchestrator()
    responses    = await orchestrator.answer_quiz(quiz)

    for resp in responses:
        artifact.append_llm_response(resp)

    # ── Display results ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"REPLAY: {quiz.meta.title} ({len(quiz.questions)} questões)")
    print(f"{'='*60}")
    for question in quiz.questions:
        resp = next((r for r in responses if r.question_hash == question.question_hash), None)
        if resp:
            print(f"\n[Slot {question.slot}] {question.text[:80]}")
            for alt in question.alternatives:
                marker = " <--" if alt.id == resp.answer else ""
                print(f"  {alt.id}) {alt.text[:80]}{marker}")
            print(f"  IA: {resp.answer} ({resp.confidence:.0%}) — {resp.reasoning[:80]}")
            if resp.from_cache:
                print("  (cache)")

    # ── Review if requested ───────────────────────────────────────────────────
    if mode == ExecutionMode.REVIEW_MODE:
        reviewed = await review_quiz(quiz, responses)
        artifact.save_reviewed_answers(reviewed)

    artifact.finalize()
    logger.info("replay.done", execution_id=ctx.execution_id)


if __name__ == "__main__":
    import sys
    from backend.core.config import settings
    configure_logging(settings.log_level, settings.log_file)

    if len(sys.argv) < 2:
        print("Usage: python -m backend.automation.replay.replay_runner <quiz_data.json>")
        sys.exit(1)

    asyncio.run(replay(sys.argv[1]))
