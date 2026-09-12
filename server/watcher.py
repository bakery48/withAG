"""Conversation.md を監視して差分を配信する。"""
from __future__ import annotations

import asyncio
import difflib
import time
from pathlib import Path
from typing import Awaitable, Callable

from .config import WatchConfig


def compute_delta(old: str, new: str) -> str:
    """old から new への「増えた部分」を取り出す。

    追記されただけなら末尾を切り出す。ファイルごと書き換えられた場合は
    行単位の差分から追加行だけを拾う。
    """
    if not old:
        return new
    if new.startswith(old):
        return new[len(old):]

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    added: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(new_lines[j1:j2])
    return "".join(added)


class ConversationWatcher:
    """ポーリング方式。エディタ系アプリの書き込みは通知が飛ばない事があるので
    inotify/watchdog ではなく単純な定期チェックにしている。"""

    def __init__(
        self,
        cfg: WatchConfig,
        on_delta: Callable[[str], Awaitable[None]],
        on_settle: Callable[[str], Awaitable[None]],
        on_status: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self.cfg = cfg
        self.path = Path(cfg.path)
        self.on_delta = on_delta
        self.on_settle = on_settle
        self.on_status = on_status

        self._content = ""
        self._pending = ""
        self._last_change = 0.0
        self._signature: tuple[int, float] | None = None
        self._exists: bool | None = None
        # 起動時点でファイルが無い場合は「過去ログ」も存在しないので、
        # 後から作られた内容は最初から全部配信してよい。
        self._primed = not self.path.exists()
        self._task: asyncio.Task | None = None
        self.last_update_at: float | None = None

    # ---- ライフサイクル -------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="conversation-watcher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "size": self.path.stat().st_size if self.path.exists() else 0,
            "streaming": bool(self._pending),
            "last_update_at": self.last_update_at,
        }

    # ---- 本体 -----------------------------------------------------
    async def _run(self) -> None:
        interval = max(self.cfg.poll_interval_ms, 50) / 1000
        settle = max(self.cfg.settle_ms, 200) / 1000
        while True:
            try:
                await self._tick(settle)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 監視は止めない
                print(f"[watcher] エラー: {exc!r}")
            await asyncio.sleep(interval)

    async def _tick(self, settle: float) -> None:
        exists = self.path.exists()
        if exists != self._exists:
            self._exists = exists
            if not exists:
                # 会話がリセットされてファイルが作り直されるケース。
                # 基準を捨てて、次に現れた内容は新しい会話として扱う。
                self._content = ""
                self._signature = None
                self._primed = True
            if self.on_status:
                await self.on_status(self.status())
        if not exists:
            return

        stat = self.path.stat()
        signature = (stat.st_size, stat.st_mtime)
        if signature != self._signature:
            self._signature = signature
            content = await asyncio.to_thread(self._read)
            if not self._primed:
                # 起動時点で既にある中身は「過去ログ」なので原則配信しない。
                # ここで基準を作っておかないと、最初の応答を取りこぼす。
                self._primed = True
                if not self.cfg.load_existing_on_start:
                    self._content = content
                    return
            if content != self._content:
                delta = compute_delta(self._content, content)
                self._content = content
                if delta.strip():
                    self._pending += delta
                    self._last_change = time.time()
                    self.last_update_at = self._last_change
                    await self.on_delta(delta)

        if self._pending and (time.time() - self._last_change) >= settle:
            text, self._pending = self._pending, ""
            await self.on_settle(text)

    def _read(self) -> str:
        try:
            return self.path.read_text(encoding=self.cfg.encoding, errors="replace")
        except FileNotFoundError:
            return self._content
        except PermissionError:
            # 書き込み中に掴めない事があるので次のポーリングに任せる
            return self._content
