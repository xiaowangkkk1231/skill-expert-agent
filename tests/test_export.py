from app.core.export import EXPORTERS, download_name, key_points, render
from app.schemas import Skill

SKILL = Skill(
    name="content-writing-rules",
    description="内容写作的硬性约束与输出规范；适用于：公众号写作、文案润色。",
    body=(
        "# Content Writing Rules\n\n"
        "## 必须避免\n"
        "- 不要用赋能、打造这类词\n"
        "- 不要开场自我介绍\n\n"
        "## 风格要求\n"
        "- 短句优先\n\n"
        "## 工作流\n"
        "- 先写钩子再展开\n"
    ),
)


def test_three_exporters_registered():
    assert set(EXPORTERS) == {"claude-code", "chatgpt", "memory"}


def test_claude_has_yaml_frontmatter():
    out = render("claude-code", SKILL)
    assert out.startswith("---\nname: content-writing-rules")
    assert "description: 内容写作的硬性约束" in out
    assert "## 必须避免" in out


def test_chatgpt_has_no_frontmatter():
    out = render("chatgpt", SKILL)
    assert not out.startswith("---")
    assert out.startswith("# content-writing-rules")
    assert "---" in out  # 分隔线仍在
    assert "## 必须避免" in out


def test_memory_is_short_and_numbered():
    out = render("memory", SKILL)
    assert "要点：" in out
    assert out.count("\n1. ") == 1
    assert "- " not in out.split("要点：")[1]


def test_key_points_capped_at_five():
    body = "# T\n" + "".join(f"- 规则 {i}\n" for i in range(20))
    assert len(key_points(body)) == 5


def test_key_points_fallback_when_no_bullets():
    points = key_points("一段没有列表的正文，" * 30)
    assert len(points) == 1
    assert points[0].endswith("…")


def test_download_name():
    assert download_name("claude-code", SKILL) == "content-writing-rules-SKILL.md"
    assert download_name("chatgpt", SKILL) == "custom-instructions.md"
    assert download_name("memory", SKILL) == "memory-short.txt"
