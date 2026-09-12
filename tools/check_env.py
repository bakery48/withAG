"""起動前の環境チェック。run.bat から呼ばれる。

終了コード: 0=OK / 1=依存パッケージが足りない / 2=Python のバージョンが古い
"""
import sys

if sys.version_info < (3, 10):
    print(f"[withAG] Python 3.10 以上が必要です（現在: {sys.version.split()[0]}）。")
    sys.exit(2)

missing = []
for module in ("fastapi", "uvicorn"):
    try:
        __import__(module)
    except ImportError:
        missing.append(module)

if sys.version_info < (3, 11):
    try:
        __import__("tomli")
    except ImportError:
        missing.append("tomli")

if missing:
    print(f"[withAG] 不足しているパッケージ: {', '.join(missing)}")
    sys.exit(1)
sys.exit(0)
