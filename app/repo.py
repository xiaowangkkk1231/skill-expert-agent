from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete, func, select

from app.db import Event, Run, Skill, Version, now, session_scope, uuid4


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------- runs ----------------

def create_run(conversation: str, base_skill_id: str | None, provider: str) -> Run:
    with session_scope() as s:
        run = Run(
            id=uuid4(),
            status="queued",
            conversation=conversation,
            conv_sha256=sha256(conversation.strip()),
            base_skill_id=base_skill_id,
            provider=provider,
            payload_json="{}",
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        s.expunge(run)
        return run


def get_run(run_id: str) -> Run | None:
    with session_scope() as s:
        run = s.get(Run, run_id)
        if run:
            s.expunge(run)
        return run


def update_run(run_id: str, **fields: Any) -> None:
    with session_scope() as s:
        run = s.get(Run, run_id)
        if not run:
            return
        for k, v in fields.items():
            setattr(run, k, v)
        s.commit()


def finish_run(run_id: str, status: str, error: str | None = None) -> None:
    update_run(run_id, status=status, error=error, finished_at=now())


def find_cached_version(conv_sha: str) -> str | None:
    """同一段对话已经提炼过且落过库，直接复用。"""
    with session_scope() as s:
        row = s.execute(
            select(Run.version_id)
            .where(Run.conv_sha256 == conv_sha, Run.version_id.is_not(None))
            .order_by(Run.created_at.desc())
        ).first()
        return row[0] if row else None


# ---------------- events ----------------

def append_event(run_id: str, event: str, data: dict) -> int:
    with session_scope() as s:
        last = s.execute(
            select(func.max(Event.seq)).where(Event.run_id == run_id)
        ).scalar()
        seq = int(last or 0) + 1
        s.add(Event(run_id=run_id, seq=seq, event=event,
                    data_json=json.dumps(data, ensure_ascii=False)))
        s.commit()
        return seq


def events_since(run_id: str, after: int = 0) -> list[tuple[int, str, str]]:
    with session_scope() as s:
        rows = s.execute(
            select(Event.seq, Event.event, Event.data_json)
            .where(Event.run_id == run_id, Event.seq > after)
            .order_by(Event.seq)
        ).all()
        return [(r[0], r[1], r[2]) for r in rows]


# ---------------- skills & versions ----------------

def list_skills() -> list[dict]:
    with session_scope() as s:
        skills = s.execute(select(Skill).order_by(Skill.updated_at.desc())).scalars().all()
        out = []
        for sk in skills:
            vcount = s.execute(
                select(func.count()).select_from(Version).where(Version.skill_id == sk.id)
            ).scalar() or 0
            out.append({
                "id": sk.id, "name": sk.name, "description": sk.description,
                "latest_v": sk.latest_v, "versions": vcount,
                "updated_at": sk.updated_at.isoformat(timespec="minutes"),
            })
        return out


def get_skill(skill_id: str) -> dict | None:
    with session_scope() as s:
        sk = s.get(Skill, skill_id)
        if not sk:
            return None
        latest = s.execute(
            select(Version).where(Version.skill_id == skill_id)
            .order_by(Version.version.desc())
        ).scalars().first()
        return {
            "id": sk.id, "name": sk.name, "description": sk.description,
            "latest_v": sk.latest_v,
            "latest": _version_dict(latest) if latest else None,
        }


def list_versions(skill_id: str) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Version).where(Version.skill_id == skill_id)
            .order_by(Version.version.desc())
        ).scalars().all()
        return [_version_dict(v, light=True) for v in rows]


def _version_dict(v: Version, light: bool = False) -> dict:
    d = {
        "id": v.id, "skill_id": v.skill_id, "version": v.version,
        "name": v.name, "description": v.description,
        "created_at": v.created_at.isoformat(timespec="minutes"),
        "diff": json.loads(v.diff_json or "[]"),
    }
    if not light:
        d["body"] = v.body
        d["clusters"] = json.loads(v.clusters_json or "{}")
        d["signals"] = json.loads(v.signals_json or "[]")
        d["preview"] = json.loads(v.preview_json or "{}")
    return d


def get_version(version_id: str) -> dict | None:
    with session_scope() as s:
        v = s.get(Version, version_id)
        return _version_dict(v) if v else None


def latest_version_of(skill_id: str) -> dict | None:
    with session_scope() as s:
        v = s.execute(
            select(Version).where(Version.skill_id == skill_id)
            .order_by(Version.version.desc())
        ).scalars().first()
        return _version_dict(v) if v else None


def save_version(
    *, skill_id: str | None, name: str, description: str, body: str,
    clusters: dict, signals: list[dict], diff: list[dict], run_id: str,
    create_new: bool = False,
) -> str:
    """落一条不可变版本快照。skill 不存在则创建。"""
    with session_scope() as s:
        skill = s.get(Skill, skill_id) if skill_id and not create_new else None
        if skill is None:
            skill = Skill(id=uuid4(), name=name, description=description, latest_v=0)
            s.add(skill)
            s.flush()

        latest = s.execute(
            select(func.max(Version.version)).where(Version.skill_id == skill.id)
        ).scalar() or 0

        ver = Version(
            id=uuid4(), skill_id=skill.id, version=int(latest) + 1,
            name=name, description=description, body=body,
            clusters_json=json.dumps(clusters, ensure_ascii=False),
            signals_json=json.dumps(signals, ensure_ascii=False),
            diff_json=json.dumps(diff, ensure_ascii=False),
            preview_json=json.dumps({"name": name, "description": description,
                                     "body": body}, ensure_ascii=False),
            run_ids_json=json.dumps([run_id]),
        )
        s.add(ver)
        skill.latest_v = int(latest) + 1
        skill.updated_at = now()
        skill.description = description
        s.commit()
        return ver.id


def delete_skill(skill_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(Version).where(Version.skill_id == skill_id))
        s.execute(delete(Skill).where(Skill.id == skill_id))
        s.commit()
