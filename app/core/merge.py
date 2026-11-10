from __future__ import annotations

from app.core.similarity import similarity
from app.schemas import DiffEntry, Signal


def merge(
    old: list[Signal], new: list[Signal], threshold: float = 0.80
) -> tuple[list[Signal], list[DiffEntry]]:
    """按 sid 精匹配 + 文本相似度模糊匹配，产出合并结果与变化清单。

    原则：默认不删除。旧版有、新版没提到的条目只标记为 orphan，
    交给用户确认 —— 误删一条约束的代价远高于多留一条。
    """
    by_sid = {s.sid: s for s in old}
    matched_old: dict[str, str] = {}      # old.sid -> new.text
    added: list[Signal] = []
    modified: list[DiffEntry] = []

    for ns in new:
        hit = by_sid.get(ns.sid)
        if hit is None:
            best_sid, best_sim = None, 0.0
            for osig in old:
                r = similarity(ns.text, osig.text)
                if r > best_sim:
                    best_sid, best_sim = osig.sid, r
            if best_sid and best_sim >= threshold:
                hit = by_sid[best_sid]

        if hit is None:
            added.append(ns)
            continue

        matched_old[hit.sid] = ns.text
        if ns.text.strip() != hit.text.strip():
            modified.append(DiffEntry(kind="modified", text=ns.text, old=hit.text, sid=hit.sid))

    merged: list[Signal] = []
    for osig in old:
        new_text = matched_old.get(osig.sid)
        if new_text is not None and new_text.strip() != osig.text.strip():
            merged.append(osig.model_copy(update={"text": new_text, "verified": osig.verified}))
        else:
            merged.append(osig)
    merged.extend(added)

    diff: list[DiffEntry] = [DiffEntry(kind="added", text=s.text, sid=s.sid) for s in added]
    diff.extend(modified)
    for osig in old:
        if osig.sid not in matched_old:
            diff.append(DiffEntry(kind="orphan", text=osig.text, sid=osig.sid))

    return merged, diff


def summarize(diff: list[DiffEntry]) -> str:
    a = sum(1 for d in diff if d.kind == "added")
    m = sum(1 for d in diff if d.kind == "modified")
    o = sum(1 for d in diff if d.kind == "orphan")
    parts = []
    if a:
        parts.append(f"+{a} 条")
    if m:
        parts.append(f"改 {m} 条")
    if o:
        parts.append(f"未提及 {o} 条")
    return " · ".join(parts) or "无变化"
