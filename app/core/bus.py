from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    """进程内发布订阅：SSE 端点订阅某个 run 的事件队列。"""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subs[run_id].discard(q)
        if not self._subs[run_id]:
            self._subs.pop(run_id, None)

    def publish(self, run_id: str, message: dict[str, Any]) -> None:
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass


bus = EventBus()
