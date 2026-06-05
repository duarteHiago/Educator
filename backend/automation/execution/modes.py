"""
Execution modes and context.

DRY_RUN     — opens quiz, extracts, consults LLM, prints. No DOM interaction.
REVIEW_MODE — fills answers in DOM, waits for human approval. Never auto-submits.
AUTO_MODE   — fills and submits. Blocked on HIGH_VALUE courses.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from backend.automation.profiles.course_profiles import CourseProfile, get_profile, assert_submission_allowed


@dataclass
class UserRunContext:
    """Credenciais e paths isolados por usuário para execução cloud."""
    user_id:      str
    cpf:          str
    ava_password: str
    proxy_token:  str
    proxy_url:    str
    session_dir:  Path = field(default_factory=lambda: Path(f"/tmp/educator/sessions/default"))

    def __post_init__(self) -> None:
        self.session_dir = Path(f"/tmp/educator/sessions/{self.user_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_file(self) -> Path:
        return self.session_dir / "session.json"


class ExecutionMode(str, Enum):
    DRY_RUN     = "DRY_RUN"
    REVIEW_MODE = "REVIEW_MODE"
    AUTO_MODE   = "AUTO_MODE"


_FILL_ALLOWED    = {ExecutionMode.REVIEW_MODE, ExecutionMode.AUTO_MODE}
_SUBMIT_ALLOWED  = {ExecutionMode.AUTO_MODE}
_NAVIGATE_PAGES  = {ExecutionMode.DRY_RUN, ExecutionMode.REVIEW_MODE, ExecutionMode.AUTO_MODE}


@dataclass
class ExecutionContext:
    course_id:      int
    cmid:           int
    mode:           ExecutionMode
    execution_id:   str          = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at:     datetime     = field(default_factory=datetime.utcnow)
    force_submit:   bool         = False  # explicit human override for HIGH_VALUE

    @property
    def course_profile(self) -> CourseProfile:
        return get_profile(self.course_id)

    @property
    def artifact_dir(self) -> Path:
        base = Path("./logs/quizzes") / self.execution_id
        base.mkdir(parents=True, exist_ok=True)
        return base

    def can_fill_dom(self) -> bool:
        return self.mode in _FILL_ALLOWED

    def can_submit(self) -> bool:
        if self.mode not in _SUBMIT_ALLOWED:
            return False
        try:
            assert_submission_allowed(self.course_id, force=self.force_submit)
            return True
        except PermissionError:
            return False

    def assert_submit_safe(self) -> None:
        """Call before any submission. Raises if not allowed."""
        if self.mode not in _SUBMIT_ALLOWED:
            raise RuntimeError(f"Submission not allowed in mode {self.mode}.")
        assert_submission_allowed(self.course_id, force=self.force_submit)

    def summary(self) -> str:
        return (
            f"[{self.execution_id}] mode={self.mode.value} "
            f"course={self.course_id}({self.course_profile.value}) "
            f"cmid={self.cmid}"
        )
