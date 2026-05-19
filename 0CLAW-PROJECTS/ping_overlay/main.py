"""
PingOverlay — Latency / Packet Loss / FPS của process game đã chọn.

Flow:
  1. Dialog chọn process (.exe)
  2. Quét netstat -> geolocate -> chọn Server (city)
  3. Overlay bám sát góc trên-trái client area của cửa sổ game,
     hiển thị Latency / Loss / FPS.

ANTI-CHEAT:
  - Overlay là Win32 window độc lập, KHÔNG inject/hook vào game.
  - FPS lấy qua PresentMon (Intel GameTechDev), cơ chế ETW, KHÔNG inject.
    Cùng cách CapFrameX/FrameView dùng — an toàn với EAC/BattlEye/ACE.
  - Ứng dụng cần chạy với quyền Administrator:
      * ping3 raw socket
      * ETW session của PresentMon
"""
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import ctypes
import types
import webbrowser
from collections import deque
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk
from pathlib import Path

import ping3
import psutil
from PIL import Image, ImageDraw, ImageTk
import pystray

from net_utils import (
    established_remote_ips,
    gameplay_remote_ips,
    persistent_remote_ips,
    active_traffic_ips,
    gameplay_traffic_ips,
    active_server_endpoints,
    find_accelerators,
    all_established_by_pid,
    all_remote_ips_by_pid,
    wait_for_lobby,
    scan_cities,
)
from overlay import Overlay
from window_utils import get_hwnd_for_pid, get_client_topleft_size, get_window_area
from fps import FpsMonitor

import config as app_config
from app_version import __version__
from hotkey import GlobalHotkey
import autostart
from metrics import MemoryMonitor, RollingWindow, fmt_ratio_bytes_pct
from system_tweaks import GameTweaksManager, TWEAK_CARDS
from events import EventAlert, EventMonitor, normalize_guild_id
import license_admin
from ui_runtime import (
    apply_custom_cursor,
    bind_ui_click_sound,
    play_ui_alert,
    play_ui_click,
    restore_system_cursor,
    set_custom_cursor,
)
from updater import (
    check_for_update,
    check_incremental_update,
    cleanup_stale_update_artifacts,
    download_incremental_from_repo,
    download_update,
    install_downloaded_update,
    install_incremental_update,
    install_via_installer_setup,
    is_onedir_install,
    is_supported_runtime,
)


# Process KHÔNG được coi là game
PROCESS_BLACKLIST = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "discord.exe", "slack.exe", "teams.exe", "msteams.exe", "spotify.exe",
    "zalo.exe", "telegram.exe", "whatsapp.exe", "zoom.exe", "skype.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "epicwebhelper.exe",
    "eadesktop.exe", "origin.exe", "battle.net.exe", "battlenet.exe",
    "uplay.exe", "ubisoftconnect.exe", "rockstargameslauncher.exe",
    "riotclientservices.exe", "riotclientux.exe",
    "explorer.exe", "searchapp.exe", "searchhost.exe", "shellexperiencehost.exe",
    "code.exe", "cursor.exe", "claude.exe", "pycharm64.exe", "devenv.exe",
    "notepad.exe", "notepad++.exe", "outlook.exe", "onenote.exe",
    "onedrive.exe", "dropbox.exe",
    "obs64.exe", "obs32.exe", "streamlabs obs.exe",
    "nvcontainer.exe", "nvidia web helper.exe", "gfexperience.exe",
    "svchost.exe", "dllhost.exe", "conhost.exe", "runtimebroker.exe",
    "csrss.exe", "smss.exe", "winlogon.exe", "services.exe", "lsass.exe",
}

DEFAULT_GAME_PROCESS = "wwm.exe"
APP_DISPLAY_NAME = "WWM Overlay"
APP_EXE_BASENAME = "PingOverlay"
APP_GUI_TITLE = "WWM Overlay Control Center"
APP_SETTINGS_TITLE = "WWM Overlay Settings"
LEGACY_APP_EXE_BASENAME = "WWMOverlay"

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_RESTORE = 9
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
GA_ROOT = 2

ping3.EXCEPTIONS = False


def _apply_rounded_corners(dlg: "tk.Toplevel") -> None:
    """Apply Windows 11 rounded corners to a custom-caption Toplevel via DWM.

    Equivalent to the DwmSetWindowAttribute call in _configure_native_window
    for the main panel.  Safe to call on any Windows version — silently
    does nothing on Windows 10 or if DWM is unavailable.
    """
    try:
        dlg.update_idletasks()
        hwnd = int(dlg.winfo_id())
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype  = ctypes.c_void_p
        root = user32.GetAncestor(ctypes.c_void_p(hwnd), GA_ROOT)
        hwnd = int(root or hwnd)
        corner_pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(33),          # DWMWA_WINDOW_CORNER_PREFERENCE
            ctypes.byref(corner_pref),
            ctypes.sizeof(corner_pref),
        )
    except Exception:
        pass


DISPLAY_MS_ACTIVE = 500
DISPLAY_MS_WAITING = 900
WINDOW_POLL_MS_ACTIVE = 500
WINDOW_POLL_MS_IDLE = 1000
PING_INTERVAL_S = 0.5   # khoảng cách mỗi lần ping (giây)
IP_RESCAN_EVERY = 20    # cứ N ping thì scan lại IP (~10s)
LOSS_WINDOW = 20        # số mẫu gần nhất tính packet loss

DEVELOPER_NAME = "ムKim - ぶMiêuGiaぶ Guild WWM"
COPYRIGHT_YEAR = "2026"
DONATE_URL   = "https://www.paypal.com/donate/?hosted_button_id=5F4PKX7KSHDYN"
WEBSITE_URL  = "https://wwmoverlay.com"
DISCORD_URL  = "https://discord.gg/sSjavfYzna"

# Per-plan PayPal payment links (mirrored from website/app.js)
LICENSE_PLANS = [
    {"id": "1d",  "en": "1 Day",    "vi": "1 Ngày",   "usd":  0.50, "vnd":    12_000, "url": "https://www.paypal.com/ncp/payment/RHPYMYJ4EV64J"},
    {"id": "7d",  "en": "7 Days",   "vi": "7 Ngày",   "usd":  3.00, "vnd":    75_000, "url": "https://www.paypal.com/ncp/payment/ULAP5WQBLDY4E"},
    {"id": "30d", "en": "30 Days",  "vi": "30 Ngày",  "usd": 10.00, "vnd":   250_000, "url": "https://www.paypal.com/ncp/payment/753UMNZUD3MVS"},
    {"id": "90d", "en": "90 Days",  "vi": "90 Ngày",  "usd": 25.00, "vnd":   625_000, "url": "https://www.paypal.com/ncp/payment/YS9HS96XSK3T4"},
    {"id": "ltm", "en": "Lifetime", "vi": "Lifetime", "usd": 50.00, "vnd": 1_250_000, "url": "https://www.paypal.com/ncp/payment/TBZRBXLBT2DB8"},
]
import resources as _res
ASSET_DIR        = _res.BASE
ICON_PNG         = _res.ICON_PNG
DONATE_PNG       = _res.DONATE_PNG
DISCORD_PNG      = _res.DISCORD_PNG
WWM_LOGO_PNG     = _res.WWM_LOGO_PNG
APP_WINDOW_ICON_PNG = WWM_LOGO_PNG
TAB_ICON_DIR     = _res.TAB_ICON_DIR
TAB_OVERLAY_PNG  = _res.TAB_OVERLAY_PNG
TAB_TWEAK_PNG    = _res.TAB_TWEAK_PNG
BAR_ICON_DIR     = _res.BAR_ICON_DIR
BAR_LANGUAGE_PNG = _res.BAR_LANGUAGE_PNG
BAR_ABOUT_PNG    = _res.BAR_ABOUT_PNG
BAR_SETTING_PNG  = _res.BAR_SETTING_PNG
BAR_HELP_PNG     = _res.BAR_HELP_PNG
BAR_MINIMIZE_PNG = _res.BAR_MINIMIZE_PNG
BAR_CLOSE_PNG    = _res.BAR_CLOSE_PNG
BAR_USER_PNG     = _res.BAR_USER_PNG
GUI_BTN_DIR      = _res.GUI_BTN_DIR
GUI_BTN_ON_PNG   = _res.GUI_BTN_ON_PNG
GUI_BTN_OFF_PNG  = _res.GUI_BTN_OFF_PNG

SUPERVISOR_MS = 2000    # nhịp kiểm tra process sống/chết + auto-detect game mới

_UI_IMAGE_CACHE: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}
_FLAG_IMAGE_CACHE: dict[str, ImageTk.PhotoImage] = {}
_PROCESS_ICON_CACHE: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}


def _load_ui_photo(path: Path, max_w: int = 0, max_h: int = 0) -> ImageTk.PhotoImage | None:
    key = (str(path), int(max_w), int(max_h))
    cached = _UI_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        img = Image.open(path)
        if max_w > 0 and max_h > 0:
            img.thumbnail((max_w, max_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _UI_IMAGE_CACHE[key] = photo
        return photo
    except Exception as e:
        print(f"[ui] image load failed: {path.name}: {e}")
        return None


def _load_fixed_ui_photo(path: Path, size: int) -> ImageTk.PhotoImage | None:
    key = (str(path), int(size), int(size))
    cached = _UI_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        img = Image.open(path).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        x = max(0, (size - img.width) // 2)
        y = max(0, (size - img.height) // 2)
        canvas.paste(img, (x, y), img)
        photo = ImageTk.PhotoImage(canvas)
        _UI_IMAGE_CACHE[key] = photo
        return photo
    except Exception as e:
        print(f"[ui] image load failed: {path.name}: {e}")
        return None


def _apply_window_icon(window) -> None:
    photo = _load_ui_photo(APP_WINDOW_ICON_PNG, 64, 64)
    if photo is None:
        return
    try:
        window._app_icon_photo = photo
        window.iconphoto(True, photo)
    except Exception:
        pass


def _load_process_icon_photo(pid: int | None, max_w: int = 22, max_h: int = 22) -> ImageTk.PhotoImage | None:
    if pid is None:
        return None
    try:
        exe_path = str(psutil.Process(int(pid)).exe())
    except Exception:
        return None
    key = (exe_path.lower(), int(max_w), int(max_h))
    cached = _PROCESS_ICON_CACHE.get(key)
    if cached is not None:
        return cached

    large_icon = ctypes.c_void_p()
    small_icon = ctypes.c_void_p()
    icon_info = None
    hdc = None

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", ctypes.c_bool),
            ("xHotspot", ctypes.c_uint32),
            ("yHotspot", ctypes.c_uint32),
            ("hbmMask", ctypes.c_void_p),
            ("hbmColor", ctypes.c_void_p),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", ctypes.c_long),
            ("bmWidth", ctypes.c_long),
            ("bmHeight", ctypes.c_long),
            ("bmWidthBytes", ctypes.c_long),
            ("bmPlanes", ctypes.c_ushort),
            ("bmBitsPixel", ctypes.c_ushort),
            ("bmBits", ctypes.c_void_p),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", ctypes.c_ushort),
            ("biBitCount", ctypes.c_ushort),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", ctypes.c_uint32 * 3),
        ]

    try:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        shell32.ExtractIconExW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint,
        ]
        shell32.ExtractIconExW.restype = ctypes.c_uint
        user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ICONINFO)]
        user32.GetIconInfo.restype = ctypes.c_bool
        user32.GetDC.argtypes = [ctypes.c_void_p]
        user32.GetDC.restype = ctypes.c_void_p
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.DestroyIcon.argtypes = [ctypes.c_void_p]
        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetDIBits.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        count = shell32.ExtractIconExW(exe_path, 0, ctypes.byref(large_icon), ctypes.byref(small_icon), 1)
        if count <= 0:
            return None
        hicon = small_icon.value or large_icon.value
        if not hicon:
            return None
        info = ICONINFO()
        if not user32.GetIconInfo(ctypes.c_void_p(hicon), ctypes.byref(info)):
            return None
        icon_info = info
        bitmap = BITMAP()
        if not info.hbmColor or not gdi32.GetObjectW(ctypes.c_void_p(info.hbmColor), ctypes.sizeof(bitmap), ctypes.byref(bitmap)):
            return None
        width = int(bitmap.bmWidth)
        height = int(bitmap.bmHeight)
        if width <= 0 or height <= 0:
            return None
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(width * height * 4)
        hdc = user32.GetDC(None)
        rows = gdi32.GetDIBits(
            ctypes.c_void_p(hdc),
            ctypes.c_void_p(info.hbmColor),
            0,
            height,
            buf,
            ctypes.byref(bmi),
            0,
        )
        if rows == 0:
            return None
        img = Image.frombuffer("RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1).copy()
        if img.getextrema()[3] == (0, 0):
            img.putalpha(255)
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        x = max(0, (max_w - img.width) // 2)
        y = max(0, (max_h - img.height) // 2)
        canvas.paste(img, (x, y), img)
        photo = ImageTk.PhotoImage(canvas)
        _PROCESS_ICON_CACHE[key] = photo
        return photo
    except Exception:
        return None
    finally:
        try:
            if hdc:
                ctypes.windll.user32.ReleaseDC(None, hdc)
        except Exception:
            pass
        try:
            if icon_info is not None:
                if icon_info.hbmColor:
                    ctypes.windll.gdi32.DeleteObject(ctypes.c_void_p(icon_info.hbmColor))
                if icon_info.hbmMask:
                    ctypes.windll.gdi32.DeleteObject(ctypes.c_void_p(icon_info.hbmMask))
        except Exception:
            pass
        for handle in (large_icon.value, small_icon.value):
            try:
                if handle:
                    ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(handle))
            except Exception:
                pass


def _flag_photo(code: str) -> ImageTk.PhotoImage | None:
    normalized = (code or "").strip().lower()
    cached = _FLAG_IMAGE_CACHE.get(normalized)
    if cached is not None:
        return cached
    try:
        img = Image.new("RGBA", (28, 18), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        if normalized == "en":
            draw.rectangle((0, 0, 27, 17), fill="#FFFFFF")
            for y in (0, 4, 8, 12, 16):
                draw.rectangle((0, y, 27, min(y + 1, 17)), fill="#D64545")
            draw.rectangle((0, 0, 11, 9), fill="#2E5BBA")
        else:
            draw.rectangle((0, 0, 27, 17), fill="#D62828")
            star = [(14, 3), (16, 8), (22, 8), (17, 11), (19, 15), (14, 12), (9, 15), (11, 11), (6, 8), (12, 8)]
            draw.polygon(star, fill="#F7D64A")
        draw.rounded_rectangle((0, 0, 27, 17), radius=4, outline="#B7C4D8", width=1)
        photo = ImageTk.PhotoImage(img)
        _FLAG_IMAGE_CACHE[normalized] = photo
        return photo
    except Exception:
        return None


def _build_dialog_caption(
    dlg: "tk.Toplevel",
    title: str,
    on_close,
    *,
    body_bg: str = "#FFFFFF",
    close_icon_path=None,
) -> "tk.Frame":
    """Replace the Windows title bar with a custom caption bar matching the main panel.

    Applies overrideredirect(True), draws a 1-px border, a #F3F3F3 caption bar
    with title label + close button (red on hover) + drag-to-move support, then
    returns the body Frame below the caption for the caller to pack content into.

    Args:
        dlg:             The Toplevel to decorate.
        title:           Caption bar title text.
        on_close:        Callable invoked when the close button is clicked.
        body_bg:         Background colour of the returned body frame.
        close_icon_path: Path to the close icon (BAR_CLOSE_PNG).  When None
                         the close button falls back to a plain "✕" label.
    """
    # Withdraw first so overrideredirect is applied before the window is mapped.
    # On Windows, setting overrideredirect on an already-visible window can
    # cause it to silently disappear or fail to render.  Each caller must call
    # dlg.deiconify() + dlg.lift() after centering geometry is applied.
    # Do NOT set -topmost here: the panel is no longer always-on-top after its
    # first open, so lift() is sufficient to stack the dialog above it. Keeping
    # -topmost would make the dialog float over every other Windows app.
    dlg.withdraw()
    dlg.overrideredirect(True)
    dlg.configure(bg="#CCCCCC")   # 1-px border colour shows through

    outer = tk.Frame(dlg, bg="#CCCCCC", bd=0, highlightthickness=0)
    outer.pack(fill="both", expand=True, padx=1, pady=1)

    caption_bg = "#F3F3F3"
    caption = tk.Frame(outer, bg=caption_bg, height=32, bd=0, highlightthickness=0)
    caption.pack(side="top", fill="x")
    caption.pack_propagate(False)

    lbl = tk.Label(
        caption, text=title, bg=caption_bg, fg="#111111",
        font=("Segoe UI", 10), anchor="w",
    )
    lbl.pack(side="left", padx=(10, 0), fill="y")

    # ── Close button ──────────────────────────────────────────────────────
    _BTN_W = 46

    def _make_close_photo(bg: str) -> "ImageTk.PhotoImage | None":
        if not close_icon_path:
            return None
        try:
            raw = _load_fixed_ui_photo(close_icon_path, 16)
            if raw is None:
                return None
            icon = ImageTk.getimage(raw).convert("RGBA")
            img  = Image.new("RGBA", (_BTN_W, 32), bg)
            img.paste(icon, ((_BTN_W - icon.width) // 2, (32 - icon.height) // 2), icon)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    n_photo = _make_close_photo(caption_bg)
    h_photo = _make_close_photo("#E81123")

    close_btn = tk.Label(
        caption, bg=caption_bg, bd=0, highlightthickness=0,
        width=_BTN_W, height=32, cursor="",
    )
    if n_photo:
        close_btn.configure(image=n_photo)
        close_btn.n_photo = n_photo          # keep reference — prevent GC
        close_btn.h_photo = h_photo or n_photo
    else:
        close_btn.configure(text="✕", font=("Segoe UI", 11), fg="#111111")

    def _btn_enter(_e=None) -> None:
        close_btn.configure(bg="#E81123")
        if n_photo:
            close_btn.configure(image=close_btn.h_photo)
        else:
            close_btn.configure(fg="#FFFFFF")

    def _btn_leave(_e=None) -> None:
        close_btn.configure(bg=caption_bg)
        if n_photo:
            close_btn.configure(image=close_btn.n_photo)
        else:
            close_btn.configure(fg="#111111")

    def _btn_click(_e=None) -> None:
        play_ui_click()
        on_close()

    close_btn.bind("<Enter>",    _btn_enter)
    close_btn.bind("<Leave>",    _btn_leave)
    close_btn.bind("<Button-1>", _btn_click)
    close_btn.pack(side="right")

    # ── Drag-to-move ──────────────────────────────────────────────────────
    _drag: dict = {}

    def _drag_start(e) -> None:
        _drag.update(x=e.x_root, y=e.y_root, wx=dlg.winfo_x(), wy=dlg.winfo_y())

    def _drag_motion(e) -> None:
        if _drag:
            dlg.geometry(
                f"+{_drag['wx'] + e.x_root - _drag['x']}"
                f"+{_drag['wy'] + e.y_root - _drag['y']}"
            )

    for _w in (caption, lbl):
        _w.bind("<ButtonPress-1>", _drag_start, add="+")
        _w.bind("<B1-Motion>",     _drag_motion, add="+")

    # ── Body frame ────────────────────────────────────────────────────────
    body = tk.Frame(outer, bg=body_bg, bd=0, highlightthickness=0)
    body.pack(side="top", fill="both", expand=True)

    # Apply Win11 rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND).
    # Scheduled via after(0) so it fires after the caller's deiconify() runs.
    # No-op on Win10 or when DWM is unavailable.
    dlg.after(0, lambda: _apply_rounded_corners(dlg))

    return body


def _show_copyright_dialog(parent, app) -> None:
    play_ui_alert()
    dialog = tk.Toplevel(parent)
    dialog.transient(parent)
    apply_custom_cursor(dialog)
    bind_ui_click_sound(dialog)

    _sys_bg = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
    dlg_body = _build_dialog_caption(
        dialog, tr(app, "copyright_title"), dialog.destroy,
        close_icon_path=BAR_CLOSE_PNG, body_bg=_sys_bg,
    )

    body_text = tr(
        app,
        "copyright_body",
        version=__version__,
        developer=DEVELOPER_NAME,
        year=COPYRIGHT_YEAR,
    )

    root = ttk.Frame(dlg_body, padding=16)
    root.pack(fill="both", expand=True)

    top = ttk.Frame(root)
    top.pack(fill="x")

    icon = _load_ui_photo(APP_WINDOW_ICON_PNG, 52, 52)
    if icon is not None:
        icon_label = ttk.Label(top, image=icon)
        icon_label.image = icon
        icon_label.pack(side="left", padx=(0, 12), anchor="n")

    text_label = ttk.Label(top, text=body_text, justify="left")
    text_label.pack(side="left", fill="both", expand=True)

    ttk.Button(root, text=tr(app, "button_ok"), command=dialog.destroy).pack(
        anchor="e", pady=(14, 0)
    )

    dialog.update_idletasks()
    x = parent.winfo_rootx() + max((parent.winfo_width() - dialog.winfo_width()) // 2, 0)
    y = parent.winfo_rooty() + max((parent.winfo_height() - dialog.winfo_height()) // 2, 0)
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()
    dialog.wait_window()


def _show_plans_popup(parent, app) -> None:
    """Popup showing all license plans with per-plan Buy Now buttons."""
    lang = getattr(app, "language", "en")

    dialog = tk.Toplevel(parent)
    dialog.title(tr(app, "gui_plans_title"))
    dialog.transient(parent)
    dialog.resizable(False, False)
    _apply_window_icon(dialog)
    apply_custom_cursor(dialog)
    bind_ui_click_sound(dialog)

    container = ttk.Frame(dialog, padding=(18, 14, 18, 14))
    container.pack(fill="both", expand=True)

    # Subtitle
    ttk.Label(
        container,
        text=tr(app, "gui_plans_subtitle"),
        font=("Segoe UI", 9),
        justify="center",
        anchor="center",
    ).pack(fill="x", pady=(0, 10))

    ttk.Separator(container, orient="horizontal").pack(fill="x", pady=(0, 8))

    # Plan rows
    for plan in LICENSE_PLANS:
        row = ttk.Frame(container)
        row.pack(fill="x", pady=4)
        row.columnconfigure(0, weight=1)   # plan name — stretches
        row.columnconfigure(1, weight=0)   # USD
        row.columnconfigure(2, weight=0)   # VND
        row.columnconfigure(3, weight=0)   # button

        plan_name = plan["vi"] if lang == "vi" else plan["en"]
        ttk.Label(
            row, text=plan_name,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        usd_str = f"${plan['usd']:.2f}".replace(".00", "")
        ttk.Label(
            row, text=usd_str,
            font=("Segoe UI", 10),
            anchor="e", width=7,
        ).grid(row=0, column=1, sticky="e")

        vnd_str = f"{plan['vnd']:,}".replace(",", ".") + " ₫"
        ttk.Label(
            row, text=vnd_str,
            font=("Segoe UI", 9),
            anchor="e", width=14,
            foreground="gray",
        ).grid(row=0, column=2, sticky="e", padx=(6, 12))

        url = plan["url"]
        ttk.Button(
            row,
            text=tr(app, "gui_plans_btn_buy"),
            cursor="",
            command=lambda u=url: (webbrowser.open(u, new=2), dialog.destroy()),
        ).grid(row=0, column=3, sticky="e")

    ttk.Separator(container, orient="horizontal").pack(fill="x", pady=(10, 0))
    ttk.Button(
        container,
        text=tr(app, "menu_close"),
        command=dialog.destroy,
    ).pack(anchor="e", pady=(8, 0))

    # Position centred on parent, then force to front
    dialog.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    dw = dialog.winfo_width()
    dh = dialog.winfo_height()
    x = parent.winfo_rootx() + max((pw - dw) // 2, 0)
    y = parent.winfo_rooty() + max((ph - dh) // 2, 0)
    dialog.geometry(f"+{x}+{y}")
    dialog.lift()
    dialog.focus_force()
    dialog.grab_set()


def _messagebox_parent(owner=None):
    parent = owner
    try:
        if parent is None:
            parent = tk._default_root  # type: ignore[attr-defined]
    except Exception:
        parent = None
    try:
        root = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
        root.withdraw()
        root.lift()
        root.focus_force()
        apply_custom_cursor(root)
        return root
    except Exception:
        return None


def _destroy_messagebox_parent(parent) -> None:
    if parent is None:
        return
    try:
        parent.destroy()
    except Exception:
        pass


def show_topmost_info(title: str, message: str, *, parent=None) -> None:
    play_ui_alert()
    top = _messagebox_parent(parent)
    try:
        messagebox.showinfo(title, message, parent=top)
    finally:
        _destroy_messagebox_parent(top)


def show_topmost_error(title: str, message: str, *, parent=None) -> None:
    play_ui_alert()
    top = _messagebox_parent(parent)
    try:
        messagebox.showerror(title, message, parent=top)
    finally:
        _destroy_messagebox_parent(top)


def ask_topmost_yesno(title: str, message: str, *, parent=None) -> bool:
    play_ui_alert()
    top = _messagebox_parent(parent)
    try:
        return bool(messagebox.askyesno(title, message, parent=top))
    finally:
        _destroy_messagebox_parent(top)


class _HoverTooltip:
    def __init__(self, parent, text_provider):
        self.parent = parent
        self.text_provider = text_provider
        self.tip: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self._hide_job = None
        self._show_job = None
        self._last_xy: tuple[int, int] | None = None

    def bind(self, widget) -> None:
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event) -> None:
        self._cancel_hide()
        self._last_xy = (int(event.x_root), int(event.y_root))
        self._schedule_show()

    def _on_motion(self, event) -> None:
        self._cancel_hide()
        self._last_xy = (int(event.x_root), int(event.y_root))
        if self.tip is None:
            self._schedule_show()
        else:
            self._place(event)
            self._update_text()

    def _on_leave(self, _event=None) -> None:
        self._cancel_show()
        self._cancel_hide()
        self._hide_job = self.parent.after(80, self._destroy_tip)

    def _cancel_hide(self) -> None:
        if self._hide_job is not None:
            try:
                self.parent.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = None

    def _cancel_show(self) -> None:
        if self._show_job is not None:
            try:
                self.parent.after_cancel(self._show_job)
            except Exception:
                pass
        self._show_job = None

    def _schedule_show(self) -> None:
        self._cancel_show()
        self._show_job = self.parent.after(1000, self._show_from_idle)

    def _show_from_idle(self) -> None:
        self._show_job = None
        if self._last_xy is None:
            return
        self._show_xy(*self._last_xy)

    def _destroy_tip(self) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
        self.tip = None
        self.label = None
        self._hide_job = None

    def _show(self, event) -> None:
        self._show_xy(int(event.x_root), int(event.y_root))

    def _show_xy(self, x_root: int, y_root: int) -> None:
        text = self._tooltip_text()
        if not text:
            return
        if self.tip is not None and self.label is not None:
            self._update_text()
            self._place_xy(x_root, y_root)
            return
        self.tip = tk.Toplevel(self.parent)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.label = tk.Label(
            self.tip,
            text=text,
            justify="left",
            relief="solid",
            bd=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        self.label.pack()
        self._place_xy(x_root, y_root)

    def _update_text(self) -> None:
        if self.label is None:
            return
        try:
            self.label.configure(text=self._tooltip_text())
        except Exception:
            pass

    def _tooltip_text(self) -> str:
        try:
            text = str(self.text_provider() or "")
        except Exception:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _place(self, event) -> None:
        self._place_xy(int(event.x_root), int(event.y_root))

    def _place_xy(self, x_root: int, y_root: int) -> None:
        if self.tip is None:
            return
        x = int(x_root) + 14
        y = int(y_root) + 18
        self.tip.geometry(f"+{x}+{y}")


class _UpdateToast:
    """Windows-style bottom-right toast notification for a pending app update.

    Shows a non-blocking overlay at the bottom-right corner of the primary
    monitor.  A progress bar counts down 10 seconds; clicking the toast
    triggers the supplied *on_click* callback and dismisses immediately.
    """

    _BG      = "#1A1A2E"
    _BORDER  = "#00C8FF"
    _FG_MAIN = "#FFFFFF"
    _FG_SUB  = "#99AAC4"
    _BAR_CLR = "#00C8FF"
    _TIMEOUT = 10_000   # ms

    def __init__(self, root: tk.Tk, version: str, on_click) -> None:
        self._root     = root
        self._version  = version
        self._on_click = on_click
        self._win: "tk.Toplevel | None" = None
        self._after_id: "str | None"    = None

    # ── public ────────────────────────────────────────────────────────────────
    def show(self) -> None:
        if self._win is not None:
            return
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=self._BG)

        W, H = 330, 90
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{sw - W - 14}+{sh - H - 56}")

        # Border frame
        outer = tk.Frame(win, bg=self._BORDER, padx=2, pady=2)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=self._BG, padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        # Icon + title row
        top_row = tk.Frame(inner, bg=self._BG)
        top_row.pack(fill="x")
        tk.Label(top_row, text="🔄", bg=self._BG, font=("Segoe UI Emoji", 14)).pack(side="left")
        tk.Label(
            top_row,
            text=f"  Update available — v{self._version}",
            bg=self._BG, fg=self._FG_MAIN,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        tk.Label(
            inner,
            text="Click to update now, or it will remind you later.",
            bg=self._BG, fg=self._FG_SUB,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(3, 6))

        # Progress bar canvas
        bar_bg = tk.Frame(inner, bg="#2A2A40", height=4)
        bar_bg.pack(fill="x", side="bottom")
        bar_bg.pack_propagate(False)
        bar_fill = tk.Frame(bar_bg, bg=self._BAR_CLR, height=4)
        bar_fill.place(x=0, y=0, relwidth=1.0, height=4)

        # Bind click on every widget
        for w in (win, outer, inner, top_row) + tuple(inner.winfo_children()) + tuple(top_row.winfo_children()):
            try:
                w.bind("<Button-1>", self._clicked)
                w.config(cursor="hand2")
            except Exception:
                pass

        self._win      = win
        self._bar_fill = bar_fill
        self._bar_bg   = bar_bg
        self._step     = 0
        self._steps    = 40
        self._tick()

    def dismiss(self) -> None:
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    # ── private ───────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        if self._win is None:
            return
        self._step += 1
        frac = max(0.0, 1.0 - self._step / self._steps)
        try:
            self._bar_bg.update_idletasks()
            w = self._bar_bg.winfo_width()
            self._bar_fill.place(x=0, y=0, width=int(w * frac), height=4)
        except Exception:
            pass
        if self._step >= self._steps:
            self.dismiss()
        else:
            interval = self._TIMEOUT // self._steps
            self._after_id = self._win.after(interval, self._tick)  # type: ignore[attr-defined]

    def _clicked(self, _event=None) -> None:
        self.dismiss()
        try:
            self._on_click()
        except Exception:
            pass


class _ImageToggle(tk.Frame):
    """Checkbox-like control rendered with custom on/off images."""

    def __init__(
        self,
        parent,
        *,
        variable: tk.BooleanVar,
        text: str = "",
        command=None,
        image_w: int = 42,
        image_h: int = 22,
        text_width: int | None = None,
    ):
        super().__init__(parent, bd=0, highlightthickness=0, bg="SystemButtonFace", cursor="")
        self.variable = variable
        self.command = command
        self._enabled = True
        self._anim_job = None
        self._anim_frames: list[ImageTk.PhotoImage] = []
        self._on_image = self._load_toggle_pil(GUI_BTN_ON_PNG, image_w, image_h)
        self._off_image = self._load_toggle_pil(GUI_BTN_OFF_PNG, image_w, image_h)
        self._on_photo = ImageTk.PhotoImage(self._on_image) if self._on_image is not None else None
        self._off_photo = ImageTk.PhotoImage(self._off_image) if self._off_image is not None else None
        self._image_label = tk.Label(self, bd=0, highlightthickness=0, bg="SystemButtonFace", cursor="")
        self._image_label.grid(row=0, column=0, sticky="w")
        self._text_label = tk.Label(
            self,
            text=text,
            bd=0,
            highlightthickness=0,
            bg="SystemButtonFace",
            fg="#111111",
            font=("Segoe UI", 9),
            cursor="",
        )
        if text_width is not None:
            self._text_label.configure(width=text_width, anchor="w")
        self._text_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self._sync_image()
        # Bind internal clicks directly. Calling ``self.bind`` here would go
        # through our public bind() override and bind child labels twice,
        # causing one user click to toggle OFF->ON->OFF.
        tk.Frame.bind(self, "<Button-1>", self._on_click, add="+")
        self._image_label.bind("<Button-1>", self._on_click, add="+")
        self._text_label.bind("<Button-1>", self._on_click, add="+")

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if cnf:
            kw.update(cnf)
        if "text" in kw:
            self._text_label.configure(text=kw.pop("text"))
        if "state" in kw:
            state = str(kw.pop("state") or "normal")
            self._enabled = state != "disabled"
            cursor = ""
            tk.Frame.configure(self, cursor=cursor)
            for widget in (self._image_label, self._text_label):
                widget.configure(cursor=cursor)
            self._text_label.configure(fg="#111111" if self._enabled else "#8A8A8A")
            self._sync_image()
        if "cursor" in kw:
            cursor = kw.pop("cursor")
            tk.Frame.configure(self, cursor=cursor)
            for widget in (self._image_label, self._text_label):
                widget.configure(cursor=cursor)
        if kw:
            super().configure(**kw)

    config = configure

    def bind(self, sequence=None, func=None, add=None):  # type: ignore[override]
        result = tk.Frame.bind(self, sequence, func, add)
        if sequence is not None and func is not None:
            self._image_label.bind(sequence, func, add)
            self._text_label.bind(sequence, func, add)
        return result

    def _on_click(self, _event=None) -> None:
        if not self._enabled:
            return
        play_ui_click()
        self.variable.set(not bool(self.variable.get()))
        if self.command is not None:
            self.command()
        self._sync_image(animate=True)

    def _load_toggle_pil(self, path: Path, max_w: int, max_h: int) -> Image.Image | None:
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
            x = max(0, (max_w - img.width) // 2)
            y = max(0, (max_h - img.height) // 2)
            canvas.paste(img, (x, y), img)
            return canvas
        except Exception as exc:
            print(f"[ui] toggle image load failed: {path.name}: {exc}")
            return None

    def _cancel_animation(self) -> None:
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._anim_job = None

    def _sync_image(self, *, animate: bool = False) -> None:
        self._cancel_animation()
        photo = self._on_photo if bool(self.variable.get()) else self._off_photo
        if animate and self._on_image is not None and self._off_image is not None:
            start = self._off_image if bool(self.variable.get()) else self._on_image
            end = self._on_image if bool(self.variable.get()) else self._off_image
            self._anim_frames = [
                ImageTk.PhotoImage(Image.blend(start, end, alpha / 5.0))
                for alpha in range(1, 6)
            ]
            self._play_animation(0)
            return
        if photo is not None:
            self._image_label.configure(image=photo, text="")
            self._image_label.image = photo
        else:
            self._image_label.configure(text="ON" if bool(self.variable.get()) else "OFF")

    def _play_animation(self, idx: int) -> None:
        if idx >= len(self._anim_frames):
            self._sync_image(animate=False)
            return
        photo = self._anim_frames[idx]
        self._image_label.configure(image=photo, text="")
        self._image_label.image = photo
        self._anim_job = self.after(18, lambda: self._play_animation(idx + 1))



I18N = {
    "en": {
        "status_waiting_start": "Waiting for Start",
        "status_waiting_lobby": "Waiting for lobby",
        "status_active": "Active",
        "status_waiting_game": "Waiting for game",
        "update_title": "Update",
        "update_exe_only": "Auto-update is only supported when running the packaged WWMOverlay.exe build.",
        "update_latest": "You are already on the latest version ({version}).",
        "update_available_title": "Update available",
        "update_available_body": "A new version {version} is available.\n\nYou are running {current}.\nThe app will download and restart to update.\n\nUpdate now?",
        "update_installing": "Updating to {version}. The app will restart automatically.",
        "update_error": "Could not update:\n{error}",
        "start_wait_game_title": "Where Winds Meet is not running",
        "start_wait_game_body": "Please launch Where Winds Meet first.\n\nAfter clicking OK, WWM Overlay will keep waiting and attach automatically when wwm.exe starts.",
        "pick_process_title": "Choose game process",
        "pick_process_desc": "Choose the process that owns the game window. The list is ranked by 3D API and network signals.",
        "pick_process_none": "No process with a large enough window was found for overlay attach.\nOpen the game first and try again.",
        "button_ok": "OK",
        "button_cancel": "Cancel",
        "pick_city_title": "Choose server (city)",
        "pick_city_none": "No city could be scanned from this process.\nThe process may not have any outbound connection yet.",
        "button_close": "Close",
        "pick_city_label": "Detected server cities:",
        "copyright_title": "Copyright",
        "copyright_body": "WWM Overlay\n\nVersion {version}\nDeveloped by {developer}\n© {year} {developer}. All rights reserved.\n\nReal-time Ping / Packet Loss / FPS / Quest / Event overlay\nfor Where Winds Meet. Anti-cheat safe (no inject).",
        "menu_show_ping": "Show Ping",
        "menu_show_loss": "Show Loss",
        "menu_show_jitter": "Show Jitter (60s)",
        "menu_show_minmax": "Show Min/Max (session)",
        "menu_show_fps": "Show FPS",
        "menu_show_low1": "Show 1% Low (60s)",
        "menu_show_frametime": "Show Frame time",
        "menu_show_cpu": "Show CPU",
        "menu_show_cpu_temp": "Show CPU Temp",
        "menu_show_gpu_temp": "Show GPU Temp",
        "menu_show_ram": "Show RAM",
        "menu_show_vram": "Show VRAM",
        "menu_show_api": "Show API",
        "menu_show_events": "Show Events",
        "menu_process": "Process: {value}",
        "menu_target": "Target: {value}",
        "menu_api": "API: {value}",
        "menu_status": "Status: {value}",
        "menu_show_app": "Show app",
        "menu_toggle_gui": "Hide/Show GUI Panel",
        "menu_monitoring_start": "Start/Stop Toogle",
        "menu_monitoring_stop": "Start/Stop Toogle",
        "menu_start_monitoring": "Start monitoring",
        "menu_stop_monitoring": "Stop monitoring",
        "menu_start_monitoring_ready": "Start monitoring [Ready]",
        "menu_start_monitoring_running": "Start monitoring [Running]",
        "menu_stop_monitoring_ready": "Stop monitoring [Running]",
        "menu_stop_monitoring_waiting": "Stop monitoring [Waiting]",
        "menu_choose_target": "Choose target process...",
        "menu_use_auto_detect": "Use auto-detect",
        "menu_options": "Options",
        "menu_check_updates": "Check for updates now",
        "menu_start_with_windows": "Start with Windows",
        "menu_reset_position": "Reset overlay position",
        "menu_hotkey": "Hotkey: {value}",
        "menu_language": "Language",
        "menu_language_en": "English",
        "menu_language_vi": "Tiếng Việt",
        "menu_donate": "Donate for ムKim",
        "gui_join_discord": "Join us on Discord",
        "menu_copyright": "Copyright",
        "menu_quit_app": "Quit app",
        "menu_close": "Close",
        "gui_window_title": "WWM Overlay Control Center",
        "gui_heading": "WWM Overlay Control Center",
        "gui_subheading": "Quick controls for monitoring and overlay display.",
        "gui_monitoring_frame": "Monitoring",
        "gui_status_label": "Status",
        "gui_options_frame": "Overlay Options",
        "gui_actions_frame": "Actions",
        "gui_developed_by":      "Developed by {developer} - v{version}",
        "gui_website_link":      "🌐  wwmoverlay.com",
        "gui_plans_title":       "Buy a License",
        "gui_plans_subtitle":    "Click Buy Now to open PayPal — the amount is pre-filled.",
        "gui_plans_btn_buy":     "Buy Now →",
        "gui_tab_overlay": "Overlay",
        "gui_tab_tweaks": "Game Tweaks",
        "gui_sidebar_overlay": "Overlay",
        "gui_sidebar_tweaks": "Game Tweaks",
        "gui_game_tab": "Where Winds Meet",
        "gui_overlay_options_frame": "Overlay Options",
        "gui_options_left_frame": "Network / Gameplay",
        "gui_options_right_frame": "Performance / System",
        "gui_tweaks_frame": "Game Tweaks",
        "gui_game_ping_frame": "Ping",
        "gui_game_data_frame": "Data connection",
        "gui_game_servers_frame": "Server IPs",
        "gui_game_show_ping": "Enable Ping",
        "gui_game_show_connection": "Enable Connection",
        "gui_game_show_server_ips": "Enable Server IPs",
        "gui_game_disabled": "Disabled",
        "gui_game_last_ping": "Last ping",
        "gui_game_average_ping": "Average ping",
        "gui_game_higher_ping": "Higher ping",
        "gui_game_lower_ping": "Lower ping",
        "gui_game_bytes_sent": "Bytes sent",
        "gui_game_bytes_received": "Bytes received",
        "gui_game_jitter": "Jitter",
        "gui_game_packet_loss": "Packet loss",
        "gui_game_servers_empty": "Waiting for active server traffic...",
        "gui_tweaks_intro": "Hover a tweak card to see what it changes and when not to use it.",
        "gui_tweak_enabled": "On",
        "gui_tweak_disabled": "Off",
        "gui_version": "v{version}",
        "gui_tweak_error_title": "System tweak",
        "gui_tweak_error_body": "Could not change '{name}':\n{error}",
        "gui_tweak_restart_title": "Restart required",
        "gui_tweak_restart_body": "'{name}' was changed.\n\nRestart Windows now to apply this tweak fully?",
        "gui_tweak_restart_now": "Restart now",
        "gui_tweak_restart_later": "Later",
        "tweak_reduce_input_lag_title": "Reduce input lag",
        "tweak_reduce_input_lag_desc": "Tunes multimedia scheduling to reduce render-path delay and avoid Windows network throttling.",
        "tweak_reduce_input_lag_note": "Not recommended if you share the PC for media-production workloads that expect Windows defaults.",
        "tweak_reduce_keyboard_input_time_title": "Reduce keyboard input time",
        "tweak_reduce_keyboard_input_time_desc": "Sets the fastest keyboard repeat delay and repeat speed available in Windows.",
        "tweak_reduce_keyboard_input_time_note": "Not recommended if you prefer slower key repeat for typing or accessibility reasons.",
        "tweak_turn_off_windows_performance_counters_title": "Turn off Windows performance counters",
        "tweak_turn_off_windows_performance_counters_desc": "Disables Game DVR capture hooks and extra Windows gaming telemetry that often runs in the background.",
        "tweak_turn_off_windows_performance_counters_note": "Not recommended if you use Xbox Game Bar capture or background recording.",
        "tweak_maximum_performance_for_games_title": "Maximum performance for games",
        "tweak_maximum_performance_for_games_desc": "Switches the system to the High Performance power plan while this tweak is enabled.",
        "tweak_maximum_performance_for_games_note": "Not recommended on laptops when battery life matters more than peak responsiveness.",
        "tweak_minimum_priority_for_background_processes_title": "Minimum priority for background processes",
        "tweak_minimum_priority_for_background_processes_desc": "Prioritizes foreground program scheduling over background services to reduce game interference.",
        "tweak_minimum_priority_for_background_processes_note": "Not recommended if you run encoding, streaming, or workstation services in the background.",
        "tweak_turn_off_network_power_saving_title": "Turn off Network power-saving",
        "tweak_turn_off_network_power_saving_desc": "Disables PCIe link-state power saving on the active power scheme to keep network devices more responsive.",
        "tweak_turn_off_network_power_saving_note": "Not recommended if you optimize primarily for battery savings or ultra-low idle power draw.",
        "tweak_turn_off_game_bar_background_recordings_title": "Turn off Game Bar background recordings",
        "tweak_turn_off_game_bar_background_recordings_desc": "Disables Xbox Game Bar background capture and automatic recording hooks.",
        "tweak_turn_off_game_bar_background_recordings_note": "Not recommended if you use Game Bar for clips, screenshots, or instant replay.",
        "tweak_keep_all_cores_active_title": "Keep all cores active",
        "tweak_keep_all_cores_active_desc": "Raises the minimum active-core parking setting on the current power plan to keep CPU cores awake.",
        "tweak_keep_all_cores_active_note": "Not recommended on laptops when you need lower idle temperature or longer battery life.",
        "tweak_turn_off_ntfs_last_access_time_stamp_title": "Turn off NTFS Last Access Time stamp",
        "tweak_turn_off_ntfs_last_access_time_stamp_desc": "Stops NTFS from updating last-access metadata on file reads to reduce small disk bookkeeping.",
        "tweak_turn_off_ntfs_last_access_time_stamp_note": "Not recommended if you rely on last-access timestamps for backup, audit, or workflow tools.",
        "tweak_turn_off_superfetch_title": "Turn off SuperFetch",
        "tweak_turn_off_superfetch_desc": "Disables the SysMain service to reduce background caching and disk activity.",
        "tweak_turn_off_superfetch_note": "Not recommended if your machine benefits from application preloading in daily desktop use.",
        "tweak_turn_off_windows_file_indexing_title": "Turn off Windows file indexing",
        "tweak_turn_off_windows_file_indexing_desc": "Disables the Windows Search indexing service to reduce background disk scans and metadata churn.",
        "tweak_turn_off_windows_file_indexing_note": "Not recommended if you depend on fast Start menu or File Explorer content search.",
        "tweak_ultimate_performance_mode_title": "Ultimate performance mode",
        "tweak_ultimate_performance_mode_desc": "Switches to the Windows Ultimate Performance power plan when available.",
        "tweak_ultimate_performance_mode_note": "Not recommended if you prefer lower power draw, lower heat, or quieter fan behavior.",
        "tooltip_show_ping": "Current round-trip latency to the detected game route.",
        "tooltip_show_loss": "Packet loss rate across recent ping samples.",
        "tooltip_show_jitter": "Connection stability over the last 60 seconds.",
        "tooltip_show_minmax": "Lowest and highest latency seen in the current session.",
        "tooltip_show_fps": "Current rendered frames per second from PresentMon.",
        "tooltip_show_low1": "1% low FPS for recent smoothness and frame pacing.",
        "tooltip_show_frametime": "Average frame render time in milliseconds.",
        "tooltip_show_cpu": "CPU usage currently attributed to the game process.",
        "tooltip_show_cpu_temp": "Current CPU temperature. Works best with LibreHardwareMonitor running. Falls back to Windows thermal-zone sensors.",
        "tooltip_show_gpu_temp": "Current GPU temperature. Supports NVIDIA (nvidia-smi) and AMD GCN-era cards (ADL). All cards work with LibreHardwareMonitor.",
        "tooltip_show_ram": "Game memory usage versus total system RAM, with percentage.",
        "tooltip_show_vram": "Active GPU memory usage versus total VRAM, with percentage.",
        "tooltip_show_api": "Detected graphics API used by the game process.",
        "tooltip_show_events": "Upcoming game events from the published local event feed.",
        "events_guild_title": "Guild ID required",
        "events_guild_body": "Enter your Where Winds Meet Guild ID to show guild-specific events on the overlay:",
        "events_guild_invalid": "Guild ID is required to show Events.",
        "gui_start_prompt_title": "Start monitoring",
        "gui_start_prompt_body": "Choose what to do with the control window after monitoring starts.",
        "gui_start_hide": "Hide to tray",
        "gui_start_minimize": "Minimize window",
        "gui_start_cancel": "Cancel",
        "gui_close_prompt_title": "Close control panel",
        "gui_close_prompt_body": "Choose what to do with WWM Overlay.",
        "gui_close_hide": "Hide to tray",
        "gui_close_exit": "Close app",
        "settings_button_tooltip": "Hotkey settings",
        "about_button_tooltip": "About / License",
        "help_button_tooltip": "Help — How to find your HWID",
        "help_hwid_title": "How to find your HWID",
        "help_hwid_body": (
            "Your HWID (Hardware ID) is needed to activate a license.\n\n"
            "Steps to find it:\n"
            "  1. Click the ⓘ About icon in the top caption bar\n"
            "  2. Select “License” from the dropdown menu\n"
            "  3. Your HWID is displayed in the License window\n\n"
            "Copy the HWID and send it to the admin to receive your license key."
        ),
        "about_menu_about": "About",
        "about_menu_license": "License",
        "settings_dialog_title": "WWM Overlay Settings",
        "settings_dialog_intro": "Configure global shortcuts. Click Capture and press the keys you want.",
        "settings_hotkeys_section": "Hotkeys",
        "settings_general_section": "General",
        "settings_start_with_windows": "Start with Windows",
        "settings_check_updates": "Check Update",
        "settings_panel_label": "Show/Hide Control Panel",
        "settings_toggle_label": "Open/Close Quest Overlay",
        "settings_scan_label": "Scan current screen",
        "settings_capture_button": "Capture",
        "settings_capture_listening": "Press keys...",
        "settings_save": "Save",
        "settings_cancel": "Cancel",
        "settings_invalid": "Quest hotkeys must include Ctrl plus one key. Control Panel may use a bare F-key.",
        "settings_function_hint": "",
        "settings_saved": "Saved.",
        "settings_saved_restart": "Saved. Restart the app to apply new hotkeys.",
        "settings_rotate_label": "Event rotate (s)",
        "settings_rotate_hint": "Seconds between events on the overlay when 2+ overlap.",
        "settings_overlay_section": "Overlay display",
        "settings_overlay_transparent": "Transparent Overlay's background",
        "settings_overlay_scale_label": "Overlay size",
        "settings_overlay_scale_hint": "Adjusts the whole overlay from 70% to 180%.",
        "uc_title":               "Account",
        "uc_login_google":        "Login with Google",
        "uc_login_discord":       "Login with Discord",
        "uc_or":                  "— or —",
        "uc_email":               "Email:",
        "uc_password":            "Password:",
        "uc_login_btn":           "Log in",
        "uc_register_hint":       "No account?",
        "uc_register_link":       "Register at wwmoverlay.com →",
        "uc_msg_empty":           "Please enter email and password.",
        "uc_msg_logging_in":      "Logging in…",
        "uc_msg_error":           "Error: {msg}",
        "uc_msg_waiting_browser": "Waiting for browser login…",
        "uc_points":              "Points: {pts}",
        "uc_license_fetching":    "Fetching your license…",
        "uc_license_ok":          "✓ License applied from your account",
        "uc_license_none":        "No license found. Contact admin.",
        "uc_license_err":         "Could not apply license.",
        "uc_sync_license":        "🔄 Sync License",
        "uc_logout":              "Log out",
        "uc_share":               "🔗  Share & earn points",
        "uc_share_copied":        "✓ Link copied! Send it to your friends 🎁",
        "settings_guild_section": "Events Guild ID",
        "settings_guild_current": "Current Guild ID:",
        "settings_guild_none": "(not set)",
        "settings_guild_clear": "Clear Guild ID",
        "settings_guild_cleared": "Guild ID cleared. Events overlay has been disabled.",
        "settings_license_section": "License (HWID)",
        "settings_license_hwid_label": "Your HWID:",
        "settings_license_copy_hwid": "Copy HWID",
        "settings_license_copied": "HWID copied to clipboard.",
        "settings_license_enter": "Enter License",
        "settings_license_clear": "Clear",
        "settings_license_unlicensed_hint":
            "No license — send the HWID above to ムKim to receive your key.",
        "settings_license_dialog_title": "Enter License Key",
        "settings_license_dialog_body":
            "Paste the license key issued by ムKim for this PC's HWID:",
        "settings_license_save": "Save license",
        "settings_license_cancel": "Cancel",
        "settings_license_save_ok": "License saved. Most features are now enabled.",
        "settings_license_save_failed": "License invalid: {reason}",
        "trial_notice_title": "24-hour trial started",
        "trial_notice_body":
            "Full features are unlocked for 24 hours on this PC.\n\n"
            "Trial expires: {expires}\n\n"
            "After that, only the free Ping/Loss overlay remains until you enter a license.",
        "overlay_waiting_lobby": "Waiting for lobby and stable connection...",
        "overlay_waiting_start": "Waiting for Start...",
        "overlay_waiting_game": "Waiting for game...",
        "overlay_waiting_match": "{process} is in menu — waiting to enter a match...",
        "overlay_error": "Error: {error}",
        "badge_recommended": "Recommended",
        "badge_candidate": "Candidate",
        "badge_recommended_accel": "Recommended via accelerator",
        "target_auto": "(auto)",
        "process_waiting": "(waiting)",
        "city_waiting": "(waiting)",
        "city_waiting_lobby": "(waiting lobby)",
        "city_waiting_net": "(waiting net)",
        "city_unknown": "(unknown)",
    },
    "vi": {
        "status_waiting_start": "Đang chờ Start",
        "status_waiting_lobby": "Đang chờ lobby",
        "status_active": "Đang hoạt động",
        "status_waiting_game": "Đang chờ game",
        "update_title": "Cập nhật",
        "update_exe_only": "Chỉ hỗ trợ tự động cập nhật khi chạy từ bản WWMOverlay.exe đã build.",
        "update_latest": "Bạn đang ở bản mới nhất ({version}).",
        "update_available_title": "Có bản cập nhật mới",
        "update_available_body": "Đã có bản mới {version}.\n\nBạn đang dùng {current}.\nỨng dụng sẽ tải và tự khởi động lại để cập nhật.\n\nCập nhật ngay?",
        "update_installing": "Đang cập nhật lên {version}. Ứng dụng sẽ tự khởi động lại.",
        "update_error": "Không thể cập nhật:\n{error}",
        "start_wait_game_title": "Chưa thấy Where Winds Meet",
        "start_wait_game_body": "Vui lòng khởi chạy Where Winds Meet trước.\n\nSau khi bấm OK, WWM Overlay sẽ tiếp tục chờ và tự bám vào wwm.exe khi game khởi chạy.",
        "pick_process_title": "Chọn process game",
        "pick_process_desc": "Chọn process đang sở hữu cửa sổ game. Danh sách đã ưu tiên theo 3D API và tín hiệu mạng.",
        "pick_process_none": "Không thấy process nào có cửa sổ đủ lớn để bám overlay.\nHãy mở game trước rồi thử lại.",
        "button_ok": "OK",
        "button_cancel": "Hủy",
        "pick_city_title": "Chọn server (thành phố)",
        "pick_city_none": "Không scan được city nào từ process.\nProcess có thể chưa có kết nối ra ngoài.",
        "button_close": "Đóng",
        "pick_city_label": "Server (city) scan được:",
        "copyright_title": "Bản quyền",
        "copyright_body": "WWM Overlay\n\nPhiên bản {version}\nPhát triển bởi {developer}\n© {year} {developer}. Đã đăng ký mọi quyền.\n\nOverlay Ping / Packet Loss / FPS / Quest / Event thời gian thực\ncho Where Winds Meet. Anti-cheat safe (không inject).",
        "menu_show_ping": "Hiện Ping",
        "menu_show_loss": "Hiện Loss",
        "menu_show_jitter": "Hiện Jitter (60s)",
        "menu_show_minmax": "Hiện Min/Max (phiên)",
        "menu_show_fps": "Hiện FPS",
        "menu_show_low1": "Hiện 1% Low (60s)",
        "menu_show_frametime": "Hiện Frame time",
        "menu_show_cpu": "Hiện CPU",
        "menu_show_cpu_temp": "Hiện nhiệt CPU",
        "menu_show_gpu_temp": "Hiện nhiệt GPU",
        "menu_show_ram": "Hiện RAM",
        "menu_show_vram": "Hiện VRAM",
        "menu_show_api": "Hiện API",
        "menu_show_events": "Hiện Events",
        "menu_process": "Process: {value}",
        "menu_target": "Target: {value}",
        "menu_api": "API: {value}",
        "menu_status": "Trạng thái: {value}",
        "menu_show_app": "Hiện ứng dụng",
        "menu_toggle_gui": "Ẩn/Hiện GUI Panel",
        "menu_monitoring_start": "Start/Stop Toogle",
        "menu_monitoring_stop": "Start/Stop Toogle",
        "menu_start_monitoring": "Bắt đầu theo dõi",
        "menu_stop_monitoring": "Dừng theo dõi",
        "menu_start_monitoring_ready": "Bắt đầu theo dõi [Sẵn sàng]",
        "menu_start_monitoring_running": "Bắt đầu theo dõi [Đang chạy]",
        "menu_stop_monitoring_ready": "Dừng theo dõi [Đang chạy]",
        "menu_stop_monitoring_waiting": "Dừng theo dõi [Đang chờ]",
        "menu_choose_target": "Chọn process mục tiêu...",
        "menu_use_auto_detect": "Dùng auto-detect",
        "menu_options": "Tùy chọn",
        "menu_check_updates": "Kiểm tra cập nhật ngay",
        "menu_start_with_windows": "Khởi động cùng Windows",
        "menu_reset_position": "Đặt lại vị trí overlay",
        "menu_hotkey": "Hotkey: {value}",
        "menu_language": "Ngôn ngữ",
        "menu_language_en": "English",
        "menu_language_vi": "Tiếng Việt",
        "menu_donate": "Donate for ムKim",
        "gui_join_discord": "Join us on Discord",
        "menu_copyright": "Bản quyền",
        "menu_quit_app": "Thoát ứng dụng",
        "menu_close": "Đóng",
        "gui_window_title": "WWM Overlay Control Center",
        "gui_heading": "WWM Overlay Control Center",
        "gui_subheading": "Điều khiển nhanh cho monitoring và hiển thị overlay.",
        "gui_monitoring_frame": "Monitoring",
        "gui_status_label": "Trạng thái",
        "gui_options_frame": "Tùy chọn Overlay",
        "gui_actions_frame": "Hành động",
        "gui_developed_by":      "Phát triển bởi {developer} - v{version}",
        "gui_website_link":      "🌐  wwmoverlay.com",
        "gui_plans_title":       "Mua License",
        "gui_plans_subtitle":    "Bấm Mua ngay để mở PayPal — số tiền đã điền sẵn.",
        "gui_plans_btn_buy":     "Mua ngay →",
        "gui_tab_overlay": "Overlay",
        "gui_tab_tweaks": "Tối ưu game",
        "gui_sidebar_overlay": "Overlay",
        "gui_sidebar_tweaks": "Tối ưu game",
        "gui_game_tab": "Where Winds Meet",
        "gui_overlay_options_frame": "Tùy chọn Overlay",
        "gui_options_left_frame": "Mạng / Gameplay",
        "gui_options_right_frame": "Hiệu năng / Hệ thống",
        "gui_tweaks_frame": "Game Tweaks",
        "gui_game_ping_frame": "Ping",
        "gui_game_data_frame": "Kết nối dữ liệu",
        "gui_game_servers_frame": "IP server",
        "gui_game_show_ping": "Bật Ping",
        "gui_game_show_connection": "Bật Connection",
        "gui_game_show_server_ips": "Bật Server IPs",
        "gui_game_disabled": "Đã tắt",
        "gui_game_last_ping": "Ping hiện tại",
        "gui_game_average_ping": "Ping trung bình",
        "gui_game_higher_ping": "Ping cao nhất",
        "gui_game_lower_ping": "Ping thấp nhất",
        "gui_game_bytes_sent": "Bytes gửi",
        "gui_game_bytes_received": "Bytes nhận",
        "gui_game_jitter": "Jitter",
        "gui_game_packet_loss": "Packet loss",
        "gui_game_servers_empty": "Đang chờ traffic server active...",
        "gui_tweaks_intro": "Rê chuột vào từng card để xem tweak đó thay đổi gì và khi nào không nên dùng.",
        "gui_tweak_enabled": "Bật",
        "gui_tweak_disabled": "Tắt",
        "gui_version": "v{version}",
        "gui_tweak_error_title": "Tweak hệ thống",
        "gui_tweak_error_body": "Không thể đổi '{name}':\n{error}",
        "gui_tweak_restart_title": "Cần khởi động lại",
        "gui_tweak_restart_body": "Đã thay đổi '{name}'.\n\nKhởi động lại Windows ngay để áp dụng đầy đủ tweak này?",
        "gui_tweak_restart_now": "Restart now",
        "gui_tweak_restart_later": "Để sau",
        "tweak_reduce_input_lag_title": "Giảm input lag",
        "tweak_reduce_input_lag_desc": "Tinh chỉnh multimedia scheduling để giảm độ trễ đường render và bỏ Windows network throttling.",
        "tweak_reduce_input_lag_note": "Không nên bật nếu máy còn dùng cho media-production và cần giữ hành vi mặc định của Windows.",
        "tweak_reduce_keyboard_input_time_title": "Giảm thời gian nhận phím",
        "tweak_reduce_keyboard_input_time_desc": "Đặt keyboard repeat delay và repeat speed về mức nhanh nhất mà Windows hỗ trợ.",
        "tweak_reduce_keyboard_input_time_note": "Không nên bật nếu bạn quen gõ với key repeat chậm hơn hoặc cần thiết lập hỗ trợ tiếp cận.",
        "tweak_turn_off_windows_performance_counters_title": "Tắt Windows performance counters",
        "tweak_turn_off_windows_performance_counters_desc": "Tắt Game DVR capture hooks và phần gaming telemetry nền của Windows thường chạy kèm.",
        "tweak_turn_off_windows_performance_counters_note": "Không nên bật nếu bạn dùng Xbox Game Bar để capture hoặc record nền.",
        "tweak_maximum_performance_for_games_title": "Hiệu năng tối đa cho game",
        "tweak_maximum_performance_for_games_desc": "Chuyển hệ thống sang power plan High Performance khi tweak này đang bật.",
        "tweak_maximum_performance_for_games_note": "Không nên bật trên laptop nếu thời lượng pin quan trọng hơn độ phản hồi tối đa.",
        "tweak_minimum_priority_for_background_processes_title": "Ưu tiên thấp cho tiến trình nền",
        "tweak_minimum_priority_for_background_processes_desc": "Ưu tiên lập lịch cho chương trình foreground hơn background services để giảm ảnh hưởng tới game.",
        "tweak_minimum_priority_for_background_processes_note": "Không nên bật nếu bạn chạy encode, stream hoặc các dịch vụ workstation ở nền.",
        "tweak_turn_off_network_power_saving_title": "Tắt power-saving của network",
        "tweak_turn_off_network_power_saving_desc": "Tắt PCIe link-state power saving trên power scheme hiện tại để thiết bị mạng phản hồi ổn định hơn.",
        "tweak_turn_off_network_power_saving_note": "Không nên bật nếu ưu tiên chính là tiết kiệm pin hoặc giảm điện năng nhàn rỗi.",
        "tweak_turn_off_game_bar_background_recordings_title": "Tắt Game Bar background recordings",
        "tweak_turn_off_game_bar_background_recordings_desc": "Tắt background capture và các hook ghi hình tự động của Xbox Game Bar.",
        "tweak_turn_off_game_bar_background_recordings_note": "Không nên bật nếu bạn dùng Game Bar để quay clip, chụp ảnh, hoặc instant replay.",
        "tweak_keep_all_cores_active_title": "Giữ tất cả core luôn active",
        "tweak_keep_all_cores_active_desc": "Tăng mức core parking tối thiểu trên power plan hiện tại để CPU core ít bị ngủ.",
        "tweak_keep_all_cores_active_note": "Không nên bật trên laptop nếu bạn cần nhiệt idle thấp hơn hoặc pin lâu hơn.",
        "tweak_turn_off_ntfs_last_access_time_stamp_title": "Tắt NTFS Last Access Time stamp",
        "tweak_turn_off_ntfs_last_access_time_stamp_desc": "Ngăn NTFS cập nhật metadata last-access khi đọc file để giảm bookkeeping đĩa nhỏ lẻ.",
        "tweak_turn_off_ntfs_last_access_time_stamp_note": "Không nên bật nếu bạn cần last-access timestamp cho backup, audit, hoặc công cụ workflow.",
        "tweak_turn_off_superfetch_title": "Tắt SuperFetch",
        "tweak_turn_off_superfetch_desc": "Tắt dịch vụ SysMain để giảm caching nền và hoạt động đọc/ghi đĩa.",
        "tweak_turn_off_superfetch_note": "Không nên bật nếu máy bạn hưởng lợi từ preload ứng dụng trong sử dụng desktop hằng ngày.",
        "tweak_turn_off_windows_file_indexing_title": "Tắt Windows file indexing",
        "tweak_turn_off_windows_file_indexing_desc": "Tắt dịch vụ Windows Search indexing để giảm quét đĩa nền và churn metadata.",
        "tweak_turn_off_windows_file_indexing_note": "Không nên bật nếu bạn phụ thuộc vào tìm kiếm nhanh trong Start menu hoặc File Explorer.",
        "tweak_ultimate_performance_mode_title": "Chế độ ultimate performance",
        "tweak_ultimate_performance_mode_desc": "Chuyển sang power plan Ultimate Performance của Windows khi khả dụng.",
        "tweak_ultimate_performance_mode_note": "Không nên bật nếu bạn ưu tiên điện năng thấp hơn, máy mát hơn, hoặc quạt êm hơn.",
        "tooltip_show_ping": "Độ trễ round-trip hiện tại tới route game đang được phát hiện.",
        "tooltip_show_loss": "Tỷ lệ mất gói dựa trên các mẫu ping gần đây.",
        "tooltip_show_jitter": "Độ ổn định kết nối trong 60 giây gần nhất.",
        "tooltip_show_minmax": "Độ trễ thấp nhất và cao nhất trong phiên hiện tại.",
        "tooltip_show_fps": "FPS render hiện tại lấy từ PresentMon.",
        "tooltip_show_low1": "1% low FPS để phản ánh độ mượt và frame pacing gần đây.",
        "tooltip_show_frametime": "Thời gian render khung hình trung bình theo mili giây.",
        "tooltip_show_cpu": "Mức sử dụng CPU hiện tại của process game.",
        "tooltip_show_cpu_temp": "Nhiệt độ CPU. Chính xác nhất khi có LibreHardwareMonitor. Fallback qua Windows thermal-zone sensor.",
        "tooltip_show_gpu_temp": "Nhiệt độ GPU. Hỗ trợ NVIDIA (nvidia-smi) và AMD GCN (ADL). Tất cả GPU đều hỗ trợ khi có LibreHardwareMonitor.",
        "tooltip_show_ram": "Dung lượng RAM game đang dùng so với tổng RAM hệ thống, kèm phần trăm.",
        "tooltip_show_vram": "Dung lượng VRAM đang dùng trên GPU active so với tổng VRAM, kèm phần trăm.",
        "tooltip_show_api": "Graphics API được phát hiện từ process game.",
        "tooltip_show_events": "Event game sắp diễn ra từ file event đã publish.",
        "events_guild_title": "Cần nhập Guild ID",
        "events_guild_body": "Nhập Guild ID trong Where Winds Meet để hiển thị event đúng theo Guild trên overlay:",
        "events_guild_invalid": "Cần nhập Guild ID để hiển thị Events.",
        "gui_start_prompt_title": "Bắt đầu theo dõi",
        "gui_start_prompt_body": "Chọn cách xử lý cửa sổ điều khiển sau khi bắt đầu monitoring.",
        "gui_start_hide": "Ẩn xuống tray",
        "gui_start_minimize": "Thu nhỏ cửa sổ",
        "gui_start_cancel": "Hủy",
        "gui_close_prompt_title": "Đóng bảng điều khiển",
        "gui_close_prompt_body": "Chọn cách xử lý WWM Overlay.",
        "gui_close_hide": "Ẩn xuống tray",
        "settings_button_tooltip": "Cài hotkey",
        "about_button_tooltip": "Thông tin / License",
        "help_button_tooltip": "Hướng dẫn — Cách lấy HWID",
        "help_hwid_title": "Cách lấy HWID",
        "help_hwid_body": (
            "HWID (Hardware ID) là mã máy cần để kích hoạt license.\n\n"
            "Các bước để lấy HWID:\n"
            "  1. Bấm icon ⓘ About trên thanh tiêu đề phía trên\n"
            "  2. Chọn \"License\" từ menu hiện ra\n"
            "  3. HWID của bạn được hiển thị trong cửa sổ License\n\n"
            "Sao chép HWID và gửi cho admin để nhận license key."
        ),
        "about_menu_about": "Thông tin",
        "about_menu_license": "License",
        "settings_dialog_title": "WWM Overlay Settings",
        "settings_dialog_intro": "Cài hotkey toàn hệ thống. Bấm Ghi rồi nhấn tổ hợp phím muốn dùng.",
        "settings_hotkeys_section": "Hotkeys",
        "settings_general_section": "Cài đặt chung",
        "settings_start_with_windows": "Khởi động cùng Windows",
        "settings_check_updates": "Kiểm tra cập nhật",
        "settings_panel_label": "Ẩn/Hiện Bảng điều khiển",
        "settings_toggle_label": "Mở/Tắt Quest Overlay",
        "settings_scan_label": "Scan màn hình hiện tại",
        "settings_capture_button": "Ghi phím",
        "settings_capture_listening": "Đang chờ phím...",
        "settings_save": "Lưu",
        "settings_cancel": "Huỷ",
        "settings_invalid": "Hotkey Quest cần có Ctrl cộng 1 phím chính. Bảng điều khiển có thể dùng riêng phím F.",
        "settings_function_hint": "",
        "settings_saved": "Đã lưu.",
        "settings_saved_restart": "Đã lưu. Khởi động lại app để áp dụng hotkey mới.",
        "settings_rotate_label": "Đảo Event (giây)",
        "settings_rotate_hint": "Khoảng giây giữa các Event trên overlay khi có 2+ event trùng giờ.",
        "settings_overlay_section": "Hiển thị Overlay",
        "settings_overlay_transparent": "Nền trong suốt của Overlay",
        "settings_overlay_scale_label": "Kích thước Overlay",
        "settings_overlay_scale_hint": "Chỉnh toàn bộ overlay từ 70% đến 180%.",
        "uc_title":               "Tài khoản",
        "uc_login_google":        "Đăng nhập bằng Google",
        "uc_login_discord":       "Đăng nhập bằng Discord",
        "uc_or":                  "— hoặc —",
        "uc_email":               "Email:",
        "uc_password":            "Mật khẩu:",
        "uc_login_btn":           "Đăng nhập",
        "uc_register_hint":       "Chưa có tài khoản?",
        "uc_register_link":       "Đăng ký tại wwmoverlay.com →",
        "uc_msg_empty":           "Vui lòng nhập email và mật khẩu.",
        "uc_msg_logging_in":      "Đang đăng nhập…",
        "uc_msg_error":           "Lỗi: {msg}",
        "uc_msg_waiting_browser": "Đang chờ đăng nhập trên trình duyệt…",
        "uc_points":              "Điểm: {pts}",
        "uc_license_fetching":    "Đang tải license từ tài khoản…",
        "uc_license_ok":          "✓ Đã áp dụng license từ tài khoản",
        "uc_license_none":        "Chưa có license. Liên hệ admin.",
        "uc_license_err":         "Không thể áp dụng license.",
        "uc_sync_license":        "🔄 Đồng bộ License",
        "uc_logout":              "Đăng xuất",
        "uc_share":               "🔗  Chia sẻ & nhận điểm",
        "uc_share_copied":        "✓ Đã sao chép! Hãy gửi cho bạn bè nhé 🎁",
        "settings_guild_section": "Guild ID cho Events",
        "settings_guild_current": "Guild ID hiện tại:",
        "settings_guild_none": "(chưa thiết lập)",
        "settings_guild_clear": "Xóa Guild ID",
        "settings_guild_cleared": "Đã xóa Guild ID. Overlay Events đã được tắt.",
        "settings_license_section": "License (HWID)",
        "settings_license_hwid_label": "Mã HWID máy này:",
        "settings_license_copy_hwid": "Sao chép HWID",
        "settings_license_copied": "Đã copy HWID vào clipboard.",
        "settings_license_enter": "Nhập License",
        "settings_license_clear": "Xoá",
        "settings_license_unlicensed_hint":
            "Chưa có License — gửi HWID phía trên cho ムKim để nhận key kích hoạt.",
        "settings_license_dialog_title": "Nhập License Key",
        "settings_license_dialog_body":
            "Dán key do ムKim cấp cho HWID của máy này:",
        "settings_license_save": "Lưu license",
        "settings_license_cancel": "Huỷ",
        "settings_license_save_ok": "Đã lưu license. Mở khoá đầy đủ tính năng.",
        "settings_license_save_failed": "License không hợp lệ: {reason}",
        "trial_notice_title": "Đã bắt đầu dùng thử 24h",
        "trial_notice_body":
            "Toàn bộ tính năng đã được mở khoá dùng thử trong 24 giờ trên PC này.\n\n"
            "Trial hết hạn: {expires}\n\n"
            "Sau thời gian này, app sẽ chỉ giữ lại Overlay Ping/Loss miễn phí cho tới khi nhập License.",
        "gui_close_exit": "Thoát ứng dụng",
        "overlay_waiting_lobby": "Đang chờ load lobby và ổn định kết nối...",
        "overlay_waiting_start": "Đang chờ Start...",
        "overlay_waiting_game": "Đang chờ game...",
        "overlay_waiting_match": "{process} đang ở menu — chờ vào match...",
        "overlay_error": "Lỗi: {error}",
        "badge_recommended": "Đề xuất",
        "badge_candidate": "Ứng viên",
        "badge_recommended_accel": "Đề xuất qua accelerator",
        "target_auto": "(tự động)",
        "process_waiting": "(đang chờ)",
        "city_waiting": "(đang chờ)",
        "city_waiting_lobby": "(đang chờ lobby)",
        "city_waiting_net": "(đang chờ mạng)",
        "city_unknown": "(không rõ)",
    },
}


def lang_code(app) -> str:
    code = ((app.cfg.get("language") if app else None) or "vi").strip().lower()
    return code if code in I18N else "vi"


def tr(app, key: str, **kwargs) -> str:
    code = lang_code(app)
    template = I18N.get(code, {}).get(key) or I18N["en"].get(key) or key
    return template.format(**kwargs)


def _consume_update_stamp_arg() -> str | None:
    args = sys.argv[1:]
    if len(args) < 2:
        return None
    try:
        idx = args.index("--update-stamp")
    except ValueError:
        return None
    if idx + 1 >= len(args):
        return None
    stamp_path = args[idx + 1]
    del args[idx:idx + 2]
    sys.argv = [sys.argv[0], *args]
    return stamp_path


def _consume_flag_arg(flag: str) -> bool:
    args = sys.argv[1:]
    if flag not in args:
        return False
    args = [arg for arg in args if arg != flag]
    sys.argv = [sys.argv[0], *args]
    return True


def _write_update_stamp(stamp_path: str | None) -> None:
    if not stamp_path:
        return
    try:
        with open(stamp_path, "w", encoding="utf-8") as f:
            f.write(f"ok {__version__}\n")
    except Exception as e:
        print(f"[update] could not write startup stamp: {e}")


def _find_quest_helper_hwnd(cfg: dict) -> tuple[int, bool] | None:
    qh_cfg = cfg.get("quest_helper") or {}
    process_name = str(qh_cfg.get("process_name") or "WWM-Tales-Overlay.exe").lower()
    title_hint = str(qh_cfg.get("window_title") or "WWM Tales Overlay").lower()
    user32 = ctypes.windll.user32
    hwnd_found: dict[str, tuple[int, bool] | None] = {"value": None}

    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _lparam):
        if not hwnd:
            return True
        pid = ctypes.c_ulong()
        try:
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
            proc = psutil.Process(int(pid.value))
            proc_name = (proc.name() or "").lower()
        except Exception:
            proc_name = ""
        try:
            length = int(user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd)))
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), title_buf, length + 1)
            title = (title_buf.value or "").lower()
        except Exception:
            title = ""
        # The embedded helper runs as PingOverlay.exe too, so process name alone
        # would also match the main control panel/overlay windows. Use title as
        # the authoritative selector when configured.
        if (title_hint and title_hint in title) or (not title_hint and process_name and proc_name == process_name):
            visible = bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))
            hwnd_found["value"] = (int(hwnd), visible)
            return False
        return True

    try:
        user32.EnumWindows(enum_proc_type(_callback), None)
    except Exception:
        return hwnd_found["value"]
    return hwnd_found["value"]


def close_quest_helper(cfg: dict, app: "AppState | None" = None) -> None:
    if app is not None:
        helper = getattr(app, "quest_helper_overlay", None)
        if helper is not None:
            try:
                if helper.winfo_exists():
                    helper.close()
                    print("[quest-helper] embedded overlay closed")
            except Exception:
                pass
            app.quest_helper_overlay = None

    found = _find_quest_helper_hwnd(cfg)
    if found is None:
        return
    hwnd, _visible = found
    user32 = ctypes.windll.user32
    pid = ctypes.c_ulong()
    try:
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        helper_pid = int(pid.value)
    except Exception:
        helper_pid = 0
    try:
        user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE
    except Exception as e:
        print(f"[quest-helper] close message failed: {e}")
    if helper_pid <= 0 or helper_pid == os.getpid():
        return
    try:
        proc = psutil.Process(helper_pid)
        proc.wait(timeout=2.0)
        print("[quest-helper] closed")
        return
    except psutil.TimeoutExpired:
        pass
    except Exception:
        return
    try:
        psutil.Process(helper_pid).terminate()
        print("[quest-helper] terminated")
    except Exception as e:
        print(f"[quest-helper] terminate failed: {e}")


def cleanup_quest_scan_images() -> None:
    try:
        from wwm_tales.overlay import cleanup_scan_images

        cleanup_scan_images()
    except Exception as e:
        print(f"[quest-helper] scan image cleanup failed: {e}")


def _scan_hotkey_flags(qh_cfg: dict) -> tuple[int, int]:
    """Translate cfg.quest_helper.scan_hotkey to (mod_flags, vk) for the
    wwm_tales GlobalHotkeys helper. Falls back to Ctrl+Alt+G."""
    from hotkey import _resolve_modifiers, _resolve_vk

    spec = (qh_cfg or {}).get("scan_hotkey") or {}
    modifiers = spec.get("modifiers") or ["ctrl", "alt"]
    key = spec.get("key") or "G"
    flags = _resolve_modifiers(modifiers) & ~0x4000  # strip MOD_NOREPEAT
    vk = _resolve_vk(key) or 0x47  # 'G'
    return flags, vk


def _persist_quest_helper_position(cfg: dict, x: int, y: int) -> None:
    qh = cfg.setdefault("quest_helper", {})
    pos = qh.setdefault("position", {})
    if pos.get("x") == int(x) and pos.get("y") == int(y):
        return
    pos["x"] = int(x)
    pos["y"] = int(y)
    app_config.save(cfg)


def toggle_quest_helper(cfg: dict, app: "AppState | None" = None) -> None:
    qh_cfg = cfg.get("quest_helper") or {}
    if not qh_cfg.get("enabled", True):
        return
    # Quest helper is a licensed feature — bail when unlicensed. The
    # bare ping/loss overlay still works because that path is
    # independently routed.
    if app is not None and not getattr(app, "licensed", False):
        print("[quest-helper] ignored: license required")
        return
    if app is not None and qh_cfg.get("require_monitoring", True):
        required_proc = str(qh_cfg.get("require_process") or DEFAULT_GAME_PROCESS).lower()
        if (
            not app.monitoring_enabled
            or not app.active
            or (required_proc and app.proc_name.lower() != required_proc)
        ):
            print("[quest-helper] ignored: start monitoring and attach wwm.exe first")
            return
    if app is not None:
        helper = getattr(app, "quest_helper_overlay", None)
        try:
            if helper is not None and helper.winfo_exists():
                helper.toggle_visible()
                print("[quest-helper] embedded overlay toggled")
                return
        except Exception:
            app.quest_helper_overlay = None

        try:
            from wwm_tales.overlay import OverlayApp as QuestHelperOverlay
            from wwm_tales.scraper import DEFAULT_OUTPUT_PATH as QUEST_HELPER_DATA_PATH

            parent = getattr(app, "quest_helper_parent", None)
            if parent is None:
                print("[quest-helper] ignored: missing Tk parent")
                return
            pos_cfg = (qh_cfg.get("position") or {})
            try:
                position = (int(pos_cfg.get("x")), int(pos_cfg.get("y"))) if pos_cfg else None
            except Exception:
                position = None
            scan_hotkey = _scan_hotkey_flags(qh_cfg)
            app.quest_helper_overlay = QuestHelperOverlay(
                QUEST_HELPER_DATA_PATH,
                DEFAULT_GAME_PROCESS,
                master=parent,
                enable_hotkeys=True,
                scan_hotkey=scan_hotkey,
                position=position,
                on_position_changed=lambda x, y: _persist_quest_helper_position(cfg, x, y),
                debug_save_captures=bool(qh_cfg.get("debug_save_captures", False)),
            )
            print("[quest-helper] embedded overlay created")
            return
        except Exception as e:
            print(f"[quest-helper] embedded overlay failed: {e}")
            return

    print("[quest-helper] ignored: embedded overlay requires AppState")


def _make_icon_image(color: str) -> "Image.Image":
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    d.text((20, 20), "P", fill="black")
    return img


ICON_GREEN = _make_icon_image("#00FF66")
ICON_RED = _make_icon_image("#FF3333")
_PICK_CONTEXT = None


class AppState:
    """Trạng thái session hiện tại. Khi process game tắt, session dừng
    nhưng app vẫn chạy nền — supervisor sẽ tự bắt game mới khi xuất hiện.
    """
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pid: int | None = None
        self.proc_name: str = "(waiting)"
        self.city: str = "(waiting)"
        self.fps_mon: "FpsMonitor | None" = None
        self.mem_mon: "MemoryMonitor | None" = None
        self.ping_state: "PingState | None" = None
        self.api: str = "Unknown"
        self.active: bool = False
        self.warming: bool = False
        self.warmup_stop: threading.Event | None = None
        self.hotkey_label: str = "(none)"
        self.monitoring_enabled: bool = False
        self.update_in_progress: bool = False
        self.startup_update_check_done = threading.Event()
        self.startup_update_info = None
        self.startup_update_error: str = ""
        self.startup_update_version: str = ""
        self.startup_update_probe_consumed: bool = False
        self.session_token: int = 0
        self.control_panel = None
        self.game_panel_options: "GamePanelOptions | None" = None
        self.event_monitor: "EventMonitor | None" = None
        self.game_tweaks = GameTweaksManager(cfg)
        self.net_base_sent_b: int | None = None
        self.net_base_recv_b: int | None = None
        self.net_last_sent_b: int | None = None
        self.net_last_recv_b: int | None = None
        self.net_last_t: float | None = None
        self.net_rate_sent_bps: float | None = None
        self.net_rate_recv_bps: float | None = None
        self.server_endpoints: list[dict] = []
        self.server_endpoints_mode: str = "none"
        self.server_endpoints_lock = threading.Lock()
        self.server_endpoint_worker_token: tuple[int, int] | None = None
        self.server_endpoint_worker_lock = threading.Lock()
        self.quest_helper_overlay = None
        self.quest_helper_parent = None
        # Licensing — populated by main()'s initial check via license_check.
        # ``licensed=True`` unlocks every feature; ``False`` keeps only
        # the bare ping/loss display in the overlay alive (the always-
        # free baseline). UI surfaces (ControlPanel, tray menu) consult
        # ``app.licensed`` directly.
        self.licensed: bool = False
        self.license_key_valid: bool = False
        self.license_status = None  # license_check.LicenseStatus | None
        self.trial_status = None  # license_check.TrialStatus | None
        self.trial_active: bool = False
        self.trial_notice_pending: bool = False
        self.remote_trial_active: bool = False
        self.remote_trial_started_at: str = ""
        self.remote_trial_expires_at: str = ""
        self.remote_trial_seconds_remaining: int = 0
        self.remote_trial_checked: bool = False
        self.license_admin_banned: bool = False
        self.license_admin_reason: str = ""
        self.license_admin_checked_at: str = ""
        self.license_admin_force_update: bool = False
        self.license_admin_version_blocked: bool = False
        self.license_admin_command_reason: str = ""
        self.license_admin_force_update_pending: bool = False
        self.license_admin_update_callback = None
        # Online license check (from Supabase via Edge Function heartbeat)
        self.license_server_licensed: bool = False
        self.license_server_expires_at: str = ""
        self.license_server_plan_id: str = ""


def _apply_license_status(app: AppState, status, *, create_trial: bool = True) -> None:
    """Apply local license status, 24h trial state, plus remote admin ban."""
    app.license_status = status
    app.license_key_valid = bool(getattr(status, "is_licensed", False))
    trial = None
    remote_trial_required = license_admin.is_client_enabled(getattr(app, "cfg", {}) or {})
    if not app.license_key_valid:
        if remote_trial_required:
            app.trial_active = _remote_trial_is_active(app)
            app.trial_status = None
            app.trial_notice_pending = _remote_trial_notice_pending(app)
        else:
            try:
                import license_check as _lc
                # Fetch admin-configured trial days from Supabase (cached after
                # first call, falls back to 1 day on network failure).
                _lc.refresh_trial_duration()
                trial = _lc.trial_status(create=create_trial)
            except Exception as exc:
                print(f"[license] trial check failed: {exc}")
                trial = None
            app.trial_status = trial
            app.trial_active = bool(getattr(trial, "is_active", False))
            app.trial_notice_pending = bool(
                app.trial_active and not bool(getattr(trial, "notice_shown", True))
            )
    else:
        app.trial_active = False
        app.trial_notice_pending = False
    app.trial_status = trial
    # Dual-gate: offline HMAC  OR  online Supabase DB says licensed
    # Both paths are blocked by admin ban.
    app.licensed = (
        app.license_key_valid
        or app.trial_active
        or bool(getattr(app, "license_server_licensed", False))
    ) and not bool(getattr(app, "license_admin_banned", False))


def _parse_access_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.astimezone()
        return dt.astimezone()
    except Exception:
        return None


def _remote_trial_is_active(app: AppState) -> bool:
    if not bool(getattr(app, "remote_trial_active", False)):
        return False
    expires = _parse_access_iso(getattr(app, "remote_trial_expires_at", ""))
    if expires is None:
        return bool(getattr(app, "remote_trial_seconds_remaining", 0) > 0)
    return datetime.now(expires.tzinfo) < expires


def _remote_trial_notice_pending(app: AppState) -> bool:
    if not _remote_trial_is_active(app):
        return False
    try:
        import license_check as _lc
        local = _lc.trial_status(create=False)
        return not bool(getattr(local, "notice_shown", False))
    except Exception:
        return True


def _trial_access_summary(app: AppState, *, language: str = "vi") -> str:
    is_vi = (language == "vi")
    if _remote_trial_is_active(app):
        expires = _parse_access_iso(getattr(app, "remote_trial_expires_at", ""))
        if expires is not None:
            remaining = max(0, int((expires - datetime.now(expires.tzinfo)).total_seconds()))
            label = expires.strftime("%Y-%m-%d %H:%M")
        else:
            remaining = max(0, int(getattr(app, "remote_trial_seconds_remaining", 0) or 0))
            label = str(getattr(app, "remote_trial_expires_at", "") or "—")
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        if is_vi:
            return f"Trial 24h theo HWID đang hoạt động — còn {hours}h {minutes}m, hết hạn {label}"
        return f"HWID-based 24-hour trial active — {hours}h {minutes}m left, expires {label}"
    trial = getattr(app, "trial_status", None)
    if trial is not None:
        try:
            import license_check as _lc
            return _lc.trial_summary(trial, language=language)
        except Exception:
            pass
    return (
        "Trial đã hết hạn hoặc chưa được server cấp — nhập License để mở khoá đầy đủ"
        if is_vi else
        "Trial expired or not granted by server — enter a license to unlock full features"
    )


def _format_trial_expiry_for_ui(trial) -> str:
    try:
        if isinstance(trial, str):
            expires = trial
        else:
            expires = getattr(trial, "expires_at", None)
        dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str((trial if isinstance(trial, str) else getattr(trial, "expires_at", "")) or "—")


def _maybe_show_trial_notice(app: AppState, root: tk.Tk) -> None:
    if not bool(getattr(app, "trial_notice_pending", False)):
        return
    if bool(getattr(app, "license_key_valid", False)) or bool(getattr(app, "license_admin_banned", False)):
        return
    trial = getattr(app, "trial_status", None)
    remote_expires = str(getattr(app, "remote_trial_expires_at", "") or "")
    if trial is None and _remote_trial_is_active(app):
        trial_for_display = remote_expires
    else:
        trial_for_display = trial
    if not (bool(getattr(trial, "is_active", False)) or _remote_trial_is_active(app)):
        return
    try:
        play_ui_alert()
        messagebox.showinfo(
            tr(app, "trial_notice_title"),
            tr(app, "trial_notice_body", expires=_format_trial_expiry_for_ui(trial_for_display)),
            parent=root,
        )
    except Exception as exc:
        print(f"[license] trial notice failed: {exc}")
    try:
        import license_check as _lc
        remote_started = str(getattr(app, "remote_trial_started_at", "") or "")
        _lc.mark_trial_notice_shown(
            started_at=remote_started or None,
            expires_at=remote_expires or None,
        )
        _apply_license_status(app, _lc.current_status(), create_trial=True)
    except Exception:
        app.trial_notice_pending = False


def _start_access_refresh(app: AppState, root: tk.Tk) -> None:
    """Refresh license/trial gates while the app stays open."""

    def _tick() -> None:
        old_access = bool(getattr(app, "licensed", False))
        try:
            import license_check as _lc
            _apply_license_status(app, _lc.current_status(), create_trial=True)
        except Exception as exc:
            print(f"[license] access refresh failed: {exc}")
        if old_access != bool(getattr(app, "licensed", False)):
            try:
                refresh_control_panel(app)
            except Exception:
                pass
        try:
            root.after(60_000, _tick)
        except Exception:
            pass

    try:
        root.after(60_000, _tick)
    except Exception:
        pass


def _start_license_admin_heartbeat(app: AppState, cfg: dict, root: tk.Tk) -> None:
    """Send periodic HWID/license heartbeat to the configured admin endpoint.

    The backend can mark an HWID as banned. A ban only changes feature
    gating locally; the saved offline key is not deleted, so unban works
    automatically on the next successful heartbeat.
    """
    if not license_admin.is_client_enabled(cfg):
        return

    def _local_status():
        try:
            import license_check as _lc
            return _lc.current_status()
        except Exception:
            return None

    def _apply_remote(result: license_admin.AdminBanStatus) -> None:
        app.license_admin_force_update = bool(result.force_update)
        app.license_admin_version_blocked = bool(result.version_blocked)
        app.license_admin_command_reason = str(result.command_reason or "")
        app.license_admin_banned = bool(result.banned) or bool(result.version_blocked)
        if result.version_blocked:
            app.license_admin_reason = (
                result.command_reason
                or f"Version {__version__} is locked by Admin"
            )
        else:
            app.license_admin_reason = result.reason
        app.license_admin_checked_at = result.checked_at
        app.remote_trial_active = bool(result.trial_active)
        app.remote_trial_started_at = str(result.trial_started_at or "")
        app.remote_trial_expires_at = str(result.trial_expires_at or "")
        app.remote_trial_seconds_remaining = int(result.trial_seconds_remaining or 0)
        app.remote_trial_checked = True
        # Apply online license result from Supabase
        app.license_server_licensed = bool(result.licensed_server)
        app.license_server_expires_at = str(result.expires_at_server or "")
        app.license_server_plan_id = str(result.plan_id_server or "")
        status = _local_status()
        if status is not None:
            _apply_license_status(app, status)
        elif result.banned:
            app.licensed = False
        elif bool(result.licensed_server):
            # No offline key saved but server confirms license — allow
            app.licensed = True
        try:
            refresh_control_panel(app)
        except Exception:
            pass
        try:
            root.after(250, lambda: _maybe_show_trial_notice(app, root))
        except Exception:
            pass
        if result.force_update:
            app.license_admin_force_update_pending = True
            callback = getattr(app, "license_admin_update_callback", None)
            if callable(callback):
                try:
                    root.after(1000, callback)
                except Exception:
                    pass

    def worker() -> None:
        interval_s = license_admin.heartbeat_interval_seconds(cfg)
        public_ip_value = ""
        while True:
            try:
                status = _local_status()
                if status is not None:
                    if license_admin.should_lookup_public_ip(cfg):
                        public_ip_value = license_admin.public_ip() or public_ip_value
                    result = license_admin.client_heartbeat(
                        cfg,
                        hwid=status.hwid,
                        app_version=__version__,
                        licensed=bool(status.is_licensed),
                        has_saved_key=bool(status.has_saved_key),
                        license_error=status.error,
                        expires_at=status.expires_at,
                        duration_code=status.duration_code,
                        public_ip_value=public_ip_value,
                    )
                    root.after(0, lambda r=result: _apply_remote(r))
                    print(
                        "[license-admin] heartbeat ok "
                        f"banned={result.banned} version_blocked={result.version_blocked} "
                        f"force_update={result.force_update} reason={result.reason or result.command_reason or '-'}"
                    )
            except Exception as exc:
                print(f"[license-admin] heartbeat failed: {exc}")
            time.sleep(interval_s)

    threading.Thread(
        target=worker,
        daemon=True,
        name="LicenseAdminHeartbeat",
    ).start()


def session_status_text(app: AppState) -> str:
    if not app.monitoring_enabled:
        return tr(app, "status_waiting_start")
    if app.warming:
        return tr(app, "status_waiting_lobby")
    if app.active:
        return tr(app, "status_active")
    return tr(app, "status_waiting_game")


def _reset_network_session_counters(app: AppState) -> None:
    try:
        counters = psutil.net_io_counters()
        sent = int(counters.bytes_sent)
        recv = int(counters.bytes_recv)
    except Exception:
        sent = 0
        recv = 0
    now = time.monotonic()
    app.net_base_sent_b = sent
    app.net_base_recv_b = recv
    app.net_last_sent_b = sent
    app.net_last_recv_b = recv
    app.net_last_t = now
    app.net_rate_sent_bps = 0.0
    app.net_rate_recv_bps = 0.0


def _clear_network_session_counters(app: AppState) -> None:
    app.net_base_sent_b = None
    app.net_base_recv_b = None
    app.net_last_sent_b = None
    app.net_last_recv_b = None
    app.net_last_t = None
    app.net_rate_sent_bps = None
    app.net_rate_recv_bps = None


def _network_session_snapshot(app: AppState) -> dict[str, float | int | None]:
    if app.net_base_sent_b is None or app.net_base_recv_b is None:
        return {"sent_b": None, "recv_b": None, "sent_bps": None, "recv_bps": None}
    try:
        counters = psutil.net_io_counters()
        sent = int(counters.bytes_sent)
        recv = int(counters.bytes_recv)
    except Exception:
        return {
            "sent_b": None,
            "recv_b": None,
            "sent_bps": app.net_rate_sent_bps,
            "recv_bps": app.net_rate_recv_bps,
        }
    now = time.monotonic()
    last_t = app.net_last_t
    if last_t is not None and now > last_t:
        dt = max(0.001, now - last_t)
        if app.net_last_sent_b is not None:
            app.net_rate_sent_bps = max(0.0, (sent - app.net_last_sent_b) / dt)
        if app.net_last_recv_b is not None:
            app.net_rate_recv_bps = max(0.0, (recv - app.net_last_recv_b) / dt)
    app.net_last_sent_b = sent
    app.net_last_recv_b = recv
    app.net_last_t = now
    return {
        "sent_b": max(0, sent - int(app.net_base_sent_b)),
        "recv_b": max(0, recv - int(app.net_base_recv_b)),
        "sent_bps": app.net_rate_sent_bps,
        "recv_bps": app.net_rate_recv_bps,
    }


def _server_endpoints_snapshot(app: AppState) -> tuple[list[dict], str]:
    try:
        with app.server_endpoints_lock:
            return list(app.server_endpoints), str(app.server_endpoints_mode or "none")
    except Exception:
        return [], "none"


def _set_server_endpoints(app: AppState, endpoints: list[dict], mode: str) -> None:
    try:
        with app.server_endpoints_lock:
            app.server_endpoints = list(endpoints)
            app.server_endpoints_mode = str(mode or "none")
    except Exception:
        pass


def _clear_server_endpoints(app: AppState) -> None:
    _set_server_endpoints(app, [], "none")


def _game_panel_enabled(app: AppState, attr: str) -> bool:
    opts = getattr(app, "game_panel_options", None)
    if opts is None:
        return False
    return bool(getattr(opts, attr, False))


def _is_bridge_build(cfg: dict) -> bool:
    """True when this onefile exe is the bridge transition build.

    Detected by the presence of ``bridge_to_installer.enabled = true`` in the
    bundled internal_config.json.  Normal onefile and onedir builds never set
    this key.
    """
    return bool((cfg.get("bridge_to_installer") or {}).get("enabled", False))


def start_startup_update_check(app: AppState) -> None:
    """Start the network-only update probe as early as possible.

    The GUI/tray may not exist yet, so this only caches metadata. The normal
    update flow later reuses the result and performs the prompt/download.
    """
    update_cfg = app.cfg.get("update") or {}
    if not bool(update_cfg.get("enabled", True)) or not bool(update_cfg.get("check_on_startup", True)):
        app.startup_update_check_done.set()
        return
    if not is_supported_runtime():
        app.startup_update_check_done.set()
        return
    if app.startup_update_version == __version__:
        return
    app.startup_update_version = __version__
    app.startup_update_info = None
    app.startup_update_error = ""
    app.startup_update_probe_consumed = False

    def worker() -> None:
        started = time.time()
        try:
            if is_onedir_install() or _is_bridge_build(app.cfg):
                app.startup_update_info = check_incremental_update(__version__)
            else:
                app.startup_update_info = check_for_update(app.cfg, __version__)
            if app.startup_update_info is not None:
                print(
                    "[update] startup probe found "
                    f"v{app.startup_update_info.version} in {time.time() - started:.1f}s"
                )
            else:
                print(f"[update] startup probe latest in {time.time() - started:.1f}s")
        except Exception as exc:
            app.startup_update_error = str(exc)
            print(f"[update] startup probe failed: {exc}")
        finally:
            app.startup_update_check_done.set()

    threading.Thread(target=worker, daemon=True, name="StartupUpdateProbe").start()


def _run_download_and_install(info, app: "AppState", overlay: "Overlay", tray) -> None:
    """Download + install update and exit the app. Called from toast click or startup path."""
    try:
        if getattr(info, "incremental", False) and _is_bridge_build(app.cfg):
            # ── Bridge path: download installer Setup exe and migrate ───────
            bridge_cfg   = app.cfg.get("bridge_to_installer") or {}
            url_template = str(bridge_cfg.get("installer_url_template") or "")
            if not url_template:
                raise RuntimeError("bridge_to_installer.installer_url_template not configured")
            installer_url = url_template.replace("{version}", info.version)
            print(f"[bridge] downloading installer v{info.version} from {installer_url}")
            import urllib.request as _ureq
            import tempfile as _tmpmod
            _MAX_ATTEMPTS = 4
            _last_exc: Exception | None = None
            installer_path: Path | None = None
            for _attempt in range(_MAX_ATTEMPTS):
                if _attempt:
                    _delay = min(5 * _attempt, 15)
                    print(f"[bridge] retry {_attempt}/{_MAX_ATTEMPTS - 1} in {_delay}s …")
                    time.sleep(_delay)
                try:
                    fd, tmp_name = _tmpmod.mkstemp(prefix="pingoverlay-setup-", suffix=".exe")
                    os.close(fd)
                    installer_path = Path(tmp_name)
                    with _ureq.urlopen(installer_url, timeout=120) as resp, \
                            open(installer_path, "wb") as out:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                    _last_exc = None
                    break  # success
                except Exception as _exc:
                    _last_exc = _exc
                    print(f"[bridge] download attempt {_attempt + 1} failed: {_exc}")
                    if installer_path and installer_path.exists():
                        try:
                            installer_path.unlink()
                        except Exception:
                            pass
                    installer_path = None
            if _last_exc is not None:
                raise _last_exc
            assert installer_path is not None
            print(f"[bridge] installer downloaded ({installer_path.stat().st_size:,} bytes)")
            install_via_installer_setup(installer_path)
        elif getattr(info, "incremental", False) and info.manifest:
            # ── Incremental path (installer / onedir edition) ──────────────
            print(f"[update] incremental update v{info.version} — fetching changed files")
            install_dir = Path(sys.executable).parent
            stage_dir   = download_incremental_from_repo(info.manifest, install_dir)
            install_incremental_update(stage_dir, install_dir, target_version=info.version)
        else:
            # ── Full-EXE path (portable / onefile edition) ─────────────────
            print(f"[update] downloading {info.asset_name} from {info.repo} tag {info.tag}")
            download_path = download_update(info, app.cfg)
            install_downloaded_update(download_path, info.asset_name)

        def finish():
            show_topmost_info(
                tr(app, "update_title"),
                tr(app, "update_installing", version=info.version),
                parent=overlay.root,
            )
            try:
                tray.stop()
            except Exception:
                pass
            os._exit(0)

        overlay.root.after(0, finish)
    except Exception as e:
        err = str(e)
        print(f"[update] download/install error: {err}")
        overlay.root.after(
            0,
            lambda msg=err: show_topmost_error(
                tr(app, "update_title"),
                tr(app, "update_error", error=msg),
                parent=overlay.root,
            ),
        )
    finally:
        app.update_in_progress = False
        try:
            tray.update_menu()
        except Exception:
            pass


def maybe_check_for_updates(
    overlay: Overlay,
    app: AppState,
    tray: pystray.Icon,
    *,
    interactive: bool,
) -> None:
    if app.update_in_progress:
        return

    update_cfg = app.cfg.get("update") or {}
    if not update_cfg.get("enabled", True):
        return
    if not is_supported_runtime():
        if interactive:
            overlay.root.after(
                0,
                lambda: show_topmost_info(
                    tr(app, "update_title"),
                    tr(app, "update_exe_only"),
                    parent=overlay.root,
                ),
            )
        return

    app.update_in_progress = True
    try:
        tray.update_menu()
    except Exception:
        pass

    def worker():
        def _release():
            """Reset the in-progress flag so the button can be clicked again."""
            app.update_in_progress = False
            try:
                tray.update_menu()
            except Exception:
                pass

        try:
            info = None
            if (
                not interactive
                and getattr(app, "startup_update_version", "") == __version__
                and not bool(getattr(app, "startup_update_probe_consumed", False))
            ):
                app.startup_update_probe_consumed = True
                try:
                    startup_wait = float(update_cfg.get("startup_probe_wait_seconds", 2.0))
                except (TypeError, ValueError):
                    startup_wait = 4.5
                startup_wait = max(0.0, min(8.0, startup_wait))
                app.startup_update_check_done.wait(timeout=startup_wait)
                info = app.startup_update_info
                if info is None and app.startup_update_error:
                    print(f"[update] startup probe error; retrying check: {app.startup_update_error}")
                elif info is None and not app.startup_update_check_done.is_set():
                    print("[update] startup probe still running; running foreground update check")
                elif info is None and app.startup_update_check_done.is_set():
                    _release()
                    return
            if info is None:
                if is_onedir_install() or _is_bridge_build(app.cfg):
                    info = check_incremental_update(__version__)
                else:
                    info = check_for_update(app.cfg, __version__)
            if info is None:
                if interactive:
                    overlay.root.after(
                        0,
                        lambda: show_topmost_info(
                            tr(app, "update_title"),
                            tr(app, "update_latest", version=__version__),
                            parent=overlay.root,
                        ),
                    )
                _release()
                return

            auto_install = bool(update_cfg.get("auto_install", True))

            # ── Non-startup runtime check: use toast, never block ──────────────
            # "auto_install on startup only" — show Windows-style notification
            # for background / manual checks so the user isn't interrupted.
            is_startup_probe = (
                not interactive
                and getattr(app, "startup_update_probe_consumed", False)
                and bool(getattr(app, "startup_update_version", "") == __version__)
            )
            use_toast = not is_startup_probe  # show toast unless this IS the startup auto-install

            if use_toast and auto_install and not interactive:
                # Runtime background detection: toast only, no blocking install
                def _do_update_from_toast():
                    threading.Thread(
                        target=lambda: _run_download_and_install(info, app, overlay, tray),
                        daemon=True,
                    ).start()

                def _show_toast():
                    toast = _UpdateToast(overlay.root, info.version, _do_update_from_toast)
                    toast.show()

                overlay.root.after(0, _show_toast)
                _release()  # flag released; download/install will run independently via toast click
                return

            if interactive:
                # Manual "Check for updates" — show toast for clean UX
                def _do_update_interactive():
                    threading.Thread(
                        target=lambda: _run_download_and_install(info, app, overlay, tray),
                        daemon=True,
                    ).start()

                def _show_interactive_toast():
                    toast = _UpdateToast(overlay.root, info.version, _do_update_interactive)
                    toast.show()

                overlay.root.after(0, _show_interactive_toast)
                _release()  # flag released; download/install will run independently via toast click
                return

            # Startup auto-install path (only reached on actual startup probe)
            if not auto_install:
                answer: dict[str, bool] = {"value": False}
                done = threading.Event()

                def ask():
                    answer["value"] = ask_topmost_yesno(
                        tr(app, "update_available_title"),
                        tr(app, "update_available_body", version=info.version, current=__version__),
                        parent=overlay.root,
                    )
                    done.set()

                overlay.root.after(0, ask)
                done.wait()
                if not answer["value"]:
                    _release()
                    return

            # Startup auto-install: download and replace immediately
            _run_download_and_install(info, app, overlay, tray)
        except Exception as e:
            err = str(e)
            print(f"[update] error: {err}")
            app.update_in_progress = False
            try:
                tray.update_menu()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()


class OverlayOptions:
    """Bật/tắt từng chỉ số trên overlay qua tray menu.
    Trạng thái load từ config.json; mỗi lần toggle -> lưu lại đĩa.
    """
    def __init__(self, cfg: dict):
        self._cfg = cfg
        opts = cfg.get("options", {}) if isinstance(cfg, dict) else {}
        self.show_ping = bool(opts.get("show_ping", True))
        self.show_loss = bool(opts.get("show_loss", True))
        self.show_jitter = bool(opts.get("show_jitter", True))
        self.show_minmax = bool(opts.get("show_minmax", True))
        self.show_fps = bool(opts.get("show_fps", True))
        self.show_low1 = bool(opts.get("show_low1", True))
        self.show_frametime = bool(opts.get("show_frametime", False))
        self.show_cpu = bool(opts.get("show_cpu", True))
        self.show_cpu_temp = bool(opts.get("show_cpu_temp", True))
        self.show_gpu_temp = bool(opts.get("show_gpu_temp", True))
        self.show_ram = bool(opts.get("show_ram", True))
        self.show_vram = bool(opts.get("show_vram", True))
        self.show_api = bool(opts.get("show_api", True))
        self.show_events = bool(opts.get("show_events", False))
        if self.show_events and not normalize_guild_id((cfg.get("events") or {}).get("guild_id")):
            self.show_events = False
            try:
                opts["show_events"] = False
                cfg["options"] = opts
                app_config.save(cfg)
            except Exception:
                pass

    def persist(self) -> None:
        self._cfg["options"] = {
            "show_ping": self.show_ping,
            "show_loss": self.show_loss,
            "show_jitter": self.show_jitter,
            "show_minmax": self.show_minmax,
            "show_fps": self.show_fps,
            "show_low1": self.show_low1,
            "show_frametime": self.show_frametime,
            "show_cpu": self.show_cpu,
            "show_cpu_temp": self.show_cpu_temp,
            "show_gpu_temp": self.show_gpu_temp,
            "show_ram": self.show_ram,
            "show_vram": self.show_vram,
            "show_api": self.show_api,
            "show_events": self.show_events,
        }
        app_config.save(self._cfg)


class GamePanelOptions:
    """Bật/tắt các phần live-update riêng trong tab Game.

    Các option này không ảnh hưởng overlay; mục tiêu là có thể tắt phần GUI
    nặng khi đang chơi game hoặc khi panel được ẩn xuống tray.
    """
    def __init__(self, cfg: dict):
        self._cfg = cfg
        opts = cfg.get("game_panel", {}) if isinstance(cfg, dict) else {}
        self.show_ping = bool(opts.get("show_ping", True))
        self.show_connection = bool(opts.get("show_connection", True))
        self.show_server_ips = bool(opts.get("show_server_ips", True))

    def persist(self) -> None:
        self._cfg["game_panel"] = {
            "show_ping": self.show_ping,
            "show_connection": self.show_connection,
            "show_server_ips": self.show_server_ips,
        }
        app_config.save(self._cfg)


def _fmt_latency(value: float | None) -> str:
    return f"{value:.0f} ms" if value is not None else "n/a"


def _fmt_percent(value: float | None) -> str:
    return f"{value:.0f} %" if value is not None else "n/a"


def _fmt_data_bytes(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    amount = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    while amount >= 1024.0 and idx < len(units) - 1:
        amount /= 1024.0
        idx += 1
    if idx == 0:
        return f"{amount:.0f} {units[idx]}"
    if amount < 10:
        return f"{amount:.2f} {units[idx]}"
    if amount < 100:
        return f"{amount:.1f} {units[idx]}"
    return f"{amount:.0f} {units[idx]}"


def _fmt_data_with_rate(total: float | int | None, rate: float | int | None) -> str:
    if total is None:
        return "n/a"
    if rate is None:
        return _fmt_data_bytes(total)
    return f"{_fmt_data_bytes(total)}, {_fmt_data_bytes(rate)}/s"


def _fmt_temp_c(value: float | int | None) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.0f}°C"
    except Exception:
        return None


def _combine_metric_group(label: str, primary: str | None, secondary: str | None) -> str:
    if primary and secondary:
        return f"{label}: {primary} - {secondary}"
    if primary:
        return f"{label}: {primary}"
    if secondary:
        return f"{label}: {secondary}"
    return f"{label}: n/a"


def _overlay_metric(text: str, min_text: str | None = None, color: str | None = None) -> dict:
    """Metric segment with a stable minimum width to avoid overlay resizing."""
    return {
        "text": text,
        "kind": "metric",
        "min_text": min_text or text,
        "color": color,
    }


def _fmt_server_endpoint(endpoint: dict) -> str:
    country = str(endpoint.get("country_code") or "").strip().upper()
    city = str(endpoint.get("city") or "").strip()
    ip = str(endpoint.get("ip") or "").strip()
    port = int(endpoint.get("port") or 0)
    proto = str(endpoint.get("proto") or "").strip().upper()
    mode = str(endpoint.get("mode") or "")
    route = ""
    if mode.startswith("accelerator:"):
        route = f" via {mode.split(':', 1)[1]}"
    location = " ".join(part for part in (country, city) if part).strip() or "Unknown"
    address = f"{ip}:{port}" if port else ip
    proto_suffix = f" {proto}" if proto else ""
    return f"{location}  -  {address}{proto_suffix}{route}"


def _format_event_overlay(alert: EventAlert | None, *, total: int = 1, index: int = 0) -> tuple[str, str] | None:
    if alert is None:
        return None
    start_text = alert.start.strftime("%H:%M")
    end_text = alert.end.strftime("%H:%M")
    # When multiple events overlap, append a small "(2/3)" pager so the user
    # can tell the row is rotating. Skip the suffix for solo events.
    suffix = f" ({index + 1}/{total})" if total > 1 else ""
    if alert.level == "active":
        return f"EVENT: {alert.name} active until {end_text}{suffix}", "#00E5FF"
    if alert.level == "countdown":
        seconds = max(0, int((alert.start - datetime.now()).total_seconds()))
        mm, ss = divmod(seconds, 60)
        return f"EVENT: {alert.name} starts in {mm:02d}:{ss:02d} ({start_text}-{end_text}){suffix}", "#FFAA00"
    if alert.level == "next":
        minutes_total = max(1, int(round(alert.minutes_left)))
        hours, minutes = divmod(minutes_total, 60)
        if hours >= 24:
            days, rem_hours = divmod(hours, 24)
            left_text = f"{days}d {rem_hours}h"
        elif hours > 0:
            left_text = f"{hours}h {minutes}m"
        else:
            left_text = f"{minutes}m"
        return f"NEXT EVENT: {alert.name} at {start_text} (in {left_text}){suffix}", "#FFDD55"
    minutes = max(1, int(round(alert.minutes_left)))
    return f"EVENT SOON: {alert.name} at {start_text} (in {minutes}m){suffix}", "#FFDD55"


def _event_rotate_seconds(cfg: dict) -> int:
    raw = (cfg.get("events") or {}).get("rotate_interval_seconds", 8)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 8
    # Clamp: too short (<3 s) makes the row a strobe; too long (>120 s)
    # defeats the purpose of rotating.
    return max(3, min(120, seconds))


def _configured_event_guild_id(app: AppState) -> str:
    try:
        return normalize_guild_id((app.cfg.get("events") or {}).get("guild_id"))
    except Exception:
        return ""


def ensure_event_guild_id(app: AppState, parent=None) -> bool:
    """Prompt once when Events are enabled without a saved Guild ID."""
    if _configured_event_guild_id(app):
        return True
    try:
        play_ui_alert()
        guild_id = simpledialog.askstring(
            tr(app, "events_guild_title"),
            tr(app, "events_guild_body"),
            parent=parent,
        )
    except Exception as exc:
        print(f"[events] guild prompt failed: {exc}")
        guild_id = None
    normalized = normalize_guild_id(guild_id)
    if not normalized:
        try:
            play_ui_alert()
            messagebox.showinfo(
                tr(app, "events_guild_title"),
                tr(app, "events_guild_invalid"),
                parent=parent,
            )
        except Exception:
            pass
        return False
    events_cfg = app.cfg.setdefault("events", {})
    events_cfg["guild_id"] = normalized
    app_config.save(app.cfg)
    try:
        if app.event_monitor is not None:
            app.event_monitor.force_refresh()
    except Exception:
        pass
    print(f"[events] guild_id saved: {normalized}")
    return True


def _select_event_banner(app: AppState) -> tuple[str, str] | None:
    """Pick the event banner text for the current overlay frame.

    Rotate through the most relevant upcoming alerts using monotonic time so
    the cadence stays steady regardless of the per-frame display interval.
    """
    monitor = app.event_monitor
    if monitor is None:
        return None

    alerts = monitor.overlapping_alerts_snapshot()
    if len(alerts) < 2:
        alerts = monitor.upcoming_alerts_snapshot(alert_only=False)

    if len(alerts) >= 2:
        rotate_s = _event_rotate_seconds(app.cfg)
        idx = int(time.monotonic() // rotate_s) % len(alerts)
        return _format_event_overlay(alerts[idx], total=len(alerts), index=idx)
    if alerts:
        return _format_event_overlay(alerts[0])
    return None


def _overlay_clock_text() -> str:
    return datetime.now().strftime("%H:%M")


def _append_overlay_clock(text: str) -> str:
    clean = str(text or "").strip()
    clock = _overlay_clock_text()
    return f"{clean} │ {clock}" if clean else clock


_TK_CAPTURE_KEY_MAP = {
    "PRIOR": "PAGEUP",
    "NEXT": "PAGEDOWN",
    "ESCAPE": "ESC",
    "RETURN": "ENTER",
}


def _normalize_capture_key(keysym: str) -> str:
    """Convert a Tk keysym (Up, Prior, F5, A, ...) to the names that
    ``hotkey._resolve_vk`` understands."""
    name = (keysym or "").upper()
    if not name:
        return ""
    name = _TK_CAPTURE_KEY_MAP.get(name, name)
    if len(name) == 1:
        return name
    if name.startswith("F") and name[1:].isdigit():
        return name
    if name in {
        "SPACE", "TAB", "ESC", "ENTER", "INSERT", "DELETE", "HOME", "END",
        "PAGEUP", "PAGEDOWN", "BACKSPACE", "LEFT", "UP", "RIGHT", "DOWN",
    }:
        return name
    return name


def _describe_hotkey_spec(spec: dict) -> str:
    parts = []
    seen = set()
    for mod in (spec or {}).get("modifiers") or []:
        norm = str(mod).strip().lower()
        label = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt",
                 "shift": "Shift", "win": "Win", "windows": "Win"}.get(norm)
        if label and label not in seen:
            parts.append(label)
            seen.add(label)
    key = (spec or {}).get("key") or ""
    if key:
        parts.append(str(key).upper())
    return "+".join(parts) if parts else "(unset)"


class ControlPanel:
    def __init__(
        self,
        master,
        app: AppState,
        options: OverlayOptions,
        actions: dict,
    ):
        self.app = app
        self.options = options
        if self.app.game_panel_options is None:
            self.app.game_panel_options = GamePanelOptions(self.app.cfg)
        self.game_options = self.app.game_panel_options
        self.actions = actions
        self._syncing = False
        self._active_tab = "overlay"
        self._centered_once = False
        self._tweak_cards = {card.key: card for card in TWEAK_CARDS}
        self._option_keys = {
            "show_ping": "menu_show_ping",
            "show_loss": "menu_show_loss",
            "show_jitter": "menu_show_jitter",
            "show_minmax": "menu_show_minmax",
            "show_fps": "menu_show_fps",
            "show_low1": "menu_show_low1",
            "show_frametime": "menu_show_frametime",
            "show_cpu": "menu_show_cpu",
            "show_cpu_temp": "menu_show_cpu_temp",
            "show_gpu_temp": "menu_show_gpu_temp",
            "show_ram": "menu_show_ram",
            "show_vram": "menu_show_vram",
            "show_api": "menu_show_api",
            "show_events": "menu_show_events",
        }
        self._option_tooltip_keys = {
            "show_ping": "tooltip_show_ping",
            "show_loss": "tooltip_show_loss",
            "show_jitter": "tooltip_show_jitter",
            "show_minmax": "tooltip_show_minmax",
            "show_fps": "tooltip_show_fps",
            "show_low1": "tooltip_show_low1",
            "show_frametime": "tooltip_show_frametime",
            "show_cpu": "tooltip_show_cpu",
            "show_cpu_temp": "tooltip_show_cpu_temp",
            "show_gpu_temp": "tooltip_show_gpu_temp",
            "show_ram": "tooltip_show_ram",
            "show_vram": "tooltip_show_vram",
            "show_api": "tooltip_show_api",
            "show_events": "tooltip_show_events",
        }

        self.window = tk.Toplevel(master)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#CFCFCF")
        self.window.minsize(600, 0)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close_requested)
        self.window.bind("<Map>", self._on_window_mapped, add="+")
        _apply_window_icon(self.window)
        self._style = ttk.Style(self.window)
        self._style.configure("PingOverlay.Tab.TButton", padding=(6, 4))
        self._style.configure(
            "PingOverlay.ActiveTab.TButton",
            padding=(6, 4),
            font=("Segoe UI", 9, "bold"),
            foreground="#003A70",
            background="#EAF3FF",
            bordercolor="#0078D4",
            relief="solid",
        )
        self._style.map(
            "PingOverlay.ActiveTab.TButton",
            foreground=[("disabled", "#003A70"), ("active", "#003A70")],
            background=[("active", "#EAF3FF"), ("!disabled", "#EAF3FF")],
            bordercolor=[("active", "#0078D4"), ("!disabled", "#0078D4")],
            relief=[("pressed", "sunken"), ("!pressed", "solid")],
        )

        self._caption_drag: dict[str, int] | None = None
        self._panel_pos: tuple[int, int] | None = None
        self._first_shown: bool = False  # True after first show(); topmost only on first open
        self.caption_bar = tk.Frame(self.window, bg="#F3F3F3", height=32, bd=0, highlightthickness=0)
        self.caption_bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
        self.caption_bar.pack_propagate(False)
        self.caption_bar.grid_rowconfigure(0, weight=1)
        self.caption_bar.grid_columnconfigure(1, weight=1)
        caption_button_width = 30
        self.caption_icon_photo = _load_fixed_ui_photo(APP_WINDOW_ICON_PNG, 18)
        self.caption_language_photo = _load_fixed_ui_photo(BAR_LANGUAGE_PNG, 16)
        self.caption_about_photo = _load_fixed_ui_photo(BAR_ABOUT_PNG, 16)
        self.caption_setting_photo = _load_fixed_ui_photo(BAR_SETTING_PNG, 16)
        self.caption_help_photo = _load_fixed_ui_photo(BAR_HELP_PNG, 16)
        self.caption_minimize_photo = _load_fixed_ui_photo(BAR_MINIMIZE_PNG, 16)
        self.caption_close_photo = _load_fixed_ui_photo(BAR_CLOSE_PNG, 16)
        self.caption_user_photo = _load_fixed_ui_photo(BAR_USER_PNG, 16)
        self.caption_icon = tk.Label(self.caption_bar, bg="#F3F3F3", bd=0)
        self.caption_icon.grid(row=0, column=0, sticky="w", padx=(8, 6))
        if self.caption_icon_photo is not None:
            self.caption_icon.configure(image=self.caption_icon_photo)
            self.caption_icon.image = self.caption_icon_photo
        self.caption_title = tk.Label(
            self.caption_bar,
            bg="#F3F3F3",
            fg="#111111",
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.caption_title.grid(row=0, column=1, sticky="ew")
        self.caption_user_button = self._make_caption_button(
            "👤",
            self._open_user_center,
            image=self.caption_user_photo,
            width=caption_button_width,
        )
        self.caption_user_button.grid(row=0, column=2, sticky="ns")
        self.caption_language_button = self._make_caption_button(
            "EN",
            self._toggle_caption_language,
            image=self.caption_language_photo,
            width=caption_button_width,
        )
        self.caption_language_button.grid(row=0, column=3, sticky="ns")
        self.caption_about_button = self._make_caption_button(
            "ⓘ",
            self._open_about_menu_from_caption,
            image=self.caption_about_photo,
            width=caption_button_width,
        )
        self.caption_about_button.grid(row=0, column=4, sticky="ns")
        self.caption_settings_button = self._make_caption_button(
            "⚙",
            self._open_settings_from_caption,
            image=self.caption_setting_photo,
            width=caption_button_width,
        )
        self.caption_settings_button.grid(row=0, column=5, sticky="ns")
        self.caption_help_button = self._make_caption_button(
            "?",
            self._open_help_popup,
            image=self.caption_help_photo,
            width=caption_button_width,
        )
        self.caption_help_button.grid(row=0, column=6, sticky="ns")
        self.caption_minimize_button = self._make_caption_button(
            "─",
            self.minimize,
            image=self.caption_minimize_photo,
            width=caption_button_width,
        )
        self.caption_minimize_button.grid(row=0, column=7, sticky="ns")
        self.caption_close_button = self._make_caption_button(
            "×",
            self._on_close_requested,
            image=self.caption_close_photo,
            width=caption_button_width,
            close=True,
        )
        self.caption_close_button.grid(row=0, column=8, sticky="ns")
        self._caption_about_tooltip = _HoverTooltip(
            self.window,
            lambda: tr(self.app, "about_button_tooltip"),
        )
        self._caption_about_tooltip.bind(self.caption_about_button)
        self._caption_settings_tooltip = _HoverTooltip(
            self.window,
            lambda: tr(self.app, "settings_button_tooltip"),
        )
        self._caption_settings_tooltip.bind(self.caption_settings_button)
        self._caption_help_tooltip = _HoverTooltip(
            self.window,
            lambda: tr(self.app, "help_button_tooltip"),
        )
        self._caption_help_tooltip.bind(self.caption_help_button)
        self._caption_user_tooltip = _HoverTooltip(
            self.window,
            lambda: tr(self.app, "uc_title"),
        )
        self._caption_user_tooltip.bind(self.caption_user_button)
        for widget in (self.caption_bar, self.caption_icon, self.caption_title):
            widget.bind("<ButtonPress-1>", self._on_caption_drag_start, add="+")
            widget.bind("<B1-Motion>", self._on_caption_drag_motion, add="+")
            widget.bind("<ButtonRelease-1>", self._on_caption_drag_end, add="+")

        root = ttk.Frame(self.window, padding=8)
        root.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        self._sidebar_overlay_photo = _load_fixed_ui_photo(TAB_OVERLAY_PNG, 22)
        self._sidebar_tweak_photo = _load_fixed_ui_photo(TAB_TWEAK_PNG, 22)

        content = ttk.Frame(root)
        content.pack(side="top", fill="x")
        content.grid_columnconfigure(0, weight=1)

        header_row = ttk.Frame(content)
        header_row.grid(row=0, column=0, sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)
        self.heading_label = ttk.Label(header_row, font=("Segoe UI", 18, "bold"), anchor="center", justify="center")
        self.heading_label.grid(row=0, column=0, sticky="ew")
        top_row = ttk.Frame(content)
        top_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        top_row.grid_columnconfigure(0, weight=1, minsize=330)
        top_row.grid_columnconfigure(1, weight=0, minsize=210)

        self.language_var = tk.StringVar(value=lang_code(self.app))

        self.monitoring_frame = ttk.LabelFrame(top_row, padding=(10, 8))
        self.monitoring_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.monitoring_frame.columnconfigure(0, weight=1)
        self.monitoring_frame.columnconfigure(1, weight=0)
        self.status_caption = ttk.Label(self.monitoring_frame, font=("Segoe UI", 10))
        self.status_caption.grid(row=0, column=0, sticky="w")
        self.status_value = ttk.Label(self.monitoring_frame, font=("Segoe UI", 10, "bold"))
        self.status_value.grid(row=1, column=0, sticky="w", pady=(3, 8))

        buttons = ttk.Frame(self.monitoring_frame)
        buttons.grid(row=2, column=0, pady=(2, 0))
        self.monitor_button = ttk.Button(buttons, command=self._on_monitor_toggle_clicked, cursor="")
        self.monitor_button.grid(row=0, column=0)
        self._wwm_logo_photo = _load_ui_photo(WWM_LOGO_PNG, 128, 76)
        self.wwm_logo_label = ttk.Label(self.monitoring_frame, anchor="center")
        self.wwm_logo_label.grid(row=0, column=1, rowspan=3, sticky="e", padx=(12, 0))

        action_column = ttk.Frame(top_row)
        action_column.grid(row=0, column=1, sticky="nsew")
        action_column.grid_columnconfigure(0, weight=1)
        action_column.grid_rowconfigure(0, weight=1)
        action_column.grid_rowconfigure(1, weight=1)

        self.donate_box = ttk.Frame(action_column, padding=(6, 4))
        self.donate_box.grid(row=0, column=0, sticky="s")
        self.donate_box.grid_columnconfigure(0, weight=1)
        self.donate_button = ttk.Label(self.donate_box, anchor="center", cursor="")
        self.donate_button.grid(row=0, column=0)
        self.donate_button.bind("<Button-1>", self._on_donate_clicked)
        self._donate_photo = _load_ui_photo(DONATE_PNG, 180, 40)

        self.discord_button = ttk.Label(action_column, anchor="center", cursor="")
        self.discord_button.grid(row=1, column=0, sticky="n", pady=(4, 0))
        self.discord_button.bind("<Button-1>", self._on_discord_clicked)
        self._discord_photo = _load_ui_photo(DISCORD_PNG, 132, 34)

        self.tab_bar = tk.Canvas(
            content,
            height=38,
            highlightthickness=0,
            bd=0,
            bg="SystemButtonFace",
            cursor="",
        )
        self.tab_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.tab_bar.bind("<Configure>", lambda _e: self._render_tab_bar())
        self.tab_bar.bind("<Button-1>", self._on_tab_bar_click)
        self._game_tab_photo = _load_fixed_ui_photo(ICON_PNG, 22)
        self._game_tab_button_visible = False
        self._tab_labels = {"overlay": "", "tweaks": "", "game": ""}
        self._tab_icons = {
            "overlay": self._sidebar_overlay_photo,
            "tweaks": self._sidebar_tweak_photo,
            "game": self._game_tab_photo,
        }
        self._tab_visible = {"overlay": True, "tweaks": True, "game": False}
        self._tab_bounds: dict[str, tuple[int, int, int, int]] = {}
        self._tab_fixed_widths = {"overlay": 112, "tweaks": 126, "game": 154}
        self._tab_indicator_box: tuple[float, float, float, float] | None = None
        self._tab_anim_job = None

        self.content_host = ttk.Frame(content)
        self.content_host.grid(row=3, column=0, sticky="new", pady=(4, 0))
        self.content_host.grid_columnconfigure(0, weight=1)

        self.overlay_tab = ttk.Frame(self.content_host)
        self.tweaks_tab = ttk.Frame(self.content_host)
        self.game_tab = ttk.Frame(self.content_host)
        self.overlay_tab.grid(row=0, column=0, sticky="nsew")
        self.tweaks_tab.grid(row=0, column=0, sticky="nsew")
        self.game_tab.grid(row=0, column=0, sticky="nsew")

        self.options_frame = ttk.LabelFrame(self.overlay_tab, padding=(10, 8))
        self.options_frame.pack(fill="x")
        self.options_frame.grid_columnconfigure(0, weight=1)
        self.options_frame.grid_columnconfigure(1, weight=1)

        self.options_left_frame = ttk.Frame(self.options_frame, padding=(4, 2))
        self.options_left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.options_right_frame = ttk.Frame(self.options_frame, padding=(4, 2))
        self.options_right_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.option_vars: dict[str, tk.BooleanVar] = {}
        self.option_buttons: dict[str, _ImageToggle] = {}
        self.option_tooltips: dict[str, _HoverTooltip] = {}
        option_order = [
            "show_ping", "show_jitter", "show_fps", "show_frametime", "show_cpu_temp", "show_gpu_temp", "show_vram",
            "show_loss", "show_minmax", "show_low1", "show_cpu", "show_ram", "show_api", "show_events",
        ]
        for idx, attr in enumerate(option_order):
            var = tk.BooleanVar(value=bool(getattr(self.options, attr)))
            parent_frame = self.options_left_frame if idx < (len(option_order) // 2) else self.options_right_frame
            row = idx if idx < (len(option_order) // 2) else idx - (len(option_order) // 2)
            btn = _ImageToggle(
                parent_frame,
                variable=var,
                command=lambda name=attr: self._on_option_toggle(name, bool(self.option_vars[name].get())),
                text_width=28,
            )
            btn.grid(row=row, column=0, sticky="w", pady=3)
            self.option_vars[attr] = var
            self.option_buttons[attr] = btn
            tooltip = _HoverTooltip(self.window, lambda name=attr: tr(self.app, self._option_tooltip_keys[name]))
            tooltip.bind(btn)
            self.option_tooltips[attr] = tooltip

        self.tweaks_frame = ttk.LabelFrame(self.tweaks_tab, padding=(10, 8))
        self.tweaks_frame.pack(fill="x")
        self.tweak_grid = ttk.Frame(self.tweaks_frame)
        self.tweak_grid.pack(fill="both", expand=True)
        self.tweak_grid.columnconfigure(0, weight=1)
        self.tweak_grid.columnconfigure(1, weight=1)

        self.tweak_vars: dict[str, tk.BooleanVar] = {}
        self.tweak_buttons: dict[str, _ImageToggle] = {}
        self.tweak_tooltips: dict[str, _HoverTooltip] = {}
        for idx, card in enumerate(TWEAK_CARDS):
            row = idx // 2
            col = idx % 2
            var = tk.BooleanVar(value=self.app.game_tweaks.is_enabled(card.key))
            check = _ImageToggle(
                self.tweak_grid,
                variable=var,
                command=lambda name=card.key: self._on_tweak_toggle(name, bool(self.tweak_vars[name].get())),
                text_width=34,
            )
            check.grid(row=row, column=col, sticky="w", padx=(0, 10) if col == 0 else (10, 0), pady=3)
            self.tweak_vars[card.key] = var
            self.tweak_buttons[card.key] = check
            tooltip = _HoverTooltip(
                self.window,
                lambda name=card.key: (
                    f"{tr(self.app, self._tweak_cards[name].title_key)}\n"
                    f"{tr(self.app, self._tweak_cards[name].desc_key)}\n"
                    f"{tr(self.app, self._tweak_cards[name].note_key)}"
                ),
            )
            tooltip.bind(check)
            self.tweak_tooltips[card.key] = tooltip

        self.game_options_frame = ttk.Frame(self.game_tab)
        self.game_options_frame.pack(fill="x", pady=(0, 6))
        self.game_option_vars: dict[str, tk.BooleanVar] = {}
        self.game_option_buttons: dict[str, _ImageToggle] = {}
        game_option_order = [
            ("show_ping", "gui_game_show_ping"),
            ("show_connection", "gui_game_show_connection"),
            ("show_server_ips", "gui_game_show_server_ips"),
        ]
        for idx, (attr, _label_key) in enumerate(game_option_order):
            var = tk.BooleanVar(value=bool(getattr(self.game_options, attr)))
            btn = _ImageToggle(
                self.game_options_frame,
                variable=var,
                command=lambda name=attr: self._on_game_option_toggle(
                    name,
                    bool(self.game_option_vars[name].get()),
                ),
                text_width=18,
            )
            btn.grid(row=0, column=idx, sticky="w", padx=(0, 18))
            self.game_option_vars[attr] = var
            self.game_option_buttons[attr] = btn

        self.game_stats_frame = ttk.Frame(self.game_tab)
        self.game_stats_frame.pack(fill="x")
        self.game_stats_frame.columnconfigure(0, weight=1, uniform="game_stats")
        self.game_stats_frame.columnconfigure(1, weight=1, uniform="game_stats")

        self.game_ping_frame = ttk.LabelFrame(self.game_stats_frame, padding=(10, 8))
        self.game_ping_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.game_data_frame = ttk.LabelFrame(self.game_stats_frame, padding=(10, 8))
        self.game_data_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.game_servers_frame = ttk.LabelFrame(self.game_tab, padding=(10, 8))
        self.game_servers_frame.pack(fill="x", pady=(6, 0))
        self.game_servers_frame.columnconfigure(0, weight=1)
        self.game_servers_frame.rowconfigure(0, weight=1)
        self.game_server_canvas = tk.Canvas(
            self.game_servers_frame,
            height=66,
            highlightthickness=0,
            bd=0,
        )
        self.game_server_canvas.grid(row=0, column=0, sticky="ew")
        self.game_server_scrollbar = ttk.Scrollbar(
            self.game_servers_frame,
            orient="vertical",
            command=self.game_server_canvas.yview,
        )
        self.game_server_canvas.configure(yscrollcommand=self.game_server_scrollbar.set)
        self.game_server_inner = ttk.Frame(self.game_server_canvas)
        self._game_server_window_id = self.game_server_canvas.create_window(
            (0, 0),
            window=self.game_server_inner,
            anchor="nw",
        )
        self.game_server_inner.bind("<Configure>", self._on_game_server_inner_configure)
        self.game_server_canvas.bind("<Configure>", self._on_game_server_canvas_configure)
        self.game_server_labels: list[ttk.Label] = []
        self.game_metric_labels: dict[str, tuple[ttk.Label, ttk.Label]] = {}
        for idx, key in enumerate(("last_ping", "average_ping", "higher_ping", "lower_ping")):
            name = ttk.Label(self.game_ping_frame, width=16)
            value = ttk.Label(self.game_ping_frame, font=("Segoe UI", 9, "bold"), anchor="e", width=16)
            name.grid(row=idx, column=0, sticky="w", pady=2)
            value.grid(row=idx, column=1, sticky="e", padx=(16, 0), pady=2)
            self.game_ping_frame.columnconfigure(0, weight=1, minsize=120)
            self.game_ping_frame.columnconfigure(1, weight=0, minsize=120)
            self.game_metric_labels[key] = (name, value)
        for idx, key in enumerate(("bytes_sent", "bytes_received", "jitter", "packet_loss")):
            name = ttk.Label(self.game_data_frame, width=16)
            value = ttk.Label(self.game_data_frame, font=("Segoe UI", 9, "bold"), anchor="e", width=18)
            name.grid(row=idx, column=0, sticky="w", pady=2)
            value.grid(row=idx, column=1, sticky="e", padx=(16, 0), pady=2)
            self.game_data_frame.columnconfigure(0, weight=1, minsize=120)
            self.game_data_frame.columnconfigure(1, weight=0, minsize=130)
            self.game_metric_labels[key] = (name, value)

        footer_frame = ttk.Frame(root)
        footer_frame.pack(side="bottom", fill="x", pady=(8, 0))
        footer_frame.grid_columnconfigure(0, weight=1)
        self.developed_by_label = ttk.Label(footer_frame, anchor="center", justify="center", font=("Segoe UI", 9))
        self.developed_by_label.grid(row=0, column=0, sticky="ew")
        self.website_link_label = ttk.Label(
            footer_frame, anchor="center",
            font=("Segoe UI", 8, "underline"),
            foreground="#4a90d9", cursor="hand2",
        )
        self.website_link_label.grid(row=1, column=0, sticky="ew", pady=(1, 4))
        self.website_link_label.bind(
            "<Button-1>",
            lambda _e: webbrowser.open(WEBSITE_URL, new=2),
        )

        self.refresh()
        self._show_tab("overlay")
        self._lock_to_largest_tab()
        apply_custom_cursor(self.window)
        bind_ui_click_sound(self.window)
        self.window.after(0, self._configure_native_window)
        self.window.after(1500, self._live_refresh)

    def _make_caption_button(
        self,
        text: str,
        command,
        *,
        image: ImageTk.PhotoImage | None = None,
        width: int,
        close: bool = False,
    ) -> tk.Label:
        normal_bg = "#F3F3F3"
        hover_bg = "#E5E5E5"
        close_hover_bg = "#E81123"
        height = 32

        def _button_photo(bg: str) -> ImageTk.PhotoImage | None:
            if image is None:
                return None
            try:
                icon = ImageTk.getimage(image).convert("RGBA")
                button = Image.new("RGBA", (int(width), height), bg)
                x = max(0, (int(width) - icon.width) // 2)
                y = max(0, (height - icon.height) // 2)
                button.paste(icon, (x, y), icon)
                return ImageTk.PhotoImage(button)
            except Exception:
                return None

        normal_photo = _button_photo(normal_bg)
        hover_photo = _button_photo(close_hover_bg if close else hover_bg)
        label = tk.Label(
            self.caption_bar,
            bg=normal_bg,
            bd=0,
            highlightthickness=0,
            cursor="",
        )
        if normal_photo is not None:
            # width/height are PIXEL dimensions for image labels — keep them here.
            label.configure(
                image=normal_photo,
                width=width,
                height=height,
            )
            label.normal_photo = normal_photo
            label.hover_photo = hover_photo or normal_photo
        else:
            # For text-fallback labels do NOT pass width/height at pixel scale:
            # Tk interprets width/height as character-columns/text-lines for text
            # labels, so height=32 would mean 32 lines (~600 px) and blow up the
            # caption bar grid row height even when pack_propagate(False) is set.
            label.configure(
                text=text,
                font=("Segoe UI", 11),
                fg="#111111",
                padx=max(0, (width - 20) // 2),  # approximate horizontal centering
            )

        def _enter(_event=None) -> None:
            label.configure(bg=close_hover_bg if close else hover_bg)
            if normal_photo is not None:
                label.configure(image=label.hover_photo)

        def _leave(_event=None) -> None:
            label.configure(bg=normal_bg)
            if normal_photo is not None:
                label.configure(image=label.normal_photo)

        def _click(_event=None) -> None:
            play_ui_click()
            command()

        label.bind("<Enter>", _enter, add="+")
        label.bind("<Leave>", _leave, add="+")
        label.bind("<Button-1>", _click, add="+")
        return label

    def _open_about_from_caption(self) -> None:
        _show_copyright_dialog(self.window, self.app)

    def _open_about_menu_from_caption(self) -> None:
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(
            label=tr(self.app, "about_menu_about"),
            command=lambda: (play_ui_click(), self._open_about_from_caption()),
        )
        menu.add_command(
            label=tr(self.app, "about_menu_license"),
            command=lambda: (play_ui_click(), self._open_license_dialog()),
        )
        try:
            x = self.caption_about_button.winfo_rootx()
            y = self.caption_about_button.winfo_rooty() + self.caption_about_button.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _open_settings_from_caption(self) -> None:
        self._open_hotkey_settings()

    def _open_help_popup(self) -> None:
        """Show a small popup explaining how to find the HWID."""
        play_ui_click()
        title = tr(self.app, "help_hwid_title")
        body  = tr(self.app, "help_hwid_body")

        dlg = tk.Toplevel(self.window)
        dlg.transient(self.window)

        dlg_body = _build_dialog_caption(
            dlg, title, dlg.destroy,
            close_icon_path=BAR_CLOSE_PNG, body_bg="#FFFFFF",
        )

        # ── content ────────────────────────────────────────────────────────
        frame = tk.Frame(dlg_body, bg="#FFFFFF", padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        lbl_title = tk.Label(
            frame, text=title,
            bg="#FFFFFF", fg="#111111",
            font=("Segoe UI", 11, "bold"),
            anchor="w", justify="left",
        )
        lbl_title.pack(anchor="w", pady=(0, 10))

        lbl_body = tk.Label(
            frame, text=body,
            bg="#FFFFFF", fg="#333333",
            font=("Segoe UI", 10),
            anchor="w", justify="left",
            wraplength=380,
        )
        lbl_body.pack(anchor="w")

        btn_ok = tk.Button(
            frame, text="OK",
            font=("Segoe UI", 9),
            bg="#0078D4", fg="#FFFFFF",
            activebackground="#005A9E", activeforeground="#FFFFFF",
            relief="flat", bd=0, padx=20, pady=6, cursor="hand2",
            command=dlg.destroy,
        )
        btn_ok.pack(pady=(16, 0))

        # ── centre on parent ────────────────────────────────────────────────
        dlg.update_idletasks()
        pw = self.window.winfo_rootx()
        py = self.window.winfo_rooty()
        pW = self.window.winfo_width()
        pH = self.window.winfo_height()
        dW = dlg.winfo_reqwidth()
        dH = dlg.winfo_reqheight()
        dlg.geometry(f"+{pw + (pW - dW) // 2}+{py + (pH - dH) // 2}")
        dlg.deiconify()
        dlg.lift()
        dlg.grab_set()

    def _open_user_center(self) -> None:
        """Open the Account / User Center dialog (login, license sync, share)."""
        # If already open, bring to front
        dlg = getattr(self, "_uc_dialog", None)
        if dlg is not None:
            try:
                dlg.lift()
                dlg.focus_force()
                return
            except Exception:
                self._uc_dialog = None

        import threading as _threading
        import account_sync as _acc

        dialog = tk.Toplevel(self.window)
        self._uc_dialog = dialog
        dialog.transient(self.window)
        # Non-modal — no grab_set() so user can keep using the app
        apply_custom_cursor(dialog)
        bind_ui_click_sound(dialog)

        def _on_close() -> None:
            self._uc_dialog = None
            try:
                dialog.destroy()
            except Exception:
                pass

        _sys_bg = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
        dlg_body = _build_dialog_caption(
            dialog, tr(self.app, "uc_title"), _on_close,
            close_icon_path=BAR_CLOSE_PNG, body_bg=_sys_bg,
        )

        outer = ttk.Frame(dlg_body, padding=(16, 12, 16, 16))
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, minsize=280, weight=1)

        # ── helpers ───────────────────────────────────────────────────────────

        def _center_dialog() -> None:
            dialog.update_idletasks()
            dw = dialog.winfo_reqwidth()
            dh = dialog.winfo_reqheight()
            try:
                import ctypes.wintypes as _wt
                hwnd = self._hwnd()
                if hwnd:
                    _u32 = ctypes.windll.user32
                    _u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_wt.RECT)]
                    _u32.GetWindowRect.restype = ctypes.c_bool
                    _r = _wt.RECT()
                    if _u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(_r)):
                        wx, wy = _r.left, _r.top
                        ww = _r.right - _r.left
                        wh = _r.bottom - _r.top
                        cx = wx + max(0, (ww - dw) // 2)
                        cy = wy + max(0, (wh - dh) // 2)
                        dialog.geometry(f"+{cx}+{cy}")
                        return
            except Exception:
                pass
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            dialog.geometry(f"+{max(0, (sw - dw) // 2)}+{max(0, (sh - dh) // 2)}")

        def _auto_sync_license(sess: dict) -> None:
            """Fetch license key from Supabase account and apply locally (background)."""
            mv = getattr(dialog, "_lic_msg_var", None)
            ml = getattr(dialog, "_lic_msg_label", None)
            if mv:
                mv.set(tr(self.app, "uc_license_fetching"))
            if ml:
                ml.configure(foreground="#888888")

            def _bg() -> None:
                try:
                    import license_check as _lc
                    import account_sync as _acc2
                    token = sess.get("access_token", "")
                    key = _acc2.fetch_user_license_key(token) if token else None
                    if key:
                        status = _lc.save_license(key)
                        ok = status.is_licensed
                        def _upd() -> None:
                            mv2 = getattr(dialog, "_lic_msg_var", None)
                            ml2 = getattr(dialog, "_lic_msg_label", None)
                            if mv2:
                                mv2.set(tr(self.app, "uc_license_ok") if ok else tr(self.app, "uc_license_err"))
                            if ml2:
                                ml2.configure(foreground="#1f9b4a" if ok else "#C0392B")
                            try:
                                _apply_license_status(self.app, _lc.current_status())
                                refresh_control_panel(self.app)
                            except Exception:
                                pass
                        try:
                            dialog.after(0, _upd)
                        except Exception:
                            pass
                    else:
                        def _upd_none() -> None:
                            mv2 = getattr(dialog, "_lic_msg_var", None)
                            ml2 = getattr(dialog, "_lic_msg_label", None)
                            if mv2:
                                mv2.set(tr(self.app, "uc_license_none"))
                            if ml2:
                                ml2.configure(foreground="#b07800")
                        try:
                            dialog.after(0, _upd_none)
                        except Exception:
                            pass
                except Exception:
                    pass

            _threading.Thread(target=_bg, daemon=True, name="UC-SyncLic").start()

        def _render(sess: dict | None) -> None:
            for w in outer.winfo_children():
                w.destroy()
            # Clear stored refs
            try:
                del dialog._lic_msg_var   # type: ignore[attr-defined]
                del dialog._lic_msg_label  # type: ignore[attr-defined]
            except AttributeError:
                pass

            if not sess:
                # ── Not logged in ──────────────────────────────────────────────
                ttk.Label(
                    outer,
                    text=tr(self.app, "uc_title"),
                    font=("Segoe UI", 12, "bold"),
                ).grid(row=0, column=0, sticky="w", pady=(0, 12))

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_login_google"),
                    cursor="",
                    command=lambda: _do_oauth("google"),
                ).grid(row=1, column=0, sticky="ew", pady=(0, 4))

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_login_discord"),
                    cursor="",
                    command=lambda: _do_oauth("discord"),
                ).grid(row=2, column=0, sticky="ew", pady=(0, 10))

                ttk.Label(
                    outer,
                    text=tr(self.app, "uc_or"),
                    foreground="#888888",
                    font=("Segoe UI", 9),
                ).grid(row=3, column=0, pady=(0, 8))

                fields = ttk.Frame(outer)
                fields.grid(row=4, column=0, sticky="ew", pady=(0, 4))
                fields.grid_columnconfigure(1, weight=1)

                ttk.Label(fields, text=tr(self.app, "uc_email")).grid(
                    row=0, column=0, sticky="w", padx=(0, 8))
                email_var = tk.StringVar()
                email_entry = ttk.Entry(fields, textvariable=email_var, width=24)
                email_entry.grid(row=0, column=1, sticky="ew")

                ttk.Label(fields, text=tr(self.app, "uc_password")).grid(
                    row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
                pw_var = tk.StringVar()
                pw_entry = ttk.Entry(fields, textvariable=pw_var, show="•", width=24)
                pw_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))

                msg_var = tk.StringVar()
                msg_lbl = ttk.Label(
                    outer, textvariable=msg_var,
                    wraplength=280, foreground="#C0392B", font=("Segoe UI", 9),
                )
                msg_lbl.grid(row=5, column=0, sticky="w", pady=(6, 4))

                def _on_login_fail(err: str) -> None:
                    msg_var.set(tr(self.app, "uc_msg_error", msg=err))
                    msg_lbl.configure(foreground="#C0392B")

                def _on_login_success(new_sess: dict) -> None:
                    _render(new_sess)
                    _center_dialog()
                    _auto_sync_license(new_sess)

                def _do_login() -> None:
                    e = email_var.get().strip()
                    p = pw_var.get()
                    if not e or not p:
                        msg_var.set(tr(self.app, "uc_msg_empty"))
                        msg_lbl.configure(foreground="#C0392B")
                        return
                    msg_var.set(tr(self.app, "uc_msg_logging_in"))
                    msg_lbl.configure(foreground="#888888")
                    dialog.update_idletasks()

                    def _bg() -> None:
                        ok, err, new_sess = _acc.login(e, p)
                        if ok:
                            merged = _acc.fetch_and_merge_profile(new_sess, self.app.cfg)
                            _acc.save_session(merged)
                            try:
                                dialog.after(0, lambda: _on_login_success(merged))
                            except Exception:
                                pass
                        else:
                            try:
                                dialog.after(0, lambda: _on_login_fail(err))
                            except Exception:
                                pass

                    _threading.Thread(target=_bg, daemon=True, name="UC-Login").start()

                def _do_oauth(provider: str) -> None:
                    msg_var.set(tr(self.app, "uc_msg_waiting_browser"))
                    msg_lbl.configure(foreground="#888888")
                    dialog.update_idletasks()

                    def _bg() -> None:
                        ok, err, new_sess = _acc.login_oauth(provider)
                        if ok:
                            merged = _acc.fetch_and_merge_profile(new_sess, self.app.cfg)
                            _acc.save_session(merged)
                            try:
                                dialog.after(0, lambda: _on_login_success(merged))
                            except Exception:
                                pass
                        else:
                            try:
                                dialog.after(0, lambda: _on_login_fail(err))
                            except Exception:
                                pass

                    _threading.Thread(
                        target=_bg, daemon=True, name=f"UC-OAuth-{provider}"
                    ).start()

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_login_btn"),
                    cursor="",
                    command=_do_login,
                ).grid(row=6, column=0, sticky="ew", pady=(0, 8))
                pw_entry.bind("<Return>", lambda _e: _do_login())

                reg_frame = ttk.Frame(outer)
                reg_frame.grid(row=7, column=0, sticky="w")
                ttk.Label(
                    reg_frame,
                    text=tr(self.app, "uc_register_hint"),
                    font=("Segoe UI", 9),
                ).pack(side="left")
                reg_link = ttk.Label(
                    reg_frame,
                    text=tr(self.app, "uc_register_link"),
                    foreground="#0078D4",
                    cursor="hand2",
                    font=("Segoe UI", 9, "underline"),
                )
                reg_link.pack(side="left", padx=(4, 0))
                reg_link.bind(
                    "<Button-1>",
                    lambda _e: (play_ui_click(), webbrowser.open(WEBSITE_URL, new=2)),
                )

                email_entry.focus_set()

            else:
                # ── Logged in ──────────────────────────────────────────────────
                name = sess.get("full_name") or ""
                email = sess.get("email", "")
                pts = sess.get("referral_points", 0)

                display_name = name or email
                ttk.Label(
                    outer,
                    text=display_name,
                    font=("Segoe UI", 11, "bold"),
                ).grid(row=0, column=0, sticky="w", pady=(0, 2))

                info_parts: list[str] = []
                if name and email:
                    info_parts.append(email)
                if pts is not None:
                    info_parts.append(tr(self.app, "uc_points", pts=pts))
                ttk.Label(
                    outer,
                    text="  •  ".join(info_parts) if info_parts else "",
                    foreground="#555555",
                    font=("Segoe UI", 9),
                ).grid(row=1, column=0, sticky="w", pady=(0, 10))

                ttk.Separator(outer, orient="horizontal").grid(
                    row=2, column=0, sticky="ew", pady=(0, 10))

                lic_msg_var = tk.StringVar()
                lic_msg_lbl = ttk.Label(
                    outer, textvariable=lic_msg_var,
                    font=("Segoe UI", 9), wraplength=280,
                )
                lic_msg_lbl.grid(row=3, column=0, sticky="w", pady=(0, 6))

                # Store refs so _auto_sync_license can update them
                dialog._lic_msg_var = lic_msg_var    # type: ignore[attr-defined]
                dialog._lic_msg_label = lic_msg_lbl  # type: ignore[attr-defined]

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_sync_license"),
                    cursor="",
                    command=lambda: _auto_sync_license(sess),
                ).grid(row=4, column=0, sticky="ew", pady=(0, 10))

                ttk.Separator(outer, orient="horizontal").grid(
                    row=5, column=0, sticky="ew", pady=(0, 10))

                share_msg_var = tk.StringVar()

                def _do_share() -> None:
                    ref_code = sess.get("referral_code", "")
                    share_url = f"{WEBSITE_URL}?ref={ref_code}" if ref_code else WEBSITE_URL
                    try:
                        dialog.clipboard_clear()
                        dialog.clipboard_append(share_url)
                        share_msg_var.set(tr(self.app, "uc_share_copied"))
                    except Exception:
                        pass

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_share"),
                    cursor="",
                    command=_do_share,
                ).grid(row=6, column=0, sticky="ew", pady=(0, 2))

                ttk.Label(
                    outer,
                    textvariable=share_msg_var,
                    foreground="#1f9b4a",
                    font=("Segoe UI", 9),
                ).grid(row=7, column=0, sticky="w", pady=(0, 8))

                def _do_logout() -> None:
                    token = sess.get("access_token", "")
                    def _bg() -> None:
                        _acc.logout(token)
                        try:
                            dialog.after(0, lambda: (_render(None), _center_dialog()))
                        except Exception:
                            pass
                    _threading.Thread(target=_bg, daemon=True, name="UC-Logout").start()

                ttk.Button(
                    outer,
                    text=tr(self.app, "uc_logout"),
                    cursor="",
                    command=_do_logout,
                ).grid(row=8, column=0, sticky="ew")

        # ── lifecycle ─────────────────────────────────────────────────────────
        sess0 = _acc.load_session()
        _render(sess0)
        _center_dialog()
        dialog.deiconify()
        dialog.lift()
        if sess0:
            _auto_sync_license(sess0)

    def _toggle_caption_language(self) -> None:
        current = lang_code(self.app)
        next_lang = "vi" if current == "en" else "en"
        try:
            self.language_var.set(next_lang)
        except Exception:
            pass
        self.actions["set_language"](next_lang)

    def _on_caption_drag_start(self, event) -> None:
        # winfo_x/y returns 0 for overrideredirect windows; use GetWindowRect instead
        wx, wy = 0, 0
        try:
            import ctypes.wintypes as _wt
            hwnd = self._hwnd()
            if hwnd:
                user32 = ctypes.windll.user32
                user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_wt.RECT)]
                user32.GetWindowRect.restype = ctypes.c_bool
                _r = _wt.RECT()
                if user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(_r)):
                    wx, wy = _r.left, _r.top
        except Exception:
            pass
        self._caption_drag = {
            "x": int(event.x_root),
            "y": int(event.y_root),
            "wx": wx,
            "wy": wy,
        }

    def _on_caption_drag_motion(self, event) -> None:
        if not self._caption_drag:
            return
        dx = int(event.x_root) - self._caption_drag["x"]
        dy = int(event.y_root) - self._caption_drag["y"]
        nx = self._caption_drag["wx"] + dx
        ny = self._caption_drag["wy"] + dy
        self.window.geometry(f"+{nx}+{ny}")
        self._panel_pos = (nx, ny)

    def _on_caption_drag_end(self, _event=None) -> None:
        self._caption_drag = None

    def _on_window_mapped(self, _event=None) -> None:
        try:
            if self.window.state() != "iconic":
                self.window.overrideredirect(True)
                self.window.after(0, self._configure_native_window)
                self.window.after(300, self._query_window_pos)
        except Exception:
            pass

    def prepare_initial_render(self) -> None:
        """Render/layout the panel while it is still hidden.

        Startup uses this so the splash can stay visible until the control
        panel is fully measured. The actual window is deiconified later.
        """
        try:
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            self._lock_to_largest_tab()
            self.window.update_idletasks()
        except Exception as exc:
            print(f"[gui] initial render failed: {exc}")

    def show(self) -> None:
        _is_first = not self._first_shown
        if _is_first:
            self._first_shown = True
        try:
            self.window.overrideredirect(True)
            if _is_first:
                # First open: force topmost so the panel isn't buried under other windows.
                self.window.attributes("-topmost", True)
            self._lock_to_largest_tab()
            self.window.deiconify()
            self.window.state("normal")
        except Exception:
            pass
        self.window.after(0, self._configure_native_window)
        self.window.after(300, self._query_window_pos)
        self._show_native(SW_RESTORE)
        self.window.lift()
        if _is_first:
            try:
                self.window.attributes("-topmost", True)
            except Exception:
                pass
            # Drop always-on-top after the panel is fully visible on screen.
            # Subsequent opens behave as a normal (non-topmost) window.
            self.window.after(400, self._drop_topmost)
        try:
            self.window.focus_force()
        except Exception:
            pass

    def _drop_topmost(self) -> None:
        """Remove always-on-top after the first open; panel becomes a normal window."""
        try:
            self.window.attributes("-topmost", False)
        except Exception:
            pass

    def hide(self) -> None:
        self._disable_game_panel_features()
        try:
            self.window.withdraw()
        except Exception:
            pass
        self._show_native(SW_HIDE)

    def minimize(self) -> None:
        try:
            self.window.attributes("-topmost", False)
            self.window.update_idletasks()
            self.window.overrideredirect(False)
            self.window.deiconify()
            self.window.state("iconic")
        except Exception:
            pass
        self._show_native(SW_SHOWMINIMIZED)

    def refresh(self) -> None:
        self._syncing = True
        self.window.title(tr(self.app, "gui_window_title"))
        self.caption_title.configure(text=tr(self.app, "gui_window_title"))
        self.heading_label.configure(text=tr(self.app, "gui_heading"))
        self.language_var.set(lang_code(self.app))
        self.monitoring_frame.configure(text=tr(self.app, "gui_monitoring_frame"))
        self.status_caption.configure(text=tr(self.app, "gui_status_label"))
        self.status_value.configure(text=session_status_text(self.app))
        self.monitor_button.configure(
            text=tr(self.app, "menu_stop_monitoring" if self.app.monitoring_enabled else "menu_start_monitoring"),
            state="normal",
        )
        if self._wwm_logo_photo is not None:
            self.wwm_logo_label.configure(image=self._wwm_logo_photo, text="")
            self.wwm_logo_label.image = self._wwm_logo_photo
        else:
            self.wwm_logo_label.configure(text="")
        self.options_frame.configure(text=tr(self.app, "gui_overlay_options_frame"))
        self.tweaks_frame.configure(text=tr(self.app, "gui_tweaks_frame"))
        self.game_ping_frame.configure(text=tr(self.app, "gui_game_ping_frame"))
        self.game_data_frame.configure(text=tr(self.app, "gui_game_data_frame"))
        self.game_servers_frame.configure(text=tr(self.app, "gui_game_servers_frame"))
        self._sync_game_sections()
        self._tab_labels["overlay"] = tr(self.app, "gui_sidebar_overlay")
        self._tab_labels["tweaks"] = tr(self.app, "gui_sidebar_tweaks")
        self._sync_game_tab_visibility()

        if self._donate_photo is not None:
            self.donate_button.configure(image=self._donate_photo, text="", cursor="")
        else:
            self.donate_button.configure(text=tr(self.app, "menu_donate"), image="", cursor="")
        if self._discord_photo is not None:
            self.discord_button.configure(image=self._discord_photo, text="", cursor="")
        else:
            self.discord_button.configure(text=tr(self.app, "gui_join_discord"), image="", cursor="")
        self.developed_by_label.configure(
            text=tr(
                self.app,
                "gui_developed_by",
                version=__version__,
                developer=DEVELOPER_NAME,
            )
        )
        self.website_link_label.configure(text=tr(self.app, "gui_website_link"))

        # License gate — when unlicensed, every option/tweak/game-toggle
        # checkbox goes ``state="disabled"`` except the always-free
        # ping/loss display in the overlay tab. The bare ping/loss
        # baseline still updates in the overlay because the gate is
        # also enforced in display_loop; here we just lock the UI so
        # the user can't toggle anything they shouldn't.
        licensed = bool(getattr(self.app, "licensed", False))
        free_options = {"show_ping", "show_loss"}

        for attr, var in self.option_vars.items():
            enabled = bool(getattr(self.options, attr))
            var.set(enabled)
            btn = self.option_buttons[attr]
            btn.configure(text=tr(self.app, self._option_keys[attr]))
            btn.configure(
                state="normal" if (licensed or attr in free_options) else "disabled"
            )

        game_option_labels = {
            "show_ping": "gui_game_show_ping",
            "show_connection": "gui_game_show_connection",
            "show_server_ips": "gui_game_show_server_ips",
        }
        for attr, var in self.game_option_vars.items():
            enabled = bool(getattr(self.game_options, attr))
            var.set(enabled)
            btn = self.game_option_buttons[attr]
            btn.configure(text=tr(self.app, game_option_labels[attr]))
            btn.configure(state="normal" if licensed else "disabled")

        for key, card in self._tweak_cards.items():
            enabled = self.app.game_tweaks.is_enabled(key)
            self.tweak_vars[key].set(enabled)
            btn = self.tweak_buttons[key]
            btn.configure(text=tr(self.app, card.title_key))
            btn.configure(state="normal" if licensed else "disabled")
        self._refresh_game_metrics()
        self._syncing = False

    def _visible_tab_specs(self) -> list[tuple[str, str, ImageTk.PhotoImage | None]]:
        order = ("overlay", "tweaks", "game")
        return [
            (name, self._tab_labels.get(name, name.title()), self._tab_icons.get(name))
            for name in order
            if self._tab_visible.get(name, False)
        ]

    def _tab_text_width(self, text: str, *, bold: bool = False) -> int:
        # Segoe UI 9 is close to ttk's default tab text; this keeps the canvas
        # tab width stable without importing tkinter.font globally.
        try:
            import tkinter.font as tkfont
            font = tkfont.Font(family="Segoe UI", size=9, weight=("bold" if bold else "normal"))
            return int(font.measure(text))
        except Exception:
            return max(48, len(text) * 7)

    def _render_tab_bar(self) -> None:
        try:
            self.tab_bar.delete("all")
        except Exception:
            return
        if not self._tab_visible.get(self._active_tab, False):
            self._active_tab = "overlay"
            self._tab_indicator_box = None
        specs = self._visible_tab_specs()
        self._tab_bounds = {}
        x = 2
        y0 = 2
        height = 32
        gap = 6
        for name, label, _icon in specs:
            width = max(
                self._tab_fixed_widths.get(name, 112),
                self._tab_text_width(label, bold=True) + 46,
            )
            self._tab_bounds[name] = (x, y0, x + width, y0 + height)
            x += width + gap

        active_box = self._tab_bounds.get(self._active_tab)
        if active_box is None and specs:
            self._active_tab = specs[0][0]
            active_box = self._tab_bounds.get(self._active_tab)
        if active_box is not None:
            if self._tab_indicator_box is None:
                self._tab_indicator_box = tuple(float(v) for v in active_box)
            self._draw_tab_indicator(self._tab_indicator_box)

        for name, label, icon in specs:
            x1, y1, x2, y2 = self._tab_bounds[name]
            tag = f"tab_{name}"
            if name != self._active_tab:
                self.tab_bar.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill="SystemButtonFace",
                    outline="#D0D0D0",
                    width=1,
                    tags=(tag, "tab_item"),
                )
            ix = x1 + 18
            if icon is not None:
                self.tab_bar.create_image(ix, (y1 + y2) // 2, image=icon, tags=(tag, "tab_item"))
            self.tab_bar.create_text(
                x1 + 34,
                (y1 + y2) // 2,
                anchor="w",
                text=label,
                font=("Segoe UI", 9, "bold" if name == self._active_tab else "normal"),
                fill="#003A70" if name == self._active_tab else "#000000",
                tags=(tag, "tab_item"),
            )
            self.tab_bar.tag_bind(tag, "<Enter>", lambda _e: set_custom_cursor())
            self.tab_bar.tag_bind(tag, "<Leave>", lambda _e: set_custom_cursor())

        try:
            self.tab_bar.configure(width=max(x + 2, 1), height=36)
        except Exception:
            pass

    def _draw_tab_indicator(self, box: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = box
        self.tab_bar.create_rectangle(
            int(x1),
            int(y1),
            int(x2),
            int(y2),
            fill="#EAF3FF",
            outline="#0078D4",
            width=1,
            tags=("tab_indicator",),
        )

    def _animate_tab_indicator(self, target_tab: str) -> None:
        target = self._tab_bounds.get(target_tab)
        if target is None:
            self._render_tab_bar()
            return
        start = self._tab_indicator_box or tuple(float(v) for v in target)
        end = tuple(float(v) for v in target)
        if self._tab_anim_job is not None:
            try:
                self.window.after_cancel(self._tab_anim_job)
            except Exception:
                pass
            self._tab_anim_job = None

        steps = 8

        def _step(i: int = 1) -> None:
            t = min(1.0, i / steps)
            # Smoothstep easing: visible slide without feeling jumpy.
            eased = t * t * (3.0 - 2.0 * t)
            self._tab_indicator_box = tuple(
                start[idx] + (end[idx] - start[idx]) * eased
                for idx in range(4)
            )
            self._render_tab_bar()
            if i < steps:
                self._tab_anim_job = self.window.after(14, lambda: _step(i + 1))
            else:
                self._tab_indicator_box = end
                self._tab_anim_job = None
                self._render_tab_bar()

        _step()

    def _on_tab_bar_click(self, event) -> None:
        for name, (x1, y1, x2, y2) in self._tab_bounds.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                play_ui_click()
                self._show_tab(name)
                return

    def _game_tab_available(self) -> bool:
        return bool(self.app.pid and self.app.proc_name.strip().lower() == "wwm.exe")

    def _sync_game_tab_visibility(self) -> None:
        available = self._game_tab_available()
        if available:
            icon = _load_process_icon_photo(self.app.pid, 22, 22) or self._game_tab_photo
            self._game_tab_photo = icon
            self._tab_icons["game"] = icon
            self._tab_labels["game"] = tr(self.app, "gui_game_tab")
            if not self._game_tab_button_visible:
                self._game_tab_button_visible = True
                self._tab_visible["game"] = True
                self._render_tab_bar()
                self.window.after_idle(self._lock_to_largest_tab)
            else:
                self._tab_visible["game"] = True
                self._render_tab_bar()
            return
        if self._game_tab_button_visible:
            self._game_tab_button_visible = False
            self._tab_visible["game"] = False
        if self._active_tab == "game":
            self._active_tab = "overlay"
            self.game_tab.grid_remove()
            self.tweaks_tab.grid_remove()
            self.overlay_tab.grid(row=0, column=0, sticky="nsew")
            self._tab_indicator_box = None
        self._render_tab_bar()

    def _show_tab(self, tab_name: str) -> None:
        if tab_name == "game" and not self._game_tab_available():
            tab_name = "overlay"
        previous_tab = self._active_tab
        self._active_tab = tab_name
        self.overlay_tab.grid_remove()
        self.tweaks_tab.grid_remove()
        self.game_tab.grid_remove()
        if tab_name == "overlay":
            self.overlay_tab.grid(row=0, column=0, sticky="nsew")
        elif tab_name == "tweaks":
            self.tweaks_tab.grid(row=0, column=0, sticky="nsew")
        else:
            self.game_tab.grid(row=0, column=0, sticky="nsew")
        self.refresh()
        if previous_tab != tab_name:
            self._animate_tab_indicator(tab_name)
        else:
            self._render_tab_bar()
        self.window.after_idle(self._restore_locked_size)

    def _sync_game_sections(self) -> None:
        if bool(getattr(self.game_options, "show_ping", False)):
            self.game_ping_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        else:
            self.game_ping_frame.grid_remove()
        if bool(getattr(self.game_options, "show_connection", False)):
            self.game_data_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        else:
            self.game_data_frame.grid_remove()
        if bool(getattr(self.game_options, "show_server_ips", False)):
            if not self.game_servers_frame.winfo_ismapped():
                self.game_servers_frame.pack(fill="x", pady=(6, 0))
        else:
            self.game_servers_frame.pack_forget()

    def _disable_game_panel_features(self) -> None:
        changed = False
        for attr in ("show_ping", "show_connection", "show_server_ips"):
            if bool(getattr(self.game_options, attr, False)):
                setattr(self.game_options, attr, False)
                changed = True
        if self._active_tab == "game":
            self._active_tab = "overlay"
            self.game_tab.grid_remove()
            self.overlay_tab.grid(row=0, column=0, sticky="nsew")
        if changed:
            try:
                self.game_options.persist()
            except Exception as e:
                print(f"[gui] persist game panel options error: {e}")
            _clear_server_endpoints(self.app)
            self.refresh()

    def _fit_to_content(self) -> tuple[int, int]:
        try:
            self.window.update_idletasks()
            width = max(600, self.window.winfo_reqwidth())
            height = self.window.winfo_reqheight()
            self.window.geometry(f"{width}x{height}")
            return width, height
        except Exception:
            return 600, 0

    def _lock_to_largest_tab(self) -> None:
        original_tab = self._active_tab
        original_lang = self.app.cfg.get("language", lang_code(self.app))
        sizes: list[tuple[int, int]] = []
        try:
            # Measure both supported UI languages before locking geometry so
            # swapping language from the caption button does not shift controls.
            for language in ("en", "vi"):
                self.app.cfg["language"] = language
                self.refresh()
                self._show_tab_for_measure("overlay")
                sizes.append(self._fit_to_content())
                self._show_tab_for_measure("tweaks")
                sizes.append(self._fit_to_content())
                if self._game_tab_available():
                    sizes.append(self._measure_full_game_tab_size())
        finally:
            self.app.cfg["language"] = original_lang
            if original_tab == "game" and not self._game_tab_available():
                original_tab = "overlay"
            self._show_tab_for_measure(original_tab)
            self.refresh()
        width = max(size[0] for size in sizes) if sizes else 600
        height = max(size[1] for size in sizes) if sizes else self.window.winfo_reqheight()
        self._locked_geometry = (width, height)
        if not self._centered_once:
            self._center_on_screen(width, height)
            self._centered_once = True
        else:
            self._restore_locked_size()

    def _measure_full_game_tab_size(self) -> tuple[int, int]:
        """Measure Game tab as if all optional sections are visible.

        This keeps the Control Panel geometry stable even when Ping,
        Connection, or Server IPs are disabled to save resources.
        """
        saved = {
            "show_ping": bool(getattr(self.game_options, "show_ping", False)),
            "show_connection": bool(getattr(self.game_options, "show_connection", False)),
            "show_server_ips": bool(getattr(self.game_options, "show_server_ips", False)),
        }
        try:
            for attr in saved:
                setattr(self.game_options, attr, True)
            self._show_tab_for_measure("game")
            self._sync_game_sections()
            self._refresh_game_metrics()
            return self._fit_to_content()
        finally:
            for attr, value in saved.items():
                setattr(self.game_options, attr, value)
            self._sync_game_sections()

    def _show_tab_for_measure(self, tab_name: str) -> None:
        self._active_tab = tab_name
        self.overlay_tab.grid_remove()
        self.tweaks_tab.grid_remove()
        self.game_tab.grid_remove()
        if tab_name == "overlay":
            self.overlay_tab.grid(row=0, column=0, sticky="nsew")
        elif tab_name == "tweaks":
            self.tweaks_tab.grid(row=0, column=0, sticky="nsew")
        else:
            self.game_tab.grid(row=0, column=0, sticky="nsew")

    def _restore_locked_size(self) -> None:
        size = getattr(self, "_locked_geometry", None)
        if not size:
            return
        try:
            self.window.geometry(f"{size[0]}x{size[1]}")
        except Exception:
            pass

    def _center_on_screen(self, width: int, height: int) -> None:
        try:
            self.window.update_idletasks()
            screen_w = int(self.window.winfo_screenwidth())
            screen_h = int(self.window.winfo_screenheight())
            x = max(0, (screen_w - int(width)) // 2)
            y = max(0, (screen_h - int(height)) // 2)
            self.window.geometry(f"{int(width)}x{int(height)}+{x}+{y}")
        except Exception:
            self._restore_locked_size()

    def _set_game_metric(self, key: str, label_key: str, value: str) -> None:
        labels = self.game_metric_labels.get(key)
        if labels is None:
            return
        name_label, value_label = labels
        name_label.configure(text=tr(self.app, label_key))
        value_label.configure(text=value)

    def _on_game_server_inner_configure(self, _event=None) -> None:
        try:
            self.game_server_canvas.configure(
                scrollregion=self.game_server_canvas.bbox("all")
            )
        except Exception:
            pass

    def _on_game_server_canvas_configure(self, event=None) -> None:
        try:
            width = int(event.width) if event is not None else self.game_server_canvas.winfo_width()
            self.game_server_canvas.itemconfigure(self._game_server_window_id, width=width)
        except Exception:
            pass

    def _set_game_server_rows(self, rows: list[str]) -> None:
        if not rows:
            rows = [tr(self.app, "gui_game_servers_empty")]
        while len(self.game_server_labels) < len(rows):
            label = ttk.Label(
                self.game_server_inner,
                font=("Segoe UI", 9),
                anchor="w",
                wraplength=520,
            )
            label.pack(fill="x", pady=2)
            self.game_server_labels.append(label)
        for idx, label in enumerate(self.game_server_labels):
            if idx < len(rows):
                label.configure(text=rows[idx])
                if not label.winfo_ismapped():
                    label.pack(fill="x", pady=2)
            else:
                label.pack_forget()
        try:
            if len(rows) > 3:
                self.game_server_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
            else:
                self.game_server_scrollbar.grid_remove()
                self.game_server_canvas.yview_moveto(0)
        except Exception:
            pass
        try:
            self.game_server_canvas.after_idle(self._on_game_server_inner_configure)
        except Exception:
            pass

    def _refresh_game_metrics(self) -> None:
        available = self._game_tab_available()
        if bool(getattr(self.game_options, "show_ping", False)):
            ping_stats = (
                self.app.ping_state.stats_snapshot()
                if available and self.app.ping_state is not None
                else {}
            )
            self._set_game_metric("last_ping", "gui_game_last_ping", _fmt_latency(ping_stats.get("last")))
            self._set_game_metric("average_ping", "gui_game_average_ping", _fmt_latency(ping_stats.get("avg")))
            self._set_game_metric("higher_ping", "gui_game_higher_ping", _fmt_latency(ping_stats.get("max")))
            self._set_game_metric("lower_ping", "gui_game_lower_ping", _fmt_latency(ping_stats.get("min")))

        if bool(getattr(self.game_options, "show_connection", False)):
            net = _network_session_snapshot(self.app) if available else {}
            self._set_game_metric(
                "bytes_sent",
                "gui_game_bytes_sent",
                _fmt_data_with_rate(net.get("sent_b"), net.get("sent_bps")),
            )
            self._set_game_metric(
                "bytes_received",
                "gui_game_bytes_received",
                _fmt_data_with_rate(net.get("recv_b"), net.get("recv_bps")),
            )
            ping_stats = (
                self.app.ping_state.stats_snapshot()
                if available and self.app.ping_state is not None
                else {}
            )
            self._set_game_metric("jitter", "gui_game_jitter", _fmt_latency(ping_stats.get("jitter")))
            self._set_game_metric("packet_loss", "gui_game_packet_loss", _fmt_percent(ping_stats.get("loss")))

        if bool(getattr(self.game_options, "show_server_ips", False)):
            endpoints, _mode = _server_endpoints_snapshot(self.app) if available else ([], "none")
            self._set_game_server_rows([_fmt_server_endpoint(item) for item in endpoints])

    def _live_refresh(self) -> None:
        try:
            if not self.window.winfo_exists():
                return
            self.status_value.configure(text=session_status_text(self.app))
            self._sync_game_tab_visibility()
            if self._active_tab == "game":
                self._refresh_game_metrics()
        except Exception:
            pass
        try:
            self.window.after(1500, self._live_refresh)
        except Exception:
            pass

    def _on_option_toggle(self, attr: str, enabled: bool) -> None:
        if self._syncing:
            return
        # License gate — every overlay metric option except the
        # always-free ping/loss baseline is locked when unlicensed.
        # Defence in depth: even if a tray menu callback flips the
        # var, we revert it here.
        free_options = {"show_ping", "show_loss"}
        if attr not in free_options and not bool(getattr(self.app, "licensed", False)):
            self._syncing = True
            try:
                self.option_vars[attr].set(bool(getattr(self.options, attr)))
            finally:
                self._syncing = False
            return
        current = bool(getattr(self.options, attr))
        if current != enabled:
            changed = self.actions["toggle_option"](attr)
            if changed is False:
                self._syncing = True
                try:
                    self.option_vars[attr].set(bool(getattr(self.options, attr)))
                finally:
                    self._syncing = False
        self.refresh()

    def _on_game_option_toggle(self, attr: str, enabled: bool) -> None:
        if self._syncing:
            return
        # License gate — entire Game tab is licensed-only.
        if not bool(getattr(self.app, "licensed", False)):
            self._syncing = True
            try:
                self.game_option_vars[attr].set(
                    bool(getattr(self.game_options, attr))
                )
            finally:
                self._syncing = False
            return
        current = bool(getattr(self.game_options, attr))
        if current != enabled:
            setattr(self.game_options, attr, enabled)
            try:
                self.game_options.persist()
            except Exception as e:
                print(f"[gui] persist game panel options error: {e}")
            if attr == "show_server_ips":
                if enabled and self.app.pid and self.app.monitoring_enabled:
                    start_server_endpoint_monitor(self.app, self.app.pid, self.app.session_token)
                elif not enabled:
                    _clear_server_endpoints(self.app)
            if attr == "show_connection" and enabled and self.app.pid:
                _reset_network_session_counters(self.app)
        self.refresh()
        self.window.after_idle(self._lock_to_largest_tab)

    def _on_tweak_toggle(self, key: str, enabled: bool) -> None:
        if self._syncing:
            return
        # License gate — every game tweak is locked when unlicensed.
        if not bool(getattr(self.app, "licensed", False)):
            self._syncing = True
            try:
                self.tweak_vars[key].set(self.app.game_tweaks.is_enabled(key))
            finally:
                self._syncing = False
            return
        card = self._tweak_cards[key]
        try:
            restart_required = bool(self.actions["set_game_tweak"](key, enabled))
            if enabled and restart_required:
                self._prompt_restart_now(tr(self.app, card.title_key))
        except Exception as e:
            self.tweak_vars[key].set(not enabled)
            play_ui_alert()
            messagebox.showerror(
                tr(self.app, "gui_tweak_error_title"),
                tr(self.app, "gui_tweak_error_body", name=tr(self.app, card.title_key), error=str(e)),
            )
        finally:
            self.refresh()

    def _on_monitor_toggle_clicked(self) -> None:
        play_ui_click()
        if self.app.monitoring_enabled:
            self._on_stop_clicked()
        else:
            self._on_start_clicked()

    def _on_start_clicked(self) -> None:
        choice = self._prompt_start_behavior()
        if choice is None:
            self.actions["show_overlay"]()
            return
        if choice == "tray":
            self.hide()
        else:
            self.minimize()
        self.actions["start_monitoring"]()
        self.window.after(50, self.refresh)
        self.actions["show_overlay"]()
        self.window.after(200, self.actions["show_overlay"])

    def _on_stop_clicked(self) -> None:
        self.monitor_button.configure(state="disabled")
        self.window.after_idle(self.actions["stop_monitoring"])
        self.window.after(50, self.refresh)
        self.window.after(200, self.refresh)

    def _on_donate_clicked(self, _event=None) -> None:
        play_ui_click()
        _show_plans_popup(self.window, self.app)

    def _open_hotkey_settings(self) -> None:
        cfg = self.app.cfg
        qh_cfg = cfg.setdefault("quest_helper", {})
        panel_cfg = cfg.setdefault("panel", {})
        events_cfg = cfg.setdefault("events", {})
        overlay_cfg = cfg.setdefault("overlay", {})
        toggle_spec  = dict(qh_cfg.get("hotkey") or {"modifiers": ["ctrl", "alt"], "key": "H"})
        scan_spec    = dict(qh_cfg.get("scan_hotkey") or {"modifiers": ["ctrl", "alt"], "key": "G"})
        panel_spec   = dict(panel_cfg.get("hotkey") or {"modifiers": [], "key": "F8"})
        original_hotkeys = {
            "toggle":  dict(toggle_spec),
            "scan":    dict(scan_spec),
            "panel":   dict(panel_spec),
        }
        rotate_default = _event_rotate_seconds(cfg)
        try:
            overlay_scale_default = int(round(float(overlay_cfg.get("scale", 1.0)) * 100))
        except (TypeError, ValueError):
            overlay_scale_default = 100
        overlay_scale_default = max(70, min(180, overlay_scale_default))

        dialog = tk.Toplevel(self.window)
        dialog.transient(self.window)
        apply_custom_cursor(dialog)
        bind_ui_click_sound(dialog)

        def _close() -> None:
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        _sys_bg = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
        dlg_body = _build_dialog_caption(
            dialog, tr(self.app, "settings_dialog_title"), _close,
            close_icon_path=BAR_CLOSE_PNG, body_bg=_sys_bg,
        )

        container = ttk.Frame(dlg_body, padding=16)
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, minsize=160)
        container.grid_columnconfigure(1, minsize=130, weight=1)
        container.grid_columnconfigure(2, minsize=130)
        ttk.Label(
            container,
            text=tr(self.app, "settings_dialog_intro"),
            wraplength=470,
            justify="left",
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        toggle_var  = tk.StringVar(value=_describe_hotkey_spec(toggle_spec))
        scan_var    = tk.StringVar(value=_describe_hotkey_spec(scan_spec))
        panel_var   = tk.StringVar(value=_describe_hotkey_spec(panel_spec))
        state = {
            "toggle":  toggle_spec,
            "scan":    scan_spec,
            "panel":   panel_spec,
            "error":   None,
        }
        error_var = tk.StringVar(value="")

        ttk.Label(
            container,
            text=tr(self.app, "settings_hotkeys_section"),
            font=("Segoe UI", 11, "bold"),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))

        def _make_row(row_idx: int, label_key: str, var: tk.StringVar, target: str) -> None:
            ttk.Label(container, text=tr(self.app, label_key), font=("Segoe UI", 10, "bold")).grid(
                row=row_idx, column=0, sticky="w", pady=4, padx=(0, 10)
            )
            display = ttk.Label(container, textvariable=var, font=("Segoe UI", 10), width=22, anchor="w")
            display.grid(row=row_idx, column=1, sticky="ew", pady=4)
            ttk.Button(
                container,
                text=tr(self.app, "settings_capture_button"),
                cursor="",
                command=lambda: _capture_for(target, display, var),
            ).grid(row=row_idx, column=2, sticky="e", padx=(8, 0), pady=4)

        def _capture_for(target: str, display, var: tk.StringVar) -> None:
            var.set(tr(self.app, "settings_capture_listening"))
            display.configure(foreground="#0078D4")
            dialog.update_idletasks()
            captured = {"value": None}

            def _on_key(event):
                key = (event.keysym or "").upper()
                # Skip pure modifier presses — wait for the real key.
                if key in {
                    "CONTROL_L", "CONTROL_R", "ALT_L", "ALT_R",
                    "SHIFT_L", "SHIFT_R", "WIN_L", "WIN_R", "SUPER_L", "SUPER_R",
                }:
                    return
                modifiers = []
                state_mask = int(event.state)
                if state_mask & 0x4: modifiers.append("ctrl")
                if state_mask & 0x20000: modifiers.append("alt")
                if state_mask & 0x1: modifiers.append("shift")
                if state_mask & 0x40000: modifiers.append("win")
                key_norm = _normalize_capture_key(key)
                # Quest hotkeys must include Ctrl. Panel + Discord overlay
                # toggles also accept bare F-keys (e.g. F8, F9).
                is_panel_function_key = (
                    target in ("panel", "discord")
                    and not modifiers
                    and re.fullmatch(r"F(?:[1-9]|1\d|2[0-4])", key_norm)
                )
                if "ctrl" not in modifiers and not is_panel_function_key:
                    error_var.set(tr(self.app, "settings_invalid"))
                    return
                captured["value"] = {"modifiers": modifiers, "key": key_norm}
                display.configure(foreground="#222222")
                var.set(_describe_hotkey_spec(captured["value"]))
                state[target] = captured["value"]
                error_var.set("")
                dialog.unbind("<KeyPress>")

            dialog.bind("<KeyPress>", _on_key)
            dialog.focus_set()

        _make_row(2, "settings_panel_label", panel_var, "panel")
        _make_row(3, "settings_toggle_label", toggle_var, "toggle")
        _make_row(4, "settings_scan_label", scan_var, "scan")

        # Event rotation interval — only relevant when 2+ events overlap on
        # the ping overlay. Spinbox keeps it discoverable + safe (clamped).
        ttk.Separator(container, orient="horizontal").grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(10, 6)
        )
        ttk.Label(
            container,
            text=tr(self.app, "settings_general_section"),
            font=("Segoe UI", 11, "bold"),
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(
            container,
            text=tr(self.app, "settings_overlay_scale_label"),
            font=("Segoe UI", 10, "bold"),
        ).grid(row=7, column=0, sticky="w", pady=4, padx=(0, 10))
        overlay_scale_var = tk.IntVar(value=overlay_scale_default)
        scale_spin = tk.Spinbox(
            container,
            from_=70,
            to=180,
            increment=5,
            width=6,
            textvariable=overlay_scale_var,
            justify="right",
            cursor="",
        )
        scale_spin.grid(row=7, column=1, sticky="w", pady=4)
        ttk.Label(
            container,
            text=tr(self.app, "settings_overlay_scale_hint"),
            foreground="#777777",
            wraplength=200,
            font=("Segoe UI", 9, "italic"),
            justify="left",
        ).grid(row=7, column=2, sticky="ew", padx=(8, 0))

        transparent_var = tk.BooleanVar(value=bool(overlay_cfg.get("transparent_background", False)))
        transparent_toggle = _ImageToggle(
            container,
            text=tr(self.app, "settings_overlay_transparent"),
            variable=transparent_var,
        )
        transparent_toggle.grid(row=8, column=0, columnspan=3, sticky="w", pady=4)

        ttk.Label(
            container,
            text=tr(self.app, "settings_rotate_label"),
            font=("Segoe UI", 10, "bold"),
        ).grid(row=9, column=0, sticky="w", pady=4, padx=(0, 10))
        rotate_var = tk.IntVar(value=int(rotate_default))
        rotate_spin = tk.Spinbox(
            container,
            from_=3,
            to=120,
            increment=1,
            width=6,
            textvariable=rotate_var,
            justify="right",
            cursor="",
        )
        rotate_spin.grid(row=9, column=1, sticky="w", pady=4)
        ttk.Label(
            container,
            text=tr(self.app, "settings_rotate_hint"),
            foreground="#777777",
            wraplength=200,
            font=("Segoe UI", 9, "italic"),
            justify="left",
        ).grid(row=9, column=2, sticky="ew", padx=(8, 0))

        ttk.Label(
            container,
            text=tr(self.app, "settings_guild_current"),
            font=("Segoe UI", 10),
        ).grid(row=10, column=0, sticky="w", pady=4, padx=(0, 10))
        guild_var = tk.StringVar(
            value=_configured_event_guild_id(self.app) or tr(self.app, "settings_guild_none")
        )
        ttk.Label(
            container,
            textvariable=guild_var,
            font=("Consolas", 10, "bold"),
        ).grid(row=10, column=1, sticky="ew", pady=4)

        def _clear_guild_id() -> None:
            events_block = cfg.setdefault("events", {})
            events_block["guild_id"] = ""
            self.options.show_events = False
            self.option_vars["show_events"].set(False)
            self.options.persist()
            app_config.save(cfg)
            guild_var.set(tr(self.app, "settings_guild_none"))
            error_var.set(tr(self.app, "settings_guild_cleared"))
            try:
                if self.app.event_monitor is not None:
                    self.app.event_monitor.force_refresh()
            except Exception:
                pass
            try:
                refresh_control_panel(self.app)
            except Exception:
                pass

        clear_guild_btn = ttk.Button(
            container,
            text=tr(self.app, "settings_guild_clear"),
            cursor="",
            command=_clear_guild_id,
        )
        clear_guild_btn.grid(row=10, column=2, sticky="e", padx=(8, 0), pady=4)

        ttk.Label(container, textvariable=error_var, foreground="#C0392B", wraplength=560).grid(
            row=11, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        settings_actions = ttk.Frame(container)
        settings_actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        settings_actions.grid_columnconfigure(0, weight=1)
        settings_actions.grid_columnconfigure(1, weight=0)
        autostart_var = tk.BooleanVar(value=bool(cfg.get("autostart", False)))

        def _toggle_start_with_windows() -> None:
            desired = bool(autostart_var.get())
            if autostart.sync(desired):
                cfg["autostart"] = desired
                app_config.save(cfg)
                error_var.set("")
            else:
                autostart_var.set(bool(cfg.get("autostart", False)))
                error_var.set("Could not update Windows startup registry.")

        autostart_toggle = _ImageToggle(
            settings_actions,
            text=tr(self.app, "settings_start_with_windows"),
            variable=autostart_var,
            command=_toggle_start_with_windows,
        )
        autostart_toggle.grid(row=0, column=0, sticky="w")
        ttk.Button(
            settings_actions,
            text=tr(self.app, "settings_check_updates"),
            cursor="",
            command=lambda: self.actions.get("check_updates", lambda: None)(),
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

        buttons = ttk.Frame(container)
        buttons.grid(row=13, column=0, columnspan=3, sticky="e", pady=(14, 0))

        def _on_save() -> None:
            def _valid_hotkey(target: str, spec: dict) -> bool:
                key = (spec.get("key") or "").upper()
                if not key:
                    return False
                modifiers = [str(m).strip().lower() for m in (spec.get("modifiers") or [])]
                if target == "panel" and not modifiers and re.fullmatch(r"F(?:[1-9]|1\d|2[0-4])", key):
                    return True
                return "ctrl" in modifiers or "control" in modifiers

            for target in ("toggle", "scan", "panel"):
                if not _valid_hotkey(target, state[target]):
                    error_var.set(tr(self.app, "settings_invalid"))
                    return
            try:
                rotate_seconds = int(rotate_var.get())
            except (tk.TclError, ValueError):
                rotate_seconds = 8
            rotate_seconds = max(3, min(120, rotate_seconds))
            try:
                overlay_scale_percent = int(overlay_scale_var.get())
            except (tk.TclError, ValueError):
                overlay_scale_percent = 100
            overlay_scale_percent = max(70, min(180, overlay_scale_percent))

            def _normalized_hotkey(spec: dict) -> tuple[tuple[str, ...], str]:
                modifiers = tuple(
                    sorted(str(m).strip().lower() for m in (spec.get("modifiers") or []) if str(m).strip())
                )
                return modifiers, str(spec.get("key") or "").strip().upper()

            hotkeys_changed = any(
                _normalized_hotkey(state[name]) != _normalized_hotkey(original_hotkeys[name])
                for name in ("toggle", "scan", "panel")
            )
            qh_cfg["hotkey"] = state["toggle"]
            qh_cfg["scan_hotkey"] = state["scan"]
            cfg.setdefault("panel", {})["hotkey"] = state["panel"]
            events_cfg["rotate_interval_seconds"] = rotate_seconds
            overlay_cfg["transparent_background"] = bool(transparent_var.get())
            overlay_cfg["scale"] = round(overlay_scale_percent / 100.0, 2)
            app_config.save(cfg)
            try:
                self.actions.get("apply_overlay_settings", lambda: None)()
            except Exception as exc:
                print(f"[settings] apply overlay settings failed: {exc}")
            _close()
            if hotkeys_changed:
                play_ui_alert()
                messagebox.showinfo(
                    tr(self.app, "settings_dialog_title"),
                    tr(self.app, "settings_saved_restart"),
                    parent=self.window,
                )

        ttk.Button(
            buttons,
            text=tr(self.app, "settings_cancel"),
            cursor="",
            command=_close,
        ).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            buttons,
            text=tr(self.app, "settings_save"),
            cursor="",
            command=_on_save,
        ).grid(row=0, column=1)

        dialog.update_idletasks()
        x = self.window.winfo_rootx() + max((self.window.winfo_width() - dialog.winfo_width()) // 2, 0)
        y = self.window.winfo_rooty() + max((self.window.winfo_height() - dialog.winfo_height()) // 2, 0)
        dialog.geometry(f"+{x}+{y}")
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()

    def _open_license_dialog(self) -> None:
        dialog = tk.Toplevel(self.window)
        dialog.transient(self.window)
        apply_custom_cursor(dialog)
        bind_ui_click_sound(dialog)

        def _close() -> None:
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        _sys_bg = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
        dlg_body = _build_dialog_caption(
            dialog, tr(self.app, "settings_license_section"), _close,
            close_icon_path=BAR_CLOSE_PNG, body_bg=_sys_bg,
        )

        try:
            import license_check as _lc
            license_status = _lc.current_status()
        except Exception as exc:
            license_status = None
            _lc = None  # type: ignore[assignment]
            print(f"[main] license_check unavailable: {exc}")

        container = ttk.Frame(dlg_body, padding=16)
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(1, minsize=260, weight=1)

        ttk.Label(
            container,
            text=tr(self.app, "settings_license_hwid_label"),
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        hwid_text = (license_status.hwid if license_status else "—")
        hwid_var = tk.StringVar(value=hwid_text)
        hwid_entry = tk.Entry(
            container,
            textvariable=hwid_var,
            font=("Consolas", 11, "bold"),
            relief="flat",
            state="readonly",
            readonlybackground="#161922",
            fg="#f5c35b",
            highlightthickness=1,
            highlightbackground="#2a2f3a",
        )
        hwid_entry.grid(row=0, column=1, sticky="ew", ipady=4, pady=4)

        status_var = tk.StringVar(value="")
        status_label = ttk.Label(
            container,
            textvariable=status_var,
            font=("Segoe UI", 10),
            wraplength=420,
            justify="left",
        )
        status_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def _refresh_license_state() -> None:
            if _lc is None:
                status_var.set("license_check module not available")
                status_label.configure(foreground="#C0392B")
                return
            status = _lc.current_status()
            text = _lc.status_summary(status, language=lang_code(self.app))
            if not status.is_licensed:
                try:
                    _apply_license_status(self.app, status, create_trial=True)
                    if bool(getattr(self.app, "trial_active", False)):
                        text = _trial_access_summary(self.app, language=lang_code(self.app))
                except Exception:
                    pass
            if bool(getattr(self.app, "license_admin_banned", False)):
                reason = str(getattr(self.app, "license_admin_reason", "") or "")
                version_blocked = bool(getattr(self.app, "license_admin_version_blocked", False))
                if lang_code(self.app) == "vi":
                    text = "Version app này đang bị Admin khóa" if version_blocked else "HWID này đang bị Admin ban"
                    if reason:
                        text += f": {reason}"
                else:
                    text = "This app version is locked by Admin" if version_blocked else "This HWID is banned by Admin"
                    if reason:
                        text += f": {reason}"
            status_var.set(text)
            if bool(getattr(self.app, "license_admin_banned", False)):
                color = "#C0392B"
            elif status.is_licensed or bool(getattr(self.app, "trial_active", False)):
                color = "#1f9b4a"
            elif status.has_saved_key:
                color = "#C0392B"
            else:
                color = "#b07800"
            status_label.configure(foreground=color)
            try:
                _apply_license_status(self.app, status)
            except Exception:
                pass
            try:
                refresh_control_panel(self.app)
            except Exception:
                pass

        def _copy_hwid() -> None:
            try:
                self.window.clipboard_clear()
                self.window.clipboard_append(hwid_text)
                status_var.set(tr(self.app, "settings_license_copied"))
                status_label.configure(foreground="#1f9b4a")
            except Exception as exc:
                status_var.set(str(exc))
                status_label.configure(foreground="#C0392B")

        def _open_license_entry_dialog() -> None:
            if _lc is None:
                return
            sub = tk.Toplevel(dialog)
            sub.transient(dialog)

            def _close_sub() -> None:
                try:
                    sub.grab_release()
                except Exception:
                    pass
                sub.destroy()

            _sys_bg2 = ttk.Style().lookup("TFrame", "background") or "#F0F0F0"
            sub_body = _build_dialog_caption(
                sub, tr(self.app, "settings_license_dialog_title"), _close_sub,
                close_icon_path=BAR_CLOSE_PNG, body_bg=_sys_bg2,
            )
            box = ttk.Frame(sub_body, padding=14)
            box.pack(fill="both", expand=True)
            ttk.Label(
                box,
                text=tr(self.app, "settings_license_dialog_body"),
                wraplength=420,
                justify="left",
                font=("Segoe UI", 10),
            ).pack(anchor="w")
            entry = tk.Text(
                box,
                width=58,
                height=4,
                font=("Consolas", 10),
                wrap="word",
                relief="flat",
                bg="#161922",
                fg="#f5c35b",
                insertbackground="#f5c35b",
            )
            entry.pack(fill="x", pady=(8, 8))
            try:
                clip = sub.clipboard_get().strip()
                if clip and clip.upper().startswith("PO1-"):
                    entry.insert("1.0", clip)
            except Exception:
                pass
            sub_status_var = tk.StringVar(value="")
            sub_status = ttk.Label(
                box,
                textvariable=sub_status_var,
                wraplength=420,
                justify="left",
                font=("Segoe UI", 10),
            )
            sub_status.pack(anchor="w")

            def _on_save_license() -> None:
                key_text = entry.get("1.0", "end").strip()
                if not key_text:
                    return
                status = _lc.save_license(key_text)
                if status.is_licensed:
                    sub_status.configure(foreground="#1f9b4a")
                    sub_status_var.set(tr(self.app, "settings_license_save_ok"))
                    _refresh_license_state()
                    sub.after(900, _close_sub)
                else:
                    sub_status.configure(foreground="#C0392B")
                    sub_status_var.set(
                        tr(
                            self.app,
                            "settings_license_save_failed",
                            reason=(status.error or "unknown"),
                        )
                    )

            row = ttk.Frame(box)
            row.pack(fill="x", pady=(8, 0))
            ttk.Button(
                row,
                text=tr(self.app, "settings_license_cancel"),
                cursor="",
                command=_close_sub,
            ).pack(side=tk.RIGHT, padx=(8, 0))
            ttk.Button(
                row,
                text=tr(self.app, "settings_license_save"),
                cursor="",
                command=_on_save_license,
            ).pack(side=tk.RIGHT)

            sub.update_idletasks()
            # dialog is overrideredirect — parse geometry string for reliable coords
            try:
                import re as _re
                _gm = _re.match(r"\d+x\d+\+(-?\d+)\+(-?\d+)", dialog.winfo_geometry())
                _dx = int(_gm.group(1)) if _gm else dialog.winfo_rootx()
                _dy = int(_gm.group(2)) if _gm else dialog.winfo_rooty()
            except Exception:
                _dx, _dy = dialog.winfo_rootx(), dialog.winfo_rooty()
            sx = _dx + max((dialog.winfo_width()  - sub.winfo_width())  // 2, 0)
            sy = _dy + max((dialog.winfo_height() - sub.winfo_height()) // 2, 0)
            sub.geometry(f"+{sx}+{sy}")
            sub.deiconify()
            sub.lift()
            sub.grab_set()

        def _on_clear_license() -> None:
            if _lc is None:
                return
            _lc.clear_license()
            _refresh_license_state()

        buttons = ttk.Frame(container)
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure(0, weight=1)
        ttk.Button(
            buttons,
            text=tr(self.app, "settings_license_copy_hwid"),
            cursor="",
            command=_copy_hwid,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            buttons,
            text=tr(self.app, "settings_license_enter"),
            cursor="",
            command=_open_license_entry_dialog,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            buttons,
            text=tr(self.app, "settings_license_clear"),
            cursor="",
            command=_on_clear_license,
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(
            buttons,
            text=tr(self.app, "button_close"),
            cursor="",
            command=_close,
        ).grid(row=0, column=3, padx=(8, 0))

        _refresh_license_state()

        def _center_dialog() -> None:
            """Center the dialog over the main panel using GetWindowRect."""
            dialog.update_idletasks()
            dw = dialog.winfo_reqwidth()
            dh = dialog.winfo_reqheight()
            try:
                import ctypes.wintypes as _wt
                hwnd = self._hwnd()
                if hwnd:
                    _u32 = ctypes.windll.user32
                    _u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_wt.RECT)]
                    _u32.GetWindowRect.restype = ctypes.c_bool
                    _r = _wt.RECT()
                    if _u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(_r)):
                        wx, wy = _r.left, _r.top
                        ww = _r.right - _r.left
                        wh = _r.bottom - _r.top
                        cx = wx + max(0, (ww - dw) // 2)
                        cy = wy + max(0, (wh - dh) // 2)
                        dialog.geometry(f"+{cx}+{cy}")
                        return
            except Exception:
                pass
            # Fallback: center on screen
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            dialog.geometry(f"+{max(0, (sw - dw) // 2)}+{max(0, (sh - dh) // 2)}")

        _center_dialog()
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()

    def _on_discord_clicked(self, _event=None) -> None:
        play_ui_click()
        self.actions["discord"]()

    def _on_close_requested(self) -> None:
        choice = self._prompt_close_behavior()
        if choice == "tray":
            self.hide()
        elif choice == "close":
            self.actions["quit_app"]()

    def _prompt_start_behavior(self) -> str | None:
        return self._prompt_choice_dialog(
            tr(self.app, "gui_start_prompt_title"),
            tr(self.app, "gui_start_prompt_body"),
            [
                (tr(self.app, "gui_start_hide"), "tray"),
                (tr(self.app, "gui_start_minimize"), "minimize"),
                (tr(self.app, "gui_start_cancel"), None),
            ],
        )

    def _prompt_close_behavior(self) -> str | None:
        return self._prompt_choice_dialog(
            tr(self.app, "gui_close_prompt_title"),
            tr(self.app, "gui_close_prompt_body"),
            [
                (tr(self.app, "gui_close_hide"), "tray"),
                (tr(self.app, "gui_close_exit"), "close"),
                (tr(self.app, "gui_start_cancel"), None),
            ],
        )

    def _prompt_restart_now(self, tweak_name: str) -> None:
        choice = self._prompt_choice_dialog(
            tr(self.app, "gui_tweak_restart_title"),
            tr(self.app, "gui_tweak_restart_body", name=tweak_name),
            [
                (tr(self.app, "gui_tweak_restart_now"), "restart"),
                (tr(self.app, "gui_tweak_restart_later"), None),
            ],
        )
        if choice == "restart":
            self.actions["restart_windows"]()

    def _prompt_choice_dialog(self, title: str, body: str, choices: list[tuple[str, str | None]]) -> str | None:
        result = {"value": None}
        dialog = tk.Toplevel(self.window)
        dialog.title(title)
        dialog.transient(self.window)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: _close(None))
        _apply_window_icon(dialog)
        apply_custom_cursor(dialog)
        bind_ui_click_sound(dialog)

        container = ttk.Frame(dialog, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=body,
            justify="left",
            wraplength=320,
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=(14, 0))
        for idx, _ in enumerate(choices):
            buttons.columnconfigure(idx, weight=1)

        def _close(value: str | None) -> None:
            result["value"] = value
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        last = len(choices) - 1
        for idx, (label, value) in enumerate(choices):
            padx = (0, 4) if idx == 0 else ((4, 0) if idx == last else 4)
            ttk.Button(
                buttons,
                text=label,
                command=lambda v=value: _close(v),
                cursor="",
            ).grid(row=0, column=idx, sticky="ew", padx=padx)

        dialog.update_idletasks()
        x = self.window.winfo_rootx() + max((self.window.winfo_width() - dialog.winfo_width()) // 2, 0)
        y = self.window.winfo_rooty() + max((self.window.winfo_height() - dialog.winfo_height()) // 2, 0)
        dialog.geometry(f"+{x}+{y}")
        dialog.wait_window()
        return result["value"]

    def _hwnd(self) -> int:
        try:
            self.window.update_idletasks()
            hwnd = int(self.window.winfo_id())
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            root = user32.GetAncestor(ctypes.c_void_p(hwnd), GA_ROOT)
            return int(root or hwnd)
        except Exception:
            return 0

    def _query_window_pos(self) -> None:
        """Cache actual screen position via Win32 GetWindowRect (reliable for overrideredirect)."""
        try:
            import ctypes.wintypes as _wt
            hwnd = self._hwnd()
            if hwnd:
                user32 = ctypes.windll.user32
                user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_wt.RECT)]
                user32.GetWindowRect.restype = ctypes.c_bool
                _r = _wt.RECT()
                if user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(_r)):
                    if _r.right > _r.left and _r.bottom > _r.top:
                        self._panel_pos = (_r.left, _r.top)
        except Exception:
            pass

    def _configure_native_window(self) -> None:
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype = ctypes.c_long
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool
            style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
            style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, style)
            try:
                # Windows 11+: request softly rounded corners for the
                # borderless/custom-caption control panel. No-op on older
                # Windows builds.
                corner_pref = ctypes.c_int(2)  # DWMWCP_ROUND
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(33),  # DWMWA_WINDOW_CORNER_PREFERENCE
                    ctypes.byref(corner_pref),
                    ctypes.sizeof(corner_pref),
                )
            except Exception:
                pass
            user32.SetWindowPos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(0),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )
        except Exception:
            pass

    def _show_native(self, mode: int) -> None:
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.ShowWindow.restype = ctypes.c_bool
            user32.ShowWindow(ctypes.c_void_p(hwnd), mode)
        except Exception:
            pass


def refresh_control_panel(app: AppState) -> None:
    cp = getattr(app, "control_panel", None)
    if cp is not None:
        try:
            cp.window.after(0, cp.refresh)
        except Exception:
            try:
                cp.refresh()
            except Exception:
                pass


# ---------- Auto-detect ----------
def _find_pinned_process(target_name: str) -> tuple[int, str] | None:
    """Pin mode: tìm process theo đúng tên exe (case-insensitive).
    Không yêu cầu 3D API, ESTABLISHED hay cửa sổ visible vì game có thể
    đang ở splash/loading. Nếu nhiều PID trùng tên: ưu tiên window lớn nhất.
    """
    target = (target_name or "").strip().lower()
    if not target:
        return None
    MIN_WINDOW_AREA = 640 * 480
    cands: list[tuple[int, str, int]] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = (p.info.get("name") or "").strip()
        except Exception:
            continue
        if name.lower() != target:
            continue
        pid = p.info.get("pid")
        if not pid:
            continue
        hwnd = get_hwnd_for_pid(pid)
        area = get_window_area(hwnd) if hwnd else 0
        if hwnd and area < MIN_WINDOW_AREA:
            area = 0
        cands.append((pid, name, area))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[2])
    pid, name, _ = cands[0]
    return pid, name


def detect_game_process(target_name: str | None = None) -> tuple[int, str] | None:
    """Xác định process game online.
    - Nếu `target_name` được set (pin mode) -> chỉ tìm đúng tên đó.
    - Ngược lại auto-detect: ESTABLISHED tới IP public + cửa sổ + 3D API +
      không trong blacklist; chọn process nhiều kết nối public nhất.
    """
    if target_name:
        return _find_pinned_process(target_name)

    by_pid = all_remote_ips_by_pid()
    if not by_pid:
        by_pid = all_established_by_pid()
    accelerator_active = bool(find_accelerators())

    MIN_WINDOW_AREA = 640 * 480  # loại tray app / popup nhỏ

    candidates: list[tuple[int, str, int, int, int]] = []
    rejected: list[str] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pid = int(p.info.get("pid") or 0)
            name = (p.info.get("name") or "").strip()
        except Exception:
            continue
        if pid <= 0 or not name.lower().endswith(".exe"):
            continue
        if name.lower() in PROCESS_BLACKLIST:
            continue

        hwnd = get_hwnd_for_pid(pid)
        if not hwnd:
            rejected.append(f"{name}[no-window]")
            continue

        area = get_window_area(hwnd)
        if area < MIN_WINDOW_AREA:
            rejected.append(f"{name}[small-window]")
            continue

        # Dấu hiệu mạnh nhất phân biệt game vs launcher/app:
        # process đã load graphics API 3D (D3D11/D3D12/Vulkan/OpenGL).
        # Launcher (Epic, Steam, Battle.net) thường chỉ dùng CEF/GDI,
        # không load d3d11/d3d12/vulkan-1.dll.
        api = detect_graphics_api(pid)
        if api == "Unknown":
            rejected.append(f"{name}[no-3d-api]")
            continue

        public_ips = by_pid.get(pid, [])
        if not public_ips and not accelerator_active:
            rejected.append(f"{name}[no-public-net]")
            continue

        score = len(public_ips) * 100 + min(area // 100000, 20)
        if not public_ips and accelerator_active:
            # Khi đi qua ExitLag/Gearup, game có thể chỉ nói chuyện với local proxy.
            score += 30

        candidates.append((pid, name, score, len(public_ips), area))
    if not candidates and rejected:
        print(f"[detect] rejected: {', '.join(rejected[:10])}")
    if not candidates:
        return None
    # Ưu tiên: score tổng, rồi public connection count, rồi window lớn nhất.
    candidates.sort(key=lambda c: (-c[2], -c[3], -c[4]))
    pid, name, _, _, _ = candidates[0]
    return pid, name


def _active_traffic_ips(pid: int) -> list[str]:
    """Lấy IP mà process đang thực sự gửi/nhận dữ liệu, theo thứ tự ưu tiên:
      1. UDP remote endpoints (gameplay socket của game online)
      2. TCP/UDP bền vững (có mặt ở 2 snapshot cách 2s)
      3. Fallback: toàn bộ ESTABLISHED
    """
    ips = gameplay_remote_ips(pid)
    if ips:
        return ips
    ips = persistent_remote_ips(pid, delay=2.0)
    if ips:
        return ips
    return established_remote_ips(pid)


def detect_graphics_api(pid: int) -> str:
    """Xác định graphics API của process qua danh sách DLL đã load.
    Không inject, chỉ đọc memory_maps của process (cần quyền đủ).
    Ưu tiên: DX12 > DX11 > Vulkan > OpenGL > Unknown.
    Ghi chú: một số game load cả d3d11.dll lẫn d3d12.dll — nếu có d3d12
    thì renderer thật gần như luôn là DX12.
    """
    try:
        maps = psutil.Process(pid).memory_maps()
    except Exception:
        return "Unknown"
    names: set[str] = set()
    for m in maps:
        try:
            p = (m.path or "").lower()
        except Exception:
            continue
        if p:
            names.add(p)
    def has(dll: str) -> bool:
        return any(dll in n for n in names)
    if has("d3d12.dll"):
        return "DX12"
    if has("d3d11.dll"):
        return "DX11"
    if has("vulkan-1.dll"):
        return "Vulkan"
    if has("opengl32.dll"):
        return "OpenGL"
    return "Unknown"


def pick_nearest_city_from_ips(ips: list[str]) -> str | None:
    """Từ list IP đã được xác định là gameplay server, chọn city có
    ICMP latency thấp nhất; fallback city đầu nếu ICMP bị block."""
    scanned = scan_cities(ips)
    if not scanned:
        return None
    city_ip: dict[str, str] = {}
    for city, ip, _ in scanned:
        city_ip.setdefault(city, ip)

    best_city: str | None = None
    best_lat: float | None = None
    for city, ip in city_ip.items():
        try:
            r = ping3.ping(ip, timeout=1, unit="ms")
        except Exception:
            r = None
        if r is None or r is False:
            continue
        lat = float(r)
        if best_lat is None or lat < best_lat:
            best_city, best_lat = city, lat
    return best_city or next(iter(city_ip))


# ---------- Dialogs ----------
def _pickable_process_entries() -> list[dict]:
    """Chuẩn bị danh sách process để user pin target.
    Chỉ giữ process có cửa sổ chính đủ lớn; sort theo tín hiệu giống game
    để user không phải mò giữa browser/launcher/tool nền.
    """
    by_pid = all_remote_ips_by_pid()
    if not by_pid:
        by_pid = all_established_by_pid()
    accelerator_active = bool(find_accelerators())

    min_window_area = 640 * 480
    entries: list[dict] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pid = int(p.info.get("pid") or 0)
            name = (p.info.get("name") or "").strip()
        except Exception:
            continue
        if pid <= 0 or not name.lower().endswith(".exe"):
            continue

        hwnd = get_hwnd_for_pid(pid)
        if not hwnd:
            continue
        area = get_window_area(hwnd)
        if area < min_window_area:
            continue

        api = detect_graphics_api(pid)
        public_ips = by_pid.get(pid, [])
        routed_via_accelerator = accelerator_active and not public_ips
        recommended = (
            name.lower() not in PROCESS_BLACKLIST
            and api != "Unknown"
            and (bool(public_ips) or accelerator_active)
        )

        score = 0
        if name.lower() not in PROCESS_BLACKLIST:
            score += 200
        if api != "Unknown":
            score += 120
        score += min(len(public_ips), 5) * 25
        if routed_via_accelerator:
            score += 30
        score += min(area // 100000, 20)

        entries.append({
            "pid": pid,
            "name": name,
            "api": api,
            "public_ip_count": len(public_ips),
            "routed_via_accelerator": routed_via_accelerator,
            "score": score,
            "recommended": recommended,
        })

    entries.sort(
        key=lambda e: (
            not e["recommended"],
            -e["score"],
            e["name"].lower(),
            e["pid"],
        )
    )
    return entries


def pick_process() -> tuple[int, str] | None:
    procs = _pickable_process_entries()
    app = _PICK_CONTEXT
    win = tk.Tk()
    win.title(tr(app, "pick_process_title"))
    win.geometry("760x520")
    tk.Label(
        win,
        text=tr(app, "pick_process_desc"),
        justify="left",
        wraplength=700,
    ).pack(padx=10, pady=8, anchor="w")

    lb = tk.Listbox(win, width=110, height=22)
    for entry in procs:
        badge = tr(app, "badge_recommended")
        if not entry["recommended"]:
            badge = tr(app, "badge_candidate")
        elif entry["routed_via_accelerator"]:
            badge = tr(app, "badge_recommended_accel")
        lb.insert(
            tk.END,
            f"{entry['pid']:>6}  {entry['name']:<28}  "
            f"API:{entry['api']:<7}  Net:{entry['public_ip_count']:<2}  {badge}",
        )
    lb.pack(padx=10, pady=6, fill="both", expand=True)
    if procs:
        lb.selection_set(0)
        lb.activate(0)

    result: dict = {}

    def ok():
        sel = lb.curselection()
        if sel:
            entry = procs[sel[0]]
            result["value"] = (entry["pid"], entry["name"])
            win.destroy()

    if not procs:
        tk.Label(
            win,
            text=tr(app, "pick_process_none"),
            fg="red",
            justify="left",
        ).pack(padx=10, pady=8, anchor="w")

    btns = tk.Frame(win)
    btns.pack(pady=8)
    tk.Button(btns, text=tr(app, "button_ok"), width=16, command=ok,
              state=("normal" if procs else "disabled")).pack(side="left", padx=6)
    tk.Button(btns, text=tr(app, "button_cancel"), width=16, command=win.destroy).pack(side="left", padx=6)
    win.mainloop()
    return result.get("value")


def pick_city(cities: list[str]) -> str | None:
    app = _PICK_CONTEXT
    win = tk.Tk()
    win.title(tr(app, "pick_city_title"))
    win.geometry("360x170")
    if not cities:
        tk.Label(win, text=tr(app, "pick_city_none"),
                 fg="red").pack(pady=20)
        tk.Button(win, text=tr(app, "button_close"), width=12, command=win.destroy).pack()
        win.mainloop()
        return None

    tk.Label(win, text=tr(app, "pick_city_label")).pack(pady=6)
    var = tk.StringVar()
    cb = ttk.Combobox(win, textvariable=var, values=cities,
                      state="readonly", width=42)
    cb.current(0)
    cb.pack(pady=6)

    result: dict = {}

    def ok():
        result["value"] = var.get()
        win.destroy()

    tk.Button(win, text=tr(app, "button_ok"), width=16, command=ok).pack(pady=10)
    win.mainloop()
    return result.get("value")


# ---------- Tray ----------
def make_tray_icon(overlay: Overlay, options: OverlayOptions,
                   app: AppState):
    def _display_proc_name() -> str:
        return tr(app, "process_waiting") if app.proc_name == "(waiting)" else app.proc_name

    def menu_text(key: str, **kwargs):
        def _label(item):
            resolved = {
                name: (value() if callable(value) else value)
                for name, value in kwargs.items()
            }
            return tr(app, key, **resolved)
        return _label

    def on_click(icon, item=None):
        overlay.root.after(0, _show_control_panel)

    def _shutdown_app() -> None:
        try:
            close_quest_helper(cfg, app)
        except Exception as e:
            print(f"[quest-helper] shutdown close failed: {e}")
        cleanup_quest_scan_images()
        cp = getattr(app, "control_panel", None)
        if cp is not None:
            try:
                cp.window.destroy()
            except Exception:
                pass
        overlay.close()
        try:
            tray.stop()
        except Exception:
            pass
        restore_system_cursor()
        # Force-exit: khi chạy onefile --windowed, một số thread backend
        # (pystray Win32, PresentMon, ETW, hotkey) không dọn kịp và
        # mainloop có thể không thoát. Dùng os._exit để chắc chắn.
        os._exit(0)

    def on_quit(icon, item=None):
        play_ui_click()
        overlay.root.after(0, _shutdown_app)

    def _show_control_panel() -> None:
        play_ui_click()
        cp = getattr(app, "control_panel", None)
        if cp is not None:
            cp.show()

    def _toggle_control_panel() -> None:
        play_ui_click()
        cp = getattr(app, "control_panel", None)
        if cp is None:
            return
        try:
            if cp.window.state() == "withdrawn":
                cp.show()
            else:
                cp.hide()
        except Exception:
            cp.show()

    def _refresh_ui() -> None:
        refresh_control_panel(app)
        def _refresh_tray_once() -> None:
            try:
                was_visible = bool(getattr(tray, "visible", False))
                if was_visible:
                    tray.visible = False
                tray.menu = _build_menu()
                try:
                    tray.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
                except Exception:
                    pass
                if was_visible:
                    tray.visible = True
                else:
                    tray.update_menu()
            except Exception:
                pass
        _refresh_tray_once()
        for delay_ms in (75, 200, 500):
            overlay.root.after(delay_ms, _refresh_tray_once)

    def _toggle_option(attr: str) -> bool:
        # License gate — only ping/loss are free; refuse the toggle on
        # everything else when unlicensed. Both the ControlPanel
        # callback and the tray-menu path funnel through here, so a
        # single check covers both surfaces.
        free_options = {"show_ping", "show_loss"}
        if attr not in free_options and not bool(getattr(app, "licensed", False)):
            print(f"[tray] toggle_option {attr!r} ignored: license required")
            return False
        new_value = not bool(getattr(options, attr))
        if attr == "show_events" and new_value:
            ok = ensure_event_guild_id(app, getattr(app.control_panel, "window", overlay.root))
            if not ok:
                print("[events] show_events ignored: missing guild_id")
                return False
        setattr(options, attr, new_value)
        try:
            options.persist()
        except Exception as e:
            print(f"[tray] persist options error: {e}")
        _refresh_ui()
        return True

    def make_toggle(attr: str):
        def _f(icon, item):
            play_ui_click()
            overlay.root.after(0, lambda: _toggle_option(attr))
        return _f

    def on_toggle_autostart(icon, item):
        play_ui_click()
        cur = bool(app.cfg.get("autostart", False))
        new_val = not cur
        ok = autostart.sync(new_val)
        if ok:
            app.cfg["autostart"] = new_val
            app_config.save(app.cfg)
        else:
            print("[tray] autostart toggle failed; state unchanged")
        _refresh_ui()

    def on_reset_position(icon, item):
        play_ui_click()
        ov = app.cfg.setdefault("overlay", {})
        ov["offset_x"] = 12
        ov["offset_y"] = 8
        app_config.save(app.cfg)
        try:
            overlay.set_offset(12, 8)
        except Exception:
            pass
        print("[tray] overlay offset reset to (12, 8)")

    def on_toggle_auto_update(icon, item):
        play_ui_click()
        upd = app.cfg.setdefault("update", {})
        upd["check_on_startup"] = not bool(upd.get("check_on_startup", True))
        app_config.save(app.cfg)
        _refresh_ui()

    def _set_language(lang: str):
        app.cfg["language"] = lang
        app_config.save(app.cfg)
        _refresh_ui()

    def on_set_language(lang: str):
        play_ui_click()
        overlay.root.after(0, lambda: _set_language(lang))

    def on_check_updates(icon, item=None):
        play_ui_click()
        overlay.root.after(
            0,
            lambda: maybe_check_for_updates(
                overlay,
                app,
                tray,
                interactive=True,
            ),
        )

    def _set_monitoring_enabled(enabled: bool) -> bool:
        if app.monitoring_enabled == enabled:
            return bool(app.active)
        app.monitoring_enabled = enabled
        attached = False
        if not enabled:
            stop_session(app, overlay, tray)
            overlay.root.after(0, overlay.hide)
            try:
                tray.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
            except Exception:
                pass
            print("[tray] monitoring paused; waiting for Start")
        else:
            try:
                tray.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
            except Exception:
                pass
            app.cfg["target_process"] = DEFAULT_GAME_PROCESS
            app_config.save(app.cfg)
            try:
                if app.event_monitor is not None:
                    app.event_monitor.force_refresh()
            except Exception:
                pass
            detected = detect_game_process(DEFAULT_GAME_PROCESS)
            if detected and not app.active:
                pid, proc_name = detected
                start_session(app, overlay, tray, pid, proc_name)
                attached = True
            else:
                overlay.set_text(tr(app, "overlay_waiting_game"), color="#888888")
                overlay.show()
                play_ui_alert()
                messagebox.showinfo(
                    tr(app, "start_wait_game_title"),
                    tr(app, "start_wait_game_body"),
                )
            print(f"[tray] monitoring enabled; waiting for {DEFAULT_GAME_PROCESS}")
        _refresh_ui()
        return attached

    def _apply_target_process(target_name: str | None,
                              selected: tuple[int, str] | None = None) -> None:
        normalized = (target_name or "").strip()
        app.cfg["target_process"] = normalized
        app_config.save(app.cfg)

        was_active = app.active or app.warming or app.pid is not None
        if was_active:
            stop_session(app, overlay, tray)

        if selected is not None and app.monitoring_enabled:
            pid, proc_name = selected
            start_session(app, overlay, tray, pid, proc_name)
        elif not normalized and app.monitoring_enabled:
            detected = detect_game_process(None)
            if detected:
                pid, proc_name = detected
                start_session(app, overlay, tray, pid, proc_name)

        _refresh_ui()

        if normalized:
            print(f"[tray] target process pinned: {normalized}")
        else:
            print("[tray] target process set to auto-detect")

    def on_start_monitoring(icon, item=None):
        play_ui_click()
        if app.monitoring_enabled:
            _refresh_ui()
            return
        overlay.root.after(0, lambda: _set_monitoring_enabled(True))

    def on_stop_monitoring(icon, item=None):
        play_ui_click()
        if not app.monitoring_enabled:
            _refresh_ui()
            return
        overlay.root.after(0, lambda: _set_monitoring_enabled(False))

    def on_toggle_monitoring(icon, item=None):
        if app.monitoring_enabled:
            on_stop_monitoring(icon, item)
        else:
            on_start_monitoring(icon, item)

    def on_use_auto_detect(icon, item=None):
        play_ui_click()
        overlay.root.after(0, lambda: _apply_target_process(None))

    def on_choose_target(icon, item=None):
        play_ui_click()
        def _choose():
            global _PICK_CONTEXT
            _PICK_CONTEXT = app
            selected = pick_process()
            if not selected:
                return
            pid, proc_name = selected
            _apply_target_process(proc_name, (pid, proc_name))
        overlay.root.after(0, _choose)

    def on_copyright(icon, item):
        play_ui_click()
        def show():
            _show_copyright_dialog(overlay.root, app)
        overlay.root.after(0, show)

    def on_donate(icon, item=None):
        play_ui_click()
        def _show():
            try:
                _show_plans_popup(overlay.root, app)
            except Exception as e:
                print(f"[tray] donate popup error: {e}")
        overlay.root.after(0, _show)

    def on_discord(icon, item=None):
        play_ui_click()
        try:
            webbrowser.open(DISCORD_URL, new=2)
        except Exception as e:
            print(f"[tray] discord open error: {e}")

    def _restart_windows() -> None:
        play_ui_click()
        try:
            subprocess.Popen(
                ["shutdown", "/r", "/t", "0"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            play_ui_alert()
            messagebox.showerror(tr(app, "gui_tweak_error_title"), str(e))

    def _set_game_tweak(key: str, enabled: bool) -> bool:
        app.game_tweaks.set_enabled(key, enabled)
        app_config.save(app.cfg)
        print(f"[tweak] {key} -> {'on' if enabled else 'off'}")
        _refresh_ui()
        return bool(enabled and app.game_tweaks.requires_restart(key))

    # License-aware enable for tray menu options. Ping + Loss are
    # always free; everything else greys out until a valid license
    # is loaded. The option toggle path itself
    # (``_toggle_option``) also refuses gated attrs as a defence-
    # in-depth backstop.
    def _licensed():
        return bool(getattr(app, "licensed", False))

    def _build_options_menu():
        return pystray.Menu(
            pystray.MenuItem(menu_text("menu_show_ping"), make_toggle("show_ping"),
                             checked=lambda i: options.show_ping),
            pystray.MenuItem(menu_text("menu_show_loss"), make_toggle("show_loss"),
                             checked=lambda i: options.show_loss),
            pystray.MenuItem(menu_text("menu_show_jitter"), make_toggle("show_jitter"),
                             checked=lambda i: options.show_jitter,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_minmax"), make_toggle("show_minmax"),
                             checked=lambda i: options.show_minmax,
                             enabled=lambda i: _licensed()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_fps"), make_toggle("show_fps"),
                             checked=lambda i: options.show_fps,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_low1"), make_toggle("show_low1"),
                             checked=lambda i: options.show_low1,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_frametime"), make_toggle("show_frametime"),
                             checked=lambda i: options.show_frametime,
                             enabled=lambda i: _licensed()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_cpu"), make_toggle("show_cpu"),
                             checked=lambda i: options.show_cpu,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_cpu_temp"), make_toggle("show_cpu_temp"),
                             checked=lambda i: options.show_cpu_temp,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_gpu_temp"), make_toggle("show_gpu_temp"),
                             checked=lambda i: options.show_gpu_temp,
                             enabled=lambda i: _licensed()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_ram"), make_toggle("show_ram"),
                             checked=lambda i: options.show_ram,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_vram"), make_toggle("show_vram"),
                             checked=lambda i: options.show_vram,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_api"), make_toggle("show_api"),
                             checked=lambda i: options.show_api,
                             enabled=lambda i: _licensed()),
            pystray.MenuItem(menu_text("menu_show_events"), make_toggle("show_events"),
                             checked=lambda i: options.show_events,
                             enabled=lambda i: _licensed()),
        )

    def _build_language_menu():
        return pystray.Menu(
            pystray.MenuItem(
                menu_text("menu_language_en"),
                lambda icon, item: on_set_language("en"),
                checked=lambda i: lang_code(app) == "en",
            ),
            pystray.MenuItem(
                menu_text("menu_language_vi"),
                lambda icon, item: on_set_language("vi"),
                checked=lambda i: lang_code(app) == "vi",
            ),
        )

    def _build_menu():
        return pystray.Menu(
            pystray.MenuItem(
                menu_text("menu_toggle_gui"),
                lambda icon, item: overlay.root.after(0, _toggle_control_panel),
                default=True,
            ),
            pystray.MenuItem(menu_text("menu_check_updates"), on_check_updates,
                             enabled=lambda i: not app.update_in_progress),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_quit_app"), on_quit),
        )

    icon = pystray.Icon(APP_EXE_BASENAME, ICON_RED, f"{APP_DISPLAY_NAME} (waiting)", _build_menu())
    try:
        import pystray._util.win32 as tray_win32

        original_on_notify = icon._on_notify

        def _patched_on_notify(self, wparam, lparam):
            if lparam == tray_win32.WM_RBUTTONUP:
                try:
                    self.menu = _build_menu()
                    self.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
                except Exception:
                    pass
            return original_on_notify(wparam, lparam)

        icon._on_notify = types.MethodType(_patched_on_notify, icon)
    except Exception:
        pass
    icon.default_action = on_click
    actions = {
        "toggle_option": _toggle_option,
        "set_language": _set_language,
        "start_monitoring": lambda: _set_monitoring_enabled(True),
        "stop_monitoring": lambda: _set_monitoring_enabled(False),
        "donate": lambda: on_donate(None),
        "discord": lambda: on_discord(None),
        "set_game_tweak": _set_game_tweak,
        "restart_windows": _restart_windows,
        "show_control_panel": _show_control_panel,
        "toggle_control_panel": _toggle_control_panel,
        "check_updates": lambda: on_check_updates(None),
        "show_overlay": lambda: overlay.root.after(0, overlay.show),
        "apply_overlay_settings": lambda: overlay.set_theme(app.cfg.get("theme"), app.cfg.get("overlay")),
        "quit_app": lambda: overlay.root.after(0, _shutdown_app),
        "refresh_ui": _refresh_ui,
    }
    return icon, actions


# ---------- Loops ----------
def window_follow_loop(overlay: Overlay, app: AppState):
    """Bám cửa sổ của process hiện tại (lấy PID từ AppState)."""
    local = {"hwnd": None, "pid": None}

    def tick():
        delay_ms = WINDOW_POLL_MS_IDLE
        try:
            if app.pid != local["pid"]:
                local["pid"] = app.pid
                local["hwnd"] = None
            if app.pid:
                delay_ms = WINDOW_POLL_MS_ACTIVE
                hwnd = local["hwnd"] or get_hwnd_for_pid(app.pid)
                local["hwnd"] = hwnd
                if hwnd:
                    if app.monitoring_enabled and app.active:
                        overlay.show()
                    rect = get_client_topleft_size(hwnd)
                    if rect and rect[2] > 0 and rect[3] > 0:
                        overlay.move_to_client(rect[0], rect[1])
                        if app.monitoring_enabled and app.active:
                            overlay.show()
                    else:
                        local["hwnd"] = None
                elif app.monitoring_enabled and app.active:
                    overlay.show()
        except Exception:
            pass
        finally:
            overlay.schedule(delay_ms, tick)

    tick()


class PingState:
    """Chia sẻ latency/loss/jitter/min-max giữa ping thread và display loop.
    - Loss: cửa sổ N sample gần nhất (LOSS_WINDOW).
    - Jitter (stdev) + rolling min/max: 60s gần nhất (RollingWindow).
    - Session min/max: tích luỹ từ start_session, reset khi đổi session.
    """

    JITTER_WINDOW_S = 60.0

    def __init__(self, pid: int, target_city: str):
        self.pid = pid
        self.target_norm = target_city.strip().lower()
        self.ip: str | None = None
        self.latency: float | None = None
        self.hist: deque[bool] = deque(maxlen=LOSS_WINDOW)
        self.lat_window = RollingWindow(self.JITTER_WINDOW_S)
        self.session_min: float | None = None
        self.session_max: float | None = None
        self.traffic_mode: str = "none"  # 'direct' | 'accelerator:<Name>' | 'none'
        self.lock = threading.Lock()
        self._stop = False

    def loss_pct(self) -> float | None:
        with self.lock:
            if not self.hist:
                return None
            lost = sum(1 for ok in self.hist if not ok)
            return lost / len(self.hist) * 100.0

    def jitter_ms(self) -> float | None:
        with self.lock:
            return self.lat_window.stddev()

    def session_minmax(self) -> tuple[float | None, float | None]:
        with self.lock:
            return self.session_min, self.session_max

    def snapshot(self) -> tuple[float | None, float | None]:
        with self.lock:
            lat = self.latency
        return lat, self.loss_pct()

    def stats_snapshot(self) -> dict[str, float | None]:
        with self.lock:
            values = self.lat_window.values()
            loss = None
            if self.hist:
                lost = sum(1 for ok in self.hist if not ok)
                loss = lost / len(self.hist) * 100.0
            jitter = None
            if len(values) >= 2:
                avg = sum(values) / len(values)
                jitter = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
            return {
                "last": self.latency,
                "avg": (sum(values) / len(values)) if values else None,
                "min": self.session_min,
                "max": self.session_max,
                "loss": loss,
                "jitter": jitter,
            }

    def _resolve_ip(self) -> None:
        """Xác định IP đang TX/RX dữ liệu thật với process. Thứ tự:
        1. gameplay_traffic_ips: direct nếu wwm.exe có public IP, ngược lại
           rơi sang accelerator (ExitLag/Gearup) outbound nếu detect.
        2. UDP gameplay endpoints / ESTABLISHED — fallback cuối cùng.

        Trong tập trên, ưu tiên IP nào geolocate ra `target_city`. Nếu
        không match city nào, dùng IP active đầu tiên (đã sort theo stability).
        Lưu mode vào self.traffic_mode để display_loop biết hiển thị suffix
        '[via ExitLag]' nếu đang đi qua tunnel.
        """
        try:
            ips, mode = gameplay_traffic_ips(self.pid, window_s=1.5,
                                              threshold=0.66)
            if not ips:
                # Last-resort fallback (psutil UDP rỗng + không accelerator)
                ips = (gameplay_remote_ips(self.pid)
                       or established_remote_ips(self.pid))
                mode = "fallback" if ips else "none"

            if not ips:
                with self.lock:
                    self.ip = None
                    self.traffic_mode = mode
                return

            chosen: str | None = None
            scanned = scan_cities(ips)
            for city, ip, _geo in scanned:
                if city.strip().lower() == self.target_norm:
                    chosen = ip
                    break
            if chosen is None:
                chosen = ips[0]

            with self.lock:
                self.ip = chosen
                self.traffic_mode = mode
            return
        except Exception as e:
            print(f"[ping] resolve_ip error: {e}")
        with self.lock:
            self.ip = None
            self.traffic_mode = "none"

    def run(self) -> None:
        counter = 0
        while not self._stop:
            if counter % IP_RESCAN_EVERY == 0 or self.ip is None:
                self._resolve_ip()
            counter += 1

            ip = self.ip
            if not ip:
                with self.lock:
                    self.hist.append(False)
                    self.latency = None
                time.sleep(PING_INTERVAL_S)
                continue

            try:
                r = ping3.ping(ip, timeout=1, unit="ms")
            except Exception:
                r = None
            ok = r is not None and r is not False
            with self.lock:
                self.hist.append(ok)
                if ok:
                    lat = float(r)
                    self.latency = lat
                    self.lat_window.append(lat)
                    if self.session_min is None or lat < self.session_min:
                        self.session_min = lat
                    if self.session_max is None or lat > self.session_max:
                        self.session_max = lat
            time.sleep(PING_INTERVAL_S)

    def stop(self) -> None:
        self._stop = True


def start_server_endpoint_monitor(app: AppState, pid: int, session_token: int) -> None:
    if not _game_panel_enabled(app, "show_server_ips"):
        _clear_server_endpoints(app)
        return
    worker_key = (int(pid), int(session_token))
    try:
        with app.server_endpoint_worker_lock:
            if app.server_endpoint_worker_token == worker_key:
                return
            app.server_endpoint_worker_token = worker_key
    except Exception:
        pass

    def worker() -> None:
        last_signature: tuple | None = None
        try:
            while (
                app.monitoring_enabled
                and app.pid == pid
                and app.session_token == session_token
                and _game_panel_enabled(app, "show_server_ips")
            ):
                try:
                    endpoints, mode = active_server_endpoints(
                        pid,
                        window_s=1.0,
                        threshold=0.5,
                        limit=6,
                    )
                    if (
                        app.pid == pid
                        and app.session_token == session_token
                        and _game_panel_enabled(app, "show_server_ips")
                    ):
                        signature = (
                            mode,
                            tuple(
                                (
                                    item.get("ip"),
                                    item.get("port"),
                                    item.get("proto"),
                                    item.get("city"),
                                    item.get("country_code"),
                                )
                                for item in endpoints
                            ),
                        )
                        if signature != last_signature:
                            last_signature = signature
                            _set_server_endpoints(app, endpoints, mode)
                            refresh_control_panel(app)
                except Exception as e:
                    print(f"[net] server endpoint monitor error: {e}")
                for _ in range(16):
                    if (
                        not app.monitoring_enabled
                        or app.pid != pid
                        or app.session_token != session_token
                        or not _game_panel_enabled(app, "show_server_ips")
                    ):
                        return
                    time.sleep(0.5)
        finally:
            _clear_server_endpoints(app)
            try:
                with app.server_endpoint_worker_lock:
                    if app.server_endpoint_worker_token == worker_key:
                        app.server_endpoint_worker_token = None
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True, name="ServerEndpointMonitor").start()


def display_loop(overlay: Overlay, app: AppState, options: OverlayOptions):
    """Compact 1-dòng nén theo thứ tự:
       Ping 42ms │ Loss 0% │ FPS 144 │ RAM 2.1/16G │ VRAM 4.5/8G │ API DX12
    """
    def tick():
        delay_ms = DISPLAY_MS_WAITING
        try:
            event_banner = None
            try:
                if options.show_events and app.event_monitor is not None:
                    event_banner = _select_event_banner(app)
            except Exception:
                event_banner = None

            if app.warming:
                overlay.set_text(
                    _append_overlay_clock(tr(app, "overlay_waiting_lobby")),
                    color="#FFAA00",
                )
            elif not app.monitoring_enabled:
                overlay.set_text(_append_overlay_clock(tr(app, "overlay_waiting_start")), color="#888888")
            elif not app.active:
                overlay.set_text(_append_overlay_clock(tr(app, "overlay_waiting_game")), color="#888888")
            elif app.ping_state is None:
                overlay.set_text(
                    _append_overlay_clock(tr(app, "overlay_waiting_match", process=app.proc_name)),
                    color="#FFAA00",
                )
            else:
                delay_ms = DISPLAY_MS_ACTIVE
                lat, loss = app.ping_state.snapshot()
                mem_needed = any((
                    options.show_cpu,
                    options.show_cpu_temp,
                    options.show_gpu_temp,
                    options.show_ram,
                    options.show_vram,
                ))
                mem = app.mem_mon.snapshot() if app.mem_mon and mem_needed else None

                # License gate — when unlicensed, only the bare
                # Ping + Loss segments render; everything else
                # (jitter/min-max/FPS/CPU/RAM/VRAM/API/events/etc.) is
                # suppressed regardless of the per-option toggles. This
                # is the always-free baseline called out in the
                # requirements.
                _licensed = bool(getattr(app, "licensed", False))
                segments: list[dict] = []
                if options.show_ping:
                    _ping_color: str | None = None
                    if lat is not None:
                        if lat < 30:
                            _ping_color = "#00FF88"   # xanh  — excellent (< 30ms)
                        elif lat < 80:
                            _ping_color = "#FFD700"   # vàng  — good     (30–79ms)
                        elif lat <= 120:
                            _ping_color = "#FF8C00"   # cam   — fair     (80–120ms)
                        else:
                            _ping_color = "#FF4444"   # đỏ    — poor     (> 120ms)
                    segments.append(
                        _overlay_metric(
                            f"Ping: {lat:.0f}ms" if lat is not None else "Ping: n/a",
                            "Ping: 999ms",
                            color=_ping_color,
                        )
                    )
                if options.show_loss:
                    segments.append(
                        _overlay_metric(
                            f"Loss: {loss:.0f}%" if loss is not None else "Loss: n/a",
                            "Loss: 100%",
                        )
                    )
                if _licensed and options.show_jitter:
                    jitter = app.ping_state.jitter_ms()
                    segments.append(
                        _overlay_metric(
                            f"Jitter: {jitter:.0f}ms" if jitter is not None else "Jitter: n/a",
                            "Jitter: 999ms",
                        )
                    )
                if _licensed and options.show_minmax:
                    smin, smax = app.ping_state.session_minmax()
                    if smin is not None and smax is not None:
                        text = f"Min/Max: {smin:.0f}/{smax:.0f}ms"
                    else:
                        text = "Min/Max: -/-"
                    segments.append(_overlay_metric(text, "Min/Max: 999/999ms"))
                if _licensed and (options.show_fps or options.show_frametime):
                    fps_text = None
                    frametime_text = None
                    fps_color: str | None = None
                    if options.show_fps:
                        fps_val = app.fps_mon.fps() if app.fps_mon else None
                        fps_text = f"{fps_val:.0f}" if fps_val is not None else "n/a"
                        # Color-code by FPS tier: red < 40, orange < 60, green ≥ 60
                        if fps_val is not None:
                            if fps_val < 40:
                                fps_color = "#FF4444"   # red   — very low
                            elif fps_val < 60:
                                fps_color = "#FF9900"   # orange — below 60
                            else:
                                fps_color = "#44DD44"   # green  — 60+ fps
                    if options.show_frametime:
                        ftime = (app.fps_mon.frame_time_ms()
                                 if app.fps_mon else None)
                        frametime_text = f"{ftime:.1f}ms" if ftime is not None else "n/a"
                    if options.show_fps:
                        segments.append(
                            _overlay_metric(
                                _combine_metric_group("FPS", fps_text, frametime_text),
                                "FPS: 999 - 99.9ms" if options.show_frametime else "FPS: 999",
                                color=fps_color,
                            )
                        )
                    else:
                        segments.append(
                            _overlay_metric(
                                _combine_metric_group("Frame Time", frametime_text, None),
                                "Frame Time: 99.9ms",
                            )
                        )
                if _licensed and options.show_low1:
                    low1 = (app.fps_mon.one_percent_low_fps()
                            if app.fps_mon else None)
                    segments.append(
                        _overlay_metric(
                            f"1% Low: {low1:.0f}" if low1 is not None else "1% Low: n/a",
                            "1% Low: 999",
                        )
                    )
                if _licensed and (options.show_cpu or options.show_cpu_temp) and mem is not None:
                    cpu_text = None
                    cpu_temp_text = None
                    if options.show_cpu:
                        cpu_pct = mem.get("cpu_proc_pct")
                        cpu_text = f"{cpu_pct:.0f}%" if cpu_pct is not None else "n/a"
                    if options.show_cpu_temp:
                        cpu_temp_text = _fmt_temp_c(mem.get("cpu_temp_c")) or "n/a"
                    segments.append(
                        _overlay_metric(
                            _combine_metric_group("CPU", cpu_text, cpu_temp_text),
                            "CPU: 100% - 100°C" if options.show_cpu and options.show_cpu_temp else (
                                "CPU: 100%" if options.show_cpu else "CPU: 100°C"
                            ),
                        )
                    )
                if _licensed and options.show_ram and mem is not None:
                    segments.append(
                        _overlay_metric(
                            "RAM: " + fmt_ratio_bytes_pct(
                                mem.get("ram_proc_b"), mem.get("ram_total_b")
                            ),
                            "RAM: 99.9/999G (100%)",
                        )
                    )
                if _licensed and (options.show_vram or options.show_gpu_temp) and mem is not None:
                    vram_text = None
                    gpu_temp_text = None
                    vram_used = mem.get("vram_gpu_b")
                    if vram_used is None:
                        vram_used = mem.get("vram_proc_b")
                    if options.show_vram:
                        vram_text = fmt_ratio_bytes_pct(vram_used, mem.get("vram_total_b"))
                    if options.show_gpu_temp:
                        gpu_temp_text = _fmt_temp_c(mem.get("gpu_temp_c")) or "n/a"
                    if options.show_vram:
                        segments.append(
                            _overlay_metric(
                                _combine_metric_group("VRAM", vram_text, gpu_temp_text),
                                "VRAM: 99.9/999G (100%) - 100°C" if options.show_gpu_temp else "VRAM: 99.9/999G (100%)",
                            )
                        )
                    else:
                        segments.append(
                            _overlay_metric(
                                _combine_metric_group("GPU Temp", gpu_temp_text, None),
                                "GPU Temp: 100°C",
                            )
                        )
                if _licensed and options.show_api:
                    segments.append(_overlay_metric(f"API: {app.api}", "API: DX12"))

                try:
                    mode = app.ping_state.traffic_mode if app.ping_state else ""
                except Exception:
                    mode = ""
                if _licensed and isinstance(mode, str) and mode.startswith("accelerator:"):
                    accelerator = mode.split(":", 1)[1]
                    segments.append(_overlay_metric(f"[via {accelerator}]", "[via Gearup Booster]"))

                clock_text = _overlay_clock_text()
                color = "#00FF66" if lat is not None else "#FFAA00"
                if _licensed and options.show_events and event_banner is not None:
                    event_text, event_color = event_banner
                    if event_color == "#FFAA00":
                        color = event_color
                    segments.append({"text": event_text, "kind": "event"})
                segments.append(_overlay_metric(clock_text, "23:59"))
                overlay.set_segments(segments, color=color)
        except Exception as e:
            overlay.set_text(_append_overlay_clock(tr(app, "overlay_error", error=e)), color="#FF5555")
        finally:
            if app.monitoring_enabled:
                overlay.show()
            overlay.schedule(delay_ms, tick)

    tick()


# ---------- Session lifecycle ----------
def start_session(app: AppState, overlay: Overlay, tray: pystray.Icon,
                  pid: int, proc_name: str) -> None:
    if not app.monitoring_enabled:
        return
    # Luôn bắt đầu từ state rỗng để lần Start sau Stop không tái dùng
    # monitor/snapshot của process cũ.
    if app.fps_mon:
        try:
            app.fps_mon.stop()
        except Exception:
            pass
        app.fps_mon = None
    if app.mem_mon:
        try:
            app.mem_mon.stop()
        except Exception:
            pass
        app.mem_mon = None
    if app.ping_state:
        try:
            app.ping_state.stop()
        except Exception:
            pass
        app.ping_state = None

    fps_mon = FpsMonitor(pid)
    if not fps_mon.start():
        print(f"[session] FPS monitor disabled: {fps_mon.error}")
        fps_mon = None

    mem_mon = MemoryMonitor(pid)
    if not mem_mon.start():
        print(f"[session] Memory monitor disabled (psutil failed)")
        mem_mon = None

    app.pid = pid
    app.proc_name = proc_name
    app.city = "(waiting lobby)"
    app.fps_mon = fps_mon
    app.mem_mon = mem_mon
    app.ping_state = None
    app.api = detect_graphics_api(pid)
    app.active = True
    app.warming = True
    app.warmup_stop = threading.Event()
    app.session_token += 1
    _reset_network_session_counters(app)
    _clear_server_endpoints(app)
    try:
        if app.event_monitor is not None:
            app.event_monitor.force_refresh()
    except Exception:
        pass
    session_token = app.session_token
    start_server_endpoint_monitor(app, pid, session_token)

    overlay.root.after(0, overlay.show)
    overlay.root.after(150, overlay.show)
    overlay.root.after(500, overlay.show)
    refresh_control_panel(app)
    try:
        tray.title = f"{APP_DISPLAY_NAME} — {proc_name} (warming)"
        tray.update_menu()
    except Exception:
        pass
    print(f"[session] started: {proc_name} (PID {pid}) — chờ user vào lobby...")

    def warmup():
        """Vòng lặp vô hạn: chờ user vào match (UDP gameplay) hoặc kết nối
        bền vững. Khi chưa có IP -> chuyển warming=False + city='(waiting net)'
        để display_loop hiển thị message rõ; nghỉ 10s rồi thử lại.
        Thoát chỉ khi stop_ev set hoặc PID đổi (process chết / session khác).
        """
        stop_ev = app.warmup_stop
        assert stop_ev is not None
        attempt = 0
        lobby_ips: list[str] = []
        while (
            not stop_ev.is_set()
            and app.monitoring_enabled
            and app.pid == pid
            and app.session_token == session_token
        ):
            attempt += 1
            ips = wait_for_lobby(pid, stop_ev)
            if stop_ev.is_set() or not app.monitoring_enabled or app.pid != pid or app.session_token != session_token:
                return
            if not ips:
                ips = persistent_remote_ips(pid) or []
            # Accelerator fallback: nếu wwm.exe không lộ public IP nào,
            # thử IPs outbound của ExitLag/Gearup/... (tunnel exit nodes)
            if not ips:
                accel_ips, mode = gameplay_traffic_ips(pid, window_s=2.0,
                                                       threshold=0.5)
                if accel_ips and mode.startswith("accelerator"):
                    print(f"[session] warmup using {mode} route")
                    ips = accel_ips
            if ips:
                lobby_ips = ips
                break
            # Chưa có IP -> báo trạng thái rõ, nghỉ rồi retry
            if app.session_token != session_token:
                return
            app.warming = False
            app.city = "(waiting net)"
            refresh_control_panel(app)
            try:
                tray.title = f"{APP_DISPLAY_NAME} — {proc_name} (waiting net)"
                tray.update_menu()
            except Exception:
                pass
            print(f"[session] warmup attempt {attempt}: no lobby IPs yet, "
                  f"retry in 10s")
            if stop_ev.wait(timeout=10.0):
                return

        if (
            stop_ev.is_set()
            or not app.monitoring_enabled
            or app.pid != pid
            or app.session_token != session_token
            or not lobby_ips
        ):
            return

        city = pick_nearest_city_from_ips(lobby_ips) or "(unknown)"
        if stop_ev.is_set() or not app.monitoring_enabled or app.pid != pid or app.session_token != session_token:
            return
        app.city = city
        ping_state = PingState(pid, city)
        app.ping_state = ping_state
        app.warming = False
        threading.Thread(target=ping_state.run, daemon=True).start()
        refresh_control_panel(app)
        try:
            tray.title = f"{APP_DISPLAY_NAME} — {proc_name}"
            tray.update_menu()
        except Exception:
            pass
        print(f"[session] lobby ready: {proc_name} @ {city}")

    threading.Thread(target=warmup, daemon=True).start()


def stop_session(app: AppState, overlay: Overlay, tray: pystray.Icon) -> None:
    try:
        close_quest_helper(app.cfg, app)
    except Exception as e:
        print(f"[quest-helper] stop close failed: {e}")
    app.session_token += 1
    if app.warmup_stop:
        app.warmup_stop.set()
    if app.ping_state:
        app.ping_state.stop()
    if app.fps_mon:
        app.fps_mon.stop()
    if app.mem_mon:
        app.mem_mon.stop()
    old = app.proc_name
    app.pid = None
    app.proc_name = "(waiting)"
    app.city = "(waiting)"
    app.fps_mon = None
    app.mem_mon = None
    app.ping_state = None
    app.api = "Unknown"
    app.active = False
    app.warming = False
    app.warmup_stop = None
    _clear_network_session_counters(app)
    _clear_server_endpoints(app)

    if app.monitoring_enabled:
        overlay.set_text(tr(app, "overlay_waiting_game"), color="#888888")
        overlay.root.after(0, overlay.show)
    else:
        overlay.root.after(0, overlay.hide)
    refresh_control_panel(app)
    try:
        tray.icon = ICON_RED
        tray.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
        tray.update_menu()
    except Exception:
        pass
    print(f"[session] stopped: {old}")


def supervisor_loop(overlay: Overlay, app: AppState, tray: pystray.Icon):
    """Theo dõi process: nếu chết -> dừng session. Nếu rảnh -> tự detect
    game mới và start session.
    Nếu config.target_process set -> pin mode, chỉ bám đúng process đó.
    """
    def tick():
        try:
            target = DEFAULT_GAME_PROCESS if app.monitoring_enabled else None
            if app.active:
                if not app.monitoring_enabled or app.pid is None or not psutil.pid_exists(app.pid):
                    stop_session(app, overlay, tray)
            elif app.monitoring_enabled:
                detected = detect_game_process(target)
                if detected:
                    pid, proc_name = detected
                    if app.monitoring_enabled:
                        start_session(app, overlay, tray, pid, proc_name)

            # Icon chỉ XANH khi đã có cả process VÀ server (city resolved).
            # Trong lúc warmup / chờ lobby / chưa detect -> ĐỎ.
            ready = (
                app.active
                and not app.warming
                and app.ping_state is not None
                and app.city not in ("(waiting lobby)", "(no lobby)", "(unknown)", "(waiting)")
            )
            desired = ICON_GREEN if ready else ICON_RED
            try:
                if getattr(tray, "icon", None) is not desired:
                    tray.icon = desired
            except Exception:
                pass
        except Exception as e:
            print(f"[supervisor] error: {e}")
        finally:
            overlay.schedule(SUPERVISOR_MS, tick)

    tick()


INSTANCE_LOCK_FILENAME = ".instance.lock"


def _instance_lock_path() -> Path:
    """``%APPDATA%\\PingOverlay\\.instance.lock`` — version-aware
    single-instance marker. JSON: ``{pid, version, exe_path, started_at}``."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = Path(base) / "PingOverlay"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / INSTANCE_LOCK_FILENAME


def _read_instance_lock() -> dict | None:
    path = _instance_lock_path()
    if not path.exists():
        return None
    try:
        import json as _json
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_instance_lock() -> None:
    path = _instance_lock_path()
    try:
        import json as _json
        payload = {
            "pid": int(os.getpid()),
            "version": str(__version__),
            "exe_path": str(Path(sys.executable).resolve()) if getattr(sys, "frozen", False) else "",
            "started_at": time.time(),
        }
        path.write_text(_json.dumps(payload), encoding="utf-8")
    except Exception as exc:
        print(f"[main] could not write instance lock: {exc}")


def _delete_instance_lock(*, only_if_owned: bool = True) -> None:
    """Delete the lock file. When ``only_if_owned`` is True (default),
    skip if the lock points at a different PID — that means a newer
    instance has already taken over and we shouldn't clobber its lock."""
    path = _instance_lock_path()
    try:
        if not path.exists():
            return
        if only_if_owned:
            data = _read_instance_lock() or {}
            if int(data.get("pid") or 0) != os.getpid():
                return
        path.unlink()
    except Exception:
        pass


def _parse_version_tuple(value: str) -> tuple[int, int, int]:
    try:
        parts = str(value or "").strip().split(".")
        nums = [int("".join(c for c in p if c.isdigit()) or "0") for p in parts[:3]]
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)  # type: ignore[return-value]
    except Exception:
        return (0, 0, 0)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        try:
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
        except Exception:
            pass
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _looks_like_pingoverlay_exe(name: str) -> bool:
    """Loose match so versioned exe names (``WWMOverlay-v0.1.144.exe``)
    are recognized too — the original guard only matched the exact
    current exe filename, which let differently-named versions coexist."""
    if not name:
        return False
    n = name.lower()
    if not n.endswith(".exe"):
        return False
    return n.startswith(APP_EXE_BASENAME.lower()) or n.startswith(LEGACY_APP_EXE_BASENAME.lower())


def _terminate_other_pingoverlay_instances() -> int:
    """Kill every other WWMOverlay/PingOverlay process.

    Belt-and-braces fallback for when the lock file is missing or
    stale (process crashed without cleaning up). Skips this process
    and its parent (PyInstaller bootloader). Falls through silently in
    dev mode.
    """
    if not getattr(sys, "frozen", False):
        return 0
    own_pid = os.getpid()
    try:
        own_parent = psutil.Process(own_pid).ppid()
    except Exception:
        own_parent = -1

    killed = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            if pid in (own_pid, own_parent) or pid <= 0:
                continue
            name = (proc.info.get("name") or "")
            if not _looks_like_pingoverlay_exe(name):
                continue
            try:
                proc.terminate()
                proc.wait(timeout=2.5)
            except psutil.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            killed += 1
        except Exception:
            continue
    if killed:
        print(f"[main] terminated {killed} stale {APP_DISPLAY_NAME} process(es)")
        time.sleep(0.4)
    return killed


def _show_newer_running_message(running_version: str) -> None:
    """Pop a dialog explaining a newer instance is active and refusing
    to launch this older copy. Tk first, Win32 ``MessageBoxW``
    fallback, console as last resort."""
    title = APP_DISPLAY_NAME
    body = (
        f"Đang có bản mới hơn (v{running_version}) chạy.\n"
        f"Bạn vừa mở v{__version__} (cũ hơn).\n\n"
        f"Đóng bản mới trước nếu thực sự muốn chạy bản cũ này.\n"
        f"A newer version (v{running_version}) is already running; "
        f"this older v{__version__} won't launch."
    )
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        root = _tk.Tk()
        root.withdraw()
        play_ui_alert()
        _mb.showinfo(title, body)
        root.destroy()
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, body, title, 0x40)
    except Exception:
        print(f"[main] {title}: {body}")


def _enforce_single_instance() -> None:
    """Single-instance guard with version awareness.

    * Older-than-running launch → show "newer version is running" and
      ``sys.exit(0)`` so the user can't downgrade by accident.
    * Newer-than-running launch → terminate the older instance, clear
      its lock, take over.
    * Equal-version → terminate the existing instance and re-launch
      this one. Maintains the prior behavior where double-clicking the
      same exe replaces the running tray icon.
    * Stale lock (PID dead) → silently take over.

    Always finishes by writing our own lock so subsequent launches see
    us as the active instance.
    """
    # In dev mode there's no exe to identify by, so we just do the
    # conservative name-based fallback and skip the lock.
    if not getattr(sys, "frozen", False):
        _terminate_other_pingoverlay_instances()
        return

    own_version = _parse_version_tuple(__version__)
    lock = _read_instance_lock()
    if isinstance(lock, dict):
        running_pid = int(lock.get("pid") or 0)
        running_version_str = str(lock.get("version") or "0.0.0")
        running_version = _parse_version_tuple(running_version_str)
        if _is_pid_alive(running_pid):
            if running_version > own_version:
                _show_newer_running_message(running_version_str)
                sys.exit(0)
            # We are equal-or-newer → terminate the running one.
            try:
                proc = psutil.Process(running_pid)
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except psutil.TimeoutExpired:
                    proc.kill()
                tag = "older" if running_version < own_version else "same-version"
                print(
                    f"[main] terminated {tag} {APP_DISPLAY_NAME} v{running_version_str} "
                    f"(PID {running_pid}); taking over"
                )
                time.sleep(0.4)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as exc:
                print(f"[main] terminate running instance failed: {exc}")

    # Catch any same-name leftovers that didn't write a lock.
    _terminate_other_pingoverlay_instances()
    _write_instance_lock()


_LEGACY_VERSIONED_EXE_RE = re.compile(
    r"^PingOverlay(?:[-_\s]?v?)(\d+\.\d+\.\d+)\.exe$",
    re.IGNORECASE,
)


def _legacy_exe_version(path: Path) -> tuple[int, int, int] | None:
    match = _LEGACY_VERSIONED_EXE_RE.match(path.name)
    if not match:
        return None
    version = _parse_version_tuple(match.group(1))
    return version if version != (0, 0, 0) else None


def _legacy_cleanup_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        try:
            dirs.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    try:
        dirs.append(Path.home() / "Downloads")
    except Exception:
        pass

    unique: list[Path] = []
    seen: set[str] = set()
    for folder in dirs:
        try:
            key = str(folder.resolve()).lower()
        except Exception:
            key = str(folder).lower()
        if key not in seen:
            seen.add(key)
            unique.append(folder)
    return unique


def cleanup_old_legacy_exes() -> None:
    """Delete old ``PingOverlay-vX.Y.Z.exe`` / ``PingOverlayvX.Y.Z.exe`` files.

    This runs only in the packaged app. It deliberately skips unversioned
    ``PingOverlay.exe`` because there is no safe way to know whether that file
    is older than the current build without starting/inspecting it.
    """
    if not getattr(sys, "frozen", False):
        return
    current_version = _parse_version_tuple(__version__)
    if current_version == (0, 0, 0):
        return
    try:
        current_path = Path(sys.executable).resolve()
    except Exception:
        current_path = Path("")

    deleted = 0
    for folder in _legacy_cleanup_dirs():
        if not folder.exists() or not folder.is_dir():
            continue
        try:
            candidates = list(folder.glob("PingOverlay*.exe"))
        except Exception as exc:
            print(f"[cleanup] scan failed {folder}: {exc}")
            continue
        for candidate in candidates:
            try:
                path = candidate.resolve()
                if current_path and path == current_path:
                    continue
                version = _legacy_exe_version(path)
                if version is None or version >= current_version:
                    continue
                path.unlink()
                deleted += 1
                print(f"[cleanup] deleted old legacy exe: {path.name}")
            except PermissionError:
                print(f"[cleanup] could not delete in-use legacy exe: {candidate}")
            except Exception as exc:
                print(f"[cleanup] delete failed {candidate}: {exc}")
    if deleted:
        print(f"[cleanup] deleted {deleted} old legacy PingOverlay exe file(s)")


def main():
    update_stamp_path = _consume_update_stamp_arg()
    # Version-aware single-instance guard. Reads %APPDATA%\\PingOverlay\\
    # .instance.lock to compare versions: newer → terminate + take
    # over; older → show "newer is running" message and exit. Falls
    # back to a name-pattern kill (PingOverlay*.exe) so versioned
    # downloads from the GitHub release also play nicely.
    _enforce_single_instance()
    cleanup_old_legacy_exes()
    cfg = app_config.load()
    cleanup_stale_update_artifacts()
    _write_update_stamp(update_stamp_path)
    print(f"[main] version: {__version__}")
    print(f"[main] config path: {app_config.config_path()}")
    print(f"[main] target_process: {cfg.get('target_process')}  "
          f"autostart: {cfg.get('autostart')}")
    print(f"[main] update: {cfg.get('update')}")

    # Đồng bộ autostart registry với cfg ngay lúc khởi động
    try:
        autostart.sync(bool(cfg.get("autostart", False)))
    except Exception as e:
        print(f"[main] autostart sync error: {e}")

    app = AppState(cfg)
    start_startup_update_check(app)
    # Initial license probe. Reads %APPDATA%/PingOverlay/license.json and
    # validates against the current HWID. Result drives feature gating
    # in ControlPanel + tray menu. UI surfaces poll ``app.licensed``.
    try:
        import license_check as _lc
        status = _lc.current_status()
        _apply_license_status(app, status)
        print(
            f"[main] license: {'OK' if status.is_licensed else 'unlicensed'} "
            f"hwid={status.hwid} reason={status.error or '-'}"
        )
    except Exception as exc:
        print(f"[main] license check failed: {exc}")
        app.licensed = False
        app.license_status = None
    options = OverlayOptions(cfg)
    app.game_panel_options = GamePanelOptions(cfg)
    app.event_monitor = EventMonitor(cfg)
    app.event_monitor.start()
    try:
        app.event_monitor.force_refresh()
    except Exception:
        pass

    def _persist_offset(x: int, y: int) -> None:
        ov = cfg.setdefault("overlay", {})
        ov["offset_x"] = int(x)
        ov["offset_y"] = int(y)
        app_config.save(cfg)
        print(f"[main] overlay offset saved: ({x}, {y})")

    overlay = Overlay(cfg=cfg, on_offset_changed=_persist_offset)
    app.quest_helper_parent = overlay.root
    overlay.set_text(_append_overlay_clock(tr(app, "overlay_waiting_start")), color="#888888")
    overlay.hide()  # khởi động ở trạng thái ẩn; supervisor sẽ bật khi có game
    _start_license_admin_heartbeat(app, cfg, overlay.root)

    tray, actions = make_tray_icon(overlay, options, app)
    try:
        tray.title = f"{APP_DISPLAY_NAME} ({session_status_text(app)})"
    except Exception:
        pass
    app.control_panel = ControlPanel(
        overlay.root,
        app,
        options,
        actions,
    )
    app.control_panel.prepare_initial_render()
    app.control_panel.show()
    overlay.root.after(700, lambda: _maybe_show_trial_notice(app, overlay.root))
    _start_access_refresh(app, overlay.root)
    threading.Thread(target=tray.run, daemon=True).start()

    # Global hotkey toggle overlay
    hk_cfg = cfg.get("hotkey") or {}
    hk = GlobalHotkey(
        modifiers=hk_cfg.get("modifiers", ["ctrl", "shift"]),
        key=hk_cfg.get("key", "P"),
        on_pressed=lambda: overlay.root.after(0, overlay.toggle),
    )
    if hk.start():
        app.hotkey_label = hk.describe()
        print(f"[main] hotkey registered: {app.hotkey_label}")
    else:
        app.hotkey_label = "(failed)"
        print("[main] hotkey registration failed; continue without")

    panel_hotkey = None
    panel_cfg = cfg.get("panel") or {}
    panel_key_cfg = panel_cfg.get("hotkey") or {}
    panel_key = str(panel_key_cfg.get("key") or "").strip()
    if panel_key:
        def _toggle_panel() -> None:
            try:
                if app.control_panel is None:
                    return
                window = app.control_panel.window
                if window.state() == "withdrawn":
                    app.control_panel.show()
                else:
                    app.control_panel.hide()
            except Exception as exc:
                print(f"[panel-hotkey] toggle failed: {exc}")
        panel_hotkey = GlobalHotkey(
            modifiers=panel_key_cfg.get("modifiers", []) or [],
            key=panel_key,
            on_pressed=lambda: overlay.root.after(0, _toggle_panel),
            hotkey_id=3,
        )
        if panel_hotkey.start():
            print(f"[main] panel hotkey registered: {panel_hotkey.describe()}")
        else:
            print("[main] panel hotkey registration failed; continue without")
            panel_hotkey = None

    qh_hotkey = None
    qh_cfg = cfg.get("quest_helper") or {}
    if qh_cfg.get("enabled", True):
        qh_key_cfg = qh_cfg.get("hotkey") or {}
        qh_hotkey = GlobalHotkey(
            modifiers=qh_key_cfg.get("modifiers", ["ctrl", "alt"]),
            key=qh_key_cfg.get("key", "H"),
            on_pressed=lambda: overlay.root.after(0, lambda: toggle_quest_helper(cfg, app)),
            hotkey_id=2,
        )
        if qh_hotkey.start():
            print(f"[main] quest helper hotkey registered: {qh_hotkey.describe()}")
        else:
            print("[main] quest helper hotkey registration failed; continue without")
    try:
        tray.update_menu()
    except Exception:
        pass
    refresh_control_panel(app)

    def _run_admin_forced_update() -> None:
        if not bool(getattr(app, "license_admin_force_update_pending", False)):
            return
        app.license_admin_force_update_pending = False
        maybe_check_for_updates(
            overlay,
            app,
            tray,
            interactive=False,
        )

    app.license_admin_update_callback = _run_admin_forced_update
    if bool(getattr(app, "license_admin_force_update_pending", False)):
        overlay.root.after(1000, _run_admin_forced_update)

    # ── Startup account sync (background) ────────────────────────────────────
    def _startup_account_sync() -> None:
        try:
            import account_sync as _acc
            sess = _acc.load_session()
            if sess:
                sess2 = _acc.fetch_and_merge_profile(sess, cfg)
                _acc.save_session(sess2)
                import config as _cfg_mod
                _cfg_mod.save(cfg)
        except Exception as exc:
            print(f"[account] startup sync failed: {exc}")

        # ── Referral claim: award points to referrer now that the app runs ────
        # This converts a "pending_download" (logged on web) into a confirmed
        # first_launch by matching the machine's public IP. Idempotent — safe
        # to call on every startup; the backend deduplicates by HWID.
        try:
            from license_lib import compute_hwid, normalize_hwid
            import license_admin as _la
            hwid_val = normalize_hwid(compute_hwid())
            pub_ip   = _la.public_ip() if _la.should_lookup_public_ip(cfg) else ""
            if hwid_val and pub_ip:
                import account_sync as _acc2
                result = _acc2.claim_pending_referral(hwid_val, pub_ip)
                if result.get("ok"):
                    print(
                        f"[referral] claimed — +{result.get('points_awarded', 0)} pts "
                        f"(total {result.get('total_points', '?')})"
                        + (" — reward issued!" if result.get("reward_issued") else "")
                    )
                elif result.get("reason") not in ("already_claimed", "no_pending_download", "missing_hwid_or_ip"):
                    print(f"[referral] claim skipped: {result.get('reason') or result.get('error')}")
        except Exception as exc:
            print(f"[referral] claim failed: {exc}")

    threading.Thread(target=_startup_account_sync, daemon=True, name="AccountSync").start()

    update_cfg = cfg.get("update") or {}
    if bool(update_cfg.get("enabled", True)) and bool(update_cfg.get("check_on_startup", True)):
        def _auto_update_check() -> None:
            maybe_check_for_updates(
                overlay,
                app,
                tray,
                interactive=False,
            )

        overlay.schedule(
            100,
            _auto_update_check,
        )
        # One short retry catches GitHub/Apps Script release propagation or
        # a cold gateway returning stale "latest" metadata right after app
        # launch. The retry performs a fresh check because the startup probe
        # result is consumed by the first auto-check.
        overlay.schedule(15000, _auto_update_check)

    window_follow_loop(overlay, app)
    display_loop(overlay, app, options)
    supervisor_loop(overlay, app, tray)

    try:
        overlay.mainloop()
    finally:
        try:
            close_quest_helper(cfg, app)
        except Exception:
            pass
        cleanup_quest_scan_images()
        try:
            stop_session(app, overlay, tray)
        except Exception:
            pass
        try:
            hk.stop()
        except Exception:
            pass
        try:
            if qh_hotkey is not None:
                qh_hotkey.stop()
        except Exception:
            pass
        try:
            if panel_hotkey is not None:
                panel_hotkey.stop()
        except Exception:
            pass
        try:
            if app.event_monitor is not None:
                app.event_monitor.stop()
        except Exception:
            pass
        try:
            tray.stop()
        except Exception:
            pass
        # Release the version-aware single-instance lock so the next
        # launch isn't confused by a stale PID. Best-effort: skipped
        # silently when another (newer) instance has already taken
        # ownership of the lock.
        try:
            _delete_instance_lock()
        except Exception:
            pass
        # Đảm bảo process kết thúc ngay cả khi có thread nền còn sống
        os._exit(0)


if __name__ == "__main__":
    main()
