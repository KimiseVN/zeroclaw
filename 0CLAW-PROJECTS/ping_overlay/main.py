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
import sys
import threading
import time
import tkinter as tk
import ctypes
import types
import webbrowser
from collections import deque
from tkinter import messagebox, ttk
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
from updater import (
    check_for_update,
    cleanup_stale_update_artifacts,
    download_update,
    install_downloaded_update,
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

ping3.EXCEPTIONS = False

DISPLAY_MS_ACTIVE = 300
DISPLAY_MS_WAITING = 900
WINDOW_POLL_MS_ACTIVE = 250
WINDOW_POLL_MS_IDLE = 1000
PING_INTERVAL_S = 0.5   # khoảng cách mỗi lần ping (giây)
IP_RESCAN_EVERY = 20    # cứ N ping thì scan lại IP (~10s)
LOSS_WINDOW = 20        # số mẫu gần nhất tính packet loss

DEVELOPER_NAME = "ムKim - BunnyDOG Guild WWM"
COPYRIGHT_YEAR = "2026"
DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=5F4PKX7KSHDYN"
DISCORD_URL = "https://discord.gg/sSjavfYzna"
ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_PNG = ASSET_DIR / "icon.png"
DONATE_PNG = ASSET_DIR / "donate-pp.png"
DISCORD_PNG = ASSET_DIR / "join-dc.png"

SUPERVISOR_MS = 2000    # nhịp kiểm tra process sống/chết + auto-detect game mới

_UI_IMAGE_CACHE: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}


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


def _apply_window_icon(window) -> None:
    photo = _load_ui_photo(ICON_PNG, 64, 64)
    if photo is None:
        return
    try:
        window._app_icon_photo = photo
        window.iconphoto(True, photo)
    except Exception:
        pass


def _show_copyright_dialog(parent, app) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title(tr(app, "copyright_title"))
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.grab_set()
    _apply_window_icon(dialog)

    body = tr(
        app,
        "copyright_body",
        version=__version__,
        developer=DEVELOPER_NAME,
        year=COPYRIGHT_YEAR,
    )

    root = ttk.Frame(dialog, padding=16)
    root.pack(fill="both", expand=True)

    top = ttk.Frame(root)
    top.pack(fill="x")

    icon = _load_ui_photo(ICON_PNG, 52, 52)
    if icon is not None:
        icon_label = ttk.Label(top, image=icon)
        icon_label.image = icon
        icon_label.pack(side="left", padx=(0, 12), anchor="n")

    text_label = ttk.Label(top, text=body, justify="left")
    text_label.pack(side="left", fill="both", expand=True)

    ttk.Button(root, text=tr(app, "button_ok"), command=dialog.destroy).pack(
        anchor="e", pady=(14, 0)
    )

    dialog.update_idletasks()
    x = parent.winfo_rootx() + max((parent.winfo_width() - dialog.winfo_width()) // 2, 0)
    y = parent.winfo_rooty() + max((parent.winfo_height() - dialog.winfo_height()) // 2, 0)
    dialog.geometry(f"+{x}+{y}")
    dialog.wait_window()


class _HoverTooltip:
    def __init__(self, parent, text_provider):
        self.parent = parent
        self.text_provider = text_provider
        self.tip: tk.Toplevel | None = None
        self.label: tk.Label | None = None

    def bind(self, widget) -> None:
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event) -> None:
        self._show(event)

    def _on_motion(self, event) -> None:
        if self.tip is None:
            self._show(event)
        else:
            self._place(event)
            self._update_text()

    def _on_leave(self, _event=None) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
        self.tip = None
        self.label = None

    def _show(self, event) -> None:
        text = self.text_provider()
        if not text:
            return
        self.tip = tk.Toplevel(self.parent)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(bg="#1E1E1E")
        self.label = tk.Label(
            self.tip,
            text=text,
            justify="left",
            bg="#1E1E1E",
            fg="#F2F2F2",
            relief="solid",
            bd=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        self.label.pack()
        self._place(event)

    def _update_text(self) -> None:
        if self.label is None:
            return
        try:
            self.label.configure(text=self.text_provider())
        except Exception:
            pass

    def _place(self, event) -> None:
        if self.tip is None:
            return
        x = int(event.x_root) + 14
        y = int(event.y_root) + 18
        self.tip.geometry(f"+{x}+{y}")


I18N = {
    "en": {
        "status_waiting_start": "Waiting for Start",
        "status_waiting_lobby": "Waiting for lobby",
        "status_active": "Active",
        "status_waiting_game": "Waiting for game",
        "update_title": "Update",
        "update_exe_only": "Auto-update is only supported when running the packaged PingOverlay.exe build.",
        "update_latest": "You are already on the latest version ({version}).",
        "update_available_title": "Update available",
        "update_available_body": "A new version {version} is available.\n\nYou are running {current}.\nThe app will download and restart to update.\n\nUpdate now?",
        "update_installing": "Updating to {version}. The app will restart automatically.",
        "update_error": "Could not update:\n{error}",
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
        "copyright_body": "PingOverlay\n\nVersion {version}\nDeveloped by {developer}\n© {year} {developer}. All rights reserved.\n\nReal-time Ping / Packet Loss / FPS overlay\nfor online games. Anti-cheat safe (no inject).",
        "menu_show_ping": "Show Ping",
        "menu_show_loss": "Show Loss",
        "menu_show_jitter": "Show Jitter (60s)",
        "menu_show_minmax": "Show Min/Max (session)",
        "menu_show_fps": "Show FPS",
        "menu_show_low1": "Show 1% Low (60s)",
        "menu_show_frametime": "Show Frame time",
        "menu_show_cpu": "Show CPU",
        "menu_show_cpu_temp": "Show CPU Temp",
        "menu_show_ram": "Show RAM",
        "menu_show_vram": "Show VRAM",
        "menu_show_api": "Show API",
        "menu_process": "Process: {value}",
        "menu_target": "Target: {value}",
        "menu_api": "API: {value}",
        "menu_status": "Status: {value}",
        "menu_show_app": "Show app",
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
        "menu_auto_update": "Auto-update on launch",
        "menu_start_with_windows": "Start with Windows",
        "menu_reset_position": "Reset overlay position",
        "menu_hotkey": "Hotkey: {value}",
        "menu_language": "Language",
        "menu_language_en": "English",
        "menu_language_vi": "Tiếng Việt",
        "menu_donate": "Donate for ムKim",
        "gui_join_discord": "Join us on Discord",
        "menu_copyright": "Copyright",
        "menu_close": "Close",
        "gui_window_title": "PingOverlay Control Center",
        "gui_heading": "PingOverlay Control Center",
        "gui_subheading": "Quick controls for monitoring and overlay display.",
        "gui_language_frame": "Language",
        "gui_monitoring_frame": "Monitoring",
        "gui_status_label": "Status",
        "gui_options_frame": "Overlay Options",
        "gui_actions_frame": "Actions",
        "gui_developed_by": "Developed by {developer}",
        "tooltip_show_ping": "Current round-trip latency to the detected game route.",
        "tooltip_show_loss": "Packet loss rate across recent ping samples.",
        "tooltip_show_jitter": "Connection stability over the last 60 seconds.",
        "tooltip_show_minmax": "Lowest and highest latency seen in the current session.",
        "tooltip_show_fps": "Current rendered frames per second from PresentMon.",
        "tooltip_show_low1": "1% low FPS for recent smoothness and frame pacing.",
        "tooltip_show_frametime": "Average frame render time in milliseconds.",
        "tooltip_show_cpu": "CPU usage currently attributed to the game process.",
        "tooltip_show_cpu_temp": "Current CPU temperature when a sensor is available.",
        "tooltip_show_ram": "Game memory usage versus total system RAM, with percentage.",
        "tooltip_show_vram": "Active GPU memory usage versus total VRAM, with percentage.",
        "tooltip_show_api": "Detected graphics API used by the game process.",
        "gui_start_prompt_title": "Start monitoring",
        "gui_start_prompt_body": "Choose what to do with the control window after monitoring starts.",
        "gui_start_hide": "Hide to tray",
        "gui_start_minimize": "Minimize window",
        "gui_start_cancel": "Cancel",
        "gui_close_prompt_title": "Close control panel",
        "gui_close_prompt_body": "Choose what to do with PingOverlay.",
        "gui_close_hide": "Hide to tray",
        "gui_close_exit": "Close app",
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
        "update_exe_only": "Chỉ hỗ trợ tự động cập nhật khi chạy từ bản PingOverlay.exe đã build.",
        "update_latest": "Bạn đang ở bản mới nhất ({version}).",
        "update_available_title": "Có bản cập nhật mới",
        "update_available_body": "Đã có bản mới {version}.\n\nBạn đang dùng {current}.\nỨng dụng sẽ tải và tự khởi động lại để cập nhật.\n\nCập nhật ngay?",
        "update_installing": "Đang cập nhật lên {version}. Ứng dụng sẽ tự khởi động lại.",
        "update_error": "Không thể cập nhật:\n{error}",
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
        "copyright_body": "PingOverlay\n\nPhiên bản {version}\nPhát triển bởi {developer}\n© {year} {developer}. Đã đăng ký mọi quyền.\n\nOverlay Ping / Packet Loss / FPS thời gian thực\ncho game online. Anti-cheat safe (không inject).",
        "menu_show_ping": "Hiện Ping",
        "menu_show_loss": "Hiện Loss",
        "menu_show_jitter": "Hiện Jitter (60s)",
        "menu_show_minmax": "Hiện Min/Max (phiên)",
        "menu_show_fps": "Hiện FPS",
        "menu_show_low1": "Hiện 1% Low (60s)",
        "menu_show_frametime": "Hiện Frame time",
        "menu_show_cpu": "Hiện CPU",
        "menu_show_cpu_temp": "Hiện nhiệt CPU",
        "menu_show_ram": "Hiện RAM",
        "menu_show_vram": "Hiện VRAM",
        "menu_show_api": "Hiện API",
        "menu_process": "Process: {value}",
        "menu_target": "Target: {value}",
        "menu_api": "API: {value}",
        "menu_status": "Trạng thái: {value}",
        "menu_show_app": "Hiện ứng dụng",
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
        "menu_auto_update": "Tự cập nhật khi mở app",
        "menu_start_with_windows": "Khởi động cùng Windows",
        "menu_reset_position": "Đặt lại vị trí overlay",
        "menu_hotkey": "Hotkey: {value}",
        "menu_language": "Ngôn ngữ",
        "menu_language_en": "English",
        "menu_language_vi": "Tiếng Việt",
        "menu_donate": "Donate for ムKim",
        "gui_join_discord": "Join us on Discord",
        "menu_copyright": "Bản quyền",
        "menu_close": "Đóng",
        "gui_window_title": "Bảng điều khiển PingOverlay",
        "gui_heading": "Bảng điều khiển PingOverlay",
        "gui_subheading": "Điều khiển nhanh cho monitoring và hiển thị overlay.",
        "gui_language_frame": "Ngôn ngữ",
        "gui_monitoring_frame": "Monitoring",
        "gui_status_label": "Trạng thái",
        "gui_options_frame": "Tùy chọn Overlay",
        "gui_actions_frame": "Hành động",
        "gui_developed_by": "Phát triển bởi {developer}",
        "tooltip_show_ping": "Độ trễ round-trip hiện tại tới route game đang được phát hiện.",
        "tooltip_show_loss": "Tỷ lệ mất gói dựa trên các mẫu ping gần đây.",
        "tooltip_show_jitter": "Độ ổn định kết nối trong 60 giây gần nhất.",
        "tooltip_show_minmax": "Độ trễ thấp nhất và cao nhất trong phiên hiện tại.",
        "tooltip_show_fps": "FPS render hiện tại lấy từ PresentMon.",
        "tooltip_show_low1": "1% low FPS để phản ánh độ mượt và frame pacing gần đây.",
        "tooltip_show_frametime": "Thời gian render khung hình trung bình theo mili giây.",
        "tooltip_show_cpu": "Mức sử dụng CPU hiện tại của process game.",
        "tooltip_show_cpu_temp": "Nhiệt độ CPU hiện tại nếu máy có sensor hỗ trợ.",
        "tooltip_show_ram": "Dung lượng RAM game đang dùng so với tổng RAM hệ thống, kèm phần trăm.",
        "tooltip_show_vram": "Dung lượng VRAM đang dùng trên GPU active so với tổng VRAM, kèm phần trăm.",
        "tooltip_show_api": "Graphics API được phát hiện từ process game.",
        "gui_start_prompt_title": "Bắt đầu theo dõi",
        "gui_start_prompt_body": "Chọn cách xử lý cửa sổ điều khiển sau khi bắt đầu monitoring.",
        "gui_start_hide": "Ẩn xuống tray",
        "gui_start_minimize": "Thu nhỏ cửa sổ",
        "gui_start_cancel": "Hủy",
        "gui_close_prompt_title": "Đóng bảng điều khiển",
        "gui_close_prompt_body": "Chọn cách xử lý PingOverlay.",
        "gui_close_hide": "Ẩn xuống tray",
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


def _write_update_stamp(stamp_path: str | None) -> None:
    if not stamp_path:
        return
    try:
        with open(stamp_path, "w", encoding="utf-8") as f:
            f.write(f"ok {__version__}\n")
    except Exception as e:
        print(f"[update] could not write startup stamp: {e}")


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
        self.session_token: int = 0
        self.control_panel = None


def session_status_text(app: AppState) -> str:
    if not app.monitoring_enabled:
        return tr(app, "status_waiting_start")
    if app.warming:
        return tr(app, "status_waiting_lobby")
    if app.active:
        return tr(app, "status_active")
    return tr(app, "status_waiting_game")


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
                lambda: messagebox.showinfo(
                    tr(app, "update_title"),
                    tr(app, "update_exe_only"),
                ),
            )
        return

    app.update_in_progress = True
    try:
        tray.update_menu()
    except Exception:
        pass

    def worker():
        try:
            info = check_for_update(app.cfg, __version__)
            if info is None:
                if interactive:
                    overlay.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            tr(app, "update_title"),
                            tr(app, "update_latest", version=__version__),
                        ),
                    )
                return

            auto_install = bool(update_cfg.get("auto_install", True))
            if interactive or not auto_install:
                answer: dict[str, bool] = {"value": False}
                done = threading.Event()

                def ask():
                    answer["value"] = messagebox.askyesno(
                        tr(app, "update_available_title"),
                        tr(app, "update_available_body", version=info.version, current=__version__),
                    )
                    done.set()

                overlay.root.after(0, ask)
                done.wait()
                if not answer["value"]:
                    return

            print(f"[update] downloading {info.asset_name} from {info.repo} tag {info.tag}")
            download_path = download_update(info)
            install_downloaded_update(download_path, info.asset_name)

            def finish_and_exit():
                messagebox.showinfo(
                    tr(app, "update_title"),
                    tr(app, "update_installing", version=info.version),
                )
                try:
                    tray.stop()
                except Exception:
                    pass
                os._exit(0)

            overlay.root.after(0, finish_and_exit)
        except Exception as e:
            err = str(e)
            print(f"[update] error: {err}")
            if interactive:
                overlay.root.after(
                    0,
                    lambda msg=err: messagebox.showerror(
                        tr(app, "update_title"),
                        tr(app, "update_error", error=msg),
                    ),
                )
        finally:
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
        self.show_ram = bool(opts.get("show_ram", True))
        self.show_vram = bool(opts.get("show_vram", True))
        self.show_api = bool(opts.get("show_api", True))

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
            "show_ram": self.show_ram,
            "show_vram": self.show_vram,
            "show_api": self.show_api,
        }
        app_config.save(self._cfg)


class ControlPanel:
    def __init__(self, master, app: AppState, options: OverlayOptions, actions: dict):
        self.app = app
        self.options = options
        self.actions = actions
        self._syncing = False
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
            "show_ram": "menu_show_ram",
            "show_vram": "menu_show_vram",
            "show_api": "menu_show_api",
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
            "show_ram": "tooltip_show_ram",
            "show_vram": "tooltip_show_vram",
            "show_api": "tooltip_show_api",
        }

        self.window = tk.Toplevel(master)
        self.window.geometry("500x530")
        self.window.minsize(470, 515)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close_requested)
        _apply_window_icon(self.window)

        root = ttk.Frame(self.window, padding=14)
        root.pack(fill="both", expand=True)

        self.heading_label = ttk.Label(root, font=("Segoe UI", 15, "bold"), anchor="center", justify="center")
        self.heading_label.pack(fill="x")
        self.subheading_label = ttk.Label(root, anchor="center", justify="center")
        self.subheading_label.pack(fill="x", pady=(4, 12))

        top_row = ttk.Frame(root)
        top_row.pack(fill="x")
        top_row.columnconfigure(0, weight=1)
        top_row.columnconfigure(1, weight=1)

        left_column = ttk.Frame(top_row)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_column.columnconfigure(0, weight=1)

        self.language_frame = ttk.LabelFrame(left_column, padding=6)
        self.language_frame.grid(row=0, column=0, sticky="ew")
        self.language_var = tk.StringVar(value=lang_code(app))
        self.lang_en = ttk.Radiobutton(
            self.language_frame,
            value="en",
            variable=self.language_var,
            command=self._on_language_change,
        )
        self.lang_vi = ttk.Radiobutton(
            self.language_frame,
            value="vi",
            variable=self.language_var,
            command=self._on_language_change,
        )
        self.lang_en.pack(side="left", padx=(0, 12))
        self.lang_vi.pack(side="left")

        self.actions_frame = ttk.LabelFrame(left_column, padding=5)
        self.actions_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.donate_button = ttk.Label(self.actions_frame, anchor="center")
        self.donate_button.pack(fill="x")
        self.donate_button.bind("<Button-1>", self._on_donate_clicked)
        self._donate_photo = _load_ui_photo(DONATE_PNG, 180, 42)

        self.monitoring_frame = ttk.LabelFrame(top_row, padding=8)
        self.monitoring_frame.grid(row=0, column=1, sticky="nsew")
        self.status_caption = ttk.Label(self.monitoring_frame)
        self.status_caption.grid(row=0, column=0, sticky="w")
        self.status_value = ttk.Label(self.monitoring_frame, font=("Segoe UI", 10, "bold"))
        self.status_value.grid(row=1, column=0, sticky="w", pady=(2, 6))

        buttons = ttk.Frame(self.monitoring_frame)
        buttons.grid(row=2, column=0, pady=(2, 0))
        self.start_button = ttk.Button(buttons, command=self._on_start_clicked)
        self.start_button.grid(row=0, column=0, padx=(0, 4))
        self.stop_button = ttk.Button(buttons, command=self._on_stop_clicked)
        self.stop_button.grid(row=0, column=1, padx=(4, 0))

        self.options_frame = ttk.LabelFrame(root, padding=10)
        self.options_frame.pack(fill="x", pady=(12, 10))
        self.option_vars: dict[str, tk.BooleanVar] = {}
        self.option_buttons: dict[str, ttk.Checkbutton] = {}
        self.option_tooltips: dict[str, _HoverTooltip] = {}
        option_order = [
            "show_ping", "show_loss",
            "show_jitter", "show_minmax",
            "show_fps", "show_low1",
            "show_frametime", "show_cpu",
            "show_cpu_temp", "show_ram",
            "show_vram", "show_api",
        ]
        for idx, attr in enumerate(option_order):
            var = tk.BooleanVar(value=bool(getattr(self.options, attr)))
            btn = ttk.Checkbutton(
                self.options_frame,
                variable=var,
                command=lambda name=attr: self._on_option_toggle(name),
            )
            row = idx // 2
            col = idx % 2
            btn.grid(row=row, column=col, sticky="w", padx=(0, 16), pady=4)
            self.option_vars[attr] = var
            self.option_buttons[attr] = btn
            tooltip = _HoverTooltip(
                self.window,
                lambda name=attr: tr(self.app, self._option_tooltip_keys[name]),
            )
            tooltip.bind(btn)
            self.option_tooltips[attr] = tooltip
        self.options_frame.columnconfigure(0, weight=1)
        self.options_frame.columnconfigure(1, weight=1)

        self.developed_by_label = ttk.Label(root, anchor="center", justify="center")
        self.developed_by_label.pack(fill="x", pady=(6, 0))
        self.discord_button = ttk.Label(root, anchor="center")
        self.discord_button.pack(fill="x", pady=(4, 0))
        self.discord_button.bind("<Button-1>", self._on_discord_clicked)
        self._discord_photo = _load_ui_photo(DISCORD_PNG, 180, 36)

        self.refresh()
        self.window.after(0, self._configure_native_window)

    def show(self) -> None:
        try:
            self.window.deiconify()
            self.window.state("normal")
        except Exception:
            pass
        self._show_native(SW_RESTORE)
        self.window.lift()
        try:
            self.window.focus_force()
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self.window.withdraw()
        except Exception:
            pass
        self._show_native(SW_HIDE)

    def minimize(self) -> None:
        try:
            self.window.deiconify()
            self.window.state("iconic")
        except Exception:
            pass
        self._show_native(SW_SHOWMINIMIZED)

    def refresh(self) -> None:
        self._syncing = True
        self.language_var.set(lang_code(self.app))
        self.window.title(tr(self.app, "gui_window_title"))
        self.heading_label.configure(text=tr(self.app, "gui_heading"))
        self.subheading_label.configure(text=tr(self.app, "gui_subheading"))
        self.language_frame.configure(text=tr(self.app, "gui_language_frame"))
        self.monitoring_frame.configure(text=tr(self.app, "gui_monitoring_frame"))
        self.status_caption.configure(text=tr(self.app, "gui_status_label"))
        self.status_value.configure(text=session_status_text(self.app))
        self.start_button.configure(
            text=tr(self.app, "menu_start_monitoring"),
            state=("disabled" if self.app.monitoring_enabled else "normal"),
        )
        self.stop_button.configure(
            text=tr(self.app, "menu_stop_monitoring"),
            state=("normal" if self.app.monitoring_enabled else "disabled"),
        )
        self.options_frame.configure(text=tr(self.app, "gui_options_frame"))
        self.actions_frame.configure(text="")
        self.lang_en.configure(text=tr(self.app, "menu_language_en"))
        self.lang_vi.configure(text=tr(self.app, "menu_language_vi"))
        if self._donate_photo is not None:
            self.donate_button.configure(image=self._donate_photo, text="", cursor="hand2")
        else:
            self.donate_button.configure(text=tr(self.app, "menu_donate"), image="", cursor="hand2")
        if self._discord_photo is not None:
            self.discord_button.configure(image=self._discord_photo, text="", cursor="hand2")
        else:
            self.discord_button.configure(text=tr(self.app, "gui_join_discord"), image="", cursor="hand2")
        self.developed_by_label.configure(
            text=tr(self.app, "gui_developed_by", developer=DEVELOPER_NAME)
        )

        for attr, var in self.option_vars.items():
            var.set(bool(getattr(self.options, attr)))
            self.option_buttons[attr].configure(text=tr(self.app, self._option_keys[attr]))
        self._syncing = False

    def _on_language_change(self) -> None:
        if self._syncing:
            return
        self.actions["set_language"](self.language_var.get())

    def _on_option_toggle(self, attr: str) -> None:
        if self._syncing:
            return
        self.actions["toggle_option"](attr)

    def _on_start_clicked(self) -> None:
        choice = self._prompt_start_behavior()
        if choice is None:
            return
        if choice == "tray":
            self.hide()
        else:
            self.minimize()
        self.window.after_idle(self.actions["start_monitoring"])
        self.window.after(50, self.refresh)

    def _on_stop_clicked(self) -> None:
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.window.after_idle(self.actions["stop_monitoring"])
        self.window.after(50, self.refresh)
        self.window.after(200, self.refresh)

    def _on_donate_clicked(self, _event=None) -> None:
        self.actions["donate"]()

    def _on_discord_clicked(self, _event=None) -> None:
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

    def _prompt_choice_dialog(self, title: str, body: str,
                              choices: list[tuple[str, str | None]]) -> str | None:
        result = {"value": None}
        dialog = tk.Toplevel(self.window)
        dialog.title(title)
        dialog.transient(self.window)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: _close(None))

        container = ttk.Frame(dialog, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=body,
            justify="left",
            wraplength=320,
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
            parent = int(ctypes.windll.user32.GetParent(hwnd))
            return parent or hwnd
        except Exception:
            return 0

    def _configure_native_window(self) -> None:
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.restype = ctypes.c_long
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            user32.SetWindowPos(
                hwnd,
                0,
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
            ctypes.windll.user32.ShowWindow(hwnd, mode)
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
    Yêu cầu có cửa sổ visible đủ lớn. KHÔNG yêu cầu 3D API hay ESTABLISHED
    (game có thể đang ở splash, chưa load D3D / chưa connect).
    Nếu nhiều PID trùng tên: ưu tiên window lớn nhất.
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
        if not hwnd:
            continue
        area = get_window_area(hwnd)
        if area < MIN_WINDOW_AREA:
            continue
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
        # Force-exit: khi chạy onefile --windowed, một số thread backend
        # (pystray Win32, PresentMon, ETW, hotkey) không dọn kịp và
        # mainloop có thể không thoát. Dùng os._exit để chắc chắn.
        os._exit(0)

    def on_quit(icon, item=None):
        overlay.root.after(0, _shutdown_app)

    def _show_control_panel() -> None:
        cp = getattr(app, "control_panel", None)
        if cp is not None:
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
                    tray.title = f"PingOverlay ({session_status_text(app)})"
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

    def _toggle_option(attr: str) -> None:
        setattr(options, attr, not getattr(options, attr))
        try:
            options.persist()
        except Exception as e:
            print(f"[tray] persist options error: {e}")
        _refresh_ui()

    def make_toggle(attr: str):
        def _f(icon, item):
            _toggle_option(attr)
        return _f

    def on_toggle_autostart(icon, item):
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
        upd = app.cfg.setdefault("update", {})
        upd["check_on_startup"] = not bool(upd.get("check_on_startup", True))
        app_config.save(app.cfg)
        _refresh_ui()

    def _set_language(lang: str):
        app.cfg["language"] = lang
        app_config.save(app.cfg)
        _refresh_ui()

    def on_set_language(lang: str):
        overlay.root.after(0, lambda: _set_language(lang))

    def on_check_updates(icon, item=None):
        overlay.root.after(
            0,
            lambda: maybe_check_for_updates(
                overlay,
                app,
                tray,
                interactive=True,
            ),
        )

    def _set_monitoring_enabled(enabled: bool) -> None:
        if app.monitoring_enabled == enabled:
            return
        app.monitoring_enabled = enabled
        if not enabled:
            stop_session(app, overlay, tray)
            try:
                tray.title = f"PingOverlay ({session_status_text(app)})"
            except Exception:
                pass
            print("[tray] monitoring paused; waiting for Start")
        else:
            try:
                tray.title = f"PingOverlay ({session_status_text(app)})"
            except Exception:
                pass
            target = (app.cfg.get("target_process") or "").strip() or None
            detected = detect_game_process(target)
            if detected and not app.active:
                pid, proc_name = detected
                start_session(app, overlay, tray, pid, proc_name)
            print("[tray] monitoring enabled; waiting for game detect")
        _refresh_ui()

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
        if app.monitoring_enabled:
            _refresh_ui()
            return
        overlay.root.after(0, lambda: _set_monitoring_enabled(True))

    def on_stop_monitoring(icon, item=None):
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
        overlay.root.after(0, lambda: _apply_target_process(None))

    def on_choose_target(icon, item=None):
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
        def show():
            _show_copyright_dialog(overlay.root, app)
        overlay.root.after(0, show)

    def on_donate(icon, item=None):
        try:
            webbrowser.open(DONATE_URL, new=2)
        except Exception as e:
            print(f"[tray] donate open error: {e}")

    def on_discord(icon, item=None):
        try:
            webbrowser.open(DISCORD_URL, new=2)
        except Exception as e:
            print(f"[tray] discord open error: {e}")

    def _build_options_menu():
        return pystray.Menu(
            pystray.MenuItem(menu_text("menu_show_ping"), make_toggle("show_ping"),
                             checked=lambda i: options.show_ping),
            pystray.MenuItem(menu_text("menu_show_loss"), make_toggle("show_loss"),
                             checked=lambda i: options.show_loss),
            pystray.MenuItem(menu_text("menu_show_jitter"), make_toggle("show_jitter"),
                             checked=lambda i: options.show_jitter),
            pystray.MenuItem(menu_text("menu_show_minmax"), make_toggle("show_minmax"),
                             checked=lambda i: options.show_minmax),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_fps"), make_toggle("show_fps"),
                             checked=lambda i: options.show_fps),
            pystray.MenuItem(menu_text("menu_show_low1"), make_toggle("show_low1"),
                             checked=lambda i: options.show_low1),
            pystray.MenuItem(menu_text("menu_show_frametime"), make_toggle("show_frametime"),
                             checked=lambda i: options.show_frametime),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_cpu"), make_toggle("show_cpu"),
                             checked=lambda i: options.show_cpu),
            pystray.MenuItem(menu_text("menu_show_cpu_temp"), make_toggle("show_cpu_temp"),
                             checked=lambda i: options.show_cpu_temp),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_show_ram"), make_toggle("show_ram"),
                             checked=lambda i: options.show_ram),
            pystray.MenuItem(menu_text("menu_show_vram"), make_toggle("show_vram"),
                             checked=lambda i: options.show_vram),
            pystray.MenuItem(menu_text("menu_show_api"), make_toggle("show_api"),
                             checked=lambda i: options.show_api),
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
        monitoring_key = (
            "menu_monitoring_stop"
            if app.monitoring_enabled else
            "menu_monitoring_start"
        )
        return pystray.Menu(
            pystray.MenuItem(menu_text("menu_process", value=_display_proc_name), None, enabled=False),
            pystray.MenuItem(menu_text("menu_target", value=lambda: app.cfg.get('target_process') or tr(app, "target_auto")),
                             None, enabled=False),
            pystray.MenuItem(menu_text("menu_api", value=lambda: app.api), None, enabled=False),
            pystray.MenuItem(menu_text("menu_status", value=lambda: session_status_text(app)),
                             None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                menu_text("menu_show_app"),
                lambda icon, item: overlay.root.after(0, _show_control_panel),
                default=True,
            ),
            pystray.MenuItem(menu_text(monitoring_key), on_toggle_monitoring),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_choose_target"), on_choose_target),
            pystray.MenuItem(menu_text("menu_use_auto_detect"), on_use_auto_detect,
                             checked=lambda i: not (app.cfg.get("target_process") or "").strip()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_options"), _build_options_menu()),
            pystray.MenuItem(menu_text("menu_check_updates"), on_check_updates,
                             enabled=lambda i: not app.update_in_progress),
            pystray.MenuItem(menu_text("menu_auto_update"), on_toggle_auto_update,
                             checked=lambda i: bool((app.cfg.get("update") or {}).get("check_on_startup", True))),
            pystray.MenuItem(menu_text("menu_start_with_windows"), on_toggle_autostart,
                             checked=lambda i: bool(app.cfg.get("autostart", False))),
            pystray.MenuItem(menu_text("menu_reset_position"), on_reset_position),
            pystray.MenuItem(menu_text("menu_hotkey", value=lambda: app.hotkey_label), None, enabled=False),
            pystray.MenuItem(menu_text("menu_language"), _build_language_menu()),
            pystray.MenuItem(menu_text("menu_donate"), on_donate),
            pystray.MenuItem(menu_text("menu_copyright"), on_copyright),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(menu_text("menu_close"), on_quit),
        )

    icon = pystray.Icon("PingOverlay", ICON_RED, "PingOverlay (waiting)", _build_menu())
    try:
        import pystray._util.win32 as tray_win32

        original_on_notify = icon._on_notify

        def _patched_on_notify(self, wparam, lparam):
            if lparam == tray_win32.WM_RBUTTONUP:
                try:
                    self.menu = _build_menu()
                    self.title = f"PingOverlay ({session_status_text(app)})"
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
        "show_control_panel": _show_control_panel,
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
                    rect = get_client_topleft_size(hwnd)
                    if rect:
                        overlay.move_to_client(rect[0], rect[1])
                    else:
                        local["hwnd"] = None
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


def display_loop(overlay: Overlay, app: AppState, options: OverlayOptions):
    """Compact 1-dòng nén theo thứ tự:
       Ping 42ms │ Loss 0% │ FPS 144 │ RAM 2.1/16G │ VRAM 4.5/8G │ API DX12
    """
    def tick():
        delay_ms = DISPLAY_MS_WAITING
        try:
            if app.warming:
                overlay.set_text(
                    tr(app, "overlay_waiting_lobby"),
                    color="#FFAA00",
                )
            elif not app.monitoring_enabled:
                overlay.set_text(tr(app, "overlay_waiting_start"), color="#888888")
            elif not app.active:
                overlay.set_text(tr(app, "overlay_waiting_game"), color="#888888")
            elif app.ping_state is None:
                overlay.set_text(
                    tr(app, "overlay_waiting_match", process=app.proc_name),
                    color="#FFAA00",
                )
            else:
                delay_ms = DISPLAY_MS_ACTIVE
                lat, loss = app.ping_state.snapshot()
                jitter = app.ping_state.jitter_ms()
                smin, smax = app.ping_state.session_minmax()
                fps_val = app.fps_mon.fps() if app.fps_mon else None
                low1 = (app.fps_mon.one_percent_low_fps()
                        if app.fps_mon else None)
                ftime = (app.fps_mon.frame_time_ms()
                         if app.fps_mon else None)
                mem = app.mem_mon.snapshot() if app.mem_mon else None

                parts: list[str] = []
                if options.show_ping:
                    parts.append(
                        f"Ping: {lat:.0f}ms" if lat is not None else "Ping: n/a"
                    )
                if options.show_loss:
                    parts.append(
                        f"Loss: {loss:.0f}%" if loss is not None else "Loss: n/a"
                    )
                if options.show_jitter:
                    parts.append(
                        f"Jitter: {jitter:.0f}ms" if jitter is not None
                        else "Jitter: n/a"
                    )
                if options.show_minmax:
                    if smin is not None and smax is not None:
                        parts.append(f"Min/Max: {smin:.0f}/{smax:.0f}ms")
                    else:
                        parts.append("Min/Max: -/-")
                if options.show_fps:
                    parts.append(
                        f"FPS: {fps_val:.0f}" if fps_val is not None
                        else "FPS: n/a"
                    )
                if options.show_low1:
                    parts.append(
                        f"1% Low: {low1:.0f}" if low1 is not None
                        else "1% Low: n/a"
                    )
                if options.show_frametime:
                    parts.append(
                        f"Frame Time: {ftime:.1f}ms" if ftime is not None
                        else "Frame Time: n/a"
                    )
                if options.show_cpu and mem is not None:
                    cpu_pct = mem.get("cpu_proc_pct")
                    parts.append(
                        f"CPU: {cpu_pct:.0f}%" if cpu_pct is not None
                        else "CPU: n/a"
                    )
                if options.show_cpu_temp and mem is not None:
                    cpu_temp = mem.get("cpu_temp_c")
                    parts.append(
                        f"CPU Temp: {cpu_temp:.0f}°" if cpu_temp is not None
                        else "CPU Temp: n/a"
                    )
                if options.show_ram and mem is not None:
                    parts.append(
                        "RAM: " + fmt_ratio_bytes_pct(
                            mem.get("ram_proc_b"), mem.get("ram_total_b")
                        )
                    )
                if options.show_vram and mem is not None:
                    vram_used = mem.get("vram_gpu_b")
                    if vram_used is None:
                        vram_used = mem.get("vram_proc_b")
                    parts.append(
                        "VRAM: " + fmt_ratio_bytes_pct(
                            vram_used, mem.get("vram_total_b")
                        )
                    )
                if options.show_api:
                    parts.append(f"API: {app.api}")

                # Suffix khi traffic đi qua accelerator (ExitLag/Gearup/...)
                tail = ""
                try:
                    mode = app.ping_state.traffic_mode if app.ping_state else ""
                except Exception:
                    mode = ""
                if isinstance(mode, str) and mode.startswith("accelerator:"):
                    tail = f"  [via {mode.split(':', 1)[1]}]"

                color = "#00FF66" if lat is not None else "#FFAA00"
                overlay.set_text((" │ ".join(parts) if parts else " ") + tail,
                                 color=color)
        except Exception as e:
            overlay.set_text(tr(app, "overlay_error", error=e), color="#FF5555")
        finally:
            overlay.schedule(delay_ms, tick)

    tick()


# ---------- Session lifecycle ----------
def start_session(app: AppState, overlay: Overlay, tray: pystray.Icon,
                  pid: int, proc_name: str) -> None:
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
    session_token = app.session_token

    overlay.root.after(0, overlay.show)
    refresh_control_panel(app)
    try:
        tray.title = f"PingOverlay — {proc_name} (warming)"
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
            and app.pid == pid
            and app.session_token == session_token
        ):
            attempt += 1
            ips = wait_for_lobby(pid, stop_ev)
            if stop_ev.is_set() or app.pid != pid or app.session_token != session_token:
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
                tray.title = f"PingOverlay — {proc_name} (waiting net)"
                tray.update_menu()
            except Exception:
                pass
            print(f"[session] warmup attempt {attempt}: no lobby IPs yet, "
                  f"retry in 10s")
            if stop_ev.wait(timeout=10.0):
                return

        if (
            stop_ev.is_set()
            or app.pid != pid
            or app.session_token != session_token
            or not lobby_ips
        ):
            return

        city = pick_nearest_city_from_ips(lobby_ips) or "(unknown)"
        if stop_ev.is_set() or app.pid != pid or app.session_token != session_token:
            return
        app.city = city
        ping_state = PingState(pid, city)
        app.ping_state = ping_state
        app.warming = False
        threading.Thread(target=ping_state.run, daemon=True).start()
        refresh_control_panel(app)
        try:
            tray.title = f"PingOverlay — {proc_name}"
            tray.update_menu()
        except Exception:
            pass
        print(f"[session] lobby ready: {proc_name} @ {city}")

    threading.Thread(target=warmup, daemon=True).start()


def stop_session(app: AppState, overlay: Overlay, tray: pystray.Icon) -> None:
    if not app.active and app.pid is None:
        return
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

    overlay.root.after(0, overlay.hide)
    refresh_control_panel(app)
    try:
        tray.icon = ICON_RED
        tray.title = f"PingOverlay ({session_status_text(app)})"
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
            target = (app.cfg.get("target_process") or "").strip() or None
            if app.active:
                if app.pid is None or not psutil.pid_exists(app.pid):
                    stop_session(app, overlay, tray)
            elif app.monitoring_enabled:
                detected = detect_game_process(target)
                if detected:
                    pid, proc_name = detected
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


def main():
    update_stamp_path = _consume_update_stamp_arg()
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
    options = OverlayOptions(cfg)

    def _persist_offset(x: int, y: int) -> None:
        ov = cfg.setdefault("overlay", {})
        ov["offset_x"] = int(x)
        ov["offset_y"] = int(y)
        app_config.save(cfg)
        print(f"[main] overlay offset saved: ({x}, {y})")

    overlay = Overlay(cfg=cfg, on_offset_changed=_persist_offset)
    overlay.set_text(tr(app, "overlay_waiting_start"), color="#888888")
    overlay.hide()  # khởi động ở trạng thái ẩn; supervisor sẽ bật khi có game

    tray, actions = make_tray_icon(overlay, options, app)
    try:
        tray.title = f"PingOverlay ({session_status_text(app)})"
    except Exception:
        pass
    app.control_panel = ControlPanel(overlay.root, app, options, actions)
    app.control_panel.show()
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
    try:
        tray.update_menu()
    except Exception:
        pass
    refresh_control_panel(app)

    update_cfg = cfg.get("update") or {}
    if bool(update_cfg.get("enabled", True)) and bool(update_cfg.get("check_on_startup", True)):
        overlay.schedule(
            1500,
            lambda: maybe_check_for_updates(
                overlay,
                app,
                tray,
                interactive=False,
            ),
        )

    window_follow_loop(overlay, app)
    display_loop(overlay, app, options)
    supervisor_loop(overlay, app, tray)

    try:
        overlay.mainloop()
    finally:
        try:
            stop_session(app, overlay, tray)
        except Exception:
            pass
        try:
            hk.stop()
        except Exception:
            pass
        try:
            tray.stop()
        except Exception:
            pass
        # Đảm bảo process kết thúc ngay cả khi có thread nền còn sống
        os._exit(0)


if __name__ == "__main__":
    main()
