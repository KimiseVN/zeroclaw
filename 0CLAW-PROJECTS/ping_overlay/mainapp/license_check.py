"""Client-side license loading + validation for PingOverlay.

The license file lives at ``%APPDATA%/PingOverlay/license.json``. It's
encrypted-at-rest with a Fernet-style symmetric box derived from the
shared LICENSE_SECRET (same secret used to sign keys), so a casual
inspector can't just paste the JSON onto another machine. Cryptographic
validity comes from the HMAC signature inside the key itself
(``license_lib.verify_license``), not from the on-disk envelope.

Public surface:

* ``LicenseStatus`` — frozen dataclass with the full state needed by the
  overlay/control-panel/tray to gate features.
* ``current_status()`` — read+verify the saved license against the
  current HWID. Always safe to call; returns a status with
  ``is_licensed=False`` when unlicensed, expired, mismatched, etc.
* ``save_license(key)`` — validate then persist a freshly entered key.
* ``clear_license()`` — wipe the saved key (used after expiry, or as a
  manual "reset license" affordance).
* ``hwid_display()`` — formatted HWID string for the settings UI.

Feature gating in the rest of the app should consult
``current_status().is_licensed``. The bare ping/loss display in the
overlay is the only feature that runs without a license — everything
else (game tweaks, Quest helper, scan, events overlay rotation, etc.)
stays disabled until a valid key is loaded.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from license_lib import (
    LICENSE_SECRET,
    appdata_dir,
    compute_hwid,
    fetch_trial_days,
    license_path,
    normalize_hwid,
    verify_license,
)


_VERSION = 1
TRIAL_FILE_NAME = "trial.json"
# Default 3 days; updated at startup by refresh_trial_duration() which fetches
# the admin-configured value from Supabase site_settings.
TRIAL_DURATION = timedelta(days=3)


def refresh_trial_duration() -> timedelta:
    """Fetch admin-configured trial days from Supabase and update TRIAL_DURATION.

    Call once from a background thread at startup *before* trial_status() is
    invoked for the first time.  Falls back to 1 day (24 h) on any error.
    Only affects new trial creations; existing trial.json expiry is preserved.
    """
    global TRIAL_DURATION
    days = fetch_trial_days()
    TRIAL_DURATION = timedelta(days=days)
    return TRIAL_DURATION


@dataclass(frozen=True)
class LicenseStatus:
    """Snapshot of the current licensing state.

    Layered booleans so the UI can show a precise reason:

    * ``is_licensed`` — the catch-all gate the rest of the app should
      check. True when a saved key exists and validates against the
      current HWID and isn't past its expiry.
    * ``has_saved_key`` — distinguishes "never entered a key" from "key
      saved but invalid/expired" so the Settings dialog can word the
      hint correctly.
    * ``error`` — short machine reason (``"hwid-mismatch"``,
      ``"expired"``, ``"signature-invalid"`` ...). None when valid or
      when no key has been entered.
    * ``expires_at`` — ISO 8601 string or the literal ``"lifetime"``;
      None when no valid key.
    """
    is_licensed: bool
    has_saved_key: bool
    hwid: str
    expires_at: str | None = None
    error: str | None = None
    duration_code: str | None = None


@dataclass(frozen=True)
class TrialStatus:
    """Local 24-hour trial state for machines without a valid license."""

    is_active: bool
    has_started: bool
    started_at: str | None = None
    expires_at: str | None = None
    seconds_remaining: int = 0
    notice_shown: bool = False
    error: str | None = None


# --------------------------------------------------- on-disk envelope


def _envelope_key() -> bytes:
    """Derive a stable 32-byte encryption key from the shared secret +
    the HWID. The HWID component means a stolen license file can't be
    decrypted on a different machine even if the secret leaks."""
    material = LICENSE_SECRET + normalize_hwid(compute_hwid()).encode("utf-8")
    return hashlib.sha256(material).digest()


def _xor_stream(data: bytes, key: bytes) -> bytes:
    """ChaCha-style stretching: hash(key|nonce|counter) -> keystream."""
    out = bytearray()
    nonce = data[:16]
    body = data[16:]
    counter = 0
    block_size = 32
    while len(out) < len(body):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(b ^ s for b, s in zip(body, out[: len(body)]))


def _encrypt(plaintext: bytes) -> str:
    """Symmetric encrypt + MAC. Format: base64(nonce + ciphertext + tag)."""
    key = _envelope_key()
    nonce = secrets.token_bytes(16)
    keystream_input = nonce + plaintext  # _xor_stream uses first 16 bytes as nonce
    ciphertext = _xor_stream(keystream_input, key)
    tag = hashlib.sha256(key + nonce + ciphertext).digest()[:16]
    blob = nonce + ciphertext + tag
    return base64.b64encode(blob).decode("ascii")


def _decrypt(blob_b64: str) -> bytes | None:
    try:
        blob = base64.b64decode(blob_b64.encode("ascii"))
    except Exception:
        return None
    if len(blob) < 16 + 16:
        return None
    nonce, rest = blob[:16], blob[16:]
    ciphertext, tag = rest[:-16], rest[-16:]
    key = _envelope_key()
    expected_tag = hashlib.sha256(key + nonce + ciphertext).digest()[:16]
    if not secrets.compare_digest(tag, expected_tag):
        return None
    return _xor_stream(nonce + ciphertext, key)


# --------------------------------------------------- file IO ----


def _read_envelope(path: Path | None = None) -> dict | None:
    path = path or license_path()
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(outer, dict):
        return None
    blob = outer.get("blob")
    if not isinstance(blob, str):
        return None
    plain = _decrypt(blob)
    if plain is None:
        return None
    try:
        inner = json.loads(plain.decode("utf-8"))
    except Exception:
        return None
    return inner if isinstance(inner, dict) else None


def _write_envelope(record: dict, path: Path | None = None) -> bool:
    path = path or license_path()
    try:
        plain = json.dumps(record, ensure_ascii=False).encode("utf-8")
        envelope = {"v": _VERSION, "blob": _encrypt(plain)}
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(envelope), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as exc:
        print(f"[license] write failed: {exc}")
        return False


# --------------------------------------------------- public API ----


def trial_path() -> Path:
    return appdata_dir() / TRIAL_FILE_NAME


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def trial_status(*, create: bool = True) -> TrialStatus:
    """Return local 24-hour trial state, creating it on first unlicensed run.

    The trial is stored separately from the license key so clearing an invalid
    key does not reset the trial window.
    """
    path = trial_path()
    now = _utcnow()
    record = _read_envelope(path)
    if not record:
        if not create:
            return TrialStatus(is_active=False, has_started=False)
        started = now
        expires = started + TRIAL_DURATION
        record = {
            "started_at": started.isoformat(),
            "expires_at": expires.isoformat(),
            "notice_shown": False,
        }
        if not _write_envelope(record, path):
            return TrialStatus(
                is_active=False,
                has_started=False,
                error="trial-write-failed",
            )

    started_at = str(record.get("started_at") or "") or None
    expires_at = str(record.get("expires_at") or "") or None
    expires_dt = _parse_iso_datetime(expires_at)
    if expires_dt is None:
        return TrialStatus(
            is_active=False,
            has_started=True,
            started_at=started_at,
            expires_at=expires_at,
            notice_shown=bool(record.get("notice_shown", False)),
            error="trial-corrupt",
        )
    remaining = max(0, int((expires_dt - now).total_seconds()))
    return TrialStatus(
        is_active=remaining > 0,
        has_started=True,
        started_at=started_at,
        expires_at=expires_at,
        seconds_remaining=remaining,
        notice_shown=bool(record.get("notice_shown", False)),
    )


def mark_trial_notice_shown(*, started_at: str | None = None, expires_at: str | None = None) -> None:
    path = trial_path()
    record = _read_envelope(path)
    if not isinstance(record, dict):
        now = _utcnow()
        record = {
            "started_at": started_at or now.isoformat(),
            "expires_at": expires_at or (now + TRIAL_DURATION).isoformat(),
        }
    if record.get("notice_shown") is True:
        return
    if started_at:
        record["started_at"] = started_at
    if expires_at:
        record["expires_at"] = expires_at
    record["notice_shown"] = True
    _write_envelope(record, path)


def _format_local_time(value: str | None) -> str:
    dt = _parse_iso_datetime(value)
    if dt is None:
        return str(value or "—")
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def trial_summary(trial: TrialStatus, *, language: str = "vi") -> str:
    is_vi = (language == "vi")
    if trial.is_active:
        hours = max(0, trial.seconds_remaining) // 3600
        minutes = (max(0, trial.seconds_remaining) % 3600) // 60
        expires = _format_local_time(trial.expires_at)
        if is_vi:
            return f"Dùng thử 24h đang hoạt động — còn {hours}h {minutes}m, hết hạn {expires}"
        return f"24-hour trial active — {hours}h {minutes}m left, expires {expires}"
    if trial.has_started:
        expires = _format_local_time(trial.expires_at)
        if is_vi:
            return f"Trial 24h đã hết hạn lúc {expires} — nhập License để mở khoá đầy đủ"
        return f"24-hour trial expired at {expires} — enter a license to unlock full features"
    return ("Chưa bắt đầu trial" if is_vi else "Trial not started")


def hwid_display() -> str:
    """Cached HWID in display form ``XXXX-XXXX-XXXX-XXXX``."""
    return compute_hwid()


def current_status() -> LicenseStatus:
    """Verify the saved license (if any) against the current HWID.

    Always safe to call; returns ``LicenseStatus(is_licensed=False, ...)``
    when no license is saved or when the saved one is invalid for any
    reason. Layered booleans tell the UI exactly which message to show.
    """
    hwid = hwid_display()
    record = _read_envelope()
    if not record:
        return LicenseStatus(
            is_licensed=False,
            has_saved_key=False,
            hwid=hwid,
        )
    key = str(record.get("key") or "").strip()
    if not key:
        return LicenseStatus(
            is_licensed=False,
            has_saved_key=False,
            hwid=hwid,
        )
    duration = str(record.get("duration") or "") or None
    valid, expires, err = verify_license(key, hwid)
    return LicenseStatus(
        is_licensed=bool(valid),
        has_saved_key=True,
        hwid=hwid,
        expires_at=expires,
        error=err,
        duration_code=duration,
    )


def save_license(key: str) -> LicenseStatus:
    """Validate ``key``, persist it, and return the resulting status."""
    hwid = hwid_display()
    valid, expires, err = verify_license(key, hwid)
    if not valid:
        return LicenseStatus(
            is_licensed=False,
            has_saved_key=False,
            hwid=hwid,
            expires_at=expires,
            error=err,
        )
    record = {
        "key": (key or "").strip().upper(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
    }
    # Lift duration code out of the key for display (bytes between
    # second and third dash). The verify pass above guarantees the
    # split is well-formed.
    parts = record["key"].split("-")
    if len(parts) == 5:
        record["duration"] = parts[2].lower()
    if not _write_envelope(record):
        return LicenseStatus(
            is_licensed=False,
            has_saved_key=False,
            hwid=hwid,
            error="write-failed",
        )
    return LicenseStatus(
        is_licensed=True,
        has_saved_key=True,
        hwid=hwid,
        expires_at=expires,
        duration_code=record.get("duration"),
    )


def clear_license() -> None:
    path = license_path()
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def status_summary(status: LicenseStatus, *, language: str = "vi") -> str:
    """Single human-readable line for the Settings dialog.

    Centralized so the EN/VI strings stay in one place and the
    color/wording stays consistent across UI surfaces.
    """
    is_vi = (language == "vi")
    if status.is_licensed:
        if status.expires_at == "lifetime":
            return ("Đã kích hoạt — Vĩnh viễn"
                    if is_vi else "Licensed — Lifetime")
        try:
            dt = datetime.fromisoformat(str(status.expires_at).replace("Z", "+00:00"))
            label = dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            label = str(status.expires_at)
        return (f"Đã kích hoạt — hết hạn {label}"
                if is_vi else f"Licensed — expires {label}")
    if not status.has_saved_key:
        return ("Chưa có license — gửi HWID cho ムKim để được cấp"
                if is_vi else "No license — send your HWID to ムKim to get one")
    if status.error == "expired":
        return ("License đã hết hạn — gửi lại HWID cho ムKim"
                if is_vi else "License expired — request a new key")
    if status.error == "hwid-mismatch":
        return ("License không khớp HWID máy này — gửi HWID cho ムKim"
                if is_vi else "License doesn't match this PC's HWID")
    if status.error == "signature-invalid":
        return ("License không hợp lệ — kiểm tra lại key đã nhập"
                if is_vi else "License signature invalid")
    return (f"License không hợp lệ ({status.error}) — gửi HWID cho ムKim"
            if is_vi else f"License invalid ({status.error})")
