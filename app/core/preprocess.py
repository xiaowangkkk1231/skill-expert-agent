from __future__ import annotations

import re
from dataclasses import dataclass, field

AI_SPEAKERS = {
    "ai", "assistant", "gpt", "chatgpt", "claude", "bot", "copilot", "model",
    "模型", "助手", "智能助手", "机器人",
}
USER_SPEAKERS = {"我", "user", "me", "i", "本人", "客户", "用户"}

SPEAKER_RE = re.compile(r"^\s*([^\s：:]{1,14})\s*[：:]\s*(.*)$")
HEADER_RE = re.compile(r"^\s*[\[【].{0,60}[\]】]\s*$")

PII_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<EMAIL>"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "<PHONE>"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|AKIA|xoxb)[-_A-Za-z0-9]{12,}\b"), "<SECRET>"),
    (re.compile(r"\b\d{15,19}\b"), "<ID>"),
]

CHITCHAT_RE = re.compile(
    r"^(好的?|好吧|行|可以|没问题|收到|明白|了解|嗯+|哦+|谢谢|多谢|OK|ok|对|是的|不错|厉害|哈哈+|😀)"
)


@dataclass
class Turn:
    index: int
    speaker: str
    role: str          # user | ai | header
    text: str


@dataclass
class CleanDoc:
    text: str
    turns: list[Turn] = field(default_factory=list)
    est_tokens: int = 0
    masked: int = 0
    truncated: bool = False

    def user_text(self) -> str:
        return "\n".join(t.text for t in self.turns if t.role in ("user", "header"))


def mask_pii(text: str) -> tuple[str, int]:
    hits = 0
    for pattern, tag in PII_RULES:
        text, n = pattern.subn(tag, text)
        hits += n
    return text, hits


def estimate_tokens(text: str) -> int:
    """粗估：中文 1 字≈1 token，其他字符 4 字≈1 token。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    rest = len(text) - cjk
    return int(cjk + rest / 4)


def _detect_role(speaker: str) -> str:
    s = speaker.strip().lower()
    if s in AI_SPEAKERS:
        return "ai"
    if s in USER_SPEAKERS:
        return "user"
    # 未知说话人（真实姓名、群昵称）默认当人类
    return "user"


def parse_turns(text: str) -> list[Turn]:
    turns: list[Turn] = []
    current_speaker, current_role, buf = "", "user", []
    idx = 0

    def flush() -> None:
        nonlocal buf, idx
        body = "\n".join(buf).strip()
        if body:
            turns.append(Turn(index=idx, speaker=current_speaker or "对话",
                              role=current_role, text=body))
            idx += 1
        buf = []

    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if buf:
                buf.append("")
            continue
        if HEADER_RE.match(line):
            flush()
            turns.append(Turn(index=idx, speaker="节选", role="header", text=line.strip()))
            idx += 1
            continue
        m = SPEAKER_RE.match(line)
        if m and len(m.group(1)) <= 14:
            flush()
            current_speaker = m.group(1)
            current_role = _detect_role(current_speaker)
            buf = [m.group(2)]
        else:
            buf.append(line)
    flush()
    return turns


def compress(doc_turns: list[Turn], ai_keep: int = 200) -> str:
    """保留人类全部发言；AI 回复只留首尾，信号几乎都在人类话里。"""
    out: list[str] = []
    for t in doc_turns:
        if t.role == "header":
            out.append(t.text)
        elif t.role == "ai":
            body = t.text
            if len(body) > ai_keep:
                body = body[: ai_keep // 2] + " …… " + body[-ai_keep // 2:]
            out.append(f"{t.speaker}：{body}")
        else:
            out.append(f"{t.speaker}：{t.text}")
    return "\n".join(out)


def _head_tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 20
    return text[:head] + "\n……（中间省略）……\n" + text[-tail:]


def preprocess(raw: str, max_chars: int = 60_000) -> CleanDoc:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = text.strip()

    text, masked = mask_pii(text)
    turns = parse_turns(text)
    if not turns:
        turns = [Turn(index=0, speaker="对话", role="user", text=text)]

    compact = compress(turns)
    truncated = len(compact) > max_chars
    if truncated:
        compact = _head_tail(compact, max_chars)

    return CleanDoc(
        text=compact,
        turns=turns,
        est_tokens=estimate_tokens(compact),
        masked=masked,
        truncated=truncated,
    )


def is_chitchat(text: str) -> bool:
    return bool(CHITCHAT_RE.match(text.strip()))
