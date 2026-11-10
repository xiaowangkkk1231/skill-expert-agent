from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app import APP_NAME, APP_NAME_ZH
from app.config import BASE_DIR
from app.samples import SAMPLE_BY_KEY, SAMPLES

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(tags=["pages"])

BASE_CTX = {"app_name": APP_NAME, "app_name_zh": APP_NAME_ZH}


@router.get("/")
def overview(request: Request):
    stats = [
        {"label": "内置案例", "value": str(len(SAMPLES)), "hint": "客服 · 数据 · 面试"},
        {"label": "要求分型", "value": "4", "hint": "禁令 · 偏好 · 步骤 · 样例"},
        {"label": "体检项", "value": "14", "hint": "12 项格式 + 2 项语义"},
        {"label": "落地格式", "value": "3", "hint": "Claude · ChatGPT · 通用"},
    ]
    return templates.TemplateResponse(
        request=request, name="overview.html",
        context={**BASE_CTX, "active": "overview", "samples": SAMPLES, "stats": stats},
    )


@router.get("/play")
def play(request: Request, sample: str | None = None, base: str | None = None):
    initial = SAMPLE_BY_KEY.get(sample or "", None)
    return templates.TemplateResponse(
        request=request, name="play.html",
        context={**BASE_CTX, "active": "play", "samples": SAMPLES,
                 "initial": initial, "base_skill_id": base or ""},
    )


@router.get("/library")
def library(request: Request):
    return templates.TemplateResponse(
        request=request, name="library.html",
        context={**BASE_CTX, "active": "library"},
    )


@router.get("/learn")
def learn(request: Request):
    return templates.TemplateResponse(
        request=request, name="learn.html",
        context={**BASE_CTX, "active": "learn"},
    )
