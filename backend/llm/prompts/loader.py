"""
Prompt loader — reads versioned .md files and fills placeholders.
Format: sections ## SYSTEM and ## USER separated in the .md file.
Placeholders: {question_text}, {alternatives} — replaced via str.replace().
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_VERSIONS_DIR = Path(__file__).parent / "versions"


@lru_cache(maxsize=8)
def _load_raw(version: str) -> tuple[str, str]:
    """Returns (system_prompt, user_template) for a given version slug."""
    path = _VERSIONS_DIR / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt version not found: {path}")

    text = path.read_text(encoding="utf-8")

    system_part = ""
    user_part = ""

    if "## USER" in text:
        parts = text.split("## USER", 1)
        system_raw = parts[0]
        user_part = parts[1].strip()
    else:
        system_raw = text
        user_part = ""

    if "## SYSTEM" in system_raw:
        system_part = system_raw.split("## SYSTEM", 1)[1].strip()
    else:
        system_part = system_raw.strip()

    return system_part, user_part


def get_system_prompt(version: str = "v1", persona: str = "") -> str:
    base = _load_raw(version)[0]
    if not persona:
        return base
    # Replace the generic "Você é..." intro with the subject-specific persona
    lines = base.split("\n")
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if not replaced and line.startswith("Você é"):
            new_lines.append(persona)
            replaced = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines)


def build_user_prompt(version: str, question_text: str, alternatives: list) -> str:
    _, template = _load_raw(version)
    alts_block = "\n".join(f"{a.id}) {a.text}" for a in alternatives)
    return (
        template
        .replace("{question_text}", question_text)
        .replace("{alternatives}", alts_block)
    )


def build_user_prompt_from_request(request, version: str | None = None) -> str:
    v = version or getattr(request, "prompt_version", "v1")
    return build_user_prompt(v, request.question_text, request.alternatives)


def list_versions() -> list[str]:
    return sorted(p.stem for p in _VERSIONS_DIR.glob("*.md"))
