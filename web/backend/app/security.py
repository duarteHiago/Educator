"""
Camada de segurança centralizada.

Nada de senha ou token transita em claro fora deste módulo.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

# bcrypt rounds=12 — ~250 ms por hash, resistente a brute-force em GPUs
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    # passlib usa constant-time internamente
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(user_id: str, secret_key: str, expires_minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> str:
    """Retorna user_id ou levanta JWTError."""
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise JWTError("missing sub")
    return user_id


# ── Fernet encryption (tokens LiteLLM) ───────────────────────────────────────

class _EncryptionService:
    def __init__(self, key: str) -> None:
        self._f = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        try:
            return self._f.decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("token decryption failed") from exc


_enc: _EncryptionService | None = None


def init_encryption(key: str) -> None:
    global _enc
    _enc = _EncryptionService(key)


def encrypt_token(value: str) -> str:
    assert _enc is not None, "call init_encryption() first"
    return _enc.encrypt(value)


def decrypt_token(encrypted: str) -> str:
    assert _enc is not None, "call init_encryption() first"
    return _enc.decrypt(encrypted)


# ── Admin secret ──────────────────────────────────────────────────────────────

def verify_admin_secret(provided: str, expected: str) -> bool:
    # compare_digest evita timing attacks (não curto-circuita na primeira diferença)
    return secrets.compare_digest(provided.encode(), expected.encode())
