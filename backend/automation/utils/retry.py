import asyncio
import functools
from typing import Callable, TypeVar

from backend.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def async_retry(
    max_attempts: int = 3,
    delay_seconds: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for async functions. Retries on specified exceptions.
    Logs each attempt with structured context.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        logger.error(
                            "retry.exhausted",
                            func=func.__name__,
                            attempts=max_attempts,
                            error=str(exc),
                        )
                        raise
                    logger.warning(
                        "retry.attempt_failed",
                        func=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=str(exc),
                        retry_in=delay_seconds,
                    )
                    await asyncio.sleep(delay_seconds * attempt)
        return wrapper
    return decorator
