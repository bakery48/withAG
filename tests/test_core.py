"""依存を増やさずに動かせる単体テスト:  python -m unittest discover -s tests"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import WatchConfig  # noqa: E402
from server.parser import split_blocks, summarize  # noqa: E402
from server.watcher import ConversationWatcher, compute_delta  # noqa: E402
from server.win_input import WinInputError, parse_hotkey, VK  # noqa: E402


class ComputeDeltaTest(unittest.TestCase):
    def test_append(self):
        self.assertEqual(compute_delta("あいう", "あいうえお"), "えお")

    def test_no_change(self):
        self.assertEqual(compute_delta("same", "same"), "")

    def test_first_read(self):
        self.assertEqual(compute_delta("", "全部新しい"), "全部新しい")

    def test_rewrite_picks_added_lines(self):
        old = "1行目\n2行目\n"
        new = "1行目\n2行目\n3行目\n"
        self.assertEqual(compute_delta(old, new), "3行目\n")

    def test_rewrite_with_edit_in_middle(self):
        old = "a\nb\nc\n"
        new = "a\nB\nc\nd\n"
        delta = compute_delta(old, new)
        self.assertIn("B", delta)
        self.assertIn("d", delta)

    def test_truncated_file(self):
        # ファイルが短くなった場合でも落ちない
        self.assertEqual(compute_delta("a\nb\nc\n", "a\n"), "")


class ParserTest(unittest.TestCase):
    def test_markdown_headings(self):
        text = "## User\nこんにちは\n\n## Assistant\nはい、どうぞ\n"
        self.assertEqual(
            split_blocks(text),
            [{"role": "user", "text": "こんにちは"}, {"role": "assistant", "text": "はい、どうぞ"}],
        )

    def test_bold_label(self):
        blocks = split_blocks("**User:**\n質問です\n**Assistant:**\n回答です")
        self.assertEqual([b["role"] for b in blocks], ["user", "assistant"])

    def test_japanese_labels(self):
        blocks = split_blocks("### ユーザー\nあれ\n### アシスタント\nこれ")
        self.assertEqual([b["role"] for b in blocks], ["user", "assistant"])

    def test_default_role_when_no_heading(self):
        blocks = split_blocks("ただの本文")
        self.assertEqual(blocks, [{"role": "assistant", "text": "ただの本文"}])

    def test_code_block_is_not_treated_as_heading(self):
        text = "## Assistant\n```python\n# user\nprint(1)\n```\n"
        blocks = split_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertIn("print(1)", blocks[0]["text"])

    def test_empty(self):
        self.assertEqual(split_blocks("   \n\n"), [])

    def test_summarize(self):
        self.assertEqual(summarize("あ\n  い\tう"), "あ い う")
        self.assertTrue(summarize("x" * 200, limit=10).endswith("…"))


class HotkeyTest(unittest.TestCase):
    def test_combo(self):
        mods, main = parse_hotkey("ctrl+shift+l")
        self.assertEqual(mods, [VK["ctrl"], VK["shift"]])
        self.assertEqual(main, VK["l"])

    def test_single(self):
        mods, main = parse_hotkey("enter")
        self.assertEqual(mods, [])
        self.assertEqual(main, VK["enter"])

    def test_unknown(self):
        with self.assertRaises(WinInputError):
            parse_hotkey("ctrl+ほげ")


class WatcherTest(unittest.IsolatedAsyncioTestCase):
    async def _collect(self, prepare, write, *, load_existing=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Conversation.md"
            prepare(path)
            deltas: list[str] = []
            settled: list[str] = []
            cfg = WatchConfig(
                path=str(path), poll_interval_ms=50, settle_ms=200,
                load_existing_on_start=load_existing,
            )
            watcher = ConversationWatcher(
                cfg,
                on_delta=lambda t: _append(deltas, t),
                on_settle=lambda t: _append(settled, t),
            )
            watcher.start()
            await asyncio.sleep(0.2)
            write(path)
            await asyncio.sleep(0.8)
            await watcher.stop()
            return deltas, settled

    async def test_existing_content_is_not_replayed(self):
        deltas, settled = await self._collect(
            lambda p: p.write_text("## Assistant\n過去ログ\n", encoding="utf-8"),
            lambda p: p.open("a", encoding="utf-8").write("新しい応答\n"),
        )
        self.assertEqual(settled, ["新しい応答\n"])
        self.assertNotIn("過去ログ", "".join(deltas))

    async def test_existing_content_replayed_when_enabled(self):
        _deltas, settled = await self._collect(
            lambda p: p.write_text("過去ログ\n", encoding="utf-8"),
            lambda p: p.open("a", encoding="utf-8").write("新しい応答\n"),
            load_existing=True,
        )
        self.assertIn("過去ログ", "".join(settled))

    async def test_file_created_after_start(self):
        _deltas, settled = await self._collect(
            lambda p: None,
            lambda p: p.write_text("あとから作られた\n", encoding="utf-8"),
        )
        self.assertEqual(settled, ["あとから作られた\n"])

    async def test_streaming_chunks_are_merged_into_one_settle(self):
        async def write_twice(path: Path) -> None:
            pass

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Conversation.md"
            path.write_text("", encoding="utf-8")
            deltas: list[str] = []
            settled: list[str] = []
            cfg = WatchConfig(path=str(path), poll_interval_ms=50, settle_ms=300)
            watcher = ConversationWatcher(
                cfg,
                on_delta=lambda t: _append(deltas, t),
                on_settle=lambda t: _append(settled, t),
            )
            watcher.start()
            await asyncio.sleep(0.2)
            with path.open("a", encoding="utf-8") as fh:
                fh.write("前半")
            await asyncio.sleep(0.15)
            with path.open("a", encoding="utf-8") as fh:
                fh.write("後半\n")
            await asyncio.sleep(0.9)
            await watcher.stop()

        self.assertEqual(len(deltas), 2)
        self.assertEqual(settled, ["前半後半\n"])


async def _append(target: list[str], text: str) -> None:
    target.append(text)


if __name__ == "__main__":
    unittest.main()
