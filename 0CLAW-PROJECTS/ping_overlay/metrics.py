"""Metrics monitor: RAM (psutil), VRAM (PDH per-process + DXGI total).

Toàn bộ truy cập GPU vendor-agnostic, KHÔNG dùng nvml/AMD APIs.
- VRAM per-process (primary): `\\GPU Process Memory(pid_<PID>_*)\\Local Usage`
  qua PDH (PdhEnumObjectItemsW + PdhAddCounterW).
- VRAM per-process (fallback): subprocess `typeperf` — cùng counter, cùng
  data Task Manager dùng, robust hơn khi PDH wrapper miss instance trên
  Win11 25H2+ hoặc anti-cheat một phần.
- VRAM total: DXGI `IDXGIFactory::EnumAdapters -> GetDesc.DedicatedVideoMemory`.
- RAM per-process: psutil.Process.memory_info().rss
- RAM total: psutil.virtual_memory().total

Thread-safe đủ cho 1 reader + 1 background updater.
"""
from __future__ import annotations

import csv
import ctypes
import io
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from ctypes import POINTER, Structure, byref, c_size_t, c_void_p, wintypes
from typing import Iterable

import psutil


_CREATE_NO_WINDOW = 0x08000000


# ---------- Rolling window ----------

class RollingWindow:
    """Cửa sổ giá trị có timestamp; tự loại sample quá cũ.
    Không thread-safe — caller phải lock nếu chia sẻ giữa thread.
    """

    def __init__(self, seconds: float):
        self.seconds = float(seconds)
        self._data: deque[tuple[float, float]] = deque()

    def append(self, value: float, t: float | None = None) -> None:
        t = time.monotonic() if t is None else float(t)
        self._data.append((t, float(value)))
        self._evict(t)

    def _evict(self, now: float) -> None:
        cutoff = now - self.seconds
        while self._data and self._data[0][0] < cutoff:
            self._data.popleft()

    def values(self) -> list[float]:
        self._evict(time.monotonic())
        return [v for _, v in self._data]

    def count(self) -> int:
        self._evict(time.monotonic())
        return len(self._data)

    def stddev(self) -> float | None:
        vs = self.values()
        if len(vs) < 2:
            return None
        m = sum(vs) / len(vs)
        return (sum((v - m) ** 2 for v in vs) / len(vs)) ** 0.5

    def avg_bottom_pct(self, pct: float) -> float | None:
        """Trung bình bottom-N% giá trị (đã sort tăng dần).
        Dùng cho 1%-low frame time = avg of largest 1% frame times.
        Chú ý: caller chọn metric (frame time max -> 1% low fps).
        """
        vs = sorted(self.values())
        if not vs:
            return None
        n = max(1, int(round(len(vs) * pct)))
        return sum(vs[:n]) / n

    def avg_top_pct(self, pct: float) -> float | None:
        vs = sorted(self.values())
        if not vs:
            return None
        n = max(1, int(round(len(vs) * pct)))
        return sum(vs[-n:]) / n


# ---------- Win32 GUID helper ----------

class _GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _make_guid(s: str) -> _GUID:
    u = uuid.UUID(s)
    g = _GUID()
    ctypes.memmove(byref(g), u.bytes_le, 16)
    return g


# ---------- DXGI total VRAM ----------

class _DXGI_ADAPTER_DESC(Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128),
        ("VendorId", wintypes.UINT),
        ("DeviceId", wintypes.UINT),
        ("SubSysId", wintypes.UINT),
        ("Revision", wintypes.UINT),
        ("DedicatedVideoMemory", c_size_t),
        ("DedicatedSystemMemory", c_size_t),
        ("SharedSystemMemory", c_size_t),
        ("AdapterLuid_Low", wintypes.DWORD),
        ("AdapterLuid_High", wintypes.LONG),
    ]


# IID_IDXGIFactory: 7B7166EC-21C7-44AE-B21A-C9AE321AE369
_IID_IDXGIFactory = "7B7166EC-21C7-44AE-B21A-C9AE321AE369"
_VENDOR_MS_BASIC_RENDER = 0x1414  # Microsoft Basic Render Driver — bỏ qua

_HRESULT = ctypes.c_long


def _format_luid(high: int, low: int) -> str:
    return f"luid_0x{(high & 0xFFFFFFFF):08x}_0x{(low & 0xFFFFFFFF):08x}"


def _extract_luid(instance_name: str) -> str | None:
    m = re.search(r"(luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)", instance_name or "")
    return m.group(1).lower() if m else None


def total_vram_bytes() -> int | None:
    """Tổng VRAM dedicated của TẤT CẢ adapter (trừ Microsoft Basic Render).
    Trả None nếu DXGI không khởi tạo được.
    """
    return total_vram_bytes_for_luids()


def _dxgi_adapter_info_map() -> dict[str, dict[str, int | str]]:
    """Map adapter LUID -> metadata dùng để khớp với perf counters."""
    try:
        dxgi = ctypes.windll.dxgi
    except OSError:
        return {}
    try:
        CreateDXGIFactory = dxgi.CreateDXGIFactory
        CreateDXGIFactory.restype = _HRESULT
        CreateDXGIFactory.argtypes = [POINTER(_GUID), POINTER(c_void_p)]

        factory = c_void_p()
        iid = _make_guid(_IID_IDXGIFactory)
        hr = CreateDXGIFactory(byref(iid), byref(factory))
        if hr != 0 or not factory.value:
            return {}

        # vtable[2] = Release, vtable[7] = EnumAdapters (IDXGIFactory)
        f_vt = ctypes.cast(factory, POINTER(c_void_p))[0]
        f_vt_arr = ctypes.cast(f_vt, POINTER(c_void_p * 12))[0]

        EnumAdaptersFn = ctypes.WINFUNCTYPE(
            _HRESULT, c_void_p, wintypes.UINT, POINTER(c_void_p)
        )
        ReleaseFn = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
        enum_adapters = EnumAdaptersFn(f_vt_arr[7])
        release_factory = ReleaseFn(f_vt_arr[2])

        out: dict[str, dict[str, int | str]] = {}
        try:
            i = 0
            while True:
                adapter = c_void_p()
                hr2 = enum_adapters(factory, i, byref(adapter))
                if hr2 != 0 or not adapter.value:
                    break
                # IDXGIAdapter vtable[2]=Release, [8]=GetDesc
                a_vt = ctypes.cast(adapter, POINTER(c_void_p))[0]
                a_vt_arr = ctypes.cast(a_vt, POINTER(c_void_p * 16))[0]
                GetDescFn = ctypes.WINFUNCTYPE(
                    _HRESULT, c_void_p, POINTER(_DXGI_ADAPTER_DESC)
                )
                get_desc = GetDescFn(a_vt_arr[8])
                a_release = ReleaseFn(a_vt_arr[2])

                desc = _DXGI_ADAPTER_DESC()
                hr3 = get_desc(adapter, byref(desc))
                if hr3 == 0 and desc.VendorId != _VENDOR_MS_BASIC_RENDER:
                    luid_key = _format_luid(desc.AdapterLuid_High, desc.AdapterLuid_Low).lower()
                    out[luid_key] = {
                        "index": i,
                        "dedicated_bytes": int(desc.DedicatedVideoMemory),
                        "description": str(desc.Description or "").strip(),
                    }
                try:
                    a_release(adapter)
                except Exception:
                    pass
                i += 1
        finally:
            try:
                release_factory(factory)
            except Exception:
                pass

        return out
    except Exception as e:
        print(f"[metrics] DXGI total_vram failed: {e}")
        return {}


def total_vram_bytes_for_luids(luids: Iterable[str] | None = None) -> int | None:
    """Tổng dedicated VRAM của một hay nhiều adapter LUID."""
    adapter_map = _dxgi_adapter_info_map()
    if not adapter_map:
        return None
    if luids is None:
        total = sum(int(info["dedicated_bytes"]) for info in adapter_map.values())
        return total or None
    wanted = {str(v).strip().lower() for v in luids if str(v).strip()}
    if not wanted:
        return None
    total = sum(
        int(info["dedicated_bytes"])
        for luid, info in adapter_map.items()
        if luid in wanted
    )
    return total or None


# ---------- PDH per-process VRAM ----------

# PDH constants (winperf.h / pdh.h)
_PDH_FMT_LARGE = 0x00000400
_PDH_MORE_DATA = 0x800007D2
_ERROR_SUCCESS = 0


class _PDH_FMT_COUNTERVALUE_LARGE(Structure):
    _fields_ = [
        ("CStatus", wintypes.DWORD),
        ("largeValue", ctypes.c_longlong),
    ]


def _english_perflib_index(english_name: str) -> int | None:
    """Đọc HKLM\\...\\Perflib\\009\\Counter (REG_MULTI_SZ list of
    [index, name, index, name, ...]) tìm index theo tên English. Key 009
    luôn tồn tại trên mọi locale Windows.
    """
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Perflib\009",
            0, winreg.KEY_READ,
        ) as k:
            data, typ = winreg.QueryValueEx(k, "Counter")
        if not isinstance(data, list):
            return None
        target = english_name.strip().lower()
        i = 0
        while i + 1 < len(data):
            try:
                idx = int(data[i])
            except (ValueError, TypeError):
                i += 2
                continue
            name = (data[i + 1] or "").strip().lower()
            if name == target:
                return idx
            i += 2
    except Exception:
        return None
    return None


def _localize_perf_name(english_name: str) -> str | None:
    """Dịch English perf name sang tên hiển thị của locale hiện tại
    qua PdhLookupPerfNameByIndexW. Trả None nếu không tìm thấy."""
    idx = _english_perflib_index(english_name)
    if idx is None:
        return None
    try:
        pdh = ctypes.windll.pdh
    except OSError:
        return None
    try:
        size = wintypes.DWORD(0)
        rc = pdh.PdhLookupPerfNameByIndexW(None, idx, None, byref(size))
        if rc not in (_ERROR_SUCCESS, _PDH_MORE_DATA):
            return None
        if size.value == 0:
            return None
        buf = ctypes.create_unicode_buffer(size.value + 1)
        size.value = size.value + 1
        rc = pdh.PdhLookupPerfNameByIndexW(None, idx, buf, byref(size))
        if rc != _ERROR_SUCCESS:
            return None
        return buf.value or None
    except Exception:
        return None


class GpuProcessVramQuery:
    """PDH query đọc tổng VRAM dedicated (Local Usage) của 1 PID.

    Counter category: `GPU Process Memory`
    Instance pattern: `pid_<PID>_*` (Windows tạo nhiều instance/process,
    mỗi LUID + physical adapter một instance) -> phải sum tất cả.
    Counter: `Local Usage` (VRAM dedicated, byte).
    """

    def __init__(self, pid: int):
        self.pid = int(pid)
        self._pdh = None
        self._query: c_void_p | None = None
        self._counters: list[tuple[c_void_p, str]] = []
        self._lock = threading.Lock()
        self._error: str | None = None
        self._last_expand: float = 0.0
        self._matched_instances: list[str] = []
        self._matched_luids: set[str] = set()
        self._primary_luid: str | None = None

    def open(self) -> bool:
        try:
            self._pdh = ctypes.windll.pdh
        except OSError as e:
            self._error = f"pdh.dll missing: {e}"
            return False
        try:
            q = c_void_p()
            self._pdh.PdhOpenQueryW.argtypes = [
                wintypes.LPCWSTR, ctypes.c_void_p, POINTER(c_void_p)
            ]
            self._pdh.PdhOpenQueryW.restype = ctypes.c_long
            rc = self._pdh.PdhOpenQueryW(None, 0, byref(q))
            if rc != _ERROR_SUCCESS:
                self._error = f"PdhOpenQueryW rc={rc:#x}"
                return False
            self._query = q
        except Exception as e:
            self._error = f"open exception: {e}"
            return False
        return self._refresh_counters()

    def _expand_paths(self, pattern: str) -> list[str]:
        if self._pdh is None:
            return []
        size = wintypes.DWORD(0)
        # Truy vấn buffer size
        rc = self._pdh.PdhExpandWildCardPathW(
            None, pattern, None, byref(size), 0
        )
        if rc not in (_ERROR_SUCCESS, _PDH_MORE_DATA) or size.value == 0:
            return []
        buf = ctypes.create_unicode_buffer(size.value)
        rc = self._pdh.PdhExpandWildCardPathW(
            None, pattern, buf, byref(size), 0
        )
        if rc != _ERROR_SUCCESS:
            return []
        # multi-string: null-separated, double-null terminated
        raw = ctypes.string_at(buf, size.value * 2)
        text = raw.decode("utf-16-le", errors="ignore")
        return [s for s in text.split("\x00") if s]

    def _enum_instances(self, object_name: str) -> list[str]:
        """PdhEnumObjectItemsW: list trực tiếp instance (vd. pid_X_luid_..._phys_..)
        cho object 'GPU Process Memory'. Cách này robust hơn wildcard expand
        trên Win11 (build 22H2+) vì wildcard syntax có thể thay đổi.
        """
        if self._pdh is None:
            return []
        # PERF_DETAIL_WIZARD = 400 (chi tiết nhất)
        try:
            self._pdh.PdhEnumObjectItemsW.argtypes = [
                wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                ctypes.c_void_p, POINTER(wintypes.DWORD),
                ctypes.c_void_p, POINTER(wintypes.DWORD),
                wintypes.DWORD, wintypes.DWORD,
            ]
            self._pdh.PdhEnumObjectItemsW.restype = ctypes.c_long
        except Exception:
            return []
        counters_size = wintypes.DWORD(0)
        instances_size = wintypes.DWORD(0)
        rc = self._pdh.PdhEnumObjectItemsW(
            None, None, object_name,
            None, byref(counters_size),
            None, byref(instances_size),
            400, 0,
        )
        if rc != _PDH_MORE_DATA or instances_size.value <= 1:
            return []
        cbuf = ctypes.create_unicode_buffer(max(1, counters_size.value))
        ibuf = ctypes.create_unicode_buffer(instances_size.value)
        rc = self._pdh.PdhEnumObjectItemsW(
            None, None, object_name,
            cbuf, byref(counters_size),
            ibuf, byref(instances_size),
            400, 0,
        )
        if rc != _ERROR_SUCCESS:
            return []
        raw = ctypes.string_at(ibuf, instances_size.value * 2)
        text = raw.decode("utf-16-le", errors="ignore")
        return [s for s in text.split("\x00") if s]

    def _candidate_object_names(self) -> list[str]:
        """English trước rồi localized fallback (Vietnamese Windows etc.)."""
        names = ["GPU Process Memory"]
        loc = _localize_perf_name("GPU Process Memory")
        if loc and loc not in names:
            names.append(loc)
        return names

    def _candidate_counter_names(self) -> list[str]:
        names = ["Dedicated Usage", "Local Usage"]
        loc = _localize_perf_name("Dedicated Usage")
        if loc and loc not in names:
            names.append(loc)
        loc2 = _localize_perf_name("Local Usage")
        if loc2 and loc2 not in names:
            names.append(loc2)
        return names

    def _refresh_counters(self) -> bool:
        """Liệt kê instance trực tiếp + filter theo PID prefix. Win10/11 OK.
        Retry mỗi 5s từ vram_bytes() nếu chưa có instance."""
        if self._pdh is None or self._query is None:
            return False
        prefix = f"pid_{self.pid}_"
        used_obj: str | None = None
        used_ctr: str | None = None
        matched: list[str] = []
        for obj_name in self._candidate_object_names():
            instances = self._enum_instances(obj_name)
            if not instances:
                continue
            matched = [i for i in instances if i.startswith(prefix)]
            if matched:
                used_obj = obj_name
                # Pick first available counter that exists for this object
                for ctr_name in self._candidate_counter_names():
                    used_ctr = ctr_name
                    break
                break

        if not matched or not used_obj or not used_ctr:
            # Diagnostic: cho biết object nào hiện diện trên máy
            available_objects: list[str] = []
            for obj_name in self._candidate_object_names():
                if self._enum_instances(obj_name):
                    available_objects.append(obj_name)
            self._error = (
                f"no PDH instances for pid {self.pid} "
                f"(tried objects={self._candidate_object_names()}, "
                f"matched_objects={available_objects}; retry every 5s)"
            )
            self._matched_instances = []
            self._matched_luids = set()
            self._primary_luid = None
            return False

        paths = [f"\\{used_obj}({inst})\\{used_ctr}" for inst in matched]
        # Path đã chứa name LOCALIZED -> phải dùng PdhAddCounterW (không phải
        # PdhAddEnglishCounterW vì English variant chỉ accept English names).
        self._counters = []
        try:
            self._pdh.PdhAddCounterW.argtypes = [
                c_void_p, wintypes.LPCWSTR, ctypes.c_void_p, POINTER(c_void_p)
            ]
            self._pdh.PdhAddCounterW.restype = ctypes.c_long
        except Exception:
            return False
        for p in paths:
            h = c_void_p()
            rc = self._pdh.PdhAddCounterW(self._query, p, 0, byref(h))
            if rc == _ERROR_SUCCESS and h.value:
                inst = matched[len(self._counters)]
                self._counters.append((h, inst))
        if not self._counters:
            self._error = f"PdhAddCounterW failed for all {len(paths)} path(s)"
            self._matched_instances = []
            self._matched_luids = set()
            self._primary_luid = None
            return False
        self._last_expand = time.monotonic()
        self._error = None
        self._matched_instances = list(matched)
        self._matched_luids = {
            luid for inst in matched
            for luid in [_extract_luid(inst)]
            if luid
        }
        self._primary_luid = None
        print(f"[metrics] PDH ready: {len(self._counters)} instance(s) "
              f"for pid {self.pid} (object='{used_obj}' counter='{used_ctr}')")
        return True

    def vram_bytes(self) -> int | None:
        """Tổng VRAM dedicated của PID hiện tại (Local Usage), đơn vị byte.
        Tự refresh wildcard mỗi 5s.
        """
        if self._pdh is None or self._query is None:
            return None
        try:
            now = time.monotonic()
            if now - self._last_expand > 5.0 or not self._counters:
                self._refresh_counters()
            if not self._counters:
                return None
            self._pdh.PdhCollectQueryData.argtypes = [c_void_p]
            self._pdh.PdhCollectQueryData.restype = ctypes.c_long
            rc = self._pdh.PdhCollectQueryData(self._query)
            if rc != _ERROR_SUCCESS:
                return None
            total = 0
            self._pdh.PdhGetFormattedCounterValue.argtypes = [
                c_void_p, wintypes.DWORD, POINTER(wintypes.DWORD),
                POINTER(_PDH_FMT_COUNTERVALUE_LARGE),
            ]
            self._pdh.PdhGetFormattedCounterValue.restype = ctypes.c_long
            per_luid: dict[str, int] = {}
            for h, inst in self._counters:
                v = _PDH_FMT_COUNTERVALUE_LARGE()
                rc = self._pdh.PdhGetFormattedCounterValue(
                    h, _PDH_FMT_LARGE, None, byref(v)
                )
                if rc == _ERROR_SUCCESS and v.CStatus == 0:
                    value = int(v.largeValue)
                    total += value
                    luid = _extract_luid(inst)
                    if luid:
                        per_luid[luid] = per_luid.get(luid, 0) + value
            if per_luid:
                self._primary_luid = max(per_luid.items(), key=lambda kv: kv[1])[0]
            return total or None
        except Exception as e:
            self._error = f"collect exception: {e}"
            return None

    def close(self) -> None:
        if self._pdh is None or self._query is None:
            return
        try:
            self._pdh.PdhCloseQuery.argtypes = [c_void_p]
            self._pdh.PdhCloseQuery.restype = ctypes.c_long
            self._pdh.PdhCloseQuery(self._query)
        except Exception:
            pass
        self._query = None
        self._counters = []

    def primary_luid(self) -> str | None:
        return self._primary_luid


class GpuLocalAdapterQuery:
    """Đọc Dedicated GPU memory usage của adapter qua counter adapter-level.
    Đây là số gần với Performance tab của Task Manager hơn so với per-process.
    """

    def __init__(self):
        self._pdh = None
        self._query: c_void_p | None = None
        self._counters: list[c_void_p] = []
        self._last_expand: float = 0.0
        self._error: str | None = None
        self._target_luids: tuple[str, ...] = ()

    def open(self) -> bool:
        try:
            self._pdh = ctypes.windll.pdh
        except OSError as e:
            self._error = f"pdh.dll missing: {e}"
            return False
        try:
            q = c_void_p()
            self._pdh.PdhOpenQueryW.argtypes = [
                wintypes.LPCWSTR, ctypes.c_void_p, POINTER(c_void_p)
            ]
            self._pdh.PdhOpenQueryW.restype = ctypes.c_long
            rc = self._pdh.PdhOpenQueryW(None, 0, byref(q))
            if rc != _ERROR_SUCCESS:
                self._error = f"PdhOpenQueryW rc={rc:#x}"
                return False
            self._query = q
            return True
        except Exception as e:
            self._error = f"open exception: {e}"
            return False

    def _candidate_object_names(self) -> list[str]:
        names = ["GPU Local Adapter Memory"]
        loc = _localize_perf_name("GPU Local Adapter Memory")
        if loc and loc not in names:
            names.append(loc)
        return names

    def _candidate_counter_names(self) -> list[str]:
        names = ["Local Usage"]
        loc = _localize_perf_name("Local Usage")
        if loc and loc not in names:
            names.append(loc)
        return names

    def _enum_instances(self, object_name: str) -> list[str]:
        if self._pdh is None:
            return []
        try:
            self._pdh.PdhEnumObjectItemsW.argtypes = [
                wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                ctypes.c_void_p, POINTER(wintypes.DWORD),
                ctypes.c_void_p, POINTER(wintypes.DWORD),
                wintypes.DWORD, wintypes.DWORD,
            ]
            self._pdh.PdhEnumObjectItemsW.restype = ctypes.c_long
        except Exception:
            return []
        counters_size = wintypes.DWORD(0)
        instances_size = wintypes.DWORD(0)
        rc = self._pdh.PdhEnumObjectItemsW(
            None, None, object_name,
            None, byref(counters_size),
            None, byref(instances_size),
            400, 0,
        )
        if rc != _PDH_MORE_DATA or instances_size.value <= 1:
            return []
        cbuf = ctypes.create_unicode_buffer(max(1, counters_size.value))
        ibuf = ctypes.create_unicode_buffer(instances_size.value)
        rc = self._pdh.PdhEnumObjectItemsW(
            None, None, object_name,
            cbuf, byref(counters_size),
            ibuf, byref(instances_size),
            400, 0,
        )
        if rc != _ERROR_SUCCESS:
            return []
        raw = ctypes.string_at(ibuf, instances_size.value * 2)
        text = raw.decode("utf-16-le", errors="ignore")
        return [s for s in text.split("\x00") if s]

    def set_target_luids(self, luids: Iterable[str]) -> None:
        normalized = tuple(sorted({str(v).strip().lower() for v in luids if str(v).strip()}))
        if normalized != self._target_luids:
            self._target_luids = normalized
            self._counters = []
            self._last_expand = 0.0

    def _refresh_counters(self) -> bool:
        if self._pdh is None or self._query is None or not self._target_luids:
            return False
        matched: list[str] = []
        used_obj: str | None = None
        used_ctr: str | None = None
        for obj_name in self._candidate_object_names():
            instances = self._enum_instances(obj_name)
            if not instances:
                continue
            matched = [
                inst for inst in instances
                if (_extract_luid(inst) or "") in self._target_luids
            ]
            if matched:
                used_obj = obj_name
                used_ctr = self._candidate_counter_names()[0]
                break
        if not matched or not used_obj or not used_ctr:
            self._error = f"no adapter instances for luids={self._target_luids}"
            self._counters = []
            return False
        self._counters = []
        try:
            self._pdh.PdhAddCounterW.argtypes = [
                c_void_p, wintypes.LPCWSTR, ctypes.c_void_p, POINTER(c_void_p)
            ]
            self._pdh.PdhAddCounterW.restype = ctypes.c_long
        except Exception:
            return False
        for inst in matched:
            path = f"\\{used_obj}({inst})\\{used_ctr}"
            h = c_void_p()
            rc = self._pdh.PdhAddCounterW(self._query, path, 0, byref(h))
            if rc == _ERROR_SUCCESS and h.value:
                self._counters.append(h)
        self._last_expand = time.monotonic()
        self._error = None
        return bool(self._counters)

    def local_usage_bytes(self) -> int | None:
        if self._pdh is None or self._query is None or not self._target_luids:
            return None
        try:
            now = time.monotonic()
            if now - self._last_expand > 5.0 or not self._counters:
                self._refresh_counters()
            if not self._counters:
                return None
            self._pdh.PdhCollectQueryData.argtypes = [c_void_p]
            self._pdh.PdhCollectQueryData.restype = ctypes.c_long
            rc = self._pdh.PdhCollectQueryData(self._query)
            if rc != _ERROR_SUCCESS:
                return None
            self._pdh.PdhGetFormattedCounterValue.argtypes = [
                c_void_p, wintypes.DWORD, POINTER(wintypes.DWORD),
                POINTER(_PDH_FMT_COUNTERVALUE_LARGE),
            ]
            self._pdh.PdhGetFormattedCounterValue.restype = ctypes.c_long
            total = 0
            for h in self._counters:
                v = _PDH_FMT_COUNTERVALUE_LARGE()
                rc = self._pdh.PdhGetFormattedCounterValue(
                    h, _PDH_FMT_LARGE, None, byref(v)
                )
                if rc == _ERROR_SUCCESS and v.CStatus == 0:
                    total += int(v.largeValue)
            return total or None
        except Exception as e:
            self._error = f"collect exception: {e}"
            return None

    def close(self) -> None:
        if self._pdh is None or self._query is None:
            return
        try:
            self._pdh.PdhCloseQuery.argtypes = [c_void_p]
            self._pdh.PdhCloseQuery.restype = ctypes.c_long
            self._pdh.PdhCloseQuery(self._query)
        except Exception:
            pass
        self._query = None
        self._counters = []


# ---------- typeperf fallback (subprocess) ----------

def _query_vram_typeperf_details(pid: int,
                                 timeout_s: float = 6.0) -> tuple[int | None, str | None]:
    """Lấy Dedicated Usage của process qua `typeperf`.

    Trả `(total_bytes, primary_luid)` để caller vừa có thể hiển thị VRAM
    per-process, vừa map sang adapter-level counter giống Task Manager.
    """
    counter = f"\\GPU Process Memory(pid_{pid}_*)\\Dedicated Usage"
    try:
        proc = subprocess.run(
            ["typeperf", counter, "-sc", "1", "-y"],
            capture_output=True, text=True, timeout=timeout_s,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        return None, None
    out = proc.stdout or ""
    if not out:
        return None, None
    # Format CSV của typeperf:
    # "(PDH-CSV 4.0)","\\HOST\GPU...inst1\Dedicated Usage","\\HOST\GPU...inst2\Dedicated Usage"
    # "MM/DD/YYYY HH:MM:SS.fff","value1","value2"
    # Exiting...
    lines = [l for l in out.splitlines() if l.strip()]
    header_row: str | None = None
    data_row: str | None = None
    for ln in lines:
        if not ln.startswith('"'):
            continue
        if "PDH-CSV" in ln:
            header_row = ln
            continue
        if header_row is not None:
            data_row = ln
            break
    if not header_row or not data_row:
        return None, None
    try:
        header = next(csv.reader(io.StringIO(header_row)), [])
        row = next(csv.reader(io.StringIO(data_row)), [])
    except Exception:
        return None, None
    if len(row) < 2 or len(header) < 2:
        return None, None
    total = 0.0
    valid = 0
    per_luid: dict[str, float] = {}
    n = min(len(header), len(row))
    for i in range(1, n):
        path = header[i]
        v = row[i]
        try:
            value = float(v)
        except (ValueError, TypeError):
            continue
        total += value
        valid += 1
        luid = _extract_luid(path)
        if luid:
            per_luid[luid] = per_luid.get(luid, 0.0) + value
    if valid == 0 or total <= 0:
        return None, None
    primary_luid = None
    if per_luid:
        primary_luid = max(per_luid.items(), key=lambda kv: kv[1])[0]
    return int(total), primary_luid


def _query_vram_typeperf(pid: int, timeout_s: float = 6.0) -> int | None:
    total, _primary_luid = _query_vram_typeperf_details(pid, timeout_s)
    return total


def _diagnose_gpu_counters(timeout_s: float = 5.0) -> str:
    """Liệt kê instance Windows đang expose dưới object 'GPU Process Memory'
    qua `typeperf -qx`. Dùng để debug: nếu wwm.exe pid không xuất hiện thì
    có thể bị anti-cheat ẩn hoặc driver version cũ.
    """
    try:
        proc = subprocess.run(
            ["typeperf", "-qx", "GPU Process Memory"],
            capture_output=True, text=True, timeout=timeout_s,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as e:
        return f"(typeperf -qx failed: {e})"
    return proc.stdout or "(empty)"


# ---------- High-level monitor ----------

class MemoryMonitor:
    """Tổng hợp RAM/VRAM cho 1 PID. Cache snapshot theo nhịp poll riêng."""

    def __init__(self, pid: int, poll_sec: float = 1.0):
        self.pid = int(pid)
        self.poll_sec = float(poll_sec)
        self._proc: psutil.Process | None = None
        self._vram = GpuProcessVramQuery(pid)
        self._adapter_vram = GpuLocalAdapterQuery()
        self._stop = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snap: dict[str, float | None] = {
            "ram_proc_b": None, "ram_total_b": None,
            "vram_proc_b": None, "vram_total_b": None,
            "vram_gpu_b": None,
        }
        self._total_vram_cached: int | None = None
        # typeperf fallback state
        self._typeperf_last_call: float = 0.0
        self._typeperf_value: int | None = None
        self._typeperf_logged_ok: bool = False
        self._typeperf_min_interval_s: float = 5.0
        self._typeperf_primary_luid: str | None = None
        # Diagnostic state
        self._first_seen: float = time.monotonic()
        self._diagnose_dumped: bool = False
        self._logged_adapter_total: bool = False

    def start(self) -> bool:
        try:
            self._proc = psutil.Process(self.pid)
        except Exception as e:
            print(f"[metrics] psutil.Process({self.pid}) failed: {e}")
            return False
        # VRAM total: cache 1 lần (không đổi runtime)
        self._total_vram_cached = total_vram_bytes()
        if not self._adapter_vram.open():
            print(f"[metrics] adapter VRAM init: {self._adapter_vram._error}")
        # PDH per-process VRAM: cố mở; nếu chưa có instance vẫn cho RAM chạy,
        # vram_bytes() sẽ tự retry mỗi 5s tới khi GPU instance xuất hiện.
        if not self._vram.open():
            print(f"[metrics] PDH init: {self._vram._error}")
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="MemoryMonitor"
        )
        self._thread.start()
        return True

    def _loop(self) -> None:
        ram_total = psutil.virtual_memory().total
        while not self._stop:
            ram_proc: int | None = None
            try:
                if self._proc and self._proc.is_running():
                    ram_proc = int(self._proc.memory_info().rss)
            except Exception:
                ram_proc = None

            # Primary VRAM path: PDH (nhanh, in-process)
            vram_proc = self._vram.vram_bytes()
            primary_luid = self._vram.primary_luid()
            vram_gpu: int | None = None
            if primary_luid:
                self._adapter_vram.set_target_luids([primary_luid])
                vram_gpu = self._adapter_vram.local_usage_bytes()
                active_total = total_vram_bytes_for_luids([primary_luid])
                if active_total:
                    self._total_vram_cached = active_total
                    if not self._logged_adapter_total:
                        self._logged_adapter_total = True
                        print("[metrics] VRAM total mapped to active adapter: "
                              f"{primary_luid} -> {active_total / 1024 / 1024 / 1024:.1f} GB")

            # Fallback typeperf khi PDH miss — throttle 5s/lần (tốn 100-300ms)
            if vram_proc is None:
                now = time.monotonic()
                if now - self._typeperf_last_call >= self._typeperf_min_interval_s:
                    self._typeperf_last_call = now
                    val, typeperf_luid = _query_vram_typeperf_details(self.pid)
                    if val is not None:
                        self._typeperf_value = val
                        self._typeperf_primary_luid = typeperf_luid
                        if not self._typeperf_logged_ok:
                            self._typeperf_logged_ok = True
                            print(f"[metrics] VRAM via typeperf fallback "
                                  f"(pid {self.pid}): {val / 1024 / 1024:.0f} MB")
                # Dùng giá trị typeperf cached (cho tới poll typeperf tiếp theo)
                vram_proc = self._typeperf_value
                if primary_luid is None and self._typeperf_primary_luid:
                    primary_luid = self._typeperf_primary_luid
                    self._adapter_vram.set_target_luids([primary_luid])
                    vram_gpu = self._adapter_vram.local_usage_bytes()
                    active_total = total_vram_bytes_for_luids([primary_luid])
                    if active_total:
                        self._total_vram_cached = active_total
                        if not self._logged_adapter_total:
                            self._logged_adapter_total = True
                            print("[metrics] VRAM total mapped via typeperf fallback: "
                                  f"{primary_luid} -> {active_total / 1024 / 1024 / 1024:.1f} GB")

            # Diagnostic: cả PDH lẫn typeperf vẫn miss sau 30s -> dump 1 lần
            if (vram_proc is None
                    and not self._diagnose_dumped
                    and time.monotonic() - self._first_seen > 30.0):
                self._diagnose_dumped = True
                print(f"[metrics] VRAM unavailable cho pid {self.pid} sau 30s. "
                      f"PDH error: {self._vram._error}")
                dump = _diagnose_gpu_counters()
                if dump:
                    # Chỉ log dòng có pid_<self.pid>_ + 5 dòng đầu để gọn
                    matches = [ln for ln in dump.splitlines()
                               if f"pid_{self.pid}_" in ln]
                    print(f"[metrics] typeperf -qx 'GPU Process Memory' "
                          f"matched_for_pid={len(matches)} sample_lines:")
                    for ln in (matches[:5] or dump.splitlines()[:5]):
                        print(f"    {ln.strip()}")
                    print("[metrics] (nếu pid_<PID>_ không xuất hiện -> "
                          "anti-cheat đang block GPU performance counter "
                          "cho process này; VRAM sẽ không thể hiện)")

            with self._lock:
                self._snap["ram_proc_b"] = ram_proc
                self._snap["ram_total_b"] = ram_total
                self._snap["vram_proc_b"] = vram_proc
                self._snap["vram_gpu_b"] = vram_gpu
                self._snap["vram_total_b"] = self._total_vram_cached
            time.sleep(self.poll_sec)

    def snapshot(self) -> dict[str, float | None]:
        with self._lock:
            return dict(self._snap)

    def stop(self) -> None:
        self._stop = True
        try:
            self._vram.close()
        except Exception:
            pass
        try:
            self._adapter_vram.close()
        except Exception:
            pass


# ---------- Format helpers ----------

def fmt_bytes(b: float | int | None, unit: str = "auto") -> str:
    if b is None:
        return "n/a"
    b = float(b)
    if unit == "G" or (unit == "auto" and b >= 1024 ** 3):
        return f"{b / (1024 ** 3):.1f}G"
    if unit == "M" or (unit == "auto" and b >= 1024 ** 2):
        return f"{b / (1024 ** 2):.0f}M"
    return f"{int(b)}B"


def fmt_ratio_bytes(used: float | int | None,
                    total: float | int | None) -> str:
    """'2.1/16G' khi auto. Nếu total None: trả used. Nếu used None: 'n/a'."""
    if used is None and total is None:
        return "n/a"
    if used is None:
        return f"?/{fmt_bytes(total)}"
    if total is None or total <= 0:
        return fmt_bytes(used)
    # Cùng đơn vị: lấy total quyết định
    tg = float(total) / (1024 ** 3)
    ug = float(used) / (1024 ** 3)
    if tg >= 1.0:
        return f"{ug:.1f}/{tg:.0f}G"
    return f"{fmt_bytes(used)}/{fmt_bytes(total)}"
