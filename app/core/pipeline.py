from __future__ import annotations

import asyncio
import json
from typing import Any

from app import repo
from app.config import get_settings
from app.core import llm
from app.core.bus import bus
from app.core.clusters import cluster
from app.core.compose import InsufficientSignals, compose
from app.core.lint import lint, lint_signals
from app.core.merge import merge
from app.core.preprocess import preprocess
from app.core.quote_check import mark_verified
from app.core.signals import extract_rule
from app.schemas import Skill

BUCKET_LABEL = {
    "constraints": "约束",
    "workflows": "工作流",
    "preferences": "偏好",
    "examples": "示例",
}


async def emit(run_id: str, event: str, data: dict[str, Any]) -> int:
    seq = repo.append_event(run_id, event, data)
    bus.publish(run_id, {"seq": seq, "event": event, "data": data})
    return seq


async def pace() -> None:
    ms = get_settings().stream_pace_ms
    if ms > 0:
        await asyncio.sleep(ms / 1000)


async def execute(run_id: str, conversation: str, base_skill_id: str | None) -> None:
    settings = get_settings()
    provider = settings.resolved_provider
    try:
        repo.update_run(run_id, status="running")

        # ---------- S0 预处理 ----------
        repo.update_run(run_id, stage="preprocess")
        await emit(run_id, "stage", {"stage": "preprocess", "status": "running"})
        doc = preprocess(conversation, settings.max_input_chars)
        await emit(run_id, "stage", {
            "stage": "preprocess", "status": "done",
            "meta": {
                "turns": len(doc.turns),
                "chars": len(doc.text),
                "est_tokens": doc.est_tokens,
                "masked": doc.masked,
                "truncated": doc.truncated,
                "provider": provider,
            },
        })
        await pace()

        # ---------- S1 信号抽取 ----------
        repo.update_run(run_id, stage="signals")
        await emit(run_id, "stage", {"stage": "signals", "status": "running"})
        signals = []
        if provider == "llm":
            try:
                signals = await llm.extract_signals(settings, doc)
            except llm.LLMError as exc:
                provider = "rule"
                await emit(run_id, "notice", {
                    "level": "warn",
                    "message": f"模型调用失败，已回退到内置规则引擎：{exc}",
                })
        if not signals:
            signals = extract_rule(doc)

        signals = mark_verified(signals, doc.text)
        for sig in signals:
            await emit(run_id, "signal", sig.model_dump(mode="json"))
            await pace()
        await emit(run_id, "stage", {
            "stage": "signals", "status": "done",
            "meta": {"count": len(signals), "provider": provider},
        })
        await pace()

        # ---------- 累积：与 base 版本合并 ----------
        diff: list[dict] = []
        base_ver: dict | None = None
        if base_skill_id:
            base_ver = repo.latest_version_of(base_skill_id)
            if base_ver:
                from app.schemas import Signal  # 局部导入避免循环
                old_signals = [Signal(**s) for s in base_ver.get("signals", [])]
                signals, entries = merge(old_signals, signals)
                diff = [e.model_dump(mode="json") for e in entries]
                await emit(run_id, "diff", {"entries": diff, "base_version": base_ver["version"]})
                await pace()

        # ---------- S2 聚类 ----------
        repo.update_run(run_id, stage="clusters")
        await emit(run_id, "stage", {"stage": "clusters", "status": "running"})
        clusters = cluster(signals)
        for bucket, items in clusters.buckets().items():
            await emit(run_id, "cluster", {
                "bucket": bucket, "label": BUCKET_LABEL[bucket], "items": items,
            })
            await pace()
        await emit(run_id, "stage", {
            "stage": "clusters", "status": "done",
            "meta": {"total": clusters.total()},
        })
        await pace()

        # ---------- S3 成稿 ----------
        repo.update_run(run_id, stage="compose")
        await emit(run_id, "stage", {"stage": "compose", "status": "running"})
        text_for_domain = doc.text + "\n" + "\n".join(s.text for s in signals)
        try:
            if provider == "llm":
                try:
                    data = await llm.compose_skill(settings, json.dumps(
                        clusters.model_dump(), ensure_ascii=False))
                    skill = Skill(**data)
                except (llm.LLMError, ValueError):
                    skill = compose(clusters, text_for_domain)
            else:
                skill = compose(clusters, text_for_domain)
        except InsufficientSignals as exc:
            await emit(run_id, "error", {"message": str(exc), "stage": "compose"})
            repo.finish_run(run_id, "failed", str(exc))
            return

        await emit(run_id, "field", {"field": "name", "value": skill.name})
        await pace()
        await emit(run_id, "field", {"field": "description", "value": skill.description})
        await pace()
        buf = ""
        for i in range(0, len(skill.body), 48):
            buf += skill.body[i : i + 48]
            await emit(run_id, "delta", {"field": "body", "chunk": skill.body[i : i + 48]})
            await pace()
        await emit(run_id, "field", {"field": "body_done", "value": buf})
        await emit(run_id, "stage", {"stage": "compose", "status": "done"})
        await pace()

        # ---------- S4 校验 ----------
        repo.update_run(run_id, stage="lint")
        await emit(run_id, "stage", {"stage": "lint", "status": "running"})
        report = lint(skill)
        report.issues.extend(lint_signals(signals))
        await emit(run_id, "lint", {
            "level": report.level,
            "by_field": report.by_field(),
            "issues": [i.model_dump(mode="json") for i in report.issues],
        })
        await emit(run_id, "stage", {"stage": "lint", "status": "done"})

        payload = {
            "skill": skill.model_dump(),
            "clusters": clusters.model_dump(),
            "signals": [s.model_dump(mode="json") for s in signals],
            "diff": diff,
            "provider": provider,
            "base_version": base_ver["version"] if base_ver else None,
        }
        repo.update_run(run_id, payload_json=json.dumps(payload, ensure_ascii=False))
        await emit(run_id, "done", {
            "provider": provider,
            "signals": len(signals),
            "clusters": clusters.total(),
            "lint": report.level,
            "cost_usd": 0.0,
        })
        repo.finish_run(run_id, "done")

    except Exception as exc:  # noqa: BLE001 - 兜底，任何异常都要让前端收到
        await emit(run_id, "error", {"message": f"处理失败：{exc}", "stage": "unknown"})
        repo.finish_run(run_id, "failed", str(exc))
