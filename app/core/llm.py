from __future__ import annotations

import json
import re

import httpx

from app.config import Settings
from app.core.preprocess import CleanDoc
from app.schemas import Signal

SYSTEM_SIGNALS = """你是 Skill 蒸馏器的「信号抽取器」。任务：从对话中找出所有"用户在约束 AI 行为"的句子。

四类信号：
- preference 偏好：风格倾向、语气、审美。例："别太正式"、"用短句"
- constraint 约束：明确禁止或必须，是否决性的。例："不要 emoji"、"禁止用赋能"
- workflow 工作流：要求按步骤执行。例："先列大纲再写"、"每步先确认"
- example 示例：给出正反例。例："像这句这样改"

硬规则：
1. 只抽"对 AI 的指令"，不抽用户对世界的描述、闲聊、寒暄、任务请求。
2. 每条必须给出对话中的原句 quote，逐字复制，不得改写。
3. text 是归一后的一句话，不超过 80 字，去掉"我觉得""你能不能"这类语气词。
4. 同类重复只保留信息量最大的一条。
5. 5-15 条。如果这段对话没有足够可提炼的内容，返回空数组 []。
6. 拿不准是 preference 还是 constraint 时：能写成"不要 X"的是 constraint。

只输出 JSON 数组，不要 markdown 围栏，不要任何解释。格式：
[{"text":"每段不超过 3 句话","quote":"每段不要超过 3 句话，读起来太累","type":"constraint"}]"""

SYSTEM_COMPOSE = """你是 Skill 蒸馏器的「成稿器」。把已归类的规则写进一份 SKILL.md。

要求：
1. name：kebab-case，仅小写字母/数字/连字符，8-30 字符，不能包含 anthropic/claude/openai/skill/agent 这些词。
2. description：单行，必须同时写清"做什么"和"何时使用"，用"适用于：xxx"收尾，不超过 1024 字符。
3. body：Markdown，必须有一级标题，固定四段（缺项则省略）：## 必须避免 / ## 风格要求 / ## 工作流 / ## 示例对照。
4. 不要发明规则，只能使用给定条目。

只输出 JSON：{"name":"...","description":"...","body":"..."}"""


class LLMError(Exception):
    pass


def _strip_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json|markdown|md)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_array(text: str) -> list[dict]:
    body = _strip_fence(text)
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        raise LLMError("模型没有返回 JSON 数组")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败: {exc}") from exc


def parse_json_object(text: str) -> dict:
    body = _strip_fence(text)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("模型没有返回 JSON 对象")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败: {exc}") from exc


async def _chat(settings: Settings, system: str, user: str,
                temperature: float = 0.2, max_tokens: int = 2000) -> str:
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"请求模型失败: {exc}") from exc
    if resp.status_code >= 400:
        raise LLMError(f"模型返回 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError("模型响应结构异常") from exc


async def extract_signals(settings: Settings, doc: CleanDoc) -> list[Signal]:
    raw = await _chat(settings, SYSTEM_SIGNALS, doc.text, temperature=0.2, max_tokens=1800)
    items = parse_json_array(raw)
    out: list[Signal] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        quote = str(item.get("quote", "")).strip()
        stype = str(item.get("type", "preference")).strip()
        if not text or not quote or stype not in ("preference", "constraint", "workflow", "example"):
            continue
        out.append(Signal.build(text=text[:120], quote=quote[:300], stype=stype))
    return out[:15]


async def compose_skill(settings: Settings, clusters_json: str) -> dict:
    raw = await _chat(settings, SYSTEM_COMPOSE, clusters_json, temperature=0.3, max_tokens=2000)
    return parse_json_object(raw)
