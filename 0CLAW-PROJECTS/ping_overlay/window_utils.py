"""Tìm cửa sổ chính của process theo PID và lấy toạ độ client area."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_POPUP = 0x80000000

MONITOR_DEFAULTTONEAREST = 2


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_hwnd_for_pid(pid: int) -> int | None:
    """Trả về HWND chính của process: cửa sổ visible, top-level (không
    có owner), và có DIỆN TÍCH LỚN NHẤT. Không còn yêu cầu title text
    vì nhiều game (UE) để title rỗng khi in-game / loading.
    """
    best: list[int] = [0, 0]  # [hwnd, area]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        # Top-level = không có owner
        owner = user32.GetWindow(hwnd, 4)  # GW_OWNER
        if owner:
            return True
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        if area <= 0:
            return True
        if area > best[1]:
            best[0] = hwnd
            best[1] = area
        return True

    user32.EnumWindows(cb, 0)
    return best[0] or None


def get_window_area(hwnd: int) -> int:
    """Diện tích (pixel^2) của window rect; 0 nếu lỗi."""
    try:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return 0
        return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
    except Exception:
        return 0


def is_borderless_window(hwnd: int) -> bool:
    """True nếu cửa sổ ở chế độ borderless (fullscreen borderless window):
    - Không có WS_CAPTION và WS_THICKFRAME (không title bar, không border resize)
    - Kích thước phủ toàn bộ monitor mà nó đang nằm trên
    """
    try:
        user32.GetWindowLongW.restype = ctypes.c_long
        style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    except Exception:
        return False
    if style & WS_CAPTION:
        return False
    if style & WS_THICKFRAME:
        return False

    # Kích thước cửa sổ phải phủ monitor
    wrect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(wrect)):
        return False
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not mon:
        return False
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return False
    mr = mi.rcMonitor
    # Điều kiện: window phủ >= 95% diện tích monitor.
    # Exclusive fullscreen và borderless đều đạt; windowed-with-border
    # có WS_CAPTION đã bị loại ở trên.
    mw = mr.right - mr.left
    mh = mr.bottom - mr.top
    ww = max(0, wrect.right - wrect.left)
    wh = max(0, wrect.bottom - wrect.top)
    if mw <= 0 or mh <= 0:
        return False
    cover = (min(ww, mw) * min(wh, mh)) / float(mw * mh)
    return cover >= 0.95


def get_client_topleft_size(hwnd: int) -> tuple[int, int, int, int] | None:
    """Trả về (x, y, w, h) của client area trên toạ độ màn hình."""
    try:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return pt.x, pt.y, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return None
