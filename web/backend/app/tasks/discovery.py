"""Celery task: discover activities for a user account."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete

from app.celery_app import celery
from app.config import get_settings
from app.models import Notification, UserActivity, UserCredentials
from app.security import init_encryption, decrypt_token
from app.tasks.db import get_session

logger = logging.getLogger(__name__)


def _init_enc():
    settings = get_settings()
    init_encryption(settings.encryption_key)


async def _run_discovery(cpf: str, ava_password: str, proxy_url: str, proxy_token: str) -> list[dict]:
    from backend.automation.execution.modes import UserRunContext
    from backend.automation.flows.login import ensure_authenticated
    from backend.automation.utils.browser import get_browser_context
    from backend.automation.discovery.live_discovery import run_full_discovery

    user_ctx = UserRunContext(
        user_id=user_id,
        cpf=cpf,
        ava_password=ava_password,
        proxy_token=proxy_token,
        proxy_url=proxy_url,
    )

    async with get_browser_context(session_dir=user_ctx.session_dir) as (context, _browser, _pw):
        page = await ensure_authenticated(context, user_ctx=user_ctx)
        return await run_full_discovery(page)


@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def discover_activities_task(self, user_id: str) -> dict:
    _init_enc()
    settings = get_settings()

    with get_session() as db:
        creds_row = db.execute(
            select(UserCredentials).where(UserCredentials.user_id == uuid.UUID(user_id))
        ).scalar_one_or_none()

        if creds_row is None:
            raise ValueError(f"No credentials for user {user_id}")

        cpf      = decrypt_token(creds_row.encrypted_cpf)
        password = decrypt_token(creds_row.encrypted_password)

    try:
        activities = asyncio.run(_run_discovery(
            cpf=cpf,
            ava_password=password,
            proxy_url=settings.litellm_url,
            proxy_token=settings.litellm_master_key,
        ))
    except Exception as exc:
        logger.error("discovery.failed", extra={"user_id": user_id, "error": str(exc)})
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            with get_session() as db:
                db.add(Notification(
                    user_id=uuid.UUID(user_id),
                    title="Erro no mapeamento",
                    body=f"Não foi possível mapear suas atividades após 3 tentativas. Erro: {str(exc)[:200]}",
                    type="run_failed",
                ))
            raise

    with get_session() as db:
        # Replace all activities for this user with fresh discovery
        db.execute(delete(UserActivity).where(UserActivity.user_id == uuid.UUID(user_id)))
        for act in activities:
            db.add(UserActivity(
                user_id=uuid.UUID(user_id),
                cmid=act["cmid"],
                course_id=act["course_id"],
                course_name=act.get("course_name", ""),
                activity_type=act.get("category", "unknown"),
                title=act.get("title", ""),
                url=act.get("url"),
                discovered_at=datetime.now(timezone.utc),
            ))

        n = len(activities)
        db.add(Notification(
            user_id=uuid.UUID(user_id),
            title="Mapeamento concluído",
            body=f"{n} atividade(s) descoberta(s) nos seus cursos.",
            type="run_complete",
        ))

    logger.info("discovery.done", extra={"user_id": user_id, "total": len(activities)})
    return {"total": len(activities)}
