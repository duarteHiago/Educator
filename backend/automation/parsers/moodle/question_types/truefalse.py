"""
Parser for Moodle True/False questions.

Moodle truefalse questions share the same HTML structure as multichoice
but use class `que truefalse` and always have exactly 2 radio alternatives
("Verdadeiro"/"Falso" or "True"/"False").
"""
from bs4 import Tag

from backend.automation.parsers.moodle import selectors as sel
from backend.automation.parsers.moodle.question_types.multichoice import parse as parse_multichoice
from backend.schemas.quiz import QuizQuestion, QuestionType


def parse(container: Tag, slot: int, page: int = 0) -> QuizQuestion | None:
    """
    Parse a truefalse question. Delegates to multichoice parser (same DOM structure)
    then overrides the type field.
    """
    q = parse_multichoice(container, slot=slot, page=page)
    if q is None:
        return None
    return q.model_copy(update={"type": QuestionType.TRUEFALSE})
