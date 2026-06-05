import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.database import Base, engine
from app.routes import (
    activities, admin, auth, credentials,
    dashboard, jobs, notifications, runs, schedule, tokens,
)
from app.security import init_encryption

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
init_encryption(settings.encryption_key)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Educator API",
    docs_url=None,
    redoc_url=None,
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": "60"},
        content={"detail": "Muitas tentativas. Tente novamente em instantes."},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Dados inválidos"})


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("educator_api started")


app.include_router(auth.router,          prefix="/api/auth")
app.include_router(tokens.router,        prefix="/api/tokens")
app.include_router(admin.router,         prefix="/api/admin")
app.include_router(credentials.router,   prefix="/api/credentials")
app.include_router(jobs.router,          prefix="/api/jobs")
app.include_router(activities.router,    prefix="/api/activities")
app.include_router(runs.router,          prefix="/api/runs")
app.include_router(dashboard.router,     prefix="/api/dashboard")
app.include_router(schedule.router,      prefix="/api/schedule")
app.include_router(notifications.router, prefix="/api/notifications")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.1"}
