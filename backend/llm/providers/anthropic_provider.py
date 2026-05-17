"""
Anthropic provider — Claude models via anthropic SDK.
Parses JSON from free-text response (no native json_object mode).
"""
from __future__ import annotations

import json
import re
import time

import anthropic

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.llm.prompts import loader as prompts
from backend.llm.providers.base import BaseLLMProvider
from backend.schemas.quiz import LLMRequest, LLMResponse

logger = get_logger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or "claude-haiku-4-5-20251001"
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        version = request.prompt_version
        system_prompt = prompts.get_system_prompt(version)
        user_prompt = prompts.build_user_prompt_from_request(request, version)

        t0 = time.monotonic()
        logger.debug("llm.request",
                     provider="anthropic",
                     model=self._model,
                     version=version,
                     hash=request.question_hash[:8])

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = message.content[0].text if message.content else "{}"

        match = _JSON_RE.search(raw)
        raw_json = match.group(0) if match else raw

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            from backend.llm.providers.openai_provider import _recover_partial_json
            parsed = _recover_partial_json(raw)
            if parsed is None:
                logger.error("llm.invalid_json", provider="anthropic", raw=raw[:200])
                raise ValueError(f"Anthropic returned invalid JSON: {raw[:200]}")
            logger.warning("llm.json_recovered", provider="anthropic", hash=request.question_hash[:8])

        from backend.llm.providers.openai_provider import extract_letter
        answer = extract_letter(str(parsed.get("answer", "A")))
        confidence = float(parsed.get("confidence", 0.5))
        reasoning = str(parsed.get("reasoning", ""))

        logger.info("llm.response",
                    provider="anthropic",
                    model=self._model,
                    hash=request.question_hash[:8],
                    answer=answer,
                    confidence=confidence,
                    latency_ms=latency_ms)

        return LLMResponse(
            question_hash=request.question_hash,
            answer=answer,
            confidence=confidence,
            reasoning=reasoning,
            model=self._model,
            provider="anthropic",
            prompt_version=version,
            latency_ms=latency_ms,
        )
