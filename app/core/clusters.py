from __future__ import annotations

from app.core.similarity import dedupe, normalize_key
from app.schemas import Clusters, Signal, SignalType

BUCKET_OF = {
    SignalType.PREFERENCE: "preferences",
    SignalType.CONSTRAINT: "constraints",
    SignalType.WORKFLOW: "workflows",
    SignalType.EXAMPLE: "examples",
}

PER_BUCKET_CAP = 12

# 约束优先级最高：同一句话既像约束又像偏好时，只留在约束里
PRIORITY = ["constraints", "workflows", "examples", "preferences"]


def cluster(signals: list[Signal]) -> Clusters:
    raw: dict[str, list[str]] = {
        "preferences": [], "constraints": [], "workflows": [], "examples": []
    }
    for sig in signals:
        raw[BUCKET_OF[sig.type]].append(sig.text)

    claimed: set[str] = set()
    result: dict[str, list[str]] = {}

    for bucket in PRIORITY:
        pool = [i for i in raw[bucket] if normalize_key(i) not in claimed]
        items = dedupe(pool)[:PER_BUCKET_CAP]
        result[bucket] = items
        claimed.update(normalize_key(i) for i in items)

    return Clusters(**result)


def explain(clusters: Clusters) -> str:
    parts = []
    for label, key in (("约束", "constraints"), ("工作流", "workflows"),
                       ("偏好", "preferences"), ("示例", "examples")):
        n = len(getattr(clusters, key))
        if n:
            parts.append(f"{label} {n}")
    return " · ".join(parts) or "无"
