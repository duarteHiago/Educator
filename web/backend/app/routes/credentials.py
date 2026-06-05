from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserCredentials
from app.schemas import CredentialsSave, CredentialsStatus
from app.security import decrypt_token, encrypt_token  # noqa: F401

router = APIRouter(tags=["credentials"])


@router.post("", status_code=status.HTTP_200_OK, response_model=CredentialsStatus)
async def save_credentials(
    body: CredentialsSave,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialsStatus:
    result = await db.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()

    encrypted_cpf = encrypt_token(body.cpf)
    encrypted_password = encrypt_token(body.ava_password)

    if creds:
        creds.encrypted_cpf = encrypted_cpf
        creds.encrypted_password = encrypted_password
    else:
        creds = UserCredentials(
            user_id=user.id,
            encrypted_cpf=encrypted_cpf,
            encrypted_password=encrypted_password,
        )
        db.add(creds)

    await db.commit()
    await db.refresh(creds)
    return CredentialsStatus(exists=True, updated_at=creds.updated_at)


@router.get("/me", response_model=CredentialsStatus)
async def get_credentials_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialsStatus:
    result = await db.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    if creds is None:
        return CredentialsStatus(exists=False)
    return CredentialsStatus(exists=True, updated_at=creds.updated_at)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    if creds is None:
        raise HTTPException(status_code=404, detail="Credenciais não encontradas")
    await db.delete(creds)
    await db.commit()
