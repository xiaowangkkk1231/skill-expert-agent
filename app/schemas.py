from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SignalType(StrEnum):
    PREFERENCE = "preference"   # 偏好
    CONSTRAINT = "constraint"   # 约束
    WORKFLOW = "workflow"       # 工作流
    EXAMPLE = "example"         # 示例


TYPE_LABEL = {
    SignalType.PREFERENCE: "偏好",
    SignalType.CONSTRAINT: "约束",
    SignalType.WORKFLOW: "工作流",
    SignalType.EXAMPLE: "示例",
}


def make_sid(quote: str, stype: str) -> str:
    """稳定 id：同一句话在任何版本里都有同一个 sid，这是合并的锚点。"""
    h = hashlib.sha1(f"{stype}|{quote.strip()}".encode("utf-8")).hexdigest()[:8]
    return f"s_{h}"


class Signal(BaseModel):
    sid: str
    text: str = Field(max_length=120)
    quote: str = Field(max_length=300)
    type: SignalType
    turn: int | None = None
    verified: bool = False

    @classmethod
    def build(cls, text: str, quote: str, stype: str, turn: int | None = None) -> "Signal":
        return cls(sid=make_sid(quote, stype), text=text, quote=quote,
                   type=SignalType(stype), turn=turn)


class Clusters(BaseModel):
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not any((self.preferences, self.constraints,
                        self.workflows, self.examples))

    def total(self) -> int:
        return (len(self.preferences) + len(self.constraints)
                + len(self.workflows) + len(self.examples))

    def buckets(self) -> dict[str, list[str]]:
        return {
            "preferences": self.preferences,
            "constraints": self.constraints,
            "workflows": self.workflows,
            "examples": self.examples,
        }


class Skill(BaseModel):
    name: str = Field(max_length=64)
    description: str = Field(max_length=1024)
    body: str


class Level(StrEnum):
    ERROR = "error"
    WARN = "warn"


class Issue(BaseModel):
    field: str
    rule: str
    level: Level
    message: str
    hint: str | None = None

    @property
    def icon(self) -> str:
        return "red" if self.level == Level.ERROR else "amber"


class LintReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def level(self) -> str:
        if any(i.level == Level.ERROR for i in self.issues):
            return "error"
        if self.issues:
            return "warn"
        return "ok"

    def by_field(self) -> dict[str, str]:
        out = {"name": "ok", "description": "ok", "body": "ok", "signals": "ok"}
        for i in self.issues:
            cur = out.get(i.field, "ok")
            if i.level == Level.ERROR or cur == "error":
                out[i.field] = "error"
            else:
                out[i.field] = "warn"
        return out


class DiffEntry(BaseModel):
    kind: str                     # added | modified | orphan
    text: str
    old: str | None = None
    sid: str | None = None


class RunRequest(BaseModel):
    conversation: str
    base_skill_id: str | None = None


class SaveRequest(BaseModel):
    create_new: bool = False


class RunView(BaseModel):
    id: str
    status: str
    stage: str | None = None
    provider: str = ""
    error: str | None = None
    version_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
