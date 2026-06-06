
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import QuizExecution, Token, User
from app.schemas import RunOut, RunReport
from app.security import decrypt_token

router = APIRouter(tags=["runs"])


async def _user_by_token(raw_token: str, db: AsyncSession) -> User | None:
    """Identifica o usuário pelo token LiteLLM (mesmo padrão de /tokens/validate)."""
    result = await db.execute(
        select(Token, User)
        .join(User, User.id == Token.user_id)
        .where(Token.is_active.is_(True))
    )
    for token_row, user in result:
        try:
            if decrypt_token(token_row.encrypted_key) == raw_token:
                return user
        except Exception:
            continue
    return None


@router.post("/report", status_code=201)
async def report_run(
    body: RunReport,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Chamado pelo .exe após cada execução para persistir o resultado no portal."""
    user = await _user_by_token(body.token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Upsert: se o execution_id já existe, atualiza; senão cria
    existing = await db.execute(
        select(QuizExecution).where(QuizExecution.execution_id == body.execution_id)
    )
    run = existing.scalar_one_or_none()

    if run:
        run.status           = body.status
        run.score_percent    = body.score_percent
        run.grade_string     = body.grade_string
        run.questions_total  = body.questions_total
        run.questions_answered = body.questions_answered
        run.error_message    = body.error_message
        run.finished_at      = body.finished_at
    else:
        run = QuizExecution(
            user_id            = user.id,
            execution_id       = body.execution_id,
            cmid               = body.cmid,
            course_id          = body.course_id,
            mode               = body.mode,
            status             = body.status,
            score_percent      = body.score_percent,
            grade_string       = body.grade_string,
            questions_total    = body.questions_total,
            questions_answered = body.questions_answered,
            error_message      = body.error_message,
            started_at         = body.started_at,
            finished_at        = body.finished_at,
        )
        db.add(run)

    await db.commit()
    return {"ok": True, "execution_id": body.execution_id}


@router.get("", response_model=list[RunOut])
async def list_runs(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunOut]:
    result = await db.execute(
        select(QuizExecution)
        .where(QuizExecution.user_id == user.id)
        .order_by(QuizExecution.started_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{execution_id}", response_model=RunOut)
async def get_run(
    execution_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunOut:
    result = await db.execute(
        select(QuizExecution).where(
            QuizExecution.execution_id == execution_id,
            QuizExecution.user_id == user.id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    return run
