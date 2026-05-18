from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: Annotated[LoginRequest, Body()],
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings=Depends(get_settings),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # dummy hash evita user enumeration por diferença de timing
    dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    stored_hash = user.password_hash if user else dummy_hash

    if not verify_password(body.password, stored_hash) or user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    token = create_access_token(
        str(user.id),
        settings.secret_key,
        settings.access_token_expire_minutes,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return {"message": "Login realizado com sucesso"}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logout realizado"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
