from __future__ import annotations

import re

from app.core.preprocess import CleanDoc, is_chitchat
from app.core.similarity import dedupe
from app.schemas import Signal, SignalType

CLAUSE_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+")

PREFIXES = [
    "我觉得", "我感觉", "我想说", "我认为", "我想", "说实话", "总的来说", "总之",
    "然后呢", "然后", "还有", "还补充一条", "补充一条", "再补充一下", "另外补充",
    "另外", "而且", "其实", "就是", "所以", "但是",
    "不过", "对了", "记得", "记住", "注意", "建议", "最好", "麻烦",
    "你能不能", "你可以", "你要", "你", "我们", "咱们", "大家", "请",
]
SUFFIX_RE = re.compile(r"[吧啊呢哈哦嘛啦呀哇]+$")
EDGE_PUNCT = re.compile(r"^[，,。.、；;：:\s“”\"'（）()【】]+|[，,。.、；;：:\s“”\"'（）()【】]+$")

CONSTRAINT_CUES = [
    "不要", "别用", "别把", "别再", "别说", "别写", "别再", "禁止", "必须", "一律",
    "统一", "只用", "只能", "不能", "不允许", "不准", "不得", "严禁", "避免", "不许",
    "勿", "都要", "就要", "写死",
    "never", "must", "always", "only", "avoid", "don't", "do not", "should not",
]
WORKFLOW_LINK = re.compile(r"先.{0,30}(再|然后|接着|最后)|(^|，|,)\s*(再|然后|接着)")
WORKFLOW_CUES = [
    "步骤", "流程", "顺序", "第一步", "每步", "逐条", "依次", "分步", "先列",
    "分块", "小标题", "记得", "step", "first", "then", "workflow",
]
PREFERENCE_CUES = [
    "优先", "偏向", "更喜欢", "倾向", "风格", "语气", "口吻", "简洁", "短句",
    "正式", "口语", "轻松", "结构化", "自然", "克制",
]
EXAMPLE_CUES = ["例如", "比如", "像这句", "像这样", "反例", "正例", "参考", "示例",
                "改写成", "for example", "e.g."]

NUMERIC_RULE = re.compile(
    r"\d+\s*(行|个|条|次|px|字|档|倍).{0,14}(就|必须|以上|以内|以下|统一|标准)"
)

REQUEST_RE = re.compile(
    r"(帮我|帮忙|你能不能|你可以|能否|可不可以|麻烦你|给我).{0,24}"
    r"(写|做|改|整理|生成|翻译|润色|列|看|出|拟|起)"
)
TASK_VERB_RE = re.compile(r"^(帮|请|给我|写一|生成|翻译|润色|整理|列出|做一)")

TYPE_WEIGHT = {
    SignalType.CONSTRAINT: 3.0,
    SignalType.WORKFLOW: 2.4,
    SignalType.PREFERENCE: 1.8,
    SignalType.EXAMPLE: 1.4,
}


def _strip_prefix(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for p in PREFIXES:
            if text.startswith(p):
                rest = text[len(p) :]
                if rest[:1] in ("，", ",", "、", " ", "："):
                    rest = rest[1:]
                if len(rest) >= 4:
                    text = rest.strip()
                    changed = True
                    break
    return text


def normalize(text: str) -> str:
    t = text.strip()
    t = _strip_prefix(t)
    t = SUFFIX_RE.sub("", t)
    t = EDGE_PUNCT.sub("", t)
    t = re.sub(r"\s+", " ", t)
    t = t.replace("“", "").replace("”", "").replace('"', "")
    if len(t) > 80:
        t = t[:80].rstrip("，,。.、")
    return t


def classify(text: str) -> SignalType:
    low = text.lower()
    # 顺序有讲究：带硬性措辞的句子即使举了例子，本质仍是约束，
    # 示例类型只留给"纯举例"（反例/正例、像这句这样改）。
    if WORKFLOW_LINK.search(text) or any(c in text for c in WORKFLOW_CUES):
        return SignalType.WORKFLOW
    if (any(c in text for c in CONSTRAINT_CUES)
            or any(c in low for c in CONSTRAINT_CUES)
            or NUMERIC_RULE.search(text)):
        return SignalType.CONSTRAINT
    if any(c in text for c in EXAMPLE_CUES) or any(c in low for c in ("example", "e.g.")):
        return SignalType.EXAMPLE
    return SignalType.PREFERENCE


def _has_cue(text: str) -> bool:
    low = text.lower()
    if any(c in text for c in CONSTRAINT_CUES) or any(c in low for c in CONSTRAINT_CUES):
        return True
    if WORKFLOW_LINK.search(text) or any(c in text for c in WORKFLOW_CUES):
        return True
    if any(c in text for c in PREFERENCE_CUES):
        return True
    if NUMERIC_RULE.search(text):
        return True
    return any(c in text for c in EXAMPLE_CUES)


def _is_request(text: str) -> bool:
    if REQUEST_RE.search(text) and not any(c in text for c in CONSTRAINT_CUES):
        return True
    if TASK_VERB_RE.match(text) and not _has_cue(text):
        return True
    if text.rstrip().endswith(("？", "?")) and not any(c in text for c in CONSTRAINT_CUES):
        return True
    return False


def _score(text: str, stype: SignalType) -> float:
    score = TYPE_WEIGHT[stype]
    score += sum(1 for c in CONSTRAINT_CUES if c in text) * 0.35
    ln = len(text)
    if 6 <= ln <= 42:
        score += 1.0
    elif ln > 70:
        score -= 0.8
    return score


def extract_rule(doc: CleanDoc, limit: int = 15) -> list[Signal]:
    """规则引擎：从人类发言里挑出"调教句"，四类分型。确定性、可测试、零成本。"""
    candidates: list[tuple[float, str, str, int]] = []

    for turn in doc.turns:
        if turn.role == "ai":
            continue
        for raw in CLAUSE_SPLIT.split(turn.text):
            piece = raw.strip()
            if len(piece) < 5 or len(piece) > 300:
                continue
            if is_chitchat(piece):
                continue
            if _is_request(piece):
                continue
            text = normalize(piece)
            if len(text) < 4:
                continue
            if not _has_cue(text):
                continue
            stype = classify(text)
            candidates.append((_score(text, stype), text, piece, turn.index))

    candidates.sort(key=lambda c: -c[0])

    seen_text: list[str] = []
    signals: list[Signal] = []
    for score, text, quote, turn_idx in candidates:
        kept = dedupe(seen_text + [text])
        if text not in kept:
            continue
        seen_text.append(text)
        signals.append(Signal.build(text=text, quote=quote, stype=str(classify(text)),
                                    turn=turn_idx))
        if len(signals) >= limit:
            break
    return signals
