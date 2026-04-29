"""Global Win32 hotkey via RegisterHotKey + message loop trong thread riêng.

KHÔNG dùng thư viện ngoài (không 'keyboard', 'pynput'). Chỉ ctypes -> user32.
Chạy hoàn toàn trong thread daemon: mỗi RegisterHotKey neo vào thread đăng ký
nó, nên thread phải có message pump (PeekMessage/GetMessage).

Hỗ trợ modifiers: ctrl, alt, shift, win.
Key: ký tự ASCII A-Z / 0-9 hoặc tên virtual key đặc biệt ('F1'..'F24', 'SPACE',
'TAB', 'ESC', 'ENTER', 'INSERT', 'DELETE', 'HOME', 'END', 'PAGEUP', 'PAGEDOWN').
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Iterable


# Mod flags (RegisterHotKey)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # Win7+: không lặp khi giữ phím

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MOD_MAP = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}

# Một số virtual-key codes hay dùng (Microsoft docs)
_VK_NAMED = {
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "ENTER": 0x0D, "RETURN": 0x0D,
    "INSERT": 0x2D, "INS": 0x2D,
    "DELETE": 0x2E, "DEL": 0x2E,
    "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PGUP": 0x21,
    "PAGEDOWN": 0x22, "PGDN": 0x22,
    "BACKSPACE": 0x08, "BACK": 0x08,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
}
for i in range(1, 25):  # F1..F24
    _VK_NAMED[f"F{i}"] = 0x70 + (i - 1)


def _resolve_modifiers(mods: Iterable[str]) -> int:
    flags = 0
    for m in mods or []:
        v = _MOD_MAP.get(str(m).strip().lower())
        if v:
            flags |= v
    return flags | MOD_NOREPEAT


def _resolve_vk(key: str) -> int | None:
    if not key:
        return None
    s = str(key).strip().upper()
    if s in _VK_NAMED:
        return _VK_NAMED[s]
    if len(s) == 1:
        ch = s[0]
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    return None


class GlobalHotkey:
    """Đăng ký 1 hotkey toàn hệ thống.

    on_pressed được gọi từ thread message loop. KHÔNG đụng Tk widget trực tiếp
    trong callback — phải marshal về Tk thread bằng overlay.root.after(0, ...).
    """

    def __init__(self, modifiers: Iterable[str], key: str,
                 on_pressed: Callable[[], None], hotkey_id: int = 1):
        self._mods = _resolve_modifiers(modifiers)
        self._vk = _resolve_vk(key)
        self._on_pressed = on_pressed
        self._id = int(hotkey_id)
        self._thread: threading.Thread | None = None
        self._tid: int | None = None
        self._registered = False
        self._stopped = threading.Event()
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    @property
    def is_valid(self) -> bool:
        return self._vk is not None

    def start(self) -> bool:
        """Spawn thread + register. Trả True nếu đăng ký thành công."""
        if not self.is_valid:
            print(f"[hotkey] invalid key spec; skip register")
            return False
        ready = threading.Event()
        ok_flag = {"v": False}

        def _run():
            self._tid = self._kernel32.GetCurrentThreadId()
            ok = bool(self._user32.RegisterHotKey(
                None, self._id, self._mods, self._vk
            ))
            self._registered = ok
            ok_flag["v"] = ok
            ready.set()
            if not ok:
                err = ctypes.get_last_error()
                print(f"[hotkey] RegisterHotKey failed (err={err})")
                return
            try:
                msg = wintypes.MSG()
                while not self._stopped.is_set():
                    # GetMessage trả 0 khi WM_QUIT, -1 nếu lỗi
                    rc = self._user32.GetMessageW(
                        ctypes.byref(msg), None, 0, 0
                    )
                    if rc in (0, -1):
                        break
                    if msg.message == WM_HOTKEY and msg.wParam == self._id:
                        try:
                            self._on_pressed()
                        except Exception as e:
                            print(f"[hotkey] callback error: {e}")
                    self._user32.TranslateMessage(ctypes.byref(msg))
                    self._user32.DispatchMessageW(ctypes.byref(msg))
            finally:
                try:
                    self._user32.UnregisterHotKey(None, self._id)
                except Exception:
                    pass
                self._registered = False

        t = threading.Thread(target=_run, daemon=True, name="HotkeyThread")
        t.start()
        self._thread = t
        ready.wait(timeout=2.0)
        return ok_flag["v"]

    def stop(self) -> None:
        self._stopped.set()
        if self._tid:
            try:
                # Đẩy WM_QUIT vào message queue của thread hotkey để GetMessage thoát
                self._user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass

    def describe(self) -> str:
        """Hiển thị 'Ctrl+Shift+P' kiểu cho menu."""
        labels = []
        m = self._mods
        if m & MOD_CONTROL: labels.append("Ctrl")
        if m & MOD_ALT:     labels.append("Alt")
        if m & MOD_SHIFT:   labels.append("Shift")
        if m & MOD_WIN:     labels.append("Win")
        if self._vk is None:
            return "+".join(labels) + "+?" if labels else "(invalid)"
        # Tên ngược lại
        name = None
        for k, v in _VK_NAMED.items():
            if v == self._vk:
                name = k
                break
        if name is None:
            name = chr(self._vk) if 0x20 <= self._vk <= 0x7E else f"VK_{self._vk:#x}"
        return "+".join(labels + [name])
