"""Windows のキーボード入力・クリップボード・ウィンドウ操作 (ctypes だけで実装)。

外部ライブラリ(pyautogui 等)に依存しないぶん、環境構築が pip install fastapi だけで済む。
Windows 以外では import はできるが、実行すると RuntimeError になる。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # 他 OS でも import だけは通す（開発・テスト用）
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]


class WinInputError(RuntimeError):
    pass


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise WinInputError("この機能は Windows 上でのみ利用できます。")


# --------------------------------------------------------------------------
# SendInput 用の構造体定義
# --------------------------------------------------------------------------
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    # 3 つ全部を定義しないと sizeof(INPUT) が Windows 側と食い違い SendInput が失敗する
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


# --------------------------------------------------------------------------
# 仮想キーコード
# --------------------------------------------------------------------------
VK = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "shift": 0x10,
    "win": 0x5B, "super": 0x5B, "meta": 0x5B,
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08, "bs": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D,
}
for _i in range(1, 25):  # F1〜F24
    VK[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)

MODIFIERS = {"ctrl", "control", "alt", "menu", "shift", "win", "super", "meta"}
# 拡張キー扱いが必要なもの（テンキーと区別するため）
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B}


def parse_hotkey(spec: str) -> tuple[list[int], int | None]:
    """"ctrl+shift+l" -> ([VK_CONTROL, VK_SHIFT], VK_L) の形にほぐす。"""
    mods: list[int] = []
    main: int | None = None
    for raw in spec.replace(" ", "").lower().split("+"):
        if not raw:
            continue
        if raw not in VK:
            raise WinInputError(f"未知のキー名です: {raw!r} (指定: {spec!r})")
        if raw in MODIFIERS:
            mods.append(VK[raw])
        else:
            main = VK[raw]
    return mods, main


def _send(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise WinInputError(f"SendInput に失敗しました (err={ctypes.get_last_error()})")


def _key_input(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, 0)
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return item


def send_hotkey(spec: str, hold_ms: int = 20) -> None:
    """"ctrl+v" のような文字列を実際のキー操作として送る。"""
    _require_windows()
    mods, main = parse_hotkey(spec)
    down = [_key_input(vk, False) for vk in mods]
    if main is not None:
        down.append(_key_input(main, False))
    _send(down)
    time.sleep(hold_ms / 1000)
    up: list[INPUT] = []
    if main is not None:
        up.append(_key_input(main, True))
    up.extend(_key_input(vk, True) for vk in reversed(mods))
    _send(up)


def _unicode_inputs(ch: str) -> list[INPUT]:
    items: list[INPUT] = []
    data = ch.encode("utf-16-le")  # サロゲートペアは 2 ユニットに分かれる
    for idx in range(0, len(data), 2):
        unit = int.from_bytes(data[idx:idx + 2], "little")
        for up in (False, True):
            item = INPUT(type=INPUT_KEYBOARD)
            item.ki = KEYBDINPUT(
                wVk=0,
                wScan=unit,
                dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
                time=0,
                dwExtraInfo=0,
            )
            items.append(item)
    return items


def type_text(text: str, chunk: int = 20, delay_ms: int = 5) -> None:
    """IME を介さず Unicode を直接流し込む（日本語もそのまま入る）。

    改行は Enter を押したのと同じ扱いになり送信されてしまうため、
    呼び出し側で shift+enter に置き換えるなどの前処理をしておくこと。
    """
    _require_windows()
    buf: list[INPUT] = []
    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            buf.extend([_key_input(VK["enter"], False), _key_input(VK["enter"], True)])
        else:
            buf.extend(_unicode_inputs(ch))
        if len(buf) >= chunk * 2:
            _send(buf)
            buf = []
            time.sleep(delay_ms / 1000)
    _send(buf)


def type_text_with_soft_newline(text: str, newline_key: str = "shift+enter") -> None:
    """改行を「送信しない改行キー」に置き換えつつ入力する。"""
    _require_windows()
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if i:
            send_hotkey(newline_key)
            time.sleep(0.01)
        if line:
            type_text(line)


# --------------------------------------------------------------------------
# クリップボード
# --------------------------------------------------------------------------
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _open_clipboard(retries: int = 10, wait_ms: int = 50) -> None:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return
        time.sleep(wait_ms / 1000)
    raise WinInputError("クリップボードを開けませんでした（他のアプリが掴んでいます）。")


def get_clipboard_text() -> str | None:
    _require_windows()
    _open_clipboard()
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.c_wchar_p(ptr).value
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    _require_windows()
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.restype = ctypes.c_void_p
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not handle:
        raise WinInputError("クリップボード用メモリの確保に失敗しました。")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise WinInputError("クリップボード用メモリのロックに失敗しました。")
    ctypes.memmove(ptr, ctypes.byref(data), size)
    kernel32.GlobalUnlock(handle)

    _open_clipboard()
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise WinInputError("クリップボードへの書き込みに失敗しました。")
        # 成功した場合の handle の所有権は OS 側に移るので Free しない
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# ウィンドウ
# --------------------------------------------------------------------------
SW_RESTORE = 9
ASFW_ANY = -1

if IS_WINDOWS:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
else:  # pragma: no cover
    WNDENUMPROC = None  # type: ignore[assignment]


def list_windows() -> list[tuple[int, str]]:
    """可視ウィンドウの (hwnd, タイトル) 一覧。"""
    _require_windows()
    found: list[tuple[int, str]] = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        found.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def find_window(title_substring: str) -> tuple[int, str] | None:
    """タイトルに指定文字列を含むウィンドウを探す（大文字小文字は無視）。"""
    needle = title_substring.lower()
    matches = [(h, t) for h, t in list_windows() if needle in t.lower()]
    if not matches:
        return None
    # 同名が複数ある場合はタイトルが短い＝メインウィンドウである事が多い
    matches.sort(key=lambda x: len(x[1]))
    return matches[0]


def get_foreground_window() -> int:
    _require_windows()
    return int(user32.GetForegroundWindow() or 0)


def focus_window(hwnd: int, timeout_ms: int = 1500) -> bool:
    """対象ウィンドウを前面に持ってくる。成功したら True。"""
    _require_windows()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    user32.AllowSetForegroundWindow(ASFW_ANY)
    cur_tid = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)

    attached: list[int] = []
    try:
        for tid in {fg_tid, target_tid}:
            if tid and tid != cur_tid and user32.AttachThreadInput(cur_tid, tid, True):
                attached.append(tid)
        # フォアグラウンド制限を緩めるための Alt 空打ち
        _send([_key_input(VK["alt"], False), _key_input(VK["alt"], True)])
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        for tid in attached:
            user32.AttachThreadInput(cur_tid, tid, False)

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if int(user32.GetForegroundWindow() or 0) == hwnd:
            return True
        time.sleep(0.03)
    return int(user32.GetForegroundWindow() or 0) == hwnd
