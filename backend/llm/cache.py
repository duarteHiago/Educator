"""
Disk-based question answer cache keyed by SHA-256(question_text + alternatives) + model.
One JSON file per (question, model) pair under logs/cache/.
Keying by model prevents a bad answer from a weak model blocking a stronger one.
"""
import json
from pathlib import Path

from backend.core.logging import get_logger
from backend.schemas.quiz import LLMResponse

logger = get_logger(__name__)

_CACHE_DIR = Path("./logs/cache")


def _cache_key(question_hash: str, model: str) -> str:
    suffix = model.replace("/", "_").replace(":", "_")
    return f"{question_hash}__{suffix}"


def _path(question_hash: str, model: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{_cache_key(question_hash, model)}.json"


def get(question_hash: str, model: str) -> LLMResponse | None:
    p = _path(question_hash, model)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        resp = LLMResponse(**data)
        resp.from_cache = True
        logger.debug("cache.hit", hash=question_hash[:8], model=model)
        return resp
    except Exception as exc:
        logger.warning("cache.corrupt", hash=question_hash[:8], model=model, error=str(exc))
        return None


def put(response: LLMResponse) -> None:
    p = _path(response.question_hash, response.model)
    p.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("cache.stored", hash=response.question_hash[:8], model=response.model)
