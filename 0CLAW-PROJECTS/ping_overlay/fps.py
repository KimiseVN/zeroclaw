"""Đo FPS của process khác bằng PresentMon (Intel GameTechDev, dựa trên ETW).
KHÔNG inject, KHÔNG hook — chỉ đọc event ETW Present qua subprocess chính thức.
Đây là cách an toàn nhất với anti-cheat (cùng cơ chế CapFrameX, FrameView dùng).
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

PRESENTMON_URL = (
    "https://github.com/GameTechDev/PresentMon/releases/download/"
    "v1.10.0/PresentMon-1.10.0-x64.exe"
)


def _bin_dir() -> Path:
    """Vị trí lưu PresentMon.exe bền vững (không bị xoá khi PyInstaller
    giải nén sang temp). Khi frozen -> %LOCALAPPDATA%\\PingOverlay\\bin,
    khi dev -> ./bin cạnh source.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PingOverlay"
        return base / "bin"
    return Path(__file__).parent / "bin"


BIN_DIR = _bin_dir()
PRESENTMON_EXE = BIN_DIR / "PresentMon.exe"

CREATE_NO_WINDOW = 0x08000000


def _summarize_startup_error(stderr_text: str | None,
                             returncode: int | None) -> str:
    raw = (stderr_text or "").strip()
    low = raw.lower()
    if "access denied" in low or "administrative privileges" in low:
        return "admin_required"
    if raw:
        first = raw.splitlines()[0].strip()
        return f"startup_failed[{returncode}]: {first}"
    return f"startup_failed[{returncode}]"


def ensure_presentmon() -> Path | None:
    """Đảm bảo PresentMon.exe tồn tại ở vị trí bền vững.

    Thứ tự:
    1. Dùng bản đã có trong BIN_DIR.
    2. Nếu đang chạy bản đóng gói và bundle có kèm PresentMon.exe, copy ra BIN_DIR.
    3. Cuối cùng mới tải từ mạng.
    """
    if PRESENTMON_EXE.exists():
        return PRESENTMON_EXE
    try:
        bundled_base = getattr(sys, "_MEIPASS", None)
        if bundled_base:
            bundled = Path(bundled_base) / "bin" / "PresentMon.exe"
            if bundled.exists():
                BIN_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bundled, PRESENTMON_EXE)
                print(f"[fps] Installed bundled PresentMon -> {PRESENTMON_EXE}")
                return PRESENTMON_EXE
    except Exception as e:
        print(f"[fps] Bundled PresentMon install failed: {e}")
    try:
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[fps] Downloading PresentMon -> {PRESENTMON_EXE}")
        urllib.request.urlretrieve(PRESENTMON_URL, PRESENTMON_EXE)
        return PRESENTMON_EXE
    except Exception as e:
        print(f"[fps] Download failed: {e}")
        try:
            if PRESENTMON_EXE.exists():
                PRESENTMON_EXE.unlink()
        except Exception:
            pass
        return None


class FpsMonitor:
    """Spawn PresentMon streaming CSV qua stdout, parse msBetweenPresents.
    Cần quyền Administrator để ETW session hoạt động.
    """

    # Buffer cap đủ cho 240 FPS × 60 s rolling (~14400) + safety margin
    _BUF_MAXLEN = 20000

    def __init__(self, pid: int):
        self.pid = pid
        # Lưu (timestamp_monotonic, ms_between_presents)
        self._samples: deque[tuple[float, float]] = deque(maxlen=self._BUF_MAXLEN)
        self._samples_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = False
        self.error: str | None = None

    def start(self) -> bool:
        exe = ensure_presentmon()
        if not exe:
            self.error = "no_presentmon"
            return False
        try:
            self._proc = subprocess.Popen(
                [str(exe),
                 "-process_id", str(self.pid),
                 "-output_stdout",
                 "-no_top",
                 "-stop_existing_session",
                 "-terminate_on_proc_exit"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            self.error = f"spawn_failed: {e}"
            return False
        time.sleep(0.4)
        if self._proc.poll() is not None:
            try:
                _out, err = self._proc.communicate(timeout=1.0)
            except Exception:
                err = None
            self.error = _summarize_startup_error(err, self._proc.returncode)
            return False
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return True

    def _reader(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        header: list[str] | None = None
        idx_ms: int | None = None
        idx_dropped: int | None = None
        for line in self._proc.stdout:
            if self._stop:
                break
            line = line.strip()
            if not line:
                continue
            if header is None:
                header = [c.strip() for c in line.split(",")]
                try:
                    idx_ms = header.index("msBetweenPresents")
                except ValueError:
                    self.error = "header_missing_msBetweenPresents"
                    return
                try:
                    idx_dropped = header.index("Dropped")
                except ValueError:
                    idx_dropped = None
                continue
            cols = line.split(",")
            if idx_ms is None or idx_ms >= len(cols):
                continue
            if idx_dropped is not None and idx_dropped < len(cols):
                if cols[idx_dropped].strip() in ("1", "TRUE", "True"):
                    continue
            try:
                v = float(cols[idx_ms])
                if v > 0:
                    with self._samples_lock:
                        self._samples.append((time.monotonic(), v))
            except ValueError:
                continue

    def _snapshot_samples(self) -> list[tuple[float, float]]:
        with self._samples_lock:
            return list(self._samples)

    def _frame_times_within(self, window_s: float) -> list[float]:
        samples = self._snapshot_samples()
        if not samples:
            return []
        now = time.monotonic()
        cutoff = now - window_s
        # Snapshot trước rồi mới iterate để tránh race với reader thread.
        out: list[float] = []
        for t, ms in reversed(samples):
            if t < cutoff:
                break
            out.append(ms)
        out.reverse()
        return out

    def fps(self) -> float | None:
        """FPS hiện tại = 1000 / avg_ms của ~120 sample gần nhất."""
        samples = self._snapshot_samples()
        if not samples:
            return None
        recent = [ms for _, ms in samples[-120:]]
        if not recent:
            return None
        avg_ms = sum(recent) / len(recent)
        if avg_ms <= 0:
            return None
        return 1000.0 / avg_ms

    def frame_time_ms(self) -> float | None:
        """Frame time hiện tại (ms) = avg of 30 sample gần nhất."""
        samples = self._snapshot_samples()
        if not samples:
            return None
        recent = [ms for _, ms in samples[-30:]]
        if not recent:
            return None
        return sum(recent) / len(recent)

    def one_percent_low_fps(self, window_s: float = 60.0) -> float | None:
        """1%-low FPS chuẩn HUB/CapFrameX:
        - Lấy frame times trong cửa sổ `window_s` giây gần nhất.
        - Sort giảm dần, lấy 1% LARGEST frame times (= chậm nhất).
        - Trung bình của nhóm đó -> đổi sang FPS = 1000 / avg_ms.
        Cần tối thiểu ~100 sample để có ý nghĩa.
        """
        ts = self._frame_times_within(window_s)
        if len(ts) < 50:
            return None
        ts.sort()  # tăng dần
        n = max(1, int(round(len(ts) * 0.01)))
        worst = ts[-n:]
        avg_ms = sum(worst) / len(worst)
        if avg_ms <= 0:
            return None
        return 1000.0 / avg_ms

    def stop(self) -> None:
        self._stop = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
