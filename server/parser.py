"""Conversation.md の差分テキストを「誰の発言か」で切り分ける。

Antigravity が書き出す書式は環境によって変わりうるので、
よくある見出しパターンを広めに拾い、判別できない場合は assistant 扱いにする。
"""
from __future__ import annotations

import re

USER_WORDS = r"user|human|you|me|prompt|request|ユーザー|ユーザ|あなた|質問"
AI_WORDS = r"assistant|ai|antigravity|cascade|agent|model|gemini|response|answer|アシスタント|回答|応答"

# 例: "## User", "### Assistant", "**User:**", "User:", "---- User ----"
_HEADING = re.compile(
    rf"^\s*(?:#{{1,6}}\s*|\*{{1,2}}|-{{2,}}\s*|>\s*)?"
    rf"(?P<role>{USER_WORDS}|{AI_WORDS})"
    rf"[\s*:：_\-#]*$",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*(?:```|~~~)")


def _role_of(word: str) -> str:
    return "user" if re.fullmatch(USER_WORDS, word, re.IGNORECASE) else "assistant"


def split_blocks(text: str, default_role: str = "assistant") -> list[dict]:
    """テキストを [{role, text}, ...] に分割する。空要素は落とす。"""
    if not text.strip():
        return []

    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[dict] = []
    role = default_role
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip("\n")
        if body.strip():
            blocks.append({"role": role, "text": body})
        buf.clear()

    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            # コードブロックの中身は見出し判定しない
            in_fence = not in_fence
            buf.append(line)
            continue
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            role = _role_of(m.group("role"))
            continue
        buf.append(line)
    flush()
    return blocks or [{"role": default_role, "text": text.strip()}]


def summarize(text: str, limit: int = 120) -> str:
    """通知用に 1 行へ潰す。"""
    flat = re.sub(r"\s+", " ", text.replace("```", "")).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
