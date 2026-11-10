from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import BASE_DIR, get_settings


def now() -> datetime:
    return datetime.now(timezone.utc)


def uuid4() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    latest_v: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Version(Base):
    __tablename__ = "skill_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid4)
    skill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    clusters_json: Mapped[str] = mapped_column(Text, default="{}")
    signals_json: Mapped[str] = mapped_column(Text, default="[]")
    diff_json: Mapped[str] = mapped_column(Text, default="[]")
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    run_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conversation: Mapped[str] = mapped_column(Text, default="")
    conv_sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    base_skill_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(16), default="rule")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(Base):
    __tablename__ = "events"

    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String(24))
    data_json: Mapped[str] = mapped_column(Text, default="{}")


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.db_url.startswith("sqlite")
        if is_sqlite:
            (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            settings.db_url,
            future=True,
            connect_args={"check_same_thread": False} if is_sqlite else {},
        )
        if is_sqlite:
            # 每个事件都要 commit，默认 synchronous=FULL 在 Windows 上单次约 200ms，
            # 一次提炼 30 个事件就会拖到 6 秒。WAL + NORMAL 把提交压到毫秒级。
            @event.listens_for(_engine, "connect")
            def _sqlite_pragma(dbapi_conn, _record):  # pragma: no cover - 驱动层
                cur = dbapi_conn.cursor()
                try:
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA synchronous=NORMAL")
                    cur.execute("PRAGMA busy_timeout=5000")
                except Exception:
                    pass
                finally:
                    cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_scope() -> Session:
    get_engine()
    return _SessionLocal()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
