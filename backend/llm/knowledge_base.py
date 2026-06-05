"""
Knowledge Base — persistent shared cache of verified correct answers.

Backed by PostgreSQL (AnswerKnowledgeBase table). Gracefully disabled
when DATABASE_URL is not set (local .exe usage without cloud backend).

Operations are synchronous (psycopg2) but wrapped in a thread executor
so they don't block the async automation loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kb")
_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "+asyncpg" in db_url:
        return None
    try:
        from sqlalchemy import create_engine
        _engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
        return _engine
    except Exception as e:
        logger.warning("knowledge_base.db_unavailable", extra={"error": str(e)})
        return None


def _sync_lookup(question_hash: str, min_confidence: float) -> str | None:
    engine = _get_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT correct_answer FROM answer_knowledge_base "
                    "WHERE question_hash = :h AND confidence >= :c "
                    "LIMIT 1"
                ),
                {"h": question_hash, "c": min_confidence},
            ).fetchone()
            if row:
                logger.debug("kb.hit", extra={"hash": question_hash[:8]})
                return row[0]
    except Exception as e:
        logger.debug("kb.lookup_error", extra={"error": str(e)})
    return None


def _sync_record(question_hash: str, answer: str, confidence: float) -> None:
    engine = _get_engine()
    if engine is None:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO answer_knowledge_base
                        (id, question_hash, correct_answer, confidence, confirmation_count, last_confirmed_at)
                    VALUES
                        (gen_random_uuid(), :h, :a, :c, 1, now())
                    ON CONFLICT (question_hash) DO UPDATE SET
                        correct_answer     = EXCLUDED.correct_answer,
                        confidence         = GREATEST(answer_knowledge_base.confidence, EXCLUDED.confidence),
                        confirmation_count = answer_knowledge_base.confirmation_count + 1,
                        last_confirmed_at  = now()
                """),
                {"h": question_hash, "a": answer, "c": confidence},
            )
            logger.debug("kb.recorded", extra={"hash": question_hash[:8]})
    except Exception as e:
        logger.debug("kb.record_error", extra={"error": str(e)})


async def lookup(question_hash: str, min_confidence: float = 0.9) -> str | None:
    """Return cached correct answer or None (non-blocking)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _sync_lookup, question_hash, min_confidence)


async def record(question_hash: str, answer: str, confidence: float) -> None:
    """Persist a verified correct answer (non-blocking)."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _sync_record, question_hash, answer, confidence)
