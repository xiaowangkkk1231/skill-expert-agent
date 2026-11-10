from __future__ import annotations

from difflib import SequenceMatcher

from app.schemas import Signal


def verify_quote(quote: str, conversation: str, threshold: float = 0.82) -> bool:
    """原句必须是对话原文的连续片段（允许标点/换行差异）。

    这是整套系统里唯一能真正拦住幻觉的机制：模型编出来的规则，
    在原文里找不到出处就会被标黄。
    """
    q = (quote or "").strip()
    if len(q) < 4:
        return False
    if q in conversation:
        return True

    # 去掉标点与空白后再比一次，容忍换行与标点差异
    def strip(s: str) -> str:
        return "".join(ch for ch in s if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    sq = strip(q)
    sc = strip(conversation)
    if len(sq) >= 4 and sq in sc:
        return True

    # 退化到滑动窗口模糊匹配（长文本只在头部做，避免 O(n·m)）
    if len(sc) > 30000:
        head = sc[:30000]
    else:
        head = sc
    win = len(sq) + 6
    best = 0.0
    for i in range(0, max(1, len(head) - win), 6):
        r = SequenceMatcher(None, sq, head[i : i + win]).ratio()
        if r > best:
            best = r
            if best >= threshold:
                return True
    return best >= threshold


def mark_verified(signals: list[Signal], conversation: str) -> list[Signal]:
    out = []
    for s in signals:
        out.append(s.model_copy(update={"verified": verify_quote(s.quote, conversation)}))
    return out
