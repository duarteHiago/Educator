"""
OpenAI provider — gpt-4o-mini by default, gpt-4o as fallback.
Uses structured JSON output via response_format.
"""
import json
import re
import time

from openai import AsyncOpenAI

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.llm.prompts import loader as prompts
from backend.llm.providers.base import BaseLLMProvider
from backend.schemas.quiz import LLMRequest, LLMResponse

logger = get_logger(__name__)

_ANSWER_RE     = re.compile(r'"answer"\s*:\s*"([A-Fa-f])"')
_CONFIDENCE_RE = re.compile(r'"confidence"\s*:\s*([\d.]+)')
_REASONING_RE  = re.compile(r'"reasoning"\s*:\s*"(.*?)(?:"|$)', re.DOTALL)
_LETTER_RE     = re.compile(r'^([A-Fa-f])[.):\s]?')


def extract_letter(raw_answer: str) -> str:
    """Extracts a single letter from the answer field, handling cases where
    the LLM returns the full alternative text instead of just the letter.
    Examples: 'D. MAIS; MAIS; MAS.' → 'D', 'B)' → 'B', 'c' → 'C'
    """
    s = raw_answer.strip()
    if len(s) == 1 and s.isalpha():
        return s.upper()
    m = _LETTER_RE.match(s)
    if m:
        return m.group(1).upper()
    if s and s[0].isalpha():
        return s[0].upper()
    return "A"


def _recover_partial_json(raw: str) -> dict | None:
    """Extracts answer/confidence/reasoning via regex when JSON is truncated."""
    m_a = _ANSWER_RE.search(raw)
    m_c = _CONFIDENCE_RE.search(raw)
    if not m_a:
        return None
    reasoning = ""
    m_r = _REASONING_RE.search(raw)
    if m_r:
        reasoning = m_r.group(1).replace('\\"', '"').strip()
    return {
        "answer":     m_a.group(1).upper(),
        "confidence": float(m_c.group(1)) if m_c else 0.5,
        "reasoning":  reasoning,
    }


_TIMEOUT = 90.0  # segundos — gpt-4o-mini é rápido, 90s é mais que suficiente


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.llm_model_primary
        if settings.proxy_url:
            self._client = AsyncOpenAI(
                api_key=settings.proxy_token,
                base_url=settings.proxy_url,
                timeout=_TIMEOUT,
                max_retries=2,
            )
        else:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=_TIMEOUT,
                max_retries=2,
            )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        version = request.prompt_version
        system_prompt = prompts.get_system_prompt(version)
        user_prompt = prompts.build_user_prompt_from_request(request, version)
        t0 = time.monotonic()

        logger.debug("llm.request",
                     model=self._model,
                     version=version,
                     hash=request.question_hash[:8],
                     alternatives=len(request.alternatives))

        if request.image_b64:
            user_content: str | list = [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{request.image_b64}",
                    "detail": "low",
                }},
            ]
        else:
            user_content = user_prompt

        response = await self._client.chat.completions.create(
            model    = self._model,
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            response_format = {"type": "json_object"},
            temperature     = 0.0,
            max_tokens      = 1024,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = response.choices[0].message.content or "{}"
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "length":
            logger.warning("llm.response_truncated", model=self._model, hash=request.question_hash[:8])

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = _recover_partial_json(raw)
            if parsed is None:
                logger.error("llm.invalid_json", raw=raw[:200])
                raise ValueError(f"LLM returned invalid JSON: {raw[:200]}")
            logger.warning("llm.json_recovered", hash=request.question_hash[:8])

        answer     = extract_letter(str(parsed.get("answer", "A")))
        confidence = float(parsed.get("confidence", 0.5))
        reasoning  = str(parsed.get("reasoning", ""))

        logger.info("llm.response",
                    model=self._model,
                    hash=request.question_hash[:8],
                    answer=answer,
                    confidence=confidence,
                    latency_ms=latency_ms)

        return LLMResponse(
            question_hash  = request.question_hash,
            answer         = answer,
            confidence     = confidence,
            reasoning      = reasoning,
            model          = self._model,
            provider       = "openai",
            prompt_version = version,
            latency_ms     = latency_ms,
        )
