from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery = Celery(
    "educator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.discovery",
        "app.tasks.execution",
        "app.tasks.health_check",
        "app.tasks.scheduler",
    ],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=10,  # recycle workers to avoid memory leaks from Playwright
    beat_schedule={
        "health-check-every-6h": {
            "task": "app.tasks.health_check.health_check_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "process-scheduled-runs": {
            "task": "app.tasks.scheduler.process_scheduled_runs",
            "schedule": crontab(minute="*"),
        },
    },
)
