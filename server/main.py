"""withAG サーバ本体。

スマホ(ブラウザ) ⇄ このサーバ ⇄ Antigravity(ウィンドウ操作 / Conversation.md 監視)
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_mod
from .config import Config
from .injector import Injector
from .notify import Notifier
from .parser import split_blocks, summarize
from .store import History, Hub
from .watcher import ConversationWatcher

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
COOKIE_NAME = "withag_token"


def lan_ip() -> str:
    """スマホから叩くべき IP を推定する。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # 実際には送信しない
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def create_app(cfg: Config) -> FastAPI:
    history = History(cfg.history, cfg.history_path)
    history.load()
    hub = Hub()
    injector = Injector(cfg.antigravity)
    notifier = Notifier(cfg.notify)
    recent_sent: list[tuple[float, str]] = []  # 自分が送った文面（エコー除去用）

    def check_token(value: str | None) -> bool:
        return bool(value) and secrets.compare_digest(value, cfg.server.token)

    def require_token(request: Request) -> None:
        candidate = (
            request.query_params.get("token")
            or request.headers.get("x-token")
            or request.cookies.get(COOKIE_NAME)
        )
        if not check_token(candidate):
            raise HTTPException(status_code=401, detail="token が正しくありません。")

    def is_echo(text: str) -> bool:
        """Conversation.md 側に出てきた user 発言が、自分が送ったものかどうか。"""
        now = time.time()
        recent_sent[:] = [(ts, t) for ts, t in recent_sent if now - ts < 600]
        norm = " ".join(text.split())
        for _ts, sent in recent_sent:
            if norm and (norm == sent or norm in sent or sent in norm):
                return True
        return False

    # ---- 監視からのコールバック ---------------------------------
    async def on_delta(text: str) -> None:
        await hub.broadcast({"type": "delta", "text": text})

    async def on_settle(text: str) -> None:
        for block in split_blocks(text):
            if block["role"] == "user" and is_echo(block["text"]):
                continue
            item = await history.add(block["role"], block["text"], source="conversation")
            await hub.broadcast({"type": "message", "item": item})
            if block["role"] == "assistant":
                await notifier.push(summarize(block["text"], cfg.notify.max_chars))
        await hub.broadcast({"type": "settled"})

    async def on_watch_status(status: dict) -> None:
        await hub.broadcast({"type": "status", "watcher": status})

    watcher = ConversationWatcher(cfg.watch, on_delta, on_settle, on_watch_status)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watcher.start()
        scheme = "https" if cfg.server.ssl_certfile else "http"
        url = f"{scheme}://{lan_ip()}:{cfg.server.port}/?token={cfg.server.token}"
        print("=" * 70)
        print("  withAG 起動しました")
        print(f"  スマホでこの URL を開いてください: {url}")
        print(f"  監視対象: {cfg.watch.path}")
        print(f"  設定ファイル: {cfg.source_path}")
        if cfg.server.token == "change-me-please":
            print("  ⚠ token が初期値のままです。config.toml で変更してください。")
        print("=" * 70)
        try:
            yield
        finally:
            await watcher.stop()

    app = FastAPI(title="withAG", docs_url=None, redoc_url=None, lifespan=lifespan)

    # ---- 画面 -----------------------------------------------------
    if (WEB_DIR / "static").is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/")
    async def index(request: Request):
        response = FileResponse(WEB_DIR / "index.html")
        token = request.query_params.get("token")
        if check_token(token):
            # 一度正しい token で開けば、次回からは URL に付けなくてよい
            response.set_cookie(
                COOKIE_NAME, token, max_age=60 * 60 * 24 * 365,
                httponly=False, samesite="lax",
            )
        return response

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    # ---- API ------------------------------------------------------
    @app.get("/api/status")
    async def api_status(request: Request):
        require_token(request)
        return {
            "antigravity": injector.status(),
            "watcher": watcher.status(),
            "clients": hub.count,
            "notify": {"enabled": notifier.enabled, "last_error": notifier.last_error},
            "last_seq": history.last_seq,
            "server_time": time.time(),
        }

    @app.get("/api/windows")
    async def api_windows(request: Request):
        """window_title の設定を合わせるための一覧表示。"""
        require_token(request)
        from . import win_input as W

        if not W.IS_WINDOWS:
            return {"windows": [], "detail": "Windows 以外では取得できません。"}
        return {"windows": [{"hwnd": h, "title": t} for h, t in W.list_windows()]}

    @app.get("/api/history")
    async def api_history(request: Request, since: int = Query(0, ge=0)):
        require_token(request)
        return {"items": history.since(since), "last_seq": history.last_seq}

    @app.post("/api/send")
    async def api_send(request: Request, payload: dict = Body(...)):
        require_token(request)
        text = (payload.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text が空です。")

        item = await history.add("user", text, source="phone", pending=True)
        await hub.broadcast({"type": "message", "item": item})
        recent_sent.append((time.time(), " ".join(text.split())))

        result = await asyncio.to_thread(injector.send, text)
        await hub.broadcast({
            "type": "send_result",
            "seq": item["seq"],
            "ok": result.ok,
            "message": result.message,
        })
        if not result.ok:
            return JSONResponse(status_code=502, content={"ok": False, "detail": result.message, "seq": item["seq"]})
        return {"ok": True, "seq": item["seq"], "window": result.window_title}

    @app.post("/api/notify/test")
    async def api_notify_test(request: Request):
        require_token(request)
        if not notifier.enabled:
            raise HTTPException(status_code=400, detail="[notify] が無効です。config.toml を確認してください。")
        await notifier.push("withAG テスト通知")
        return {"ok": notifier.last_error is None, "last_error": notifier.last_error}

    # ---- WebSocket ------------------------------------------------
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, token: str | None = None, since: int = 0):
        candidate = token or ws.cookies.get(COOKIE_NAME)
        if not check_token(candidate):
            await ws.close(code=4401)
            return
        await ws.accept()
        await hub.register(ws)
        try:
            await ws.send_json({
                "type": "hello",
                "items": history.since(since),
                "last_seq": history.last_seq,
                "antigravity": injector.status(),
                "watcher": watcher.status(),
            })
            while True:
                # クライアントからは ping しか来ない想定。切断検知のために読み続ける。
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_json({"type": "pong", "t": time.time()})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await hub.unregister(ws)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="withAG: スマホから Antigravity を使うためのブリッジ")
    parser.add_argument("-c", "--config", help="設定ファイルのパス (既定: ./config.toml)")
    args = parser.parse_args()

    cfg = config_mod.load(args.config)
    app = create_app(cfg)

    import uvicorn

    uvicorn.run(
        app,
        host=cfg.server.host,
        port=cfg.server.port,
        log_level="info",
        ssl_certfile=cfg.server.ssl_certfile or None,
        ssl_keyfile=cfg.server.ssl_keyfile or None,
    )


if __name__ == "__main__":
    main()
