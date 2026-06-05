
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery
from app.database import get_db
from app.deps import get_current_user
from app.models import QuizExecution, User, UserCredentials
from app.schemas import JobRunRequest, JobStatusResponse, JobTriggerResponse

router = APIRouter(tags=["jobs"])


async def _require_credentials(user: User, db: AsyncSession) -> None:
    result = await db.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "CREDENTIALS_MISSING", "detail": "Configure suas credenciais AVA primeiro."},
        )


@router.post("/discover", response_model=JobTriggerResponse)
async def trigger_discovery(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    await _require_credentials(user, db)
    task = celery.send_task("app.tasks.discovery.discover_activities_task", args=[str(user.id)])
    return JobTriggerResponse(task_id=task.id, message="Mapeamento iniciado.")


@router.post("/run", response_model=JobTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    body: JobRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobTriggerResponse:
    await _require_credentials(user, db)

    # Block if user already has a running job for the same cmid
    result = await db.execute(
        select(QuizExecution).where(
            QuizExecution.user_id == user.id,
            QuizExecution.cmid == body.cmid,
            QuizExecution.status == "running",
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"error": "JOB_ALREADY_RUNNING", "detail": "Já há uma execução em andamento para este quiz."},
        )

    task = celery.send_task(
        "app.tasks.execution.run_quiz_task",
        args=[str(user.id), body.cmid, body.course_id, body.mode],
    )
    return JobTriggerResponse(task_id=task.id, message="Execução iniciada.")


@router.get("/{task_id}", response_model=JobStatusResponse)
async def get_job_status(
    task_id: str,
    user: User = Depends(get_current_user),
) -> JobStatusResponse:
    result = celery.AsyncResult(task_id)
    return JobStatusResponse(
        task_id=task_id,
        status=result.status,
        result=result.result if result.successful() else None,
    )


@router.get("/active/me")
async def get_active_jobs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(QuizExecution).where(
            QuizExecution.user_id == user.id,
            QuizExecution.status == "running",
        )
    )
    runs = result.scalars().all()
    return [
        {"execution_id": r.execution_id, "cmid": r.cmid, "started_at": r.started_at}
        for r in runs
    ]
