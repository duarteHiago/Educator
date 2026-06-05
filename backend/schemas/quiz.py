"""
Core data contracts for the quiz automation pipeline.
All components communicate exclusively through these schemas.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


# ── Question types ────────────────────────────────────────────────────────────

class QuestionType(str, Enum):
    MULTICHOICE = "multichoice"
    TRUEFALSE   = "truefalse"
    UNKNOWN     = "unknown"


class Alternative(BaseModel):
    id:         str   # "A", "B", "C", "D", ...
    text:       str   # Cleaned display text
    input_value: str  # Moodle radio value ("0", "1", "2", ...)
    input_name: str   # Moodle radio name  ("q12345:1_answer")
    input_id:   str   # HTML element id    ("q12345:1_answer0")


class QuizQuestion(BaseModel):
    slot:           int              # Moodle question slot (1-based)
    question_id:    str              # DOM id ("q1", "q2", ...)
    type:           QuestionType
    text:           str              # Clean text (HTML stripped)
    text_html:      str              # Raw HTML of question body
    alternatives:   list[Alternative]
    input_name:     str              # Shared radio group name
    page:           int = 0          # Which quiz page this question is on
    has_image:      bool = False     # True when question body contains <img>
    image_b64:      str | None = None  # Base64 screenshot of question area (filled by runner)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def question_hash(self) -> str:
        alts_fingerprint = "|".join(sorted(a.text for a in self.alternatives))
        content = f"{self.text.strip()}\n{alts_fingerprint}"
        return hashlib.sha256(content.encode()).hexdigest()


# ── Quiz attempt ──────────────────────────────────────────────────────────────

class QuizMeta(BaseModel):
    cmid:       int
    quiz_id:    int | None = None
    attempt_id: int | None = None
    course_id:  int
    title:      str
    total_pages: int = 1
    time_limit_seconds: int | None = None
    sesskey:    str | None = None


class ParsedQuiz(BaseModel):
    meta:           QuizMeta
    questions:      list[QuizQuestion]
    raw_html_pages: list[str] = Field(default_factory=list, exclude=True)
    parsed_at:      datetime  = Field(default_factory=datetime.utcnow)

    def question_by_slot(self, slot: int) -> QuizQuestion | None:
        return next((q for q in self.questions if q.slot == slot), None)


# ── LLM contracts ─────────────────────────────────────────────────────────────

class LLMRequest(BaseModel):
    question_hash:  str
    question_text:  str
    alternatives:   list[Alternative]
    model:          str
    provider:       str = "openai"
    prompt_version: str = "v1"
    image_b64:      str | None = None  # filled when question has an image


class LLMResponse(BaseModel):
    question_hash:  str
    answer:         str           # "A", "B", "C", "D"
    confidence:     float         # 0.0 – 1.0
    reasoning:      str
    model:          str
    provider:       str = "openai"
    prompt_version: str = "v1"
    from_cache:     bool = False
    latency_ms:     int  = 0


# ── Reviewed answers ──────────────────────────────────────────────────────────

class ReviewStatus(str, Enum):
    APPROVED  = "approved"
    OVERRIDDEN = "overridden"
    SKIPPED   = "skipped"
    PENDING   = "pending"


class ReviewedAnswer(BaseModel):
    slot:           int
    question_hash:  str
    llm_answer:     str
    final_answer:   str           # May differ if human overrode
    confidence:     float
    reasoning:      str
    status:         ReviewStatus = ReviewStatus.PENDING


# ── Submission ────────────────────────────────────────────────────────────────

class SubmissionStatus(str, Enum):
    SUCCESS    = "success"
    FAILED     = "failed"
    SKIPPED    = "skipped"
    DRY_RUN    = "dry_run"


class SubmissionResult(BaseModel):
    attempt_id:      int | None
    status:          SubmissionStatus
    score_raw:       float | None = None
    score_max:       float | None = None
    score_percent:   float | None = None
    grade_string:    str   | None = None
    submitted_at:    datetime = Field(default_factory=datetime.utcnow)
    error:           str | None = None


# ── Full execution artifact ───────────────────────────────────────────────────

class ExecutionArtifact(BaseModel):
    execution_id:   str
    mode:           str
    course_id:      int
    course_profile: str
    cmid:           int
    quiz:           ParsedQuiz | None      = None
    llm_responses:  list[LLMResponse]      = Field(default_factory=list)
    reviewed:       list[ReviewedAnswer]   = Field(default_factory=list)
    submission:     SubmissionResult | None = None
    started_at:     datetime = Field(default_factory=datetime.utcnow)
    finished_at:    datetime | None = None
