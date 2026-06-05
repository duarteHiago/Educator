
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import QuizExecution, Token, User, UserActivity
from app.schemas import DashboardStats, RunOut
from app.security import decrypt_token

router = APIRouter(tags=["dashboard"])


async def _get_litellm_spend(key_alias: str, litellm_url: str, master_key: str) -> tuple[float, float]:
    """Returns (used_usd, limit_usd). Gracefully returns (0, 0) on error."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{litellm_url}/spend/keys",
                params={"key_alias": key_alias},
                headers={"Authorization": f"Bearer {master_key}"},
            )
            if r.status_code == 200:
                data = r.json()
                keys = data if isinstance(data, list) else data.get("keys", [])
                for k in keys:
                    if k.get("key_alias") == key_alias:
                        return float(k.get("spend", 0)), float(k.get("max_budget") or 3.0)
    except Exception:
        pass
    return 0.0, 3.0


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    settings = get_settings()

    # Run counts
    total_res = await db.execute(
        select(func.count()).where(QuizExecution.user_id == user.id)
    )
    total_runs = total_res.scalar() or 0

    success_res = await db.execute(
        select(func.count()).where(
            QuizExecution.user_id == user.id,
            QuizExecution.status == "success",
        )
    )
    success_count = success_res.scalar() or 0
    success_rate = (success_count / total_runs) if total_runs > 0 else 0.0

    avg_res = await db.execute(
        select(func.avg(QuizExecution.score_percent)).where(
            QuizExecution.user_id == user.id,
            QuizExecution.score_percent.isnot(None),
        )
    )
    avg_score = avg_res.scalar()

    # Activity counts
    courses_res = await db.execute(
        select(func.count(func.distinct(UserActivity.course_id))).where(
            UserActivity.user_id == user.id
        )
    )
    courses_discovered = courses_res.scalar() or 0

    acts_res = await db.execute(
        select(func.count()).where(UserActivity.user_id == user.id)
    )
    activities_total = acts_res.scalar() or 0

    # LiteLLM spend
    credit_used, credit_limit = 0.0, 3.0
    token_res = await db.execute(
        select(Token).where(Token.user_id == user.id, Token.is_active.is_(True))
    )
    token_row = token_res.scalar_one_or_none()
    if token_row:
        credit_used, credit_limit = await _get_litellm_spend(
            token_row.key_alias, settings.litellm_url, settings.litellm_master_key
        )

    # Recent runs
    recent_res = await db.execute(
        select(QuizExecution)
        .where(QuizExecution.user_id == user.id)
        .order_by(QuizExecution.started_at.desc())
        .limit(5)
    )
    recent_runs = recent_res.scalars().all()

    return DashboardStats(
        total_runs=total_runs,
        success_rate=round(success_rate, 3),
        avg_score_percent=round(avg_score, 1) if avg_score is not None else None,
        courses_discovered=courses_discovered,
        activities_total=activities_total,
        credit_used_usd=round(credit_used, 4),
        credit_limit_usd=round(credit_limit, 2),
        recent_runs=recent_runs,
    )
