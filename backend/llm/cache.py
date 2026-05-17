"""
Disk-based question answer cache keyed by SHA-256(question_text).
One JSON file per question under logs/cache/.
Avoids redundant LLM calls for repeated questions.
"""
import json
from pathlib import Path

from backend.core.logging import get_logger
from backend.schemas.quiz import LLMResponse

logger = get_logger(__name__)

_CACHE_DIR = Path("./logs/cache")


def _path(question_hash: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{question_hash}.json"


def get(question_hash: str) -> LLMResponse | None:
    p = _path(question_hash)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        resp = LLMResponse(**data)
        resp.from_cache = True
        logger.debug("cache.hit", hash=question_hash[:8])
        return resp
    except Exception as exc:
        logger.warning("cache.corrupt", hash=question_hash[:8], error=str(exc))
        return None


def put(response: LLMResponse) -> None:
    p = _path(response.question_hash)
    p.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("cache.stored", hash=response.question_hash[:8])
