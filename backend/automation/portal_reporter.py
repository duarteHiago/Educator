"""
Portal Reporter — envia resultados de execução para o portal educator.yaatoro.com.

Chamado após cada quiz pelo activity_router. Nunca levanta exceção:
falhas de rede são logadas e ignoradas para não interromper o .exe.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.automation.execution.modes import ExecutionContext
    from backend.schemas.quiz import SubmissionResult

logger = logging.getLogger(__name__)


async def report_run(
    ctx: ExecutionContext,
    result: SubmissionResult | None,
    questions_total: int = 0,
    questions_answered: int = 0,
) -> None:
    """Envia o resultado do quiz para a API do portal. Silencioso em caso de erro."""
    from backend.core.config import settings

    portal_url = getattr(settings, "portal_api_url", "")
    token      = getattr(settings, "proxy_token", "")

    if not portal_url or not token:
        return  # .exe sem configuração de portal — skip silencioso

    try:
        import httpx
        from backend.schemas.quiz import SubmissionStatus

        status = "dry_run"
        score_pct: float | None = None
        grade_str: str | None   = None
        error_msg: str | None   = None

        if result is not None:
            if result.status == SubmissionStatus.SUCCESS:
                status    = "success"
                score_pct = result.score_percent
                grade_str = result.grade_string
            elif result.status == SubmissionStatus.FAILED:
                status    = "failed"
                error_msg = result.error

        payload = {
            "token":               token,
            "execution_id":        ctx.execution_id,
            "cmid":                ctx.cmid,
            "course_id":           ctx.course_id,
            "mode":                ctx.mode.value,
            "status":              status,
            "score_percent":       score_pct,
            "grade_string":        grade_str,
            "questions_total":     questions_total,
            "questions_answered":  questions_answered,
            "error_message":       error_msg,
            "started_at":          ctx.started_at.isoformat(),
            "finished_at":         datetime.now(timezone.utc).isoformat(),
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.post(f"{portal_url}/api/runs/report", json=payload)
            if resp.status_code == 201:
                logger.info("reporter.ok", extra={"execution_id": ctx.execution_id})
            else:
                logger.warning("reporter.api_error",
                               extra={"status": resp.status_code, "body": resp.text[:200]})

    except Exception as exc:
        logger.warning("reporter.failed", extra={"error": str(exc)})
