from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.database import Base, engine
from app.routes import admin, auth, tokens
from app.security import init_encryption

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
init_encryption(settings.encryption_key)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Educator API",
    docs_url=None,      # desativa Swagger em produção
    redoc_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Secret"],
)


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("educator_api started")


app.include_router(auth.router,   prefix="/api/auth")
app.include_router(tokens.router, prefix="/api/tokens")
app.include_router(admin.router,  prefix="/api/admin")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.1"}
