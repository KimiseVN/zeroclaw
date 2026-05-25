"""Shared license primitives for PingOverlay and the License Generator.

Both apps embed this module — verification is fully offline via
HMAC-SHA256 against ``LICENSE_SECRET``. The Google Drive folder is used
by the generator side as a record-keeping archive (Kim's bookkeeping);
clients never need to read from Drive to verify a key.

Key format::

    PO1-<HWID16>-<DURATION>-<EXPIRY_TS>-<SIG32>

* ``PO1`` — format version literal
* ``HWID16`` — 16-char dash-stripped Crockford-base32 of the machine
  fingerprint (see ``compute_hwid``)
* ``DURATION`` — one of ``1D 1W 1MO 3MO 6MO 1Y LT``
* ``EXPIRY_TS`` — Unix epoch seconds (``0`` = lifetime)
* ``SIG32`` — first 32 hex chars of HMAC-SHA256(payload, secret),
  uppercase

Anyone who reverses both binaries can extract ``LICENSE_SECRET`` and
forge keys; this scheme is intentionally lightweight for a personal
distribution where the operator (Kim) trusts the user base.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


# --------------------------------------------------------- secret ----

# Treat this as the equivalent of a passphrase: changing it invalidates
# every previously-issued key. Keep generator + client in sync.
LICENSE_SECRET = b"PingOverlay-Kim-License-v1-2026-MAY-04-7G3Q9P"
LICENSE_FORMAT = "PO1"
LICENSE_FILE_NAME = "license.json"

# --------------------------------------------------------- API backend ----
# New backend (Neon-powered) — replaces Supabase REST + Auth + Edge Functions.
# _SUPABASE_URL / _SUPABASE_ANON kept for import compatibility with account_sync.py.
_API_BASE_URL     = "https://thuytk--wwm-api-fastapi-app.modal.run"
_SUPABASE_URL     = _API_BASE_URL   # alias so account_sync.py imports work
_SUPABASE_ANON    = ""              # no longer used; JWT Bearer replaces apikey

_trial_days_cache: int | None = None


def fetch_trial_days(*, timeout: float = 4.0) -> int:
    """Read the admin-configured trial duration from the API backend.

    Cached after the first successful fetch so subsequent calls are free.
    Returns 3 on any error (network down, server unreachable, …).
    """
    global _trial_days_cache
    if _trial_days_cache is not None:
        return _trial_days_cache

    try:
        import json as _json
        from urllib import request as _req

        url = (
            f"{_API_BASE_URL}/rest/v1/site_settings"
            "?key=eq.trial&select=value"
        )
        req = _req.Request(url, headers={"Accept": "application/json"})
        with _req.urlopen(req, timeout=timeout) as resp:
            rows = _json.loads(resp.read())
            if isinstance(rows, list) and rows:
                days = (rows[0].get("value") or {}).get("days")
                if isinstance(days, (int, float)) and 1 <= float(days) <= 365:
                    _trial_days_cache = int(days)
                    return _trial_days_cache
    except Exception:
        pass

    _trial_days_cache = 3  # fallback — 3 days
    return _trial_days_cache

# (code, days). 0 = lifetime.
DURATIONS: dict[str, int] = {
    "1d": 1,
    "1w": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "lt": 0,
}

# Display labels (VI / EN) used by both apps.
DURATION_LABELS: dict[str, str] = {
    "1d": "1 ngày / 1 day",
    "1w": "1 tuần / 1 week",
    "1mo": "1 tháng / 1 month",
    "3mo": "3 tháng / 3 months",
    "6mo": "6 tháng / 6 months",
    "1y": "1 năm / 1 year",
    "lt": "Vĩnh viễn / Lifetime",
}


# --------------------------------------------------------- HWID ----


def _read_machine_guid() -> str:
    """Windows ``HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid``
    — the most stable PC identifier short of TPM. Empty on non-Windows."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg  # type: ignore[import-not-found]
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return str(value)
    except Exception:
        return ""


def _read_volume_serial(drive: str = "C:\\") -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        serial = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            drive, None, 0, ctypes.byref(serial), None, None, None, 0
        )
        if not ok:
            return ""
        return f"{serial.value:08x}"
    except Exception:
        return ""


def compute_hwid() -> str:
    """16-char Crockford-style HWID, formatted ``XXXX-XXXX-XXXX-XXXX``.

    Combines the MAC address of the primary NIC, the Windows MachineGuid
    (registry) and the C-drive volume serial. Hashed with SHA-256 and
    truncated to 80 bits → 16 base-32 chars. Stable across reboots and
    Windows updates (provided the network adapter doesn't change).
    """
    mac = uuid.getnode()
    parts = [
        f"{mac:012x}",
        _read_machine_guid(),
        _read_volume_serial(),
        sys.platform,
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    raw = base64.b32encode(digest).decode("ascii").rstrip("=")
    # Crockford-ish: avoid 0/O confusion by mapping 0→Z.
    raw = raw.replace("0", "Z").replace("1", "Y")
    code = raw[:16]
    return "-".join(code[i:i + 4] for i in range(0, 16, 4))


def normalize_hwid(hwid: str) -> str:
    """Strip dashes, whitespace; uppercase; keep alnum only."""
    return "".join(ch for ch in (hwid or "").upper() if ch.isalnum())


# --------------------------------------------------------- key ----


def _payload(hwid_norm: str, duration_code: str, expiry_ts: int) -> str:
    return f"{LICENSE_FORMAT}|{hwid_norm}|{duration_code.lower()}|{expiry_ts}"


def _sign(payload: str) -> str:
    digest = hmac.new(LICENSE_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32].upper()


def issue_license(
    hwid: str,
    duration_code: str,
    *,
    issued_by: str = "Kim",
    now: datetime | None = None,
) -> dict:
    """Generate a signed license record.

    Returns a dict suitable for archiving (``hwid`` / ``key`` / ``duration`` /
    ``issued_at`` / ``expires_at`` / ``expires_at_ts``). Raises
    ``ValueError`` for an unknown ``duration_code``.
    """
    duration_code = duration_code.lower().strip()
    if duration_code not in DURATIONS:
        raise ValueError(f"Unknown duration code: {duration_code!r}")
    hwid_norm = normalize_hwid(hwid)
    if len(hwid_norm) != 16:
        raise ValueError(f"HWID must be 16 alnum chars (got {len(hwid_norm)})")
    issued_at = now or datetime.now(timezone.utc)
    days = DURATIONS[duration_code]
    if days <= 0:
        expiry_ts = 0
        expires_at_iso = "lifetime"
        expires_at_human = "Vĩnh viễn / Lifetime"
    else:
        expires_dt = issued_at + timedelta(days=days)
        expiry_ts = int(expires_dt.timestamp())
        expires_at_iso = expires_dt.isoformat()
        expires_at_human = expires_dt.strftime("%Y-%m-%d %H:%M UTC")
    payload = _payload(hwid_norm, duration_code, expiry_ts)
    sig = _sign(payload)
    key = f"{LICENSE_FORMAT}-{hwid_norm}-{duration_code.upper()}-{expiry_ts}-{sig}"
    return {
        "hwid": hwid_norm,
        "hwid_display": "-".join(hwid_norm[i:i + 4] for i in range(0, 16, 4)),
        "duration": duration_code,
        "key": key,
        "issued_at": issued_at.isoformat(),
        "issued_by": issued_by,
        "expires_at": expires_at_iso,
        "expires_at_human": expires_at_human,
        "expires_at_ts": expiry_ts,
    }


def verify_license(key: str, hwid: str) -> tuple[bool, str | None, str | None]:
    """Validate ``key`` against the supplied ``hwid``.

    Returns ``(valid, expires_iso_or_'lifetime', error_or_None)``.
    """
    try:
        raw = (key or "").strip().upper().replace(" ", "")
        if not raw:
            return False, None, "empty"
        parts = raw.split("-")
        if len(parts) != 5:
            return False, None, "format-error"
        prefix, hwid_norm, dur_code, exp_ts_str, sig = parts
        if prefix != LICENSE_FORMAT:
            return False, None, "wrong-format"
        if hwid_norm != normalize_hwid(hwid):
            return False, None, "hwid-mismatch"
        dur_lower = dur_code.lower()
        if dur_lower not in DURATIONS:
            return False, None, "duration-unknown"
        try:
            exp_ts = int(exp_ts_str)
        except ValueError:
            return False, None, "expiry-not-int"
        expected = _sign(_payload(hwid_norm, dur_lower, exp_ts))
        if not hmac.compare_digest(sig, expected):
            return False, None, "signature-invalid"
        if exp_ts > 0:
            if time.time() > exp_ts:
                expires_iso = datetime.fromtimestamp(exp_ts, timezone.utc).isoformat()
                return False, expires_iso, "expired"
            return True, datetime.fromtimestamp(exp_ts, timezone.utc).isoformat(), None
        return True, "lifetime", None
    except Exception as exc:  # pragma: no cover — defensive
        return False, None, f"error: {exc}"


# --------------------------------------------------------- paths ----


def appdata_dir() -> Path:
    """``%APPDATA%\\PingOverlay`` (or ``~/.PingOverlay`` on non-Windows)."""
    import os
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    p = Path(base) / "PingOverlay"
    p.mkdir(parents=True, exist_ok=True)
    return p


def license_path() -> Path:
    return appdata_dir() / LICENSE_FILE_NAME
