from playwright.async_api import Page

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

# URL que só é acessível autenticado — se redirecionar para login, sessão expirou
_AUTH_CHECK_URL = settings.portal_url


async def is_session_valid(page: Page, home_url: str = _AUTH_CHECK_URL) -> bool:
    """
    Navega para home_url e verifica se a sessão ainda está ativa.
    Heurística: se o servidor redirecionar para login.unic.br, sessão expirou.
    """
    if not settings.session_file_path.exists():
        logger.info("session.no_file")
        return False

    await page.goto(home_url)
    await page.wait_for_load_state("networkidle")

    current_url = page.url

    if "login.unic.br" in current_url:
        logger.warning("session.expired", redirected_to=current_url)
        return False

    logger.info("session.valid", url=current_url)
    return True


async def invalidate_session() -> None:
    session_file = settings.session_file_path
    if session_file.exists():
        session_file.unlink()
        logger.info("session.invalidated", file=str(session_file))
