"""Provider factory — instantiates the right BaseLLMProvider by name."""
from __future__ import annotations

from backend.llm.providers.base import BaseLLMProvider


def build_provider(provider: str, model: str) -> BaseLLMProvider:
    if provider == "openai":
        from backend.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)
    if provider == "anthropic":
        from backend.llm.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)
    raise ValueError(f"Unknown provider: {provider!r}. Valid: openai, anthropic")
