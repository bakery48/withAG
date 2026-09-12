"""現在開いているウィンドウのタイトル一覧を表示する。

config.toml の [antigravity] window_title に何を書けばよいか調べる用。
    python tools/list_windows.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import win_input as W  # noqa: E402

if not W.IS_WINDOWS:
    raise SystemExit("Windows 上で実行してください。")

for hwnd, title in W.list_windows():
    print(f"{hwnd:>10}  {title}")
