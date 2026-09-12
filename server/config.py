"""config.toml の読み込みと既定値の管理。"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    print("Python 3.11 以上が必要です。", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    token: str = "change-me-please"
    ssl_certfile: str = ""
    ssl_keyfile: str = ""


@dataclass
class WatchConfig:
    path: str = ""
    encoding: str = "utf-8"
    poll_interval_ms: int = 400
    settle_ms: int = 1500
    load_existing_on_start: bool = False


@dataclass
class AntigravityConfig:
    window_title: str = "Antigravity"
    focus_chat_hotkey: str = "ctrl+shift+l"
    input_method: str = "paste"
    submit_key: str = "enter"
    focus_window_delay_ms: int = 300
    focus_chat_delay_ms: int = 250
    after_input_delay_ms: int = 150
    restore_clipboard: bool = True
    restore_foreground: bool = True
    allow_multiline: bool = True


@dataclass
class NotifyConfig:
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str = ""
    title: str = "Antigravity"
    max_chars: int = 300


@dataclass
class HistoryConfig:
    file: str = "data/history.jsonl"
    max_items: int = 500


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    antigravity: AntigravityConfig = field(default_factory=AntigravityConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    source_path: Path | None = None

    @property
    def history_path(self) -> Path:
        p = Path(self.history.file)
        return p if p.is_absolute() else ROOT / p


def _fill(cls, data: dict[str, Any]):
    """既知のキーだけを拾ってデータクラスを作る（未知キーは無視）。"""
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = set(data) - known
    for key in sorted(unknown):
        print(f"[config] 未知の設定キーを無視します: {cls.__name__}.{key}")
    return cls(**{k: v for k, v in data.items() if k in known})


def find_config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WITHAG_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return ROOT / "config.toml"


def load(explicit: str | None = None) -> Config:
    path = find_config_path(explicit)
    if not path.exists():
        example = ROOT / "config.example.toml"
        raise SystemExit(
            f"設定ファイルが見つかりません: {path}\n"
            f"まず `copy {example.name} config.toml` してから編集してください。"
        )
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    cfg = Config(
        server=_fill(ServerConfig, raw.get("server", {})),
        watch=_fill(WatchConfig, raw.get("watch", {})),
        antigravity=_fill(AntigravityConfig, raw.get("antigravity", {})),
        notify=_fill(NotifyConfig, raw.get("notify", {})),
        history=_fill(HistoryConfig, raw.get("history", {})),
        source_path=path,
    )

    # 環境変数による上書き（起動スクリプトから一時的に変えたい時用）
    if os.environ.get("WITHAG_PORT"):
        cfg.server.port = int(os.environ["WITHAG_PORT"])
    if os.environ.get("WITHAG_TOKEN"):
        cfg.server.token = os.environ["WITHAG_TOKEN"]
    if os.environ.get("WITHAG_WATCH_PATH"):
        cfg.watch.path = os.environ["WITHAG_WATCH_PATH"]

    if not cfg.watch.path:
        raise SystemExit("[watch] path が空です。Conversation.md のフルパスを設定してください。")
    if cfg.antigravity.input_method not in ("paste", "type"):
        raise SystemExit('[antigravity] input_method は "paste" か "type" のどちらかです。')
    return cfg
