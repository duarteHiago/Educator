"""Celery tasks: run quiz / run full course for a user."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.celery_app import celery
from app.config import get_settings
from app.models import (
    AnswerKnowledgeBase, Notification, QuizExecution,
    Token, User, UserCredentials,
)
from app.security import init_encryption, decrypt_token
from app.tasks.db import get_session
from app.tasks.notifications import send_run_complete, send_run_failed

logger = logging.getLogger(__name__)


def _init_enc():
    init_encryption(get_settings().encryption_key)


def _get_user_proxy_token(db, user_id: uuid.UUID) -> str:
    """Return user's LiteLLM virtual key, or master key if none configured."""
    token_row = db.execute(
        select(Token).where(Token.user_id == user_id, Token.is_active.is_(True))
    ).scalar_one_or_none()
    if token_row:
        return decrypt_token(token_row.encrypted_key)
    return get_settings().litellm_master_key


async def _async_run_quiz(
    cpf: str, ava_password: str, proxy_token: str, proxy_url: str,
    user_id: str, cmid: int, course_id: int, mode: str,
    execution_id: str,
):
    import os
    os.environ.setdefault("PROXY_URL", proxy_url)
    os.environ.setdefault("PROXY_TOKEN", proxy_token)

    from backend.automation.execution.modes import ExecutionContext, ExecutionMode, UserRunContext
    from backend.automation.flows.login import ensure_authenticated
    from backend.automation.utils.browser import get_browser_context
    from backend.automation.execution.runner import run_quiz
    from backend.llm.orchestrator import LLMOrchestrator

    user_ctx = UserRunContext(
        user_id=user_id, cpf=cpf, ava_password=ava_password,
        proxy_token=proxy_token, proxy_url=proxy_url,
    )
    exec_ctx = ExecutionContext(
        course_id=course_id, cmid=cmid,
        mode=ExecutionMode(mode),
        execution_id=execution_id,
    )
    orc = LLMOrchestrator()

    async with get_browser_context(session_dir=user_ctx.session_dir) as (context, _browser, _pw):
        page = await ensure_authenticated(context, user_ctx=user_ctx)
        return await run_quiz(page, exec_ctx, orchestrator=orc)


@celery.task(bind=True, max_retries=1, default_retry_delay=30)
def run_quiz_task(self, user_id: str, cmid: int, course_id: int, mode: str = "AUTO_MODE") -> dict:
    _init_enc()
    settings = get_settings()
    uid = uuid.UUID(user_id)
    execution_id = uuid.uuid4().hex[:12]

    with get_session() as db:
        creds_row = db.execute(
            select(UserCredentials).where(UserCredentials.user_id == uid)
        ).scalar_one_or_none()
        if creds_row is None:
            raise ValueError(f"No credentials for user {user_id}")

        cpf      = decrypt_token(creds_row.encrypted_cpf)
        password = decrypt_token(creds_row.encrypted_password)
        proxy_token = _get_user_proxy_token(db, uid)

        user_email = db.execute(
            select(User.email).where(User.id == uid)
        ).scalar_one_or_none() or ""

        db_run = QuizExecution(
            user_id=uid,
            execution_id=execution_id,
            cmid=cmid,
            course_id=course_id,
            mode=mode,
            status="running",
            celery_task_id=self.request.id,
        )
        db.add(db_run)
        run_pk = db_run.id

    try:
        result = asyncio.run(_async_run_quiz(
            cpf=cpf, ava_password=password,
            proxy_token=proxy_token, proxy_url=settings.litellm_url,
            user_id=user_id, cmid=cmid, course_id=course_id,
            mode=mode, execution_id=execution_id,
        ))
    except Exception as exc:
        with get_session() as db:
            run = db.get(QuizExecution, run_pk)
            if run:
                run.status = "failed"
                run.error_message = str(exc)[:500]
                run.finished_at = datetime.now(timezone.utc)
            db.add(Notification(
                user_id=uid, title="Execução falhou",
                body=f"Erro ao executar quiz cmid={cmid}: {str(exc)[:200]}",
                type="run_failed",
            ))
        if user_email:
            send_run_failed(user_email, f"cmid={cmid}", str(exc))
        raise self.retry(exc=exc)

    score_pct = None
    grade_str = None
    status = "success"

    if result is not None:
        from backend.schemas.quiz import SubmissionStatus
        if result.status == SubmissionStatus.SUCCESS:
            score_pct = result.score_percent
            grade_str = result.grade_string
        elif result.status == SubmissionStatus.FAILED:
            status = "failed"

    with get_session() as db:
        run = db.get(QuizExecution, run_pk)
        if run:
            run.status = status
            run.score_percent = score_pct
            run.grade_string = grade_str
            run.finished_at = datetime.now(timezone.utc)

        # Persist correct answer in knowledge base when score is high
        if score_pct is not None and score_pct >= 80.0 and result:
            _upsert_knowledge_base(db, result)

        body = f"Quiz cmid={cmid} — score: {score_pct:.1f}%" if score_pct is not None else f"Quiz cmid={cmid} concluído."
        db.add(Notification(
            user_id=uid, title="Execução concluída",
            body=body, type="run_complete",
        ))

    if user_email:
        send_run_complete(user_email, f"cmid={cmid}", 1, score_pct)

    return {"execution_id": execution_id, "status": status, "score_percent": score_pct}


def _upsert_knowledge_base(db, result) -> None:
    """Persist correct answers when quiz scored ≥ 80%."""
    try:
        from backend.schemas.quiz import SubmissionStatus
        if not result or result.status != SubmissionStatus.SUCCESS:
            return
    except Exception:
        return


@celery.task(bind=True)
def run_course_task(self, user_id: str, course_id: int, mode: str = "AUTO_MODE") -> dict:
    """Fan-out: dispatches run_quiz_task for each quiz in the user's discovered activities."""
    from sqlalchemy import select as sa_select
    from app.models import UserActivity

    uid = uuid.UUID(user_id)

    with get_session() as db:
        activities = db.execute(
            sa_select(UserActivity).where(
                UserActivity.user_id == uid,
                UserActivity.course_id == course_id,
                UserActivity.activity_type == "quiz",
            )
        ).scalars().all()

    if not activities:
        return {"dispatched": 0, "reason": "no_quizzes_found"}

    for act in activities:
        run_quiz_task.delay(user_id, act.cmid, act.course_id, mode)

    return {"dispatched": len(activities)}
