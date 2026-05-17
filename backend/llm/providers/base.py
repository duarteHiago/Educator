"""Abstract LLM provider — swap implementations without touching orchestrator."""
from abc import ABC, abstractmethod

from backend.schemas.quiz import LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a single question to the LLM and return a structured response."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...
