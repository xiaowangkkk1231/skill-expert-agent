from __future__ import annotations

import re
from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import BASE_DIR
from app.schemas import Skill

_TPL_DIR = BASE_DIR / "app" / "templates" / "export"
env = Environment(
    loader=FileSystemLoader(str(_TPL_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class Exporter:
    key: str
    title: str
    filename: str
    template: str
    hint: str


EXPORTERS: dict[str, Exporter] = {
    "claude-code": Exporter(
        key="claude-code",
        title="给 Claude Code",
        filename="SKILL.md",
        template="claude_skill.md.j2",
        hint="放到 ~/.claude/skills/{name}/SKILL.md",
    ),
    "chatgpt": Exporter(
        key="chatgpt",
        title="给 ChatGPT",
        filename="custom-instructions.md",
        template="chatgpt_ci.md.j2",
        hint="贴到 Settings → Personalization → Custom Instructions",
    ),
    "memory": Exporter(
        key="memory",
        title="通用轻量版",
        filename="memory-short.txt",
        template="short_memory.txt.j2",
        hint="贴在任何对话开头，让 AI 立即遵守",
    ),
}

BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")


def key_points(body: str, limit: int = 5) -> list[str]:
    points: list[str] = []
    for line in body.splitlines():
        m = BULLET_RE.match(line)
        if m:
            points.append(m.group(1).strip())
        if len(points) >= limit:
            break
    if not points:
        stripped = body.strip()
        points = [stripped[:200] + ("…" if len(stripped) > 200 else "")]
    return points


def render(key: str, skill: Skill) -> str:
    exporter = EXPORTERS[key]
    tpl = env.get_template(exporter.template)
    return tpl.render(s=skill, points=key_points(skill.body))


def download_name(key: str, skill: Skill) -> str:
    exporter = EXPORTERS[key]
    if exporter.filename == "SKILL.md":
        return f"{skill.name}-SKILL.md"
    return exporter.filename
