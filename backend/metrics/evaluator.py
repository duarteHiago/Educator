"""
QuizEvaluator — derives QuizMetrics from a single ExecutionArtifact.

Can be called:
  - in-process after run_quiz() returns
  - offline from a manifest.json file (replay / reporting)
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from backend.schemas.metrics import QuizMetrics
from backend.schemas.quiz import ExecutionArtifact


class QuizEvaluator:

    def from_artifact(self, artifact: ExecutionArtifact) -> QuizMetrics:
        quiz = artifact.quiz
        sub  = artifact.submission

        total_q  = len(quiz.questions) if quiz else 0
        responses = artifact.llm_responses

        cache_hits = sum(1 for r in responses if r.from_cache)
        cache_rate = cache_hits / total_q if total_q else 0.0

        confidences = [r.confidence for r in responses]
        avg_conf    = round(mean(confidences), 3) if confidences else None

        exec_time = 0.0
        if artifact.started_at and artifact.finished_at:
            exec_time = (artifact.finished_at - artifact.started_at).total_seconds()

        llm_model = responses[0].model if responses else None

        return QuizMetrics(
            execution_id     = artifact.execution_id,
            cmid             = artifact.cmid,
            course_id        = artifact.course_id,
            course_profile   = artifact.course_profile,
            title            = quiz.meta.title if quiz else "",
            mode             = artifact.mode,
            total_questions  = total_q,
            parsed_questions = total_q,
            cache_hits       = cache_hits,
            cache_rate       = round(cache_rate, 3),
            avg_confidence   = avg_conf,
            score_raw        = sub.score_raw if sub else None,
            score_max        = sub.score_max if sub else None,
            score_percent    = sub.score_percent if sub else None,
            grade_string     = sub.grade_string if sub else None,
            execution_time_s = round(exec_time, 1),
            status           = sub.status.value if sub else "unknown",
            llm_model        = llm_model,
            error            = sub.error if sub else None,
        )

    def from_manifest(self, manifest_path: Path) -> QuizMetrics:
        data     = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = ExecutionArtifact.model_validate(data)
        return self.from_artifact(artifact)
