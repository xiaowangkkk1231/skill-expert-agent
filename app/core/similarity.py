from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]+")

# 中文数字统一成阿拉伯数字，否则"3 句话"和"三句话"会被当成两条规则
_NUM_MAP = {
    "十": "10", "一": "1", "两": "2", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
}


def normalize_key(text: str) -> str:
    key = _PUNCT.sub("", text).lower()
    for zh, ar in _NUM_MAP.items():
        key = key.replace(zh, ar)
    return key


def bigrams(text: str) -> set[str]:
    key = normalize_key(text)
    if len(key) < 2:
        return {key} if key else set()
    return {key[i : i + 2] for i in range(len(key) - 1)}


def similarity(a: str, b: str) -> float:
    """字符 bigram 的 Jaccard 相似度。确定性、无依赖、对中文短语够用。"""
    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return 0.0
    inter = len(ba & bb)
    if not inter:
        return 0.0
    return inter / len(ba | bb)


def dedupe(items: list[str], threshold: float = 0.72) -> list[str]:
    """按相似度去重，保留先出现的（调用方应先按重要性排序）。"""
    kept: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        key = normalize_key(item)
        if not key:
            continue
        drop = False
        for k in kept:
            kn = normalize_key(k)
            if key == kn:
                drop = True
                break
            if key in kn and len(key) / max(len(kn), 1) > 0.6:
                drop = True
                break
            if kn in key and len(kn) / max(len(key), 1) > 0.6:
                drop = True
                break
            if similarity(key, kn) >= threshold:
                drop = True
                break
        if not drop:
            kept.append(item)
    return kept
