from app.core.lint import lint, lint_signals
from app.schemas import Signal, Skill

GOOD = Skill(
    name="content-writing-rules",
    description="内容写作的硬性约束与输出规范；适用于：公众号写作、文案润色。",
    body="# Content Writing Rules\n\n## 必须避免\n- 不要套话\n",
)


def rules(report) -> set[str]:
    return {i.rule for i in report.issues}


def test_good_skill_is_clean():
    report = lint(GOOD)
    assert report.level == "ok"
    assert report.issues == []
    assert report.by_field() == {"name": "ok", "description": "ok", "body": "ok", "signals": "ok"}


def test_name_must_be_kebab_case():
    bad = GOOD.model_copy(update={"name": "Content_Writing"})
    assert "name-format" in rules(lint(bad))
    assert lint(bad).level == "error"


def test_name_reserved_word():
    bad = GOOD.model_copy(update={"name": "claude-rules"})
    assert "name-reserved" in rules(lint(bad))


def test_name_too_long():
    bad = GOOD.model_copy(update={"name": "a" * 65})
    assert "name-too-long" in rules(lint(bad))


def test_name_too_short_is_warn():
    bad = GOOD.model_copy(update={"name": "abc"})
    assert "name-too-short" in rules(lint(bad))
    assert lint(bad).level == "warn"


def test_description_needs_when_focus():
    bad = GOOD.model_copy(update={"description": "一套写作规范。"})
    assert "desc-missing-when" in rules(lint(bad))


def test_description_multiline():
    bad = GOOD.model_copy(update={"description": "第一行\n适用于：写作"})
    assert "desc-multiline" in rules(lint(bad))


def test_description_too_long():
    bad = GOOD.model_copy(update={"description": "适用于：" + "x" * 1100})
    assert "desc-too-long" in rules(lint(bad))


def test_body_requires_h1():
    bad = GOOD.model_copy(update={"body": "## 必须避免\n- 不要套话\n"})
    assert "body-no-h1" in rules(lint(bad))


def test_body_too_long():
    bad = GOOD.model_copy(update={"body": "# T\n" + "- 条目\n" * 500})
    assert "body-too-long" in rules(lint(bad))


def test_empty_fields_are_errors():
    bad = Skill(name="", description="", body="")
    got = rules(lint(bad))
    assert {"name-required", "desc-required", "body-required"} <= got


def test_unverified_signal_flag():
    sig = Signal.build(text="不要 emoji", quote="完全不存在的一句话", stype="constraint")
    issues = lint_signals([sig.model_copy(update={"verified": False})])
    assert "signal-unverified" in {i.rule for i in issues}


def test_conflicting_rules_detected():
    a = Signal.build(text="必须用 any 类型", quote="必须用 any 类型", stype="constraint")
    b = Signal.build(text="不要用 any 类型", quote="不要用 any 类型", stype="constraint")
    issues = lint_signals([a.model_copy(update={"verified": True}),
                           b.model_copy(update={"verified": True})])
    assert "rule-conflict" in {i.rule for i in issues}


def test_verified_signals_pass():
    sig = Signal.build(text="不要 emoji", quote="不要 emoji", stype="constraint")
    issues = lint_signals([sig.model_copy(update={"verified": True})])
    assert issues == []
