"""
Activity schemas — discovered activities and per-handler results.
"""
from __future__ import annotations

import time
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ActivityType(str, Enum):
    QUIZ      = "quiz"
    MATERIAL  = "material"   # mod/page, mod/book, activityvideo — open = mark complete
    OPEN_ONLY = "open_only"  # mod/url, mod/pde, mod/lti — open AVA page = grade registered
    UNKNOWN   = "unknown"


class ActivityInfo(BaseModel):
    cmid:        int
    course_id:   int
    course_name: str
    mod:         str          # Moodle module string: "quiz", "url", "page", ...
    type:        ActivityType
    title:       str
    url:         str
    source:      str = ""     # discovery origin tag ("topic_114956", "direct", ...)
    completed:   bool = False # detectado pelo Moodle completion tracking no discovery
    grade_string: str | None = None  # nota como texto, quando disponível no discovery


class CourseInventory(BaseModel):
    course_id:     int
    course_name:   str
    activities:    list[ActivityInfo]
    discovered_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def quizzes(self) -> list[ActivityInfo]:
        return [a for a in self.activities if a.type == ActivityType.QUIZ]

    @property
    def materials(self) -> list[ActivityInfo]:
        return [a for a in self.activities if a.type == ActivityType.MATERIAL]

    @property
    def open_only(self) -> list[ActivityInfo]:
        return [a for a in self.activities if a.type == ActivityType.OPEN_ONLY]

    def by_type(self, *types: ActivityType) -> list[ActivityInfo]:
        return [a for a in self.activities if a.type in types]


class ActivityResult(BaseModel):
    cmid:       int
    course_id:  int
    type:       ActivityType
    title:      str
    success:    bool
    error:      str | None = None
    duration_s: float = 0.0
    extra:      dict = Field(default_factory=dict)
