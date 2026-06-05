"""Periodic health check: verifies AVA portal is reachable and login selectors exist."""
from __future__ import annotations

import logging

import httpx

from app.celery_app import celery
from app.config import get_settings
from app.tasks.notifications import send_health_alert

logger = logging.getLogger(__name__)

_AVA_URL   = "https://www.avaeduc.com.br"
_LOGIN_URL = "https://login.unic.br/"
_REQUIRED_SELECTORS = ["id=\"username\"", "name=\"username\""]


@celery.task
def health_check_task() -> dict:
    settings = get_settings()
    errors: list[str] = []

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            # 1. AVA Educ reachable
            try:
                r = client.get(_AVA_URL)
                if r.status_code >= 500:
                    errors.append(f"AVA Educ retornou {r.status_code}")
            except Exception as e:
                errors.append(f"AVA Educ inacessível: {e}")

            # 2. Login page has expected selector
            try:
                r = client.get(_LOGIN_URL)
                if not any(sel in r.text for sel in _REQUIRED_SELECTORS):
                    errors.append(
                        "Seletor #username não encontrado em login.unic.br — "
                        "login flow pode ter mudado"
                    )
            except Exception as e:
                errors.append(f"Página de login inacessível: {e}")
    except Exception as e:
        errors.append(f"Erro inesperado no health check: {e}")

    if errors:
        detail = "\n".join(errors)
        logger.warning("health_check.failed", extra={"errors": errors})
        if settings.admin_email:
            send_health_alert(settings.admin_email, detail)
        return {"ok": False, "errors": errors}

    logger.info("health_check.ok")
    return {"ok": True}
