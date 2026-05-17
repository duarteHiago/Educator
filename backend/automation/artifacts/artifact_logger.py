"""
Artifact logger — persists every execution artifact to disk.

Directory layout per execution:
  logs/quizzes/{execution_id}/
    raw_html/       page_0.html, page_1.html, ...
    parsed/         quiz_data.json
    llm/            requests.jsonl, responses.jsonl
    submissions/    result.json
    screenshots/    pre_submit.png, post_submit.png, error_*.png
    manifest.json   full ExecutionArtifact
"""
import json
from datetime import datetime
from pathlib import Path

from backend.automation.execution.modes import ExecutionContext
from backend.core.logging import get_logger
from backend.schemas.quiz import (
    ExecutionArtifact, LLMRequest, LLMResponse,
    ParsedQuiz, ReviewedAnswer, SubmissionResult,
)

logger = get_logger(__name__)


class ArtifactLogger:
    def __init__(self, ctx: ExecutionContext) -> None:
        self._ctx  = ctx
        self._root = ctx.artifact_dir
        self._dirs = {
            "raw_html":    self._root / "raw_html",
            "parsed":      self._root / "parsed",
            "llm":         self._root / "llm",
            "submissions": self._root / "submissions",
            "screenshots": self._root / "screenshots",
        }
        for d in self._dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        self._artifact = ExecutionArtifact(
            execution_id   = ctx.execution_id,
            mode           = ctx.mode.value,
            course_id      = ctx.course_id,
            course_profile = ctx.course_profile.value,
            cmid           = ctx.cmid,
        )
        logger.info("artifact.session_started", execution_id=ctx.execution_id, dir=str(self._root))

    # ── Raw HTML ──────────────────────────────────────────────────────────────

    def save_raw_html(self, html: str, page: int = 0) -> Path:
        path = self._dirs["raw_html"] / f"page_{page}.html"
        path.write_text(html, encoding="utf-8", errors="replace")
        logger.debug("artifact.raw_html_saved", page=page, size=len(html))
        return path

    # ── Parsed quiz ───────────────────────────────────────────────────────────

    def save_parsed_quiz(self, quiz: ParsedQuiz) -> Path:
        self._artifact.quiz = quiz
        path = self._dirs["parsed"] / "quiz_data.json"
        path.write_text(
            quiz.model_dump_json(indent=2, exclude={"raw_html_pages"}),
            encoding="utf-8",
        )
        logger.info("artifact.parsed_saved", questions=len(quiz.questions))
        return path

    # ── LLM ───────────────────────────────────────────────────────────────────

    def append_llm_request(self, req: LLMRequest) -> None:
        path = self._dirs["llm"] / "requests.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(req.model_dump_json() + "\n")

    def append_llm_response(self, resp: LLMResponse) -> None:
        self._artifact.llm_responses.append(resp)
        path = self._dirs["llm"] / "responses.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(resp.model_dump_json() + "\n")
        logger.debug("artifact.llm_response",
                     hash=resp.question_hash[:8],
                     answer=resp.answer,
                     confidence=resp.confidence,
                     from_cache=resp.from_cache)

    # ── Review ────────────────────────────────────────────────────────────────

    def save_reviewed_answers(self, answers: list[ReviewedAnswer]) -> Path:
        self._artifact.reviewed = answers
        path = self._dirs["parsed"] / "reviewed_answers.json"
        data = [a.model_dump() for a in answers]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("artifact.reviewed_saved", count=len(answers))
        return path

    # ── Submission ────────────────────────────────────────────────────────────

    def save_submission_result(self, result: SubmissionResult) -> Path:
        self._artifact.submission = result
        path = self._dirs["submissions"] / "result.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("artifact.submission_saved",
                    status=result.status.value,
                    score=result.score_percent)
        return path

    # ── Screenshots ───────────────────────────────────────────────────────────

    def screenshot_path(self, label: str) -> Path:
        return self._dirs["screenshots"] / f"{label}.png"

    # ── Manifest ──────────────────────────────────────────────────────────────

    def finalize(self) -> Path:
        self._artifact.finished_at = datetime.utcnow()
        path = self._root / "manifest.json"
        path.write_text(
            self._artifact.model_dump_json(indent=2, exclude={"quiz": {"raw_html_pages"}}),
            encoding="utf-8",
        )
        logger.info("artifact.finalized",
                    execution_id=self._ctx.execution_id,
                    dir=str(self._root))
        return path
