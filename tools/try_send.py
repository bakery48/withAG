"""スマホを使わずに、Antigravity への送信だけを試すツール。

    python tools/try_send.py "テスト送信です"

ショートカットや待ち時間の設定を詰める時に使う。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import config as config_mod  # noqa: E402
from server.injector import Injector  # noqa: E402

text = " ".join(sys.argv[1:]) or "withAG テスト送信"
cfg = config_mod.load()
injector = Injector(cfg.antigravity)

status = injector.status()
print(f"ウィンドウ検出: {status}")
print("3 秒後に送信します。Antigravity を開いたまま待ってください…")
import time  # noqa: E402

time.sleep(3)
result = injector.send(text)
print(f"結果: ok={result.ok} / {result.message}")
