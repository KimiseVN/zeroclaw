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
from collections import deque
from tkinter import messagebox, ttk

import ping3
import psutil
from PIL import Image, ImageDraw
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
from metrics import MemoryMonitor, RollingWindow, fmt_ratio_bytes
from updater import check_for_update, download_update, install_downloaded_update, is_supported_runtime


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

ping3.EXCEPTIONS = False

DISPLAY_MS = 300        # refresh overlay (latency + fps)
WINDOW_POLL_MS = 200    # theo dõi vị trí cửa sổ game
PING_INTERVAL_S = 0.5   # khoảng cách mỗi lần ping (giây)
IP_RESCAN_EVERY = 20    # cứ N ping thì scan lại IP (~10s)
LOSS_WINDOW = 20        # số mẫu gần nhất tính packet loss

DEVELOPER_NAME = "ムKim - BunnyDOG Guild WWM"
COPYRIGHT_YEAR = "2026"

SUPERVISOR_MS = 2000    # nhịp kiểm tra process sống/chết + auto-detect game mới


def _make_icon_image(color: str) -> "Image.Image":
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    d.text((20, 20), "P", fill="black")
    return img


ICON_GREEN = _make_icon_image("#00FF66")
ICON_RED = _make_icon_image("#FF3333")


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


def session_status_text(app: AppState) -> str:
    if not app.monitoring_enabled:
        return "Waiting for Start"
    if app.warming:
        return "Waiting for lobby"
    if app.active:
        return "Active"
    return "Waiting for game"


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
                    "Update",
                    "Auto-update chỉ hỗ trợ khi chạy từ bản PingOverlay.exe đã build.",
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
                            "Update",
                            f"Bạn đang ở bản mới nhất ({__version__}).",
                        ),
                    )
                return

            auto_install = bool(update_cfg.get("auto_install", True))
            if interactive or not auto_install:
                answer: dict[str, bool] = {"value": False}
                done = threading.Event()

                def ask():
                    answer["value"] = messagebox.askyesno(
                        "Update available",
                        f"Đã có bản mới {info.version}.\n\n"
                        f"Bạn đang dùng {__version__}.\n"
                        f"Ứng dụng sẽ tải và khởi động lại để cập nhật.\n\n"
                        f"Cập nhật ngay?",
                    )
                    done.set()

                overlay.root.after(0, ask)
                done.wait()
                if not answer["value"]:
                    return

            print(f"[update] downloading {info.asset_name} from {info.repo} tag {info.tag}")
            download_path = download_update(info)
            install_downloaded_update(download_path)

            def finish_and_exit():
                messagebox.showinfo(
                    "Update",
                    f"Đang cập nhật lên {info.version}. Ứng dụng sẽ tự khởi động lại.",
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
                    lambda msg=err: messagebox.showerror("Update", f"Không thể cập nhật:\n{msg}"),
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
            "show_ram": self.show_ram,
            "show_vram": self.show_vram,
            "show_api": self.show_api,
        }
        app_config.save(self._cfg)


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
    win = tk.Tk()
    win.title("Chọn process game")
    win.geometry("760x520")
    tk.Label(
        win,
        text=("Chọn process có cửa sổ game. Danh sách đã ưu tiên app có "
              "3D API và public connection."),
        justify="left",
        wraplength=700,
    ).pack(padx=10, pady=8, anchor="w")

    lb = tk.Listbox(win, width=110, height=22)
    for entry in procs:
        badge = "Recommended"
        if not entry["recommended"]:
            badge = "Candidate"
        elif entry["routed_via_accelerator"]:
            badge = "Recommended via accelerator"
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
            text=("Không thấy process nào có cửa sổ đủ lớn để bám overlay.\n"
                  "Hãy mở game trước rồi thử lại."),
            fg="red",
            justify="left",
        ).pack(padx=10, pady=8, anchor="w")

    btns = tk.Frame(win)
    btns.pack(pady=8)
    tk.Button(btns, text="OK", width=16, command=ok,
              state=("normal" if procs else "disabled")).pack(side="left", padx=6)
    tk.Button(btns, text="Cancel", width=16, command=win.destroy).pack(side="left", padx=6)
    win.mainloop()
    return result.get("value")


def pick_city(cities: list[str]) -> str | None:
    win = tk.Tk()
    win.title("Chọn Server (theo thành phố)")
    win.geometry("360x170")
    if not cities:
        tk.Label(win, text="Không scan được city nào từ process.\n"
                           "Process có thể chưa có kết nối ra ngoài.",
                 fg="red").pack(pady=20)
        tk.Button(win, text="Đóng", width=12, command=win.destroy).pack()
        win.mainloop()
        return None

    tk.Label(win, text="Server (city) scan được:").pack(pady=6)
    var = tk.StringVar()
    cb = ttk.Combobox(win, textvariable=var, values=cities,
                      state="readonly", width=42)
    cb.current(0)
    cb.pack(pady=6)

    result: dict = {}

    def ok():
        result["value"] = var.get()
        win.destroy()

    tk.Button(win, text="OK", width=16, command=ok).pack(pady=10)
    win.mainloop()
    return result.get("value")


# ---------- Tray ----------
def make_tray_icon(overlay: Overlay, options: OverlayOptions,
                   app: AppState) -> pystray.Icon:
    def on_click(icon, item=None):
        overlay.root.after(0, overlay.toggle)

    def on_quit(icon, item=None):
        def _shutdown():
            overlay.close()
            try:
                icon.stop()
            except Exception:
                pass
            # Force-exit: khi chạy onefile --windowed, một số thread backend
            # (pystray Win32, PresentMon, ETW, hotkey) không dọn kịp và
            # mainloop có thể không thoát. Dùng os._exit để chắc chắn.
            os._exit(0)
        overlay.root.after(0, _shutdown)

    def make_toggle(attr: str):
        def _f(icon, item):
            setattr(options, attr, not getattr(options, attr))
            try:
                options.persist()
            except Exception as e:
                print(f"[tray] persist options error: {e}")
            icon.update_menu()
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
        icon.update_menu()

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
        try:
            icon.update_menu()
        except Exception:
            pass

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
                tray.title = "PingOverlay (paused)"
            except Exception:
                pass
            print("[tray] monitoring paused; waiting for Start")
        else:
            try:
                tray.title = "PingOverlay (waiting for game)"
            except Exception:
                pass
            target = (app.cfg.get("target_process") or "").strip() or None
            detected = detect_game_process(target)
            if detected and not app.active:
                pid, proc_name = detected
                start_session(app, overlay, tray, pid, proc_name)
            print("[tray] monitoring enabled; waiting for game detect")
        try:
            tray.update_menu()
        except Exception:
            pass

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

        try:
            tray.update_menu()
        except Exception:
            pass

        if normalized:
            print(f"[tray] target process pinned: {normalized}")
        else:
            print("[tray] target process set to auto-detect")

    def on_start_monitoring(icon, item=None):
        overlay.root.after(0, lambda: _set_monitoring_enabled(True))

    def on_stop_monitoring(icon, item=None):
        overlay.root.after(0, lambda: _set_monitoring_enabled(False))

    def on_use_auto_detect(icon, item=None):
        overlay.root.after(0, lambda: _apply_target_process(None))

    def on_choose_target(icon, item=None):
        def _choose():
            selected = pick_process()
            if not selected:
                return
            pid, proc_name = selected
            _apply_target_process(proc_name, (pid, proc_name))
        overlay.root.after(0, _choose)

    def on_copyright(icon, item):
        def show():
            from tkinter import messagebox
            messagebox.showinfo(
                "Copyright",
                f"PingOverlay\n\n"
                f"Version {__version__}\n"
                f"Developed by {DEVELOPER_NAME}\n"
                f"\u00a9 {COPYRIGHT_YEAR} {DEVELOPER_NAME}. All rights reserved.\n\n"
                f"Real-time Ping / Packet Loss / FPS overlay\n"
                f"for online games. Anti-cheat safe (no inject).",
            )
        overlay.root.after(0, show)

    options_menu = pystray.Menu(
        pystray.MenuItem("Show Ping", make_toggle("show_ping"),
                         checked=lambda i: options.show_ping),
        pystray.MenuItem("Show Loss", make_toggle("show_loss"),
                         checked=lambda i: options.show_loss),
        pystray.MenuItem("Show Jitter (60s)", make_toggle("show_jitter"),
                         checked=lambda i: options.show_jitter),
        pystray.MenuItem("Show Min/Max (session)", make_toggle("show_minmax"),
                         checked=lambda i: options.show_minmax),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show FPS", make_toggle("show_fps"),
                         checked=lambda i: options.show_fps),
        pystray.MenuItem("Show 1% Low (60s)", make_toggle("show_low1"),
                         checked=lambda i: options.show_low1),
        pystray.MenuItem("Show Frame time", make_toggle("show_frametime"),
                         checked=lambda i: options.show_frametime),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show RAM", make_toggle("show_ram"),
                         checked=lambda i: options.show_ram),
        pystray.MenuItem("Show VRAM", make_toggle("show_vram"),
                         checked=lambda i: options.show_vram),
        pystray.MenuItem("Show API", make_toggle("show_api"),
                         checked=lambda i: options.show_api),
    )

    menu = pystray.Menu(
        pystray.MenuItem(lambda i: f"Process: {app.proc_name}", None, enabled=False),
        pystray.MenuItem(lambda i: f"Target: {app.cfg.get('target_process') or '(auto)'}",
                         None, enabled=False),
        pystray.MenuItem(lambda i: f"API: {app.api}", None, enabled=False),
        pystray.MenuItem(lambda i: f"Status: {session_status_text(app)}",
                         None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start monitoring", on_start_monitoring,
                         enabled=lambda i: not app.monitoring_enabled),
        pystray.MenuItem("Stop monitoring", on_stop_monitoring,
                         enabled=lambda i: app.monitoring_enabled),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Choose target process...", on_choose_target),
        pystray.MenuItem("Use auto-detect", on_use_auto_detect,
                         checked=lambda i: not (app.cfg.get("target_process") or "").strip()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Options", options_menu),
        pystray.MenuItem("Check for updates now", on_check_updates,
                         enabled=lambda i: not app.update_in_progress),
        pystray.MenuItem("Auto-update on launch", on_toggle_auto_update,
                         checked=lambda i: bool((app.cfg.get("update") or {}).get("check_on_startup", True))),
        pystray.MenuItem("Start with Windows", on_toggle_autostart,
                         checked=lambda i: bool(app.cfg.get("autostart", False))),
        pystray.MenuItem("Reset overlay position", on_reset_position),
        pystray.MenuItem(lambda i: f"Hotkey: {app.hotkey_label}", None, enabled=False),
        pystray.MenuItem("Copyright", on_copyright),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Close", on_quit),
    )
    icon = pystray.Icon("PingOverlay", ICON_RED, "PingOverlay (waiting)", menu)
    icon.default_action = on_click
    return icon


# ---------- Loops ----------
def window_follow_loop(overlay: Overlay, app: AppState):
    """Bám cửa sổ của process hiện tại (lấy PID từ AppState)."""
    local = {"hwnd": None, "pid": None}

    def tick():
        try:
            if app.pid != local["pid"]:
                local["pid"] = app.pid
                local["hwnd"] = None
            if app.pid:
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
            overlay.schedule(WINDOW_POLL_MS, tick)

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
        try:
            if app.warming:
                overlay.set_text(
                    "Đang chờ load lobby và ổn định kết nối...",
                    color="#FFAA00",
                )
            elif not app.monitoring_enabled:
                overlay.set_text("Đang chờ Start...", color="#888888")
            elif not app.active:
                overlay.set_text("Đang chờ game...", color="#888888")
            elif app.ping_state is None:
                overlay.set_text(
                    f"{app.proc_name} đang ở menu — chờ vào match...",
                    color="#FFAA00",
                )
            else:
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
                        f"Ping {lat:.0f}ms" if lat is not None else "Ping n/a"
                    )
                if options.show_loss:
                    parts.append(
                        f"Loss {loss:.0f}%" if loss is not None else "Loss n/a"
                    )
                if options.show_jitter:
                    parts.append(
                        f"Jitter {jitter:.0f}ms" if jitter is not None
                        else "Jitter n/a"
                    )
                if options.show_minmax:
                    if smin is not None and smax is not None:
                        parts.append(f"Min/Max {smin:.0f}/{smax:.0f}ms")
                    else:
                        parts.append("Min/Max -/-")
                if options.show_fps:
                    parts.append(
                        f"FPS {fps_val:.0f}" if fps_val is not None
                        else "FPS n/a"
                    )
                if options.show_low1:
                    parts.append(
                        f"1% Low {low1:.0f}" if low1 is not None
                        else "1% Low n/a"
                    )
                if options.show_frametime:
                    parts.append(
                        f"Frame Time {ftime:.1f}ms" if ftime is not None
                        else "Frame Time n/a"
                    )
                if options.show_ram and mem is not None:
                    parts.append(
                        "RAM " + fmt_ratio_bytes(
                            mem.get("ram_proc_b"), mem.get("ram_total_b")
                        )
                    )
                if options.show_vram and mem is not None:
                    vram_used = mem.get("vram_gpu_b")
                    if vram_used is None:
                        vram_used = mem.get("vram_proc_b")
                    parts.append(
                        "VRAM " + fmt_ratio_bytes(
                            vram_used, mem.get("vram_total_b")
                        )
                    )
                if options.show_api:
                    parts.append(f"API {app.api}")

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
            overlay.set_text(f"Lỗi: {e}", color="#FF5555")
        finally:
            overlay.schedule(DISPLAY_MS, tick)

    tick()


# ---------- Session lifecycle ----------
def start_session(app: AppState, overlay: Overlay, tray: pystray.Icon,
                  pid: int, proc_name: str) -> None:
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

    overlay.root.after(0, overlay.show)
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
        while not stop_ev.is_set() and app.pid == pid:
            attempt += 1
            ips = wait_for_lobby(pid, stop_ev)
            if stop_ev.is_set() or app.pid != pid:
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
            app.warming = False
            app.city = "(waiting net)"
            try:
                tray.title = f"PingOverlay — {proc_name} (waiting net)"
                tray.update_menu()
            except Exception:
                pass
            print(f"[session] warmup attempt {attempt}: no lobby IPs yet, "
                  f"retry in 10s")
            if stop_ev.wait(timeout=10.0):
                return

        if stop_ev.is_set() or app.pid != pid or not lobby_ips:
            return

        city = pick_nearest_city_from_ips(lobby_ips) or "(unknown)"
        if stop_ev.is_set() or app.pid != pid:
            return
        app.city = city
        ping_state = PingState(pid, city)
        app.ping_state = ping_state
        app.warming = False
        threading.Thread(target=ping_state.run, daemon=True).start()
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
    try:
        tray.icon = ICON_RED
        tray.title = ("PingOverlay (waiting for game)"
                      if app.monitoring_enabled
                      else "PingOverlay (paused)")
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
    cfg = app_config.load()
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
    overlay.set_text("Đang chờ Start...", color="#888888")
    overlay.hide()  # khởi động ở trạng thái ẩn; supervisor sẽ bật khi có game

    tray = make_tray_icon(overlay, options, app)
    try:
        tray.title = "PingOverlay (paused)"
    except Exception:
        pass
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
