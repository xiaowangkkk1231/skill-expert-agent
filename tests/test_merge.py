from app.core.merge import merge, summarize
from app.schemas import Signal


def sig(text: str, stype: str = "constraint", quote: str | None = None) -> Signal:
    return Signal.build(text=text, quote=quote or text, stype=stype)


def kinds(diff) -> dict[str, int]:
    out = {"added": 0, "modified": 0, "orphan": 0}
    for d in diff:
        out[d.kind] += 1
    return out


def test_same_signal_is_not_added():
    old = [sig("不要 emoji"), sig("每段不超过 3 句话")]
    new = [sig("不要 emoji"), sig("每段不超过 3 句话")]
    merged, diff = merge(old, new)
    assert len(merged) == 2
    assert kinds(diff) == {"added": 0, "modified": 0, "orphan": 0}


def test_new_signal_is_added():
    old = [sig("不要 emoji")]
    new = [sig("不要 emoji"), sig("必须带单元测试")]
    merged, diff = merge(old, new)
    assert len(merged) == 2
    assert kinds(diff)["added"] == 1
    assert any("单元测试" in d.text for d in diff if d.kind == "added")


def test_similar_text_is_modified_not_added():
    old = [sig("不要在同一段里塞太多句子")]
    new = [sig("不要在同一段里塞太多句子啊")]
    merged, diff = merge(old, new)
    assert len(merged) == 1
    assert kinds(diff)["modified"] == 1


def test_old_signal_never_deleted():
    """核心原则：旧版有、新版没提到的，只标记不删除。"""
    old = [sig("不要 emoji"), sig("禁止用赋能")]
    new = [sig("不要 emoji")]
    merged, diff = merge(old, new)
    assert len(merged) == 2, "旧规则必须保留"
    assert kinds(diff)["orphan"] == 1
    assert any("赋能" in d.text for d in diff if d.kind == "orphan")


def test_sid_match_wins_over_similarity():
    old = [sig("用短句", quote="用短句")]
    new = [Signal.build(text="完全不同的措辞", quote="用短句", stype="constraint")]
    merged, _ = merge(old, new)
    assert len(merged) == 1
    assert merged[0].text == "完全不同的措辞"


def test_summarize_counts():
    old = [sig("不要用赋能这个词"), sig("不要开场自我介绍")]
    new = [sig("不要用赋能这个词"), sig("必须带单元测试")]
    _, diff = merge(old, new)
    text = summarize(diff)
    assert "+1" in text
    assert "未提及 1" in text
