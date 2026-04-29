"""Toggle 'Start with Windows' qua HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.

HKCU = không cần admin để ghi (khác HKLM). Rollback đơn giản: xoá value.
Không crash app nếu lỗi quyền — chỉ trả False + log.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:  # non-Windows dev env
    winreg = None  # type: ignore[assignment]


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PingOverlay"


def _exe_target() -> str:
    """Path tuyệt đối để registry trỏ tới — quoted để tolerate space."""
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).resolve()
    else:
        # Dev mode: trỏ tới python -m main không bền, nên không khuyến khích
        # autostart trong dev. Vẫn ghi pythonw.exe + main.py để debug.
        py = Path(sys.executable).resolve()
        script = Path(__file__).resolve().parent / "main.py"
        return f'"{py}" "{script}"'
    return f'"{p}"'


def is_supported() -> bool:
    return winreg is not None


def is_enabled() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                            winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, _exe_target())
        return True
    except OSError as e:
        print(f"[autostart] enable failed: {e}")
        return False


def disable() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                            winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, VALUE_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError as e:
        print(f"[autostart] disable failed: {e}")
        return False


def sync(desired: bool) -> bool:
    """Đảm bảo registry khớp với `desired`. Trả True nếu đã thực sự khớp."""
    cur = is_enabled()
    if cur == desired:
        return True
    return enable() if desired else disable()
