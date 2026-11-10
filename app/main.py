from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import APP_NAME, APP_NAME_ZH, __version__
from app.api import pages, runs, skills
from app.config import BASE_DIR, get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    (BASE_DIR / "data").mkdir(exist_ok=True)
    print(f"[{APP_NAME}] provider={settings.resolved_provider} model={settings.llm_model}")
    yield


app = FastAPI(
    title=APP_NAME,
    description=f"{APP_NAME_ZH} — 从对话中蒸馏出可复用的 Agent Skill",
    version=__version__,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.include_router(pages.router)
app.include_router(runs.router)
app.include_router(skills.router)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "version": __version__,
        "provider": settings.resolved_provider,
        "model": settings.llm_model if settings.resolved_provider == "llm" else "rule-engine",
    }
