"""
Parser for Moodle multichoice questions.

Input:  BeautifulSoup Tag — the outer `.que.multichoice` div.
Output: QuizQuestion Pydantic model.
"""
import re
from bs4 import Tag

from backend.automation.parsers.moodle import selectors as sel
from backend.schemas.quiz import Alternative, QuizQuestion, QuestionType

_LETTER_MAP = "ABCDEFGHIJ"


def _first_text(tag: Tag, selectors: tuple[str, ...]) -> str:
    for s in selectors:
        el = tag.select_one(s)
        if el:
            return el.get_text(" ", strip=True)
    return tag.get_text(" ", strip=True)


def _first_html(tag: Tag, selectors: tuple[str, ...]) -> str:
    for s in selectors:
        el = tag.select_one(s)
        if el:
            return str(el)
    return str(tag)


def parse(container: Tag, slot: int, page: int = 0) -> QuizQuestion | None:
    """
    Parse a single multichoice question container.
    Returns None if the question structure cannot be identified.
    """
    # ── Question text ─────────────────────────────────────────────────────────
    q_text = _first_text(container, sel.QUESTION_TEXT)
    q_html = _first_html(container, sel.QUESTION_TEXT)

    if not q_text.strip():
        return None

    # ── DOM id ────────────────────────────────────────────────────────────────
    dom_id = container.get("id", f"q{slot}")

    # ── Radio buttons → alternatives ─────────────────────────────────────────
    alternatives: list[Alternative] = []
    rows = []
    for s in sel.ANSWER_ROW:
        rows = container.select(s)
        if rows:
            break

    shared_name = ""
    for i, row in enumerate(rows):
        radio = row.select_one(sel.RADIO_INPUT)
        label = row.select_one(sel.RADIO_LABEL)
        if not radio or not label:
            continue

        input_name  = radio.get("name", "")
        input_value = radio.get("value", str(i))
        input_id    = radio.get("id", "")
        label_text  = label.get_text(" ", strip=True)

        # Strip out trailing label artefacts like "(a)" from Moodle feedback
        label_text = re.sub(r"\s*\([a-z]\)\s*$", "", label_text, flags=re.IGNORECASE).strip()

        if not shared_name and input_name:
            shared_name = input_name

        alternatives.append(Alternative(
            id           = _LETTER_MAP[i] if i < len(_LETTER_MAP) else str(i),
            text         = label_text,
            input_value  = input_value,
            input_name   = input_name,
            input_id     = input_id,
        ))

    if not alternatives:
        return None

    return QuizQuestion(
        slot         = slot,
        question_id  = dom_id,
        type         = QuestionType.MULTICHOICE,
        text         = q_text,
        text_html    = q_html,
        alternatives = alternatives,
        input_name   = shared_name,
        page         = page,
    )
