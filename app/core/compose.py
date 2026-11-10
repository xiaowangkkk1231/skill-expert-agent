from __future__ import annotations

import re

from app.schemas import Clusters, Skill

RESERVED = {"anthropic", "claude", "openai", "skill", "agent"}

# slug, 中文标签, 关键词, 适用场景
DOMAINS: list[tuple[str, str, list[str], list[str]]] = [
    ("content-writing", "内容写作",
     ["写作", "公众号", "文案", "文章", "标题", "开头", "润色", "稿", "段落", "读者", "风格"],
     ["公众号写作", "文案润色", "风格统一"]),
    ("code-review", "代码评审",
     ["代码", "组件", "函数", "重构", "命名", "提交", "commit", "pr", "测试", "hook", "类型"],
     ["PR 评审", "提交前自检", "新人入职参考"]),
    ("design-system", "设计规范",
     ["设计", "间距", "字号", "圆角", "颜色", "按钮", "样式", "组件库", "ui", "交互", "状态"],
     ["设计评审", "新组件开发", "设计稿与代码对齐"]),
    ("support-reply", "客服话术",
     ["客服", "话术", "回复", "投诉", "工单", "客户", "退款"],
     ["工单回复", "投诉处理", "话术培训"]),
    ("data-report", "数据报表",
     ["报表", "指标", "数据", "图表", "看板", "口径", "同比"],
     ["周报撰写", "口径对齐", "看板维护"]),
    ("hiring", "招聘面试",
     ["面试", "招聘", "简历", "候选人", "岗位"],
     ["面试提问", "简历筛选", "评估记录"]),
]


def _title_case(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.split("-"))


def detect_domain(signals_text: str) -> tuple[str, str, list[str]]:
    low = signals_text.lower()
    best: tuple[int, str, str, list[str]] | None = None
    for slug, label, keywords, scenes in DOMAINS:
        score = sum(low.count(k.lower()) for k in keywords)
        if score and (best is None or score > best[0]):
            best = (score, slug, label, scenes)
    if best and best[0] >= 2:
        return best[1], best[2], best[3]
    return "", "通用任务", ["任何需要复用同一套规则的多轮对话"]


def make_name(slug: str, clusters: Clusters) -> str:
    if slug:
        suffix = "rules" if clusters.constraints else "guide"
        name = f"{slug}-{suffix}"
    else:
        name = "custom-skill-rules"
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    name = re.sub(r"-{2,}", "-", name)
    if name in RESERVED:
        name = f"my-{name}"
    return name[:64]


def make_description(slug: str, label: str, scenes: list[str], clusters: Clusters) -> str:
    if clusters.constraints:
        head = f"{label}的硬性约束与输出规范"
    elif clusters.workflows:
        head = f"{label}的执行流程与输出约定"
    else:
        head = f"{label}的风格偏好与输出约定"
    if clusters.preferences:
        head += "，含风格偏好"
    scene = "、".join(scenes[:3])
    desc = f"{head}；适用于：{scene}。"
    return desc.replace("\n", " ")[:1024]


def make_body(name: str, clusters: Clusters) -> str:
    lines: list[str] = [f"# {_title_case(name)}", ""]

    if clusters.constraints:
        lines.append("## 必须避免")
        lines.extend(f"- {c}" for c in clusters.constraints)
        lines.append("")

    if clusters.preferences:
        lines.append("## 风格要求")
        lines.extend(f"- {p}" for p in clusters.preferences)
        lines.append("")

    if clusters.workflows:
        lines.append("## 工作流")
        lines.extend(f"- {w}" for w in clusters.workflows)
        lines.append("")

    if clusters.examples:
        lines.append("## 示例对照")
        lines.extend(f"- 参考：{e}" for e in clusters.examples)
        lines.append("")

    if len(lines) <= 2:
        lines.append("## 说明")
        lines.append("- 这段对话里没有足够的可复用规则，建议补充更多明确的指令后再提炼。")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


class InsufficientSignals(Exception):
    """对话里没有足够可提炼的规则。"""


def compose(clusters: Clusters, signals_text: str) -> Skill:
    if clusters.is_empty() or clusters.total() < 2:
        raise InsufficientSignals("这段对话里没有找到足够的可复用规则")

    slug, label, scenes = detect_domain(signals_text)
    name = make_name(slug, clusters)
    description = make_description(slug, label, scenes, clusters)
    body = make_body(name, clusters)
    return Skill(name=name, description=description, body=body)
