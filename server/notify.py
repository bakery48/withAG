"""ntfy を使ったスマホへのプッシュ通知（任意機能）。

ブラウザを閉じていても通知を受け取りたい場合に使う。
ntfy アプリでトピックを購読しておけば、そこへ本文が飛ぶ。
"""
from __future__ import annotations

import asyncio
import urllib.error
import urllib.request

from .config import NotifyConfig


class Notifier:
    def __init__(self, cfg: NotifyConfig):
        self.cfg = cfg
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.topic.strip())

    async def push(self, text: str, title: str | None = None, click: str | None = None) -> None:
        if not self.enabled:
            return
        await asyncio.to_thread(self._push_sync, text, title or self.cfg.title, click)

    def _push_sync(self, text: str, title: str, click: str | None) -> None:
        body = text[: self.cfg.max_chars]
        url = f"{self.cfg.server.rstrip('/')}/{self.cfg.topic.strip()}"
        req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
        # ヘッダは ASCII しか通らないので日本語タイトルは避け、本文側に寄せる
        req.add_header("Title", title.encode("ascii", "ignore").decode() or "Antigravity")
        req.add_header("Tags", "speech_balloon")
        if click:
            req.add_header("Click", click)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            self.last_error = None
        except (urllib.error.URLError, OSError) as exc:
            self.last_error = repr(exc)
            print(f"[notify] 送信失敗: {exc!r}")
