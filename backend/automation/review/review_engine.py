"""
Human Review Engine — terminal-based review before submission.

Displays each question with LLM answer + reasoning.
Human can: confirm (Enter/y), override (type a letter), or skip (s).
"""
import asyncio

from backend.core.logging import get_logger
from backend.schemas.quiz import (
    LLMResponse, ParsedQuiz, ReviewedAnswer, ReviewStatus,
)

logger = get_logger(__name__)


def _print_divider():
    print("\n" + "=" * 65)


def _print_question(question, resp: LLMResponse, idx: int, total: int) -> None:
    _print_divider()
    print(f"QUESTAO {idx}/{total}  [slot={question.slot}]")
    print(f"Tipo: {question.type.value}")
    print(f"\nEnunciado:\n{question.text[:500]}")
    print("\nAlternativas:")
    for alt in question.alternatives:
        marker = " <-- IA" if alt.id == resp.answer else ""
        print(f"  {alt.id}) {alt.text[:120]}{marker}")
    print(f"\nResposta IA:   {resp.answer}")
    print(f"Confiança:     {resp.confidence:.0%}")
    print(f"Raciocínio:    {resp.reasoning}")
    if resp.from_cache:
        print("(resposta do cache)")


def _prompt_user(valid_letters: list[str]) -> tuple[str, ReviewStatus]:
    options = "/".join(valid_letters)
    print(f"\n[Enter/y = confirmar | {options} = substituir | s = pular]: ", end="", flush=True)
    raw = input().strip().upper()

    if raw in ("", "Y"):
        return "", ReviewStatus.APPROVED
    if raw == "S":
        return "", ReviewStatus.SKIPPED
    if raw in valid_letters:
        return raw, ReviewStatus.OVERRIDDEN
    print(f"Entrada inválida '{raw}'. Confirmando a resposta da IA.")
    return "", ReviewStatus.APPROVED


async def review_quiz(
    quiz: ParsedQuiz,
    llm_responses: list[LLMResponse],
    run_in_executor: bool = True,
) -> list[ReviewedAnswer]:
    """
    Present each question to the human reviewer.
    Returns list of ReviewedAnswer in slot order.
    """
    response_map = {r.question_hash: r for r in llm_responses}
    reviewed: list[ReviewedAnswer] = []
    total = len(quiz.questions)

    print("\n" + "=" * 65)
    print("MODO DE REVISAO HUMANA")
    print(f"Quiz: {quiz.meta.title}")
    print(f"Total de questões: {total}")
    print("=" * 65)

    for idx, question in enumerate(quiz.questions, start=1):
        resp = response_map.get(question.question_hash)
        if not resp:
            logger.warning("review.no_llm_response", slot=question.slot)
            reviewed.append(ReviewedAnswer(
                slot          = question.slot,
                question_hash = question.question_hash,
                llm_answer    = "?",
                final_answer  = "?",
                confidence    = 0.0,
                reasoning     = "LLM response missing",
                status        = ReviewStatus.SKIPPED,
            ))
            continue

        _print_question(question, resp, idx, total)

        valid_letters = [a.id for a in question.alternatives]

        if run_in_executor:
            loop = asyncio.get_event_loop()
            override, status = await loop.run_in_executor(
                None, _prompt_user, valid_letters
            )
        else:
            override, status = _prompt_user(valid_letters)

        final_answer = override if override else resp.answer

        if status == ReviewStatus.OVERRIDDEN:
            print(f"Substituído: {resp.answer} → {final_answer}")
        elif status == ReviewStatus.SKIPPED:
            print("Questão ignorada.")
        else:
            print(f"Confirmado: {final_answer}")

        reviewed.append(ReviewedAnswer(
            slot          = question.slot,
            question_hash = question.question_hash,
            llm_answer    = resp.answer,
            final_answer  = final_answer,
            confidence    = resp.confidence,
            reasoning     = resp.reasoning,
            status        = status,
        ))

    _print_divider()
    approved  = sum(1 for r in reviewed if r.status == ReviewStatus.APPROVED)
    overridden = sum(1 for r in reviewed if r.status == ReviewStatus.OVERRIDDEN)
    skipped   = sum(1 for r in reviewed if r.status == ReviewStatus.SKIPPED)
    print(f"REVISAO CONCLUIDA: {approved} confirmadas | {overridden} substituídas | {skipped} ignoradas")

    logger.info("review.complete",
                approved=approved, overridden=overridden, skipped=skipped)
    return reviewed
