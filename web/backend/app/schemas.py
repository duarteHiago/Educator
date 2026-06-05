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


# ── Credenciais AVA ───────────────────────────────────────────────────────────

class CredentialsSave(BaseModel):
    cpf: str = Field(min_length=11, max_length=14)   # 11 dígitos ou com pontuação
    ava_password: str = Field(min_length=4, max_length=128)

    @field_validator("cpf")
    @classmethod
    def normalize_cpf(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve conter 11 dígitos")
        return digits


class CredentialsStatus(BaseModel):
    exists: bool
    updated_at: datetime | None = None


# ── Activities ─────────────────────────────────────────────────────────────────

class ActivityOut(BaseModel):
    id: UUID
    cmid: int
    course_id: int
    course_name: str
    activity_type: str
    title: str
    url: str | None
    discovered_at: datetime

    model_config = {"from_attributes": True}


class CourseOut(BaseModel):
    course_id: int
    course_name: str
    activities: list[ActivityOut]


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


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobTriggerResponse(BaseModel):
    task_id: str
    message: str


class JobRunRequest(BaseModel):
    cmid: int
    course_id: int
    mode: str = "AUTO_MODE"


class JobStatusResponse(BaseModel):
    task_id: str
    status: str   # PENDING | STARTED | SUCCESS | FAILURE | REVOKED
    result: dict | None = None


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_runs: int
    success_rate: float
    avg_score_percent: float | None
    courses_discovered: int
    activities_total: int
    credit_used_usd: float
    credit_limit_usd: float
    recent_runs: list[RunOut]


# ── Agendamentos ──────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    course_id: int | None = None
    cron_expr: str = Field(min_length=9, max_length=64)   # e.g. "0 3 * * *"
    mode: str = "AUTO_MODE"


class ScheduleOut(BaseModel):
    id: UUID
    course_id: int | None
    cron_expr: str
    mode: str
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
