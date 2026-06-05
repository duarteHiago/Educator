"""
Moodle Quiz Parser — HTML string → ParsedQuiz.

Completely decoupled from Playwright. Receives raw HTML and produces
a structured ParsedQuiz. Works identically for live browser and replay.
"""
import re
from bs4 import BeautifulSoup, Tag

from backend.automation.parsers.moodle import selectors as sel
from backend.automation.parsers.moodle.question_types import multichoice, truefalse
from backend.core.logging import get_logger
from backend.schemas.quiz import ParsedQuiz, QuizMeta, QuestionType

logger = get_logger(__name__)


def _extract_hidden(soup: BeautifulSoup, css: str) -> str:
    el = soup.select_one(css)
    return el["value"] if el and el.get("value") else ""


def _extract_int(soup: BeautifulSoup, css: str) -> int | None:
    val = _extract_hidden(soup, css)
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _extract_title(soup: BeautifulSoup) -> str:
    for s in sel.QUIZ_TITLE.split(", "):
        el = soup.select_one(s.strip())
        if el:
            return el.get_text(" ", strip=True)
    return "Unknown Quiz"


def parse_attempt_page(
    html: str,
    meta: QuizMeta,
    page: int = 0,
    slot_offset: int = 0,
) -> tuple[list, str | None]:
    """
    Parse one attempt page.
    Returns (questions_on_page, next_page_value).

    slot_offset: number of questions already parsed (for multi-page quizzes).
    """
    soup = BeautifulSoup(html, "html.parser")
    questions = []
    slot = slot_offset + 1

    # Identify question containers
    containers: list[Tag] = []
    for s in sel.QUESTION_CONTAINER:
        containers = soup.select(s)
        if containers:
            break

    logger.debug("parser.containers_found", count=len(containers), page=page)

    for container in containers:
        q_type_class = " ".join(container.get("class", []))

        if "multichoice" in q_type_class:
            q = multichoice.parse(container, slot=slot, page=page)
        elif "truefalse" in q_type_class:
            q = truefalse.parse(container, slot=slot, page=page)
        else:
            logger.debug("parser.question_skipped",
                         classes=q_type_class, slot=slot)
            slot += 1
            continue

        if q:
            # Detect image questions — flag them so the runner can capture a screenshot
            if container.select_one("img"):
                q = q.model_copy(update={"has_image": True})
            questions.append(q)
            logger.debug("parser.question_parsed",
                         slot=slot, type=q.type,
                         has_image=q.has_image,
                         text_preview=q.text[:60])
        slot += 1

    # Determine next page
    next_page_el = soup.select_one(sel.HIDDEN_NEXT_PAGE)
    next_page = next_page_el["value"] if next_page_el else None

    return questions, next_page


def parse_quiz_pages(
    html_pages: list[str],
    meta: QuizMeta,
) -> ParsedQuiz:
    """
    Parse all HTML pages of a quiz attempt into a single ParsedQuiz.
    """
    all_questions = []
    slot_offset   = 0

    for page_num, html in enumerate(html_pages):
        qs, _ = parse_attempt_page(html, meta, page=page_num, slot_offset=slot_offset)
        all_questions.extend(qs)
        slot_offset = len(all_questions)
        logger.info("parser.page_parsed",
                    page=page_num, questions_on_page=len(qs), total=len(all_questions))

    multichoice_count = sum(1 for q in all_questions if q.type == QuestionType.MULTICHOICE)
    logger.info("parser.quiz_parsed",
                cmid=meta.cmid,
                total_questions=len(all_questions),
                multichoice=multichoice_count)

    quiz = ParsedQuiz(
        meta=meta,
        questions=all_questions,
        raw_html_pages=html_pages,
    )
    return quiz


def extract_meta_from_html(html: str, cmid: int, course_id: int) -> QuizMeta:
    """Extract quiz metadata from the view or attempt page HTML."""
    soup  = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)
    aid   = _extract_int(soup, sel.HIDDEN_ATTEMPT_ID)
    sk    = _extract_hidden(soup, sel.HIDDEN_SESSKEY)

    return QuizMeta(
        cmid       = cmid,
        course_id  = course_id,
        attempt_id = aid,
        title      = title,
        sesskey    = sk or None,
    )
