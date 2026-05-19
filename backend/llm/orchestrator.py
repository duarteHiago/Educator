"""
LLM Orchestrator — reads active config from EvolutionEngine, routes questions.

Flow per question:
  1. Check cache by question_hash
  2. Cache hit  → return cached LLMResponse
  3. Cache miss → call primary provider (from active config)
  4. If confidence < threshold → call fallback provider (next model in chain)
  5. Store result in cache
  6. Return LLMResponse

After quiz submission, call record_result() so the engine can evaluate and evolve.
"""
from __future__ import annotations

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.llm import cache as question_cache
from backend.llm.performance.evolution_engine import EvolutionAction, EvolutionEngine
from backend.llm.providers.base import BaseLLMProvider
from backend.llm.providers.factory import build_provider
from backend.schemas.quiz import LLMRequest, LLMResponse, ParsedQuiz, QuizQuestion

logger = get_logger(__name__)

_CONFIDENCE_THRESHOLD = settings.llm_confidence_threshold


class LLMOrchestrator:
    def __init__(self, engine: EvolutionEngine | None = None) -> None:
        self._engine = engine or EvolutionEngine()
        cfg = self._engine.active_config

        self._primary: BaseLLMProvider = build_provider(cfg.provider, cfg.model)
        self._prompt_version: str = cfg.prompt_version

        # Confidence fallback: one step up in the chain from current
        self._fallback: BaseLLMProvider = self._build_fallback(cfg.provider, cfg.model)

        logger.info(
            "llm.orchestrator_ready",
            provider=cfg.provider,
            model=cfg.model,
            prompt_version=cfg.prompt_version,
            fallback=self._fallback.model_name,
        )

    def _build_fallback(self, provider: str, model: str) -> BaseLLMProvider:
        """Returns one step up from current model — openai/gpt-4o as universal fallback."""
        from backend.llm.performance.evolution_engine import _MODEL_CHAIN
        idx = next(
            (i for i, (p, m) in enumerate(_MODEL_CHAIN) if p == provider and m == model),
            -1,
        )
        if idx >= 0 and idx < len(_MODEL_CHAIN) - 1:
            fp, fm = _MODEL_CHAIN[idx + 1]
            return build_provider(fp, fm)
        return build_provider(provider, model)  # same if already at top

    async def answer_question(self, question: QuizQuestion) -> LLMResponse:
        cached = question_cache.get(question.question_hash, model=self._primary.model_name)
        if cached:
            return cached

        req = LLMRequest(
            question_hash  = question.question_hash,
            question_text  = question.text,
            alternatives   = question.alternatives,
            model          = self._primary.model_name,
            provider       = self._primary.provider_name,
            prompt_version = self._prompt_version,
        )

        resp = await self._primary.complete(req)

        if resp.confidence < _CONFIDENCE_THRESHOLD:
            logger.info(
                "llm.low_confidence_escalating",
                hash=question.question_hash[:8],
                confidence=resp.confidence,
                fallback=self._fallback.model_name,
            )
            cached_fb = question_cache.get(question.question_hash, model=self._fallback.model_name)
            if cached_fb:
                return cached_fb
            req_fb = req.model_copy(update={
                "model":    self._fallback.model_name,
                "provider": self._fallback.provider_name,
            })
            resp = await self._fallback.complete(req_fb)

        question_cache.put(resp)
        return resp

    async def answer_quiz(self, quiz: ParsedQuiz) -> list[LLMResponse]:
        """Process all questions in a parsed quiz. Returns responses in slot order."""
        responses: list[LLMResponse] = []

        for question in quiz.questions:
            logger.info(
                "llm.processing_question",
                slot=question.slot,
                type=question.type.value,
                text_preview=question.text[:60],
            )
            resp = await self.answer_question(question)
            responses.append(resp)

        logger.info(
            "llm.quiz_complete",
            total=len(responses),
            from_cache=sum(1 for r in responses if r.from_cache),
        )
        return responses

    def record_result(self, cmid: int, score_percent: float) -> EvolutionAction | None:
        """
        Call after quiz submission with the real grade.
        Returns an EvolutionAction if the engine decided to switch config, else None.
        """
        action = self._engine.record_and_evaluate(cmid=cmid, score_percent=score_percent)
        if action and action.triggered:
            logger.warning(
                "llm.orchestrator.evolution_triggered",
                old=f"{action.old_config.provider}/{action.old_config.model}@{action.old_config.prompt_version}",
                new=f"{action.new_config.provider}/{action.new_config.model}@{action.new_config.prompt_version}",
                reason=action.reason,
            )
        return action
