from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import CreateUserRequest, UserOut
from app.security import hash_password, verify_admin_secret

router = APIRouter(tags=["admin"])


def _check_admin(x_admin_secret: str | None, settings) -> None:
    if x_admin_secret is None or not verify_admin_secret(x_admin_secret, settings.admin_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserRequest,
    x_admin_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings),
):
    _check_admin(x_admin_secret, settings)

    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(
    x_admin_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings),
):
    _check_admin(x_admin_secret, settings)
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.patch("/users/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: str,
    x_admin_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings),
):
    _check_admin(x_admin_secret, settings)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = False
    await db.flush()
    await db.refresh(user)
    return user
