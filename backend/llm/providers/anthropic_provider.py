"""
Anthropic provider — Claude models via anthropic SDK (direto) ou via proxy LiteLLM.

Modo direto (dev): usa anthropic.AsyncAnthropic com anthropic_api_key.
Modo proxy (.exe): usa AsyncOpenAI apontando para a VPS — LiteLLM é OpenAI-compatible
                   e roteia pelo nome do modelo para a Anthropic internamente.
"""
from __future__ import annotations

import json
import re
import time

import anthropic
from openai import AsyncOpenAI

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

        if settings.proxy_url:
            # Proxy mode: LiteLLM recebe o nome do modelo e roteia para Anthropic
            self._proxy_client = AsyncOpenAI(
                api_key=settings.proxy_token,
                base_url=settings.proxy_url,
            )
            self._native_client = None
        else:
            # Modo direto: SDK nativo da Anthropic
            self._proxy_client = None
            self._native_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._proxy_client is not None:
            return await self._complete_via_proxy(request)
        return await self._complete_native(request)

    async def _complete_via_proxy(self, request: LLMRequest) -> LLMResponse:
        """Proxy mode: chama LiteLLM via interface OpenAI-compatible."""
        from backend.llm.providers.openai_provider import _recover_partial_json, extract_letter

        version = request.prompt_version
        system_prompt = prompts.get_system_prompt(version)
        user_prompt = prompts.build_user_prompt_from_request(request, version)
        t0 = time.monotonic()

        logger.debug("llm.request",
                     provider="anthropic/proxy",
                     model=self._model,
                     version=version,
                     hash=request.question_hash[:8])

        response = await self._proxy_client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1024,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = response.choices[0].message.content or "{}"

        match = _JSON_RE.search(raw)
        raw_json = match.group(0) if match else raw

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = _recover_partial_json(raw)
            if parsed is None:
                logger.error("llm.invalid_json", provider="anthropic/proxy", raw=raw[:200])
                raise ValueError(f"Anthropic via proxy returned invalid JSON: {raw[:200]}")
            logger.warning("llm.json_recovered", provider="anthropic/proxy", hash=request.question_hash[:8])

        answer     = extract_letter(str(parsed.get("answer", "A")))
        confidence = float(parsed.get("confidence", 0.5))
        reasoning  = str(parsed.get("reasoning", ""))

        logger.info("llm.response",
                    provider="anthropic/proxy",
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

    async def _complete_native(self, request: LLMRequest) -> LLMResponse:
        """Modo direto: SDK nativo da Anthropic (uso local/dev)."""
        from backend.llm.providers.openai_provider import _recover_partial_json, extract_letter

        version = request.prompt_version
        system_prompt = prompts.get_system_prompt(version)
        user_prompt = prompts.build_user_prompt_from_request(request, version)
        t0 = time.monotonic()

        logger.debug("llm.request",
                     provider="anthropic",
                     model=self._model,
                     version=version,
                     hash=request.question_hash[:8])

        message = await self._native_client.messages.create(
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
            parsed = _recover_partial_json(raw)
            if parsed is None:
                logger.error("llm.invalid_json", provider="anthropic", raw=raw[:200])
                raise ValueError(f"Anthropic returned invalid JSON: {raw[:200]}")
            logger.warning("llm.json_recovered", provider="anthropic", hash=request.question_hash[:8])

        answer     = extract_letter(str(parsed.get("answer", "A")))
        confidence = float(parsed.get("confidence", 0.5))
        reasoning  = str(parsed.get("reasoning", ""))

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
