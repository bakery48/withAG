"""スマホから届いたテキストを Antigravity のチャット欄へ流し込む。"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .config import AntigravityConfig
from . import win_input as W


@dataclass
class InjectResult:
    ok: bool
    message: str
    window_title: str | None = None


class Injector:
    """ウィンドウ操作は同時に走らせると壊れるのでロックで直列化する。"""

    def __init__(self, cfg: AntigravityConfig):
        self.cfg = cfg
        self._lock = threading.Lock()

    # ---- 状態確認 -------------------------------------------------
    def find_target(self) -> tuple[int, str] | None:
        if not W.IS_WINDOWS:
            return None
        return W.find_window(self.cfg.window_title)

    def status(self) -> dict:
        if not W.IS_WINDOWS:
            return {"platform_ok": False, "window_found": False, "window_title": None,
                    "detail": "Windows 以外で動作中のため送信機能は無効です。"}
        target = self.find_target()
        return {
            "platform_ok": True,
            "window_found": target is not None,
            "window_title": target[1] if target else None,
            "detail": "OK" if target else f'"{self.cfg.window_title}" を含むウィンドウが見つかりません。',
        }

    # ---- 送信 -----------------------------------------------------
    def send(self, text: str) -> InjectResult:
        text = text.replace("\r\n", "\n").strip("\n")
        if not text.strip():
            return InjectResult(False, "空のテキストは送信できません。")
        if not W.IS_WINDOWS:
            return InjectResult(False, "Windows 以外では Antigravity へ送信できません。")

        with self._lock:
            try:
                return self._send_locked(text)
            except W.WinInputError as exc:
                return InjectResult(False, str(exc))
            except Exception as exc:  # 想定外も UI に見せて原因を追えるようにする
                return InjectResult(False, f"送信中に予期しないエラー: {exc!r}")

    def _send_locked(self, text: str) -> InjectResult:
        cfg = self.cfg
        target = self.find_target()
        if target is None:
            return InjectResult(False, f'"{cfg.window_title}" を含むウィンドウが見つかりません。Antigravity は起動していますか？')
        hwnd, title = target

        previous = W.get_foreground_window() if cfg.restore_foreground else 0

        if not W.focus_window(hwnd):
            return InjectResult(False, "Antigravity のウィンドウを前面にできませんでした。", title)
        time.sleep(cfg.focus_window_delay_ms / 1000)

        if cfg.focus_chat_hotkey.strip():
            W.send_hotkey(cfg.focus_chat_hotkey)
            time.sleep(cfg.focus_chat_delay_ms / 1000)

        backup = None
        if cfg.input_method == "paste":
            if cfg.restore_clipboard:
                try:
                    backup = W.get_clipboard_text()
                except W.WinInputError:
                    backup = None
            payload = text if cfg.allow_multiline else text.replace("\n", " ")
            W.set_clipboard_text(payload)
            W.send_hotkey("ctrl+v")
        else:
            if cfg.allow_multiline:
                W.type_text_with_soft_newline(text)
            else:
                W.type_text(text.replace("\n", " "))

        time.sleep(cfg.after_input_delay_ms / 1000)
        W.send_hotkey(cfg.submit_key)

        if backup is not None:
            time.sleep(0.15)  # 貼り付け完了前に戻すと空振りするので少し待つ
            try:
                W.set_clipboard_text(backup)
            except W.WinInputError:
                pass

        if cfg.restore_foreground and previous and previous != hwnd:
            time.sleep(0.1)
            W.focus_window(previous, timeout_ms=600)

        return InjectResult(True, "送信しました。", title)
