"""スマホからアクセスすべき URL の候補を洗い出す。

    python tools/net_check.py

PC に複数のネットワークアダプタ (Wi-Fi / 有線 / VPN / Hyper-V / WSL) がある場合、
起動時に表示される URL が目的のものとは限らないため、候補を全部並べる。
"""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import config as config_mod  # noqa: E402

cfg = config_mod.load()
port = cfg.server.port


def candidates() -> list[str]:
    found: list[str] = []

    # 既定の経路で外へ出る時に使われるアドレス（通常はこれが本命）
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        found.append(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()

    try:
        for addr in socket.gethostbyname_ex(socket.gethostname())[2]:
            if addr not in found:
                found.append(addr)
    except OSError:
        pass
    return found


def reachable(host: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.8)
        return sock.connect_ex((host, port)) == 0


def note(addr: str) -> str:
    if addr.startswith("127."):
        return "  (このPC専用。スマホからは使えません)"
    if addr.startswith("169.254."):
        return "  (アドレス取得に失敗している状態。使えません)"
    if addr.startswith(("172.1", "172.2", "172.3")):
        return "  (WSL / Hyper-V / Docker の仮想アダプタの可能性が高い)"
    if addr.startswith(("192.168.", "10.")):
        return "  ← 家庭内 LAN のアドレス。これが本命"
    return ""


print(f"待ち受けポート: {port}")
print(f"サーバ起動中: {'はい' if any(reachable(a) for a in candidates() + ['127.0.0.1']) else 'いいえ (先に run.bat を起動してください)'}")
print()
print("スマホで試す URL の候補:")
for addr in candidates():
    mark = "○" if reachable(addr) else "×"
    print(f"  [{mark}] http://{addr}:{port}/?token={cfg.server.token}{note(addr)}")

print()
print("※ [○] は『このPC自身から繋がる』という意味で、スマホから繋がる保証ではありません。")
print("   スマホで開けない場合は、管理者 PowerShell で次を実行してください:")
print(f'   New-NetFirewallRule -DisplayName "withAG" -Direction Inbound -Protocol TCP -LocalPort {port} -Action Allow -Profile Private,Domain')
