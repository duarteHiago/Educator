"""
PersonaBuilder — gera e cacheia persona de especialista por disciplina.

Approach C + fallback B:
  - Gera via LLM (gpt-4o-mini) uma descrição em 1-2 frases do especialista ideal
  - Cacheia em logs/personas/{course_id}.txt (gerado apenas uma vez por disciplina)
  - Se geração falhar → usa template de fallback

A persona é injetada no system_prompt de cada questão do quiz, substituindo
a descrição genérica de "assistente acadêmico" pela de um especialista da área.
"""
from __future__ import annotations

from pathlib import Path

from backend.core.logging import get_logger

logger = get_logger(__name__)

_CACHE_DIR = Path("logs/personas")

_FALLBACK_TEMPLATE = (
    "Você é um professor universitário especialista em {course_name}. "
    "Use a terminologia e metodologia específicos desta disciplina."
)

_GENERATION_PROMPT = (
    "Crie em 1-2 frases o perfil de um especialista universitário ideal "
    "para responder questões de múltipla escolha da disciplina: '{course_name}'. "
    "Comece exatamente com 'Você é'. Seja específico sobre a área de conhecimento "
    "e a abordagem metodológica. Responda APENAS com as frases do perfil."
)


async def get_persona(course_id: int, course_name: str) -> str:
    """Returns a subject-specific expert persona string, generating and caching on first call."""
    if not course_name or not course_id:
        return ""

    cache_file = _CACHE_DIR / f"{course_id}.txt"

    if cache_file.exists():
        persona = cache_file.read_text(encoding="utf-8").strip()
        logger.info("persona.cache_hit", course_id=course_id, course_name=course_name[:40])
        return persona

    persona = await _generate(course_name)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(persona, encoding="utf-8")
    logger.info("persona.generated", course_id=course_id, persona=persona[:100])

    return persona


async def _generate(course_name: str) -> str:
    try:
        from openai import AsyncOpenAI
        from backend.core.config import settings

        if settings.proxy_url:
            client = AsyncOpenAI(
                api_key=settings.proxy_token,
                base_url=settings.proxy_url,
                timeout=30.0,
            )
        else:
            client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": _GENERATION_PROMPT.format(course_name=course_name),
            }],
            temperature=0.7,
            max_tokens=80,
        )
        persona = resp.choices[0].message.content.strip()
        if persona.startswith("Você é"):
            return persona
        logger.warning("persona.bad_format", raw=persona[:80])
    except Exception as exc:
        logger.warning("persona.generation_failed", course_name=course_name, error=str(exc))

    return _FALLBACK_TEMPLATE.format(course_name=course_name)
