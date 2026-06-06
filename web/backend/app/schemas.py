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
    masked_key: str
    hostname: str | None
    is_active: bool
    generated_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class TokenGenerated(BaseModel):
    full_key: str
    key_alias: str
    message: str = "Copie este token agora. Ele não será exibido novamente."


class BindRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    hostname: str = Field(min_length=1, max_length=255)

    @field_validator("hostname")
    @classmethod
    def sanitize_hostname(cls, v: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        return "".join(c for c in v if c in allowed)[:255]


class ValidateRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    hostname: str = Field(min_length=1, max_length=255)


class ValidateResponse(BaseModel):
    valid: bool
    message: str


# ── Report do .exe ────────────────────────────────────────────────────────────

class RunReport(BaseModel):
    token: str
    execution_id: str
    cmid: int
    course_id: int
    mode: str
    status: str
    score_percent: float | None = None
    grade_string: str | None = None
    questions_total: int = 0
    questions_answered: int = 0
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


# ── Execuções ─────────────────────────────────────────────────────────────────

class RunOut(BaseModel):
    id: UUID
    execution_id: str
    cmid: int
    course_id: int
    mode: str
    status: str
    score_percent: float | None
    grade_string: str | None
    questions_total: int
    questions_answered: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_runs: int
    success_rate: float
    avg_score_percent: float | None
    credit_used_usd: float
    credit_limit_usd: float
    recent_runs: list[RunOut]


# ── Notificações ──────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: UUID
    title: str
    body: str
    type: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


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
