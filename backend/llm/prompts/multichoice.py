"""
Deterministic prompt templates for multichoice questions.
No conversational tone. Structured JSON output enforced.
"""
from __future__ import annotations
from backend.schemas.quiz import QuizQuestion

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "Você é um assistente acadêmico especializado em questões universitárias brasileiras.\n"
    "Sua única função é analisar questões de múltipla escolha e responder em JSON válido.\n"
    "Não adicione texto fora do JSON. Não explique fora do JSON."
)

_JSON_FORMAT = (
    '{\n'
    '  "answer": "<letra>",\n'
    '  "confidence": <número entre 0.0 e 1.0>,\n'
    '  "reasoning": "<explicação em uma frase>"\n'
    '}'
)


def _build(question_text: str, alts_block: str) -> str:
    return (
        f"Questão:\n{question_text}\n\n"
        f"Alternativas:\n{alts_block}\n\n"
        f"Responda APENAS com JSON válido no seguinte formato:\n{_JSON_FORMAT}"
    )


def build_user_prompt(question: QuizQuestion) -> str:
    alts = "\n".join(f"{a.id}) {a.text}" for a in question.alternatives)
    return _build(question.text, alts)


def build_user_prompt_from_request(request) -> str:
    alts = "\n".join(f"{a.id}) {a.text}" for a in request.alternatives)
    return _build(request.question_text, alts)


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer":     {"type": "string", "enum": ["A", "B", "C", "D", "E", "F"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning":  {"type": "string"},
    },
    "required": ["answer", "confidence", "reasoning"],
    "additionalProperties": False,
}
