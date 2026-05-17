from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Tokens ────────────────────────────────────────────────────────────────────

class TokenOut(BaseModel):
    key_alias: str
    masked_key: str          # primeiros 12 + "..." + últimos 4 chars
    hostname: str | None
    is_active: bool
    generated_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class TokenGenerated(BaseModel):
    """Retornado apenas na geração — única vez que o full key é exibido."""
    full_key: str
    key_alias: str
    message: str = "Copie este token agora. Ele não será exibido novamente."


class BindRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    hostname: str = Field(min_length=1, max_length=255)

    @field_validator("hostname")
    @classmethod
    def sanitize_hostname(cls, v: str) -> str:
        # mantém apenas chars válidos em hostnames
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        return "".join(c for c in v if c in allowed)[:255]


class ValidateRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    hostname: str = Field(min_length=1, max_length=255)


class ValidateResponse(BaseModel):
    valid: bool
    message: str


# ── Admin ─────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("senha deve conter ao menos um número")
        if not any(c.isupper() for c in v):
            raise ValueError("senha deve conter ao menos uma letra maiúscula")
        return v
