"""Portable JSON config for PingOverlay.

Vị trí ưu tiên:
  1. ./config.json — cùng folder với .exe (khi đóng gói) hoặc main.py (khi dev)
  2. %APPDATA%/PingOverlay/config.json — fallback nếu folder cài read-only
     (vd. khi đặt exe ở C:\\Program Files)

Ghi atomic: ghi sang .tmp rồi os.replace -> tránh corrupt khi crash giữa chừng.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


CONFIG_FILENAME = "config.json"
APPDATA_SUBDIR = "PingOverlay"


DEFAULTS: dict[str, Any] = {
    "target_process": "",
    "language": "vi",
    "hotkey": {
        "modifiers": ["ctrl", "shift"],
        "key": "P",
    },
    "autostart": False,
    "update": {
        "enabled": True,
        "check_on_startup": True,
        "auto_install": True,
        "include_prerelease": False,
        "repo": "KimiseVN/zeroclaw",
        "tag_prefix": "ping-overlay-v",
        "asset_prefix": "PingOverlay-v",
        "asset_extension": ".exe",
    },
    "options": {
        "show_ping": True,
        "show_loss": True,
        "show_jitter": False,
        "show_minmax": False,
        "show_fps": True,
        "show_low1": False,
        "show_frametime": False,
        "show_cpu": True,
        "show_cpu_temp": True,
        "show_ram": True,
        "show_vram": True,
        "show_api": True,
    },
    "overlay": {
        "offset_x": 12,
        "offset_y": 8,
        "font_size": 14,
        "padding": 12,
        "corner_radius": 12,
        "glow_radius": 5,
        "bg_alpha": 170,
        "window_alpha": 0.92,
    },
    "theme": {
        # Cyan/Magenta cyberpunk
        "text": "#00E5FF",
        "glow": "#FF00AA",
        "bg_left": "#0A2A3A",
        "bg_right": "#3A0A2A",
    },
}


def _exe_dir() -> Path:
    """Thư mục chứa exe (onefile PyInstaller) hoặc file source khi dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APPDATA_SUBDIR


def _is_writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(folder), prefix=".pcfg_", suffix=".tmp", delete=True
        ):
            pass
        return True
    except Exception:
        return False


def config_path() -> Path:
    """Quyết định path: portable trước, %APPDATA% nếu folder cài read-only."""
    portable = _exe_dir() / CONFIG_FILENAME
    if portable.exists():
        return portable
    if _is_writable(_exe_dir()):
        return portable
    appdata = _appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)
    return appdata / CONFIG_FILENAME


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override vào base, giữ key thiếu của override theo default."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    """Đọc config; trả về dict đã merge với DEFAULTS. Không bao giờ raise."""
    path = config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return copy.deepcopy(DEFAULTS)
        return _deep_merge(DEFAULTS, data)
    except Exception as e:
        print(f"[config] load error ({path}): {e}; using defaults")
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> bool:
    """Ghi atomic. Trả True nếu thành công."""
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[config] save error ({path}): {e}")
        return False


def merged_with_defaults(cfg: dict) -> dict:
    """Đảm bảo cfg có đầy đủ key của DEFAULTS (dùng khi runtime đọc lẻ)."""
    return _deep_merge(DEFAULTS, cfg or {})
