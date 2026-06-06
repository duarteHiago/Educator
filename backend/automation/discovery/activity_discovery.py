"""
ActivityDiscovery — loads, classifies, and filters the activity inventory.

Primary source: logs/activity_map.json (produced by discover_quiz_cmids.py).
Live scraping is a future concern; for now everything goes through the cached map.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.automation.profiles.course_profiles import CourseProfile, get_profile
from backend.core.logging import get_logger
from backend.schemas.activity import ActivityInfo, ActivityType, CourseInventory

logger = get_logger(__name__)

DEFAULT_MAP = Path("logs/activity_map.json")

# Map Moodle module strings → ActivityType
_MOD_TYPE: dict[str, ActivityType] = {
    "quiz":          ActivityType.QUIZ,
    "page":          ActivityType.MATERIAL,
    "book":          ActivityType.MATERIAL,
    "resource":      ActivityType.MATERIAL,
    "activityvideo": ActivityType.MATERIAL,
    "url":           ActivityType.OPEN_ONLY,
    "pde":           ActivityType.OPEN_ONLY,
    "lti":           ActivityType.OPEN_ONLY,
}

# Map explicit category strings (from discovery script) → ActivityType
_CAT_TYPE: dict[str, ActivityType] = {
    "quiz":      ActivityType.QUIZ,
    "material":  ActivityType.MATERIAL,
    "open_only": ActivityType.OPEN_ONLY,
}


class ActivityDiscovery:
    """
    Loads the activity map and provides typed, filtered views over it.
    Call .load() before any query methods.
    """

    def __init__(self, map_path: Path = DEFAULT_MAP) -> None:
        self._path = map_path
        self._raw:  list[dict] = []
        self._loaded = False

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self) -> "ActivityDiscovery":
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._raw    = data
        self._loaded = True
        logger.info("discovery.loaded", path=str(self._path), total=len(data))
        return self

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("Call ActivityDiscovery.load() before querying.")

    # ── Conversion ────────────────────────────────────────────────────────────

    def _to_activity(self, raw: dict) -> ActivityInfo:
        mod = raw.get("mod", "unknown")
        cat = raw.get("category", "")

        atype = (
            _CAT_TYPE.get(cat)
            or _MOD_TYPE.get(mod)
            or ActivityType.UNKNOWN
        )

        url = raw.get(
            "url",
            f"https://www.avaeduc.com.br/mod/{mod}/view.php?id={raw['cmid']}",
        )

        return ActivityInfo(
            cmid=raw["cmid"],
            course_id=raw["course_id"],
            course_name=raw.get("course_name", ""),
            mod=mod,
            type=atype,
            title=raw.get("title", ""),
            url=url,
            source=raw.get("source", ""),
            completed=raw.get("completed", False),
            grade_string=raw.get("grade_string"),
        )

    # ── Query API ─────────────────────────────────────────────────────────────

    def all_activities(self) -> list[ActivityInfo]:
        self._ensure_loaded()
        return [self._to_activity(r) for r in self._raw]

    def for_course(self, course_id: int) -> CourseInventory:
        self._ensure_loaded()
        activities = [
            self._to_activity(r)
            for r in self._raw
            if r["course_id"] == course_id
        ]
        name = activities[0].course_name if activities else str(course_id)
        return CourseInventory(
            course_id=course_id,
            course_name=name,
            activities=activities,
        )

    def all_courses(self) -> list[int]:
        self._ensure_loaded()
        seen: list[int] = []
        for r in self._raw:
            cid = r["course_id"]
            if cid not in seen:
                seen.append(cid)
        return seen

    def safe_test_quizzes(self) -> list[ActivityInfo]:
        self._ensure_loaded()
        return [
            self._to_activity(r)
            for r in self._raw
            if r.get("category") == "quiz"
            and get_profile(r["course_id"]) == CourseProfile.SAFE_TEST
        ]

    def high_value_quizzes(self) -> list[ActivityInfo]:
        self._ensure_loaded()
        return [
            self._to_activity(r)
            for r in self._raw
            if r.get("category") == "quiz"
            and get_profile(r["course_id"]) == CourseProfile.HIGH_VALUE
        ]

    def quizzes_for_course(self, course_id: int) -> list[ActivityInfo]:
        self._ensure_loaded()
        return [
            self._to_activity(r)
            for r in self._raw
            if r["course_id"] == course_id and r.get("category") == "quiz"
        ]

    def materials_for_course(self, course_id: int) -> list[ActivityInfo]:
        self._ensure_loaded()
        return [
            self._to_activity(r)
            for r in self._raw
            if r["course_id"] == course_id
            and r.get("category") in ("material", "open_only")
        ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        self._ensure_loaded()
        from collections import Counter
        cats = Counter(r.get("category", "unknown") for r in self._raw)
        return {
            "total": len(self._raw),
            "by_category": dict(cats),
            "courses": len(self.all_courses()),
        }
