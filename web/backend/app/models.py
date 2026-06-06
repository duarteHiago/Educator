import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class Token(Base):
    __tablename__ = "tokens"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one active token per user
    )
    # LiteLLM key stored encrypted with Fernet — never plaintext in DB
    encrypted_key = Column(Text, nullable=False)
    key_alias     = Column(String(255), nullable=False)
    # null until .exe calls /tokens/bind on first run
    hostname      = Column(String(255), nullable=True)
    is_active     = Column(Boolean, default=True, nullable=False)
    generated_at  = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at  = Column(DateTime(timezone=True), nullable=True)



class QuizExecution(Base):
    __tablename__ = "quiz_executions"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id             = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    execution_id        = Column(String(32), nullable=False, unique=True)
    cmid                = Column(Integer, nullable=False)
    course_id           = Column(Integer, nullable=False)
    mode                = Column(String(16), nullable=False)    # DRY_RUN | AUTO_MODE
    status              = Column(String(16), nullable=False, default="pending")  # pending | running | success | failed
    score_percent       = Column(Float, nullable=True)
    grade_string        = Column(String(64), nullable=True)
    questions_total     = Column(Integer, default=0)
    questions_answered  = Column(Integer, default=0)
    error_message       = Column(Text, nullable=True)
    started_at          = Column(DateTime(timezone=True), server_default=func.now())
    finished_at         = Column(DateTime(timezone=True), nullable=True)


class AnswerKnowledgeBase(Base):
    __tablename__ = "answer_knowledge_base"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_hash      = Column(String(64), nullable=False, unique=True, index=True)
    correct_answer     = Column(String(4), nullable=False)   # "A", "B", "C", ...
    confidence         = Column(Float, nullable=False)
    confirmation_count = Column(Integer, nullable=False, default=1)
    last_confirmed_at  = Column(DateTime(timezone=True), server_default=func.now())



class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title      = Column(String(255), nullable=False)
    body       = Column(Text, nullable=False)
    type       = Column(String(32), nullable=False)   # run_complete | run_failed | health_alert
    is_read    = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
