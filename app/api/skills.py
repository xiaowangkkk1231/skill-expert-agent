from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app import repo
from app.core.export import EXPORTERS, download_name, render
from app.schemas import Skill

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills() -> dict:
    return {"items": repo.list_skills()}


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict:
    data = repo.get_skill(skill_id)
    if not data:
        raise HTTPException(404, "skill 不存在")
    return data


@router.get("/{skill_id}/versions")
async def versions(skill_id: str) -> dict:
    if not repo.get_skill(skill_id):
        raise HTTPException(404, "skill 不存在")
    return {"items": repo.list_versions(skill_id)}


@router.get("/{skill_id}/preview")
async def preview(skill_id: str, format: str = "claude-code") -> dict:
    if format not in EXPORTERS:
        raise HTTPException(400, "未知的导出格式")
    ver = repo.latest_version_of(skill_id)
    if not ver:
        raise HTTPException(404, "还没有版本")
    skill = Skill(name=ver["name"], description=ver["description"], body=ver["body"])
    return {
        "format": format,
        "filename": download_name(format, skill),
        "hint": EXPORTERS[format].hint.format(name=skill.name),
        "content": render(format, skill),
    }


@router.get("/{skill_id}/export")
async def export(skill_id: str, format: str = "claude-code") -> PlainTextResponse:
    if format not in EXPORTERS:
        raise HTTPException(400, "未知的导出格式")
    ver = repo.latest_version_of(skill_id)
    if not ver:
        raise HTTPException(404, "还没有版本")
    skill = Skill(name=ver["name"], description=ver["description"], body=ver["body"])
    filename = download_name(format, skill)
    return PlainTextResponse(
        render(format, skill),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{skill_id}")
async def remove(skill_id: str) -> dict:
    if not repo.get_skill(skill_id):
        raise HTTPException(404, "skill 不存在")
    repo.delete_skill(skill_id)
    return {"deleted": True}
