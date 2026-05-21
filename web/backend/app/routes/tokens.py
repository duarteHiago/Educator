import logging
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Token, User
from app.schemas import (
    BindRequest,
    TokenGenerated,
    TokenOut,
    ValidateRequest,
    ValidateResponse,
)
from app.security import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tokens"])
limiter = Limiter(key_func=get_remote_address)


def _mask(key: str) -> str:
    return key[:12] + "..." + key[-4:] if len(key) > 16 else "****"


async def _litellm_generate(settings, alias: str) -> str:
    """Cria uma virtual key no LiteLLM. Retorna a key gerada."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.litellm_url}/key/generate",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={
                "key_alias": alias,
                "max_budget": 3.0,
                "budget_duration": "30d",
                "models": [
                    "gpt-4o-mini",
                    "gpt-4o",
                    "claude-haiku-4-5-20251001",
                    "claude-sonnet-4-6",
                ],
            },
        )
        resp.raise_for_status()
        key = resp.json().get("key")
        if not key:
            raise ValueError("LiteLLM não retornou key")
        return key


async def _litellm_revoke(settings, key: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.litellm_url}/key/delete",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={"keys": [key]},
        )
        resp.raise_for_status()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=TokenGenerated)
@limiter.limit("5/hour")
async def generate_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings=Depends(get_settings),
):
    result = await db.execute(select(Token).where(Token.user_id == user.id))
    existing = result.scalar_one_or_none()

    if existing:
        try:
            old_key = decrypt_token(existing.encrypted_key)
            await _litellm_revoke(settings, old_key)
        except Exception:
            logger.warning("revoke_litellm_failed user=%s", user.id)
        await db.delete(existing)
        await db.flush()

    alias = f"user_{user.id}"
    try:
        raw_key = await _litellm_generate(settings, alias)
    except Exception as exc:
        logger.error("litellm_generate_failed user=%s err=%s", user.id, str(exc))
        raise HTTPException(status_code=502, detail="Falha ao gerar token — tente novamente")

    token_row = Token(
        user_id=user.id,
        encrypted_key=encrypt_token(raw_key),
        key_alias=alias,
    )
    db.add(token_row)

    return TokenGenerated(full_key=raw_key, key_alias=alias)


@router.get("/me", response_model=TokenOut | None)
async def get_my_token(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Token).where(Token.user_id == user.id))
    token = result.scalar_one_or_none()
    if token is None:
        return None

    raw_key = decrypt_token(token.encrypted_key)
    return TokenOut(
        key_alias=token.key_alias,
        masked_key=_mask(raw_key),
        hostname=token.hostname,
        is_active=token.is_active,
        generated_at=token.generated_at,
        last_used_at=token.last_used_at,
    )


@router.post("/revoke", status_code=204)
async def revoke_token(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings=Depends(get_settings),
):
    result = await db.execute(select(Token).where(Token.user_id == user.id))
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=404, detail="Nenhum token ativo")

    try:
        raw_key = decrypt_token(token.encrypted_key)
        await _litellm_revoke(settings, raw_key)
    except Exception:
        logger.warning("revoke_litellm_failed user=%s", user.id)

    await db.delete(token)


# ── Endpoints chamados pelo .exe ──────────────────────────────────────────────

@router.post("/bind", response_model=ValidateResponse)
@limiter.limit("10/hour")
async def bind_hostname(
    request: Request,
    body: Annotated[BindRequest, Body()],
    db: AsyncSession = Depends(get_db),
):
    """
    Chamado pelo educator.exe na primeira execução.
    Vincula o token ao hostname da máquina.
    """
    result = await db.execute(select(Token).where(Token.is_active == True))
    tokens = result.scalars().all()

    matched: Token | None = None
    for t in tokens:
        try:
            if decrypt_token(t.encrypted_key) == body.token:
                matched = t
                break
        except Exception:
            continue

    if matched is None:
        raise HTTPException(status_code=404, detail="Token não encontrado")

    if matched.hostname is not None:
        if matched.hostname != body.hostname:
            logger.warning("bind_mismatch alias=%s", matched.key_alias)
            return ValidateResponse(valid=False, message="Token já vinculado a outra máquina")
        return ValidateResponse(valid=True, message="OK")

    matched.hostname = body.hostname
    matched.last_used_at = datetime.now(timezone.utc)
    return ValidateResponse(valid=True, message="Token vinculado com sucesso")


@router.post("/validate", response_model=ValidateResponse)
@limiter.limit("30/minute")
async def validate_token(
    request: Request,
    body: Annotated[ValidateRequest, Body()],
    db: AsyncSession = Depends(get_db),
):
    """
    Chamado pelo educator.exe a cada inicialização.
    Verifica se token + hostname são válidos. Requer bind prévio via /bind.
    """
    result = await db.execute(select(Token).where(Token.is_active == True))
    tokens = result.scalars().all()

    matched: Token | None = None
    for t in tokens:
        try:
            if decrypt_token(t.encrypted_key) == body.token:
                matched = t
                break
        except Exception:
            continue

    if matched is None:
        return ValidateResponse(valid=False, message="Token inválido ou revogado")

    if matched.hostname is None:
        return ValidateResponse(valid=False, message="Token ainda não vinculado. Execute o educator.exe uma vez primeiro.")

    if matched.hostname != body.hostname:
        return ValidateResponse(valid=False, message="Token não autorizado nesta máquina")

    matched.last_used_at = datetime.now(timezone.utc)
    return ValidateResponse(valid=True, message="OK")
