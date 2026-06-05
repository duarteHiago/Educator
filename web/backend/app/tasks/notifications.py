"""Email notifications via Resend SDK."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_resend():
    """Lazy import — resend not available in web backend container."""
    import resend  # type: ignore
    from app.config import get_settings
    settings = get_settings()
    resend.api_key = settings.resend_api_key
    return resend, settings


def send_email(to: str, subject: str, html: str) -> bool:
    """Send email via Resend. Returns True on success, False if disabled or error."""
    try:
        resend, settings = _get_resend()
        if not settings.resend_api_key:
            logger.info("email.disabled (no RESEND_API_KEY)")
            return False
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": to,
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as e:
        logger.error("email.send_failed", extra={"error": str(e)})
        return False


def send_run_complete(to: str, course_name: str, n_quizzes: int, avg_score: float | None) -> None:
    score_text = f"{avg_score:.1f}%" if avg_score is not None else "N/A"
    send_email(
        to=to,
        subject=f"[Educator] Execução concluída — {course_name}",
        html=f"""
        <p>Sua execução foi concluída.</p>
        <ul>
          <li><b>Disciplina:</b> {course_name}</li>
          <li><b>Quizzes executados:</b> {n_quizzes}</li>
          <li><b>Score médio:</b> {score_text}</li>
        </ul>
        <p><a href="https://educator.yaatoro.com/runs">Ver histórico completo</a></p>
        """,
    )


def send_run_failed(to: str, course_name: str, error: str) -> None:
    send_email(
        to=to,
        subject=f"[Educator] Falha na execução — {course_name}",
        html=f"""
        <p>Uma execução encontrou um erro.</p>
        <ul>
          <li><b>Disciplina:</b> {course_name}</li>
          <li><b>Erro:</b> {error[:300]}</li>
        </ul>
        <p><a href="https://educator.yaatoro.com/runs">Ver detalhes</a></p>
        """,
    )


def send_health_alert(to: str, detail: str) -> None:
    send_email(
        to=to,
        subject="[Educator] Alerta: seletores do AVA podem ter mudado",
        html=f"""
        <p><b>Health check falhou.</b> Os seletores do AVA Educ podem ter sido alterados.</p>
        <pre>{detail[:500]}</pre>
        <p>Verifique o portal e atualize os seletores se necessário.</p>
        """,
    )
