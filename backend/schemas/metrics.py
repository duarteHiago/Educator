"""
Metrics schemas — per-quiz and aggregate execution reporting.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QuizMetrics(BaseModel):
    execution_id:      str
    cmid:              int
    course_id:         int
    course_profile:    str
    title:             str
    mode:              str
    total_questions:   int
    parsed_questions:  int
    cache_hits:        int
    cache_rate:        float          # cache_hits / total_questions
    avg_confidence:    float | None
    score_raw:         float | None
    score_max:         float | None
    score_percent:     float | None
    grade_string:      str | None
    execution_time_s:  float
    status:            str            # "success" | "failed" | "dry_run" | ...
    llm_model:         str | None
    error:             str | None = None
    evaluated_at:      datetime = Field(default_factory=datetime.utcnow)


class BatchMetrics(BaseModel):
    total_quizzes:      int = 0
    successful:         int = 0
    failed:             int = 0
    skipped:            int = 0
    avg_score_percent:  float | None = None
    avg_cache_rate:     float | None = None
    avg_confidence:     float | None = None
    avg_execution_time: float | None = None
    quiz_metrics:       list[QuizMetrics] = Field(default_factory=list)
    generated_at:       datetime = Field(default_factory=datetime.utcnow)
