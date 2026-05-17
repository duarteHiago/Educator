"""
Course classification and execution guard.

SAFE_TEST  — allowed for all operations including auto-submit.
HIGH_VALUE — read-only by default; auto-submit requires explicit override.

Any new course_id defaults to HIGH_VALUE (fail-safe).
"""
from enum import Enum


class CourseProfile(str, Enum):
    SAFE_TEST  = "SAFE_TEST"
    HIGH_VALUE = "HIGH_VALUE"


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[int, CourseProfile] = {
    # SAFE_TEST — use for all parser/LLM/submission testing
    7136: CourseProfile.SAFE_TEST,   # Ciências Biológicas
    7137: CourseProfile.SAFE_TEST,   # Matemática
    7138: CourseProfile.SAFE_TEST,   # Português
    8339: CourseProfile.SAFE_TEST,   # Competências para a Vida
    8950: CourseProfile.SAFE_TEST,   # Projeto de Extensão II
    816:  CourseProfile.SAFE_TEST,   # Processo Seletivo

    # HIGH_VALUE — quizzes with real grade impact
    10180: CourseProfile.HIGH_VALUE,  # Algoritmos e Estrutura de Dados Avançado
    11074: CourseProfile.HIGH_VALUE,  # Segurança da Informação e de Redes
    10457: CourseProfile.HIGH_VALUE,  # Sistemas Digitais e Microprocessadores
    10741: CourseProfile.HIGH_VALUE,  # Desenvolvimento com Low Code
    5008:  CourseProfile.HIGH_VALUE,  # Projeto de Software
    11208: CourseProfile.HIGH_VALUE,  # Acelere sua Carreira
}


def get_profile(course_id: int) -> CourseProfile:
    """Returns profile for course_id. Unknown courses default to HIGH_VALUE."""
    return _REGISTRY.get(course_id, CourseProfile.HIGH_VALUE)


def is_safe(course_id: int) -> bool:
    return get_profile(course_id) == CourseProfile.SAFE_TEST


def is_high_value(course_id: int) -> bool:
    return get_profile(course_id) == CourseProfile.HIGH_VALUE


def assert_submission_allowed(course_id: int, force: bool = False) -> None:
    """
    Raises PermissionError if submission is not allowed for this course profile.
    Pass force=True only after explicit human confirmation.
    """
    if is_high_value(course_id) and not force:
        raise PermissionError(
            f"Course {course_id} is HIGH_VALUE. "
            "Auto-submit is blocked. Use DRY_RUN or REVIEW_MODE, "
            "or pass force=True after explicit human confirmation."
        )
