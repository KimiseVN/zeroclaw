"""OptizNW — Network Optimizer companion for WWM Overlay.

Standalone Tkinter app that diagnoses and tweaks Windows network settings.
Bundled as OptizNW.exe (PyInstaller onefile) alongside PingOverlay.exe.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path


# ── Resource path (frozen vs. dev) ────────────────────────────────────────────
def _res(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / filename


# ── DPI awareness ──────────────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ── Tkinter imports (deferred so headless import still works) ─────────────────
import tkinter as tk
from tkinter import ttk, scrolledtext


# ══════════════════════════════════════════════════════════════════════════════
#  Theme / palette
# ══════════════════════════════════════════════════════════════════════════════
BG          = "#1a1a2e"
BG2         = "#16213e"
BG3         = "#0f3460"
ACCENT      = "#e94560"
ACCENT2     = "#1a8fe3"
FG          = "#e0e0e0"
FG_DIM      = "#8a8a9a"
FG_OK       = "#4caf50"
FG_WARN     = "#ff9800"
FG_ERR      = "#f44336"
FG_INFO     = "#29b6f6"
FG_CMD      = "#80cbc4"
BTN_BG      = "#0f3460"
BTN_BG_HOV  = "#1a8fe3"
BTN_FG      = "#ffffff"
FONT_FAMILY = "Consolas"
FONT_NORM   = (FONT_FAMILY, 10)
FONT_BOLD   = (FONT_FAMILY, 10, "bold")
FONT_SMALL  = (FONT_FAMILY, 9)
FONT_HEAD   = ("Segoe UI", 12, "bold")
FONT_TITLE  = ("Segoe UI", 18, "bold")


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers — run subprocess, return output lines
# ══════════════════════════════════════════════════════════════════════════════
def _run(cmd: list[str], *, timeout: int = 30, decode: str = "utf-8", errors: str = "replace") -> tuple[int, str]:
    """Run *cmd*, return (returncode, stdout+stderr combined)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding=decode,
            errors=errors,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode, out.rstrip()
    except subprocess.TimeoutExpired:
        return -1, f"[Timeout after {timeout}s]"
    except FileNotFoundError:
        return -1, f"[Command not found: {cmd[0]}]"
    except Exception as exc:
        return -1, f"[Error: {exc}]"


def _run_ps(script: str, *, timeout: int = 30) -> tuple[int, str]:
    """Run a PowerShell script string."""
    return _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
    )


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _require_admin(log_fn) -> bool:
    if not _is_admin():
        log_fn("⚠  This operation requires Administrator privileges.", "warn")
        log_fn("   Right-click OptizNW.exe → Run as administrator.", "warn")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  Network diagnostic functions
# ══════════════════════════════════════════════════════════════════════════════

def _diag_basic_connectivity(log) -> None:
    log("── Basic Connectivity ──────────────────────────", "head")
    targets = [("8.8.8.8", "Google DNS"), ("1.1.1.1", "Cloudflare DNS"), ("9.9.9.9", "Quad9")]
    for ip, label in targets:
        rc, out = _run(["ping", "-n", "4", "-w", "1000", ip])
        # Extract avg RTT
        m = re.search(r"Average\s*=\s*(\d+)ms", out, re.IGNORECASE)
        avg = f"{m.group(1)} ms avg" if m else "no reply"
        loss_m = re.search(r"\((\d+)% loss\)", out, re.IGNORECASE)
        loss = loss_m.group(1) + "% loss" if loss_m else "?"
        tag = "ok" if rc == 0 and (not loss_m or loss_m.group(1) == "0") else "err"
        log(f"  {label} ({ip}):  {avg}, {loss}", tag)


def _diag_dns(log) -> None:
    log("── DNS Resolution ──────────────────────────────", "head")
    domains = ["google.com", "wwmoverlay.com", "cloudflare.com"]
    for domain in domains:
        rc, out = _run(["nslookup", domain], timeout=10)
        if rc == 0 and "Address" in out:
            addrs = [l.strip() for l in out.splitlines() if "Address:" in l and not l.strip().startswith("Server:")]
            resolved = addrs[0].replace("Address:", "").strip() if addrs else "resolved"
            log(f"  {domain}  →  {resolved}", "ok")
        else:
            log(f"  {domain}  →  FAILED", "err")

    # Show configured DNS servers
    rc2, dns_out = _run_ps(
        "Get-DnsClientServerAddress -AddressFamily IPv4 | "
        "Where-Object {$_.ServerAddresses} | "
        "Select-Object InterfaceAlias, ServerAddresses | "
        "Format-Table -AutoSize | Out-String"
    )
    if rc2 == 0 and dns_out.strip():
        log("  Configured DNS servers:", "info")
        for line in dns_out.strip().splitlines():
            if line.strip():
                log(f"    {line.strip()}", "cmd")


def _diag_mtu(log) -> None:
    log("── MTU & Packet Loss ───────────────────────────", "head")
    # Probe MTU by sending increasing packet sizes
    mtu_sizes = [1472, 1400, 1300, 1000]  # bytes (ICMP payload = MTU - 28)
    target = "8.8.8.8"
    found_mtu = None
    for size in mtu_sizes:
        rc, out = _run(["ping", "-n", "2", "-f", "-l", str(size), target], timeout=10)
        if rc == 0 and "Reply from" in out:
            found_mtu = size + 28
            break
    if found_mtu:
        log(f"  Effective MTU: ~{found_mtu} bytes", "ok" if found_mtu >= 1500 else "warn")
        if found_mtu < 1500:
            log("  ⚠ MTU below 1500 — may cause fragmentation / VPN issues", "warn")
    else:
        log("  MTU probe inconclusive (firewall may block fragmentation test)", "warn")

    # Packet loss test — 20 pings
    rc, out = _run(["ping", "-n", "20", "-w", "1000", target])
    loss_m = re.search(r"\((\d+)% loss\)", out, re.IGNORECASE)
    loss_pct = int(loss_m.group(1)) if loss_m else -1
    if loss_pct == 0:
        log("  Packet loss: 0%  ✓", "ok")
    elif loss_pct > 0:
        log(f"  Packet loss: {loss_pct}% ⚠", "warn" if loss_pct < 10 else "err")
    else:
        log("  Packet loss: test failed", "err")


def _diag_wifi(log) -> None:
    log("── Wi-Fi Analysis ──────────────────────────────", "head")
    rc, out = _run(["netsh", "wlan", "show", "interfaces"])
    if rc != 0 or "There is no wireless interface" in out or not out.strip():
        log("  No Wi-Fi interface found (wired or Wi-Fi off)", "info")
        return
    for line in out.splitlines():
        line = line.strip()
        if any(k in line for k in ("SSID", "Signal", "Radio type", "Channel", "Receive rate", "Transmit rate", "Authentication")):
            log(f"  {line}", "cmd")

    # Show nearby networks (signal summary)
    rc2, nets = _run(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if rc2 == 0:
        ssid_count = nets.count("SSID")
        log(f"  Nearby networks visible: {ssid_count}", "info")


def _diag_bandwidth_hogs(log) -> None:
    log("── Bandwidth Hogs (top active connections) ─────", "head")
    script = (
        "Get-NetTCPConnection -State Established | "
        "Group-Object OwningProcess | "
        "Sort-Object Count -Descending | "
        "Select-Object -First 10 | ForEach-Object {"
        "  $pid2 = $_.Name; "
        "  try { $pname = (Get-Process -Id $pid2 -EA Stop).ProcessName } catch { $pname = 'PID:'+$pid2 }; "
        "  [PSCustomObject]@{Process=$pname; Connections=$_.Count} "
        "} | Format-Table -AutoSize | Out-String"
    )
    rc, out = _run_ps(script, timeout=20)
    if rc == 0 and out.strip():
        for line in out.strip().splitlines():
            if line.strip():
                log(f"  {line}", "cmd")
    else:
        log("  (Could not enumerate active connections)", "warn")


def _run_full_diagnosis(log) -> None:
    log("═" * 52, "head")
    log("  OptizNW — Full Network Diagnosis", "head")
    log(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}", "info")
    log("═" * 52, "head")
    _diag_basic_connectivity(log)
    log("", None)
    _diag_dns(log)
    log("", None)
    _diag_mtu(log)
    log("", None)
    _diag_wifi(log)
    log("", None)
    _diag_bandwidth_hogs(log)
    log("═" * 52, "head")
    log("  Diagnosis complete.", "ok")


def _run_speed_test(log, *, phase: str = "before") -> dict:
    """Simple speed test using speedtest-cli or fast-cli if available, else raw TCP."""
    log(f"── Speed Test ({phase}) ─────────────────────────", "head")
    # Try speedtest-cli (pip install speedtest-cli)
    rc, out = _run(["speedtest-cli", "--simple"], timeout=60)
    result = {"phase": phase, "raw": out}
    if rc == 0 and "Download" in out:
        for line in out.strip().splitlines():
            log(f"  {line.strip()}", "ok")
        return result

    # Try speedtest (official Ookla CLI)
    rc2, out2 = _run(["speedtest", "--format=human-readable", "--accept-license", "--accept-gdpr"], timeout=60)
    if rc2 == 0 and "Download" in out2:
        for line in out2.strip().splitlines():
            if line.strip():
                log(f"  {line.strip()}", "ok")
        result["raw"] = out2
        return result

    # Fallback: wget/curl timing test
    log("  speedtest-cli not found — running basic latency probe...", "warn")
    log("  Install speedtest-cli: pip install speedtest-cli", "info")
    targets = [("8.8.8.8", "Google"), ("1.1.1.1", "Cloudflare")]
    for ip, label in targets:
        rc3, out3 = _run(["ping", "-n", "10", "-w", "500", ip])
        m = re.search(r"Average\s*=\s*(\d+)ms", out3, re.IGNORECASE)
        avg = f"{m.group(1)} ms" if m else "n/a"
        log(f"  {label} ping avg: {avg}", "cmd")
    result["raw"] = "latency-only"
    return result


def _check_dns_servers(log) -> None:
    log("── DNS Server Check & Recommendation ──────────", "head")
    _diag_dns(log)
    log("  Recommended DNS options:", "info")
    log("    Cloudflare: 1.1.1.1, 1.0.0.1  (fastest, privacy-first)", "cmd")
    log("    Google:     8.8.8.8, 8.8.4.4  (reliable, global)", "cmd")
    log("    Quad9:      9.9.9.9, 149.112.112.112  (filtered, secure)", "cmd")
    log("  To change: Settings → Network → Change Adapter Options → IPv4 Properties", "info")


def _remove_stale_wifi_profiles(log) -> None:
    if not _require_admin(log):
        return
    log("── Remove Stale Wi-Fi Profiles ─────────────────", "head")
    rc, out = _run(["netsh", "wlan", "show", "profiles"])
    if rc != 0:
        log("  Failed to list Wi-Fi profiles", "err")
        return
    # List all profiles
    profiles = re.findall(r"All User Profile\s*:\s*(.+)", out)
    if not profiles:
        log("  No saved Wi-Fi profiles found", "info")
        return
    log(f"  Found {len(profiles)} saved profile(s):", "info")
    for p in profiles:
        log(f"    • {p.strip()}", "cmd")

    # Get currently connected SSID
    rc2, iface_out = _run(["netsh", "wlan", "show", "interfaces"])
    connected_m = re.search(r"\bSSID\s*:\s*(.+)", iface_out)
    connected = connected_m.group(1).strip() if connected_m else ""

    removed = 0
    for profile in profiles:
        profile = profile.strip()
        if profile == connected:
            log(f"  Skipped (active): {profile}", "info")
            continue
        # Check if profile has stored key (if not, it's always stale / public hotspot)
        rc3, detail = _run(["netsh", "wlan", "show", "profile", f"name={profile}"])
        has_key = "Security key" in detail and "Present" in detail
        if not has_key:
            rc4, _ = _run(["netsh", "wlan", "delete", "profile", f"name={profile}"])
            if rc4 == 0:
                log(f"  Removed: {profile}", "ok")
                removed += 1
            else:
                log(f"  Failed to remove: {profile}", "err")

    log(f"  Done — removed {removed} stale profile(s)", "ok")


def _optimize_mdns(log) -> None:
    if not _require_admin(log):
        return
    log("── Optimize mDNS / Link-Local ──────────────────", "head")
    # Disable mDNS resolution on non-domain networks (reduces unnecessary broadcasts)
    script = (
        "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Dnscache\\Parameters' "
        "-Name EnableMDNS -Value 0 -Type DWord -Force 2>&1"
    )
    rc, out = _run_ps(script)
    if rc == 0:
        log("  mDNS broadcasts suppressed (EnableMDNS=0)", "ok")
    else:
        log(f"  EnableMDNS tweak: {out[:120] if out else 'failed'}", "warn")

    # Disable LLMNR (Link-Local Multicast Name Resolution)
    script2 = (
        "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient' "
        "-Name EnableMulticast -Value 0 -Type DWord -Force 2>&1"
    )
    rc2, out2 = _run_ps(script2)
    if rc2 == 0:
        log("  LLMNR multicast disabled (EnableMulticast=0)", "ok")
    else:
        log(f"  LLMNR tweak: {out2[:120] if out2 else 'failed'}", "warn")

    log("  mDNS optimization complete.", "ok")


def _tcp_ip_tweaks(log) -> None:
    if not _require_admin(log):
        return
    log("── TCP/IP Performance Tweaks ───────────────────", "head")
    tweaks = [
        # (description, PowerShell script)
        (
            "Disable TCP auto-tuning (helps some ISPs/VPNs)",
            "netsh int tcp set global autotuninglevel=disabled",
        ),
        (
            "Enable timestamps off (reduces overhead)",
            "netsh int tcp set global timestamps=disabled",
        ),
        (
            "Set ECN capability to disabled (compatibility)",
            "netsh int tcp set global ecncapability=disabled",
        ),
        (
            "Enable RSS (Receive-Side Scaling)",
            "netsh int tcp set global rss=enabled",
        ),
        (
            "Enable chimney offload",
            "netsh int tcp set global chimney=enabled",
        ),
        (
            "Increase TCP send/receive buffer",
            "Set-NetTCPSetting -SettingName InternetCustom -InitialCongestionWindowMss 10 2>&1; exit 0",
        ),
    ]
    for desc, cmd_str in tweaks:
        if cmd_str.startswith("Set-") or cmd_str.startswith("Get-"):
            rc, out = _run_ps(cmd_str)
        else:
            rc, out = _run(cmd_str.split())
        tag = "ok" if rc == 0 else "warn"
        log(f"  {'✓' if rc==0 else '⚠'} {desc}", tag)

    log("  TCP/IP tweaks applied.", "ok")
    log("  Note: Some tweaks require a reboot to take full effect.", "info")


def _flush_dns(log) -> None:
    log("── Flush DNS Cache ─────────────────────────────", "head")
    rc, out = _run(["ipconfig", "/flushdns"])
    if rc == 0:
        log("  DNS Resolver Cache flushed ✓", "ok")
    else:
        log(f"  Flush failed: {out[:120]}", "err")

    # Also flush NetBIOS name cache
    rc2, _ = _run(["nbtstat", "-RR"])
    if rc2 == 0:
        log("  NetBIOS name cache released & refreshed ✓", "ok")


# ══════════════════════════════════════════════════════════════════════════════
#  Main application window
# ══════════════════════════════════════════════════════════════════════════════
class OptizNWApp:
    APP_TITLE   = "OptizNW — Network Optimizer"
    APP_W       = 860
    APP_H       = 680
    COPYRIGHT   = "© 2026 ムKim · WWM Overlay · wwmoverlay.com"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(self.APP_TITLE)
        self.root.geometry(f"{self.APP_W}x{self.APP_H}")
        self.root.minsize(700, 500)
        self.root.configure(bg=BG)
        self._set_icon()
        self._speed_before: dict | None = None
        self._busy = False
        self._build_ui()

    def _set_icon(self) -> None:
        icon_path = _res("optiz-nw.png")
        if icon_path.exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, photo)
                self.root._optiz_icon = photo  # keep reference
            except Exception:
                pass

    # ── UI construction ────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # Pack order matters: top first, then bottom widgets (footer → status bar),
        # then side-fill widgets (button panel, log).  Reversing this order causes
        # Tkinter's pack geometry manager to raise "window isn't packed" errors.
        self._build_title_bar()
        self._build_footer()       # side="bottom" — outermost bottom strip
        self._build_status_bar()   # side="bottom" — sits just above footer
        self._build_button_panel() # side="left"
        self._build_log_area()     # side="left", fill="both", expand=True

    def _build_title_bar(self) -> None:
        bar = tk.Frame(self.root, bg=BG3, height=56)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Icon
        icon_path = _res("optiz-nw.png")
        if icon_path.exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path).resize((36, 36), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(bar, image=photo, bg=BG3)
                lbl.pack(side="left", padx=(12, 6), pady=10)
                lbl._photo = photo
            except Exception:
                pass

        title = tk.Label(
            bar, text=self.APP_TITLE,
            font=FONT_TITLE, fg=FG, bg=BG3, anchor="w",
        )
        title.pack(side="left", pady=10)

        # Admin badge
        admin_text = "● Admin" if _is_admin() else "○ Not Admin"
        admin_color = FG_OK if _is_admin() else FG_WARN
        tk.Label(bar, text=admin_text, font=FONT_SMALL, fg=admin_color, bg=BG3).pack(
            side="right", padx=16, pady=10
        )

    def _btn(self, parent, text: str, cmd, width: int = 22, color: str = BTN_BG) -> tk.Button:
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=color, fg=BTN_FG,
            activebackground=BTN_BG_HOV, activeforeground=BTN_FG,
            relief="flat", bd=0, padx=6, pady=6,
            font=FONT_NORM, width=width, cursor="hand2",
            wraplength=160, justify="left",
        )
        b.bind("<Enter>", lambda e: b.configure(bg=BTN_BG_HOV))
        b.bind("<Leave>", lambda e: b.configure(bg=color))
        return b

    def _build_button_panel(self) -> None:
        panel = tk.Frame(self.root, bg=BG2, width=200)
        panel.pack(side="left", fill="y", padx=0, pady=0)
        panel.pack_propagate(False)

        tk.Label(panel, text="DIAGNOSTICS", font=FONT_SMALL, fg=FG_DIM, bg=BG2).pack(
            anchor="w", padx=12, pady=(14, 2)
        )

        buttons = [
            # (label, command)
            ("🔍 Full Diagnosis",           self._cmd_full_diagnosis),
            ("⚡ Speed Test — Before",      self._cmd_speed_before),
            ("📊 Speed Test — After",       self._cmd_speed_after),
            ("🔬 Before/After Compare",     self._cmd_compare),
            ("🌐 DNS Check",                self._cmd_dns_check),
            ("📦 MTU & Packet Loss",        self._cmd_mtu),
            ("📡 Wi-Fi Analysis",           self._cmd_wifi),
            ("🐛 Bandwidth Hogs",           self._cmd_bandwidth_hogs),
        ]

        for label, cmd in buttons:
            b = self._btn(panel, label, cmd, width=24)
            b.pack(fill="x", padx=8, pady=2)

        ttk.Separator(panel, orient="horizontal").pack(fill="x", padx=8, pady=8)

        tk.Label(panel, text="FIXES", font=FONT_SMALL, fg=FG_DIM, bg=BG2).pack(
            anchor="w", padx=12, pady=(0, 2)
        )

        fixes = [
            ("🧹 Remove Stale Profiles",    self._cmd_remove_profiles),
            ("📻 Optimize mDNS",            self._cmd_mdns),
            ("⚙️  TCP/IP Tweaks",            self._cmd_tcp_tweaks),
            ("🔄 Flush DNS Cache",          self._cmd_flush_dns),
        ]
        for label, cmd in fixes:
            b = self._btn(panel, label, cmd, width=24, color="#1a2a1a")
            b.pack(fill="x", padx=8, pady=2)

        ttk.Separator(panel, orient="horizontal").pack(fill="x", padx=8, pady=8)

        clr = self._btn(panel, "🗑  Clear Log", self._cmd_clear_log, width=24, color="#2a1a1a")
        clr.pack(fill="x", padx=8, pady=2)

    def _build_log_area(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        header = tk.Frame(frame, bg=BG2, height=28)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=" Output Log", font=FONT_SMALL, fg=FG_DIM, bg=BG2, anchor="w").pack(
            side="left", padx=8, pady=4
        )
        self._status_label_top = tk.Label(header, text="Ready", font=FONT_SMALL, fg=FG_DIM, bg=BG2)
        self._status_label_top.pack(side="right", padx=10, pady=4)

        self._log = tk.Text(
            frame,
            bg="#0d0d1a", fg=FG,
            font=FONT_NORM, wrap="word",
            state="disabled", relief="flat", bd=0,
            selectbackground="#1a4a7a", insertbackground=FG,
        )
        self._log.pack(fill="both", expand=True, padx=0, pady=0)

        # Scrollbar
        sb = ttk.Scrollbar(frame, orient="vertical", command=self._log.yview)
        sb.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        self._log.configure(yscrollcommand=sb.set)

        # Tag colors
        self._log.tag_configure("head",  foreground=ACCENT,  font=(FONT_FAMILY, 10, "bold"))
        self._log.tag_configure("ok",    foreground=FG_OK)
        self._log.tag_configure("warn",  foreground=FG_WARN)
        self._log.tag_configure("err",   foreground=FG_ERR)
        self._log.tag_configure("info",  foreground=FG_INFO)
        self._log.tag_configure("cmd",   foreground=FG_CMD)
        self._log.tag_configure("dim",   foreground=FG_DIM)
        self._log.tag_configure("normal", foreground=FG)

        self.log("OptizNW ready.  Select an action from the left panel.", "info")
        self.log("Some fixes require Administrator privileges.", "dim")

    def _build_status_bar(self) -> None:
        self._statusbar = tk.Label(
            self.root, text="Idle", anchor="w",
            bg=BG3, fg=FG_DIM, font=FONT_SMALL,
            relief="flat", bd=0, padx=10,
        )
        self._statusbar.pack(side="bottom", fill="x")

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=BG2, height=26)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        tk.Label(footer, text=self.COPYRIGHT, font=FONT_SMALL, fg=FG_DIM, bg=BG2, anchor="center").pack(
            fill="x", pady=4
        )

    # ── Logging ───────────────────────────────────────────────────────────────
    def log(self, text: str, tag: str | None = "normal") -> None:
        def _write():
            self._log.configure(state="normal")
            self._log.insert("end", text + "\n", tag or "normal")
            self._log.configure(state="disabled")
            self._log.see("end")
        self.root.after(0, _write)

    def _set_status(self, text: str) -> None:
        def _write():
            self._statusbar.configure(text=text)
            self._status_label_top.configure(text=text)
        self.root.after(0, _write)

    # ── Thread runner ─────────────────────────────────────────────────────────
    def _run_task(self, fn, *args) -> None:
        if self._busy:
            self.log("⚠ Another task is running — please wait.", "warn")
            return

        def _worker():
            self._busy = True
            self._set_status("Running…")
            try:
                fn(self.log, *args)
            except Exception as exc:
                self.log(f"[Unhandled error: {exc}]", "err")
            finally:
                self._busy = False
                self._set_status("Done")

        threading.Thread(target=_worker, daemon=True).start()

    # ── Commands ──────────────────────────────────────────────────────────────
    def _cmd_full_diagnosis(self)  -> None: self._run_task(_run_full_diagnosis)
    def _cmd_dns_check(self)       -> None: self._run_task(_check_dns_servers)
    def _cmd_mtu(self)             -> None: self._run_task(_diag_mtu)
    def _cmd_wifi(self)            -> None: self._run_task(_diag_wifi)
    def _cmd_bandwidth_hogs(self)  -> None: self._run_task(_diag_bandwidth_hogs)
    def _cmd_remove_profiles(self) -> None: self._run_task(_remove_stale_wifi_profiles)
    def _cmd_mdns(self)            -> None: self._run_task(_optimize_mdns)
    def _cmd_tcp_tweaks(self)      -> None: self._run_task(_tcp_ip_tweaks)
    def _cmd_flush_dns(self)       -> None: self._run_task(_flush_dns)

    def _cmd_speed_before(self) -> None:
        def _worker(log):
            self._speed_before = _run_speed_test(log, phase="before")
        self._run_task(_worker)

    def _cmd_speed_after(self) -> None:
        def _worker(log):
            _run_speed_test(log, phase="after")
        self._run_task(_worker)

    def _cmd_compare(self) -> None:
        def _worker(log):
            if not self._speed_before:
                log("⚠ Run 'Speed Test — Before' first, then apply tweaks, then run 'Speed Test — After'.", "warn")
                return
            log("── Before / After Comparison ───────────────────", "head")
            log("  BEFORE:", "info")
            for line in (self._speed_before.get("raw") or "").splitlines():
                if line.strip():
                    log(f"    {line.strip()}", "cmd")
            log("  AFTER:  (run Speed Test — After then Compare again)", "info")
        self._run_task(_worker)

    def _cmd_clear_log(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self.log("Log cleared.", "dim")
        self._set_status("Idle")


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    root = tk.Tk()

    # Apply dark theme via ttk
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG2)
    style.configure("TScrollbar", background=BG3, troughcolor=BG2, arrowcolor=FG_DIM)
    style.configure("TSeparator", background=BG3)

    app = OptizNWApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
