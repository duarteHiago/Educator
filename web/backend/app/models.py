import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
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
