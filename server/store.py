"""会話履歴の保持と、WebSocket クライアントへの配信。"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from .config import HistoryConfig


class History:
    def __init__(self, cfg: HistoryConfig, path: Path):
        self.cfg = cfg
        self.path = path
        self.items: deque[dict] = deque(maxlen=cfg.max_items)
        self._seq = 0
        self._lock = asyncio.Lock()

    def load(self) -> None:
        if not self.path.exists():
            return
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        for row in rows[-self.cfg.max_items:]:
            self.items.append(row)
            self._seq = max(self._seq, int(row.get("seq", 0)))

    async def add(self, role: str, text: str, **extra: Any) -> dict:
        async with self._lock:
            self._seq += 1
            item = {"seq": self._seq, "ts": time.time(), "role": role, "text": text, **extra}
            self.items.append(item)
            await asyncio.to_thread(self._append_file, item)
            return item

    def _append_file(self, item: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"[history] 書き込み失敗: {exc!r}")

    def since(self, seq: int = 0) -> list[dict]:
        return [it for it in self.items if it["seq"] > seq]

    @property
    def last_seq(self) -> int:
        return self._seq


class Hub:
    """接続中の WebSocket をまとめて扱う。"""

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict) -> None:
        async with self._lock:
            targets: Iterable[Any] = list(self._clients)
        dead = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
