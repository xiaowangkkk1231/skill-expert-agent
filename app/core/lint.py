from __future__ import annotations

import re

from app.core.similarity import normalize_key, similarity
from app.schemas import Issue, Level, LintReport, Signal, Skill

RESERVED = {"anthropic", "claude", "openai", "skill", "agent"}
NAME_RE = re.compile(r"^[a-z0-9-]+$")
WHEN_RE = re.compile(
    r"when|use when|when to|适用|用于|何时|场景|trigger|触发|用来|当", re.I
)
H1_RE = re.compile(r"^#\s+\S", re.M)

NEG_RE = re.compile(r"(不要|禁止|别|不能|不准|不允许|严禁|避免)(.{2,30})")
POS_RE = re.compile(r"(必须|一律|统一|要用|只用|只能|务必)(.{2,30})")


def _conflict(neg_text: str, pos_text: str) -> bool:
    """neg_text 说"不要 X"，pos_text 说"必须 X" —— X 相似则互斥。"""
    n, p = NEG_RE.search(neg_text), POS_RE.search(pos_text)
    if not (n and p):
        return False
    return similarity(n.group(2), p.group(2)) >= 0.55


def lint(skill: Skill) -> LintReport:
    out: list[Issue] = []

    # ---- name ----
    name = skill.name or ""
    if not name:
        out.append(Issue(field="name", rule="name-required", level=Level.ERROR,
                         message="name 必填"))
    else:
        if len(name) > 64:
            out.append(Issue(field="name", rule="name-too-long", level=Level.ERROR,
                             message=f"name 超过 64 字符（当前 {len(name)}）",
                             hint="截到最近的词边界"))
        if not NAME_RE.match(name):
            out.append(Issue(field="name", rule="name-format", level=Level.ERROR,
                             message="name 仅允许小写字母 / 数字 / 连字符（kebab-case）",
                             hint=re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "my-skill"))
        if any(part in RESERVED for part in name.lower().split("-")):
            out.append(Issue(field="name", rule="name-reserved", level=Level.ERROR,
                             message=f'name 不能包含保留词 "{name}"'))
        if len(name) < 4:
            out.append(Issue(field="name", rule="name-too-short", level=Level.WARN,
                             message="name 太短，建议 4-30 字符以利于检索"))

    # ---- description ----
    desc = skill.description or ""
    if not desc:
        out.append(Issue(field="description", rule="desc-required", level=Level.ERROR,
                         message="description 必填"))
    else:
        if len(desc) > 1024:
            out.append(Issue(field="description", rule="desc-too-long", level=Level.ERROR,
                             message=f"description 超过 1024 字符（当前 {len(desc)}）"))
        if not WHEN_RE.search(desc):
            out.append(Issue(field="description", rule="desc-missing-when", level=Level.WARN,
                             message='description 缺少"何时使用"焦点',
                             hint='补一句"适用于：xxx"，否则 Discovery 阶段匹配不上'))
        if "\n" in desc:
            out.append(Issue(field="description", rule="desc-multiline", level=Level.WARN,
                             message="description 建议单行，多行可能让某些 YAML 解析器出错"))

    # ---- body ----
    body = skill.body or ""
    if not body:
        out.append(Issue(field="body", rule="body-required", level=Level.ERROR,
                         message="body 必填"))
    else:
        nlines = len(body.splitlines())
        if nlines > 500:
            out.append(Issue(field="body", rule="body-too-long", level=Level.WARN,
                             message=f"body 超过 500 行（当前 {nlines}），建议拆成子 skill"))
        if not H1_RE.search(body):
            out.append(Issue(field="body", rule="body-no-h1", level=Level.WARN,
                             message="body 缺少 H1 标题（# Skill 名称）"))

    return LintReport(issues=out)


def lint_signals(signals: list[Signal]) -> list[Issue]:
    """信号级体检：原句溯源 + 规则互斥。这是防幻觉的关键一环。"""
    out: list[Issue] = []

    unverified = [s for s in signals if not s.verified]
    if unverified:
        sample = unverified[0].text
        out.append(Issue(field="signals", rule="signal-unverified", level=Level.WARN,
                         message=f"{len(unverified)} 条信号在原文里找不到对应原句",
                         hint=f'例如「{sample}」，可能是模型自己总结的，请人工确认'))

    texts = [s.text for s in signals if s.type.value == "constraint"]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if _conflict(a, b) or _conflict(b, a):
                out.append(Issue(field="signals", rule="rule-conflict", level=Level.WARN,
                                 message=f"两条约束可能互斥：「{a}」与「{b}」",
                                 hint="通常后说的为准，建议删掉较早的那条"))

    # 去重后仍出现重复项（normalize 后相同）
    keys = [normalize_key(t) for t in texts]
    if len(keys) != len(set(keys)):
        out.append(Issue(field="signals", rule="signal-duplicate", level=Level.WARN,
                         message="存在重复的约束条目", hint="合并同类项后再导出"))

    return out
