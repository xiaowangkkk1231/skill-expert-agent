from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from app import repo
from app.config import get_settings
from app.core import pipeline
from app.core.bus import bus
from app.core.export import EXPORTERS, download_name, render
from app.schemas import RunRequest, Skill

router = APIRouter(prefix="/api", tags=["runs"])

_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.post("/runs")
async def create_run(payload: RunRequest) -> dict[str, Any]:
    text = (payload.conversation or "").strip()
    if len(text) < 20:
        raise HTTPException(400, "对话内容太短，至少 20 个字")
    settings = get_settings()
    if len(text) > settings.max_input_chars * 2:
        raise HTTPException(413, f"对话太长，请控制在 {settings.max_input_chars * 2} 字以内")

    if payload.base_skill_id and not repo.get_skill(payload.base_skill_id):
        raise HTTPException(404, "base skill 不存在")

    run = repo.create_run(text, payload.base_skill_id, settings.resolved_provider)
    _spawn(pipeline.execute(run.id, text, payload.base_skill_id))
    return {"run_id": run.id, "provider": settings.resolved_provider, "status": run.status}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    payload = json.loads(run.payload_json or "{}")
    return {
        "id": run.id,
        "status": run.status,
        "stage": run.stage,
        "provider": run.provider,
        "error": run.error,
        "version_id": run.version_id,
        "base_skill_id": run.base_skill_id,
        **payload,
    }


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, last_event_id: str | None = None):
    if not repo.get_run(run_id):
        raise HTTPException(404, "run 不存在")

    async def gen():
        seq = int(last_event_id or 0)
        # 先订阅再回放，避免两条事件之间漏推
        queue = bus.subscribe(run_id)
        try:
            for s, ev, data in repo.events_since(run_id, seq):
                seq = s
                yield f"id: {s}\nevent: {ev}\ndata: {data}\n\n"

            run = repo.get_run(run_id)
            if run and run.status in ("done", "failed"):
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if msg["seq"] <= seq:
                    continue
                seq = msg["seq"]
                data = json.dumps(msg["data"], ensure_ascii=False)
                yield f"id: {seq}\nevent: {msg['event']}\ndata: {data}\n\n"
                if msg["event"] in ("done", "error"):
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}/preview")
async def preview_run(run_id: str, format: str = "claude-code") -> dict[str, Any]:
    """不落库也能看三端导出效果。"""
    if format not in EXPORTERS:
        raise HTTPException(400, "未知的导出格式")
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    payload = json.loads(run.payload_json or "{}")
    data = payload.get("skill")
    if not data:
        raise HTTPException(409, "还没有可预览的结果")
    skill = Skill(**data)
    return {
        "format": format,
        "filename": download_name(format, skill),
        "hint": EXPORTERS[format].hint.format(name=skill.name),
        "content": render(format, skill),
    }


@router.get("/runs/{run_id}/export")
async def export_run(run_id: str, format: str = "claude-code") -> PlainTextResponse:
    """不落库直接下载导出物。"""
    if format not in EXPORTERS:
        raise HTTPException(400, "未知的导出格式")
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    payload = json.loads(run.payload_json or "{}")
    data = payload.get("skill")
    if not data:
        raise HTTPException(409, "还没有可导出的结果")
    skill = Skill(**data)
    filename = download_name(format, skill)
    return PlainTextResponse(
        render(format, skill),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/runs/{run_id}/save")
async def save_run(run_id: str, request: Request) -> dict[str, Any]:
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    if run.status != "done":
        raise HTTPException(409, "这次提炼还没完成")
    if run.version_id:
        return {"skill_id": None, "version_id": run.version_id, "already_saved": True}

    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    create_new = bool(body.get("create_new"))

    payload = json.loads(run.payload_json or "{}")
    skill = payload.get("skill")
    if not skill:
        raise HTTPException(409, "没有可保存的结果")

    version_id = repo.save_version(
        skill_id=run.base_skill_id,
        name=skill["name"],
        description=skill["description"],
        body=skill["body"],
        clusters=payload.get("clusters", {}),
        signals=payload.get("signals", []),
        diff=payload.get("diff", []),
        run_id=run_id,
        create_new=create_new,
    )
    repo.update_run(run_id, version_id=version_id)
    ver = repo.get_version(version_id) or {}
    return {
        "skill_id": ver.get("skill_id"),
        "version_id": version_id,
        "version": ver.get("version"),
    }
