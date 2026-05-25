"""Account sync — links PingOverlay to the wwmoverlay.com API backend (Neon).

Flow:
  login(email, password)          → store encrypted session to disk
  load_session()                  → decrypt + auto-refresh if near expiry
  fetch_and_merge_profile(sess)   → pull full_name / referral_code / points
  logout(token)                   → revoke server-side + wipe local file

Session file: %APPDATA%/PingOverlay/account.json
Encrypted with same HWID-keyed XOR scheme as license_check.py.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path

from license_lib import (
    _API_BASE_URL,
    _SUPABASE_URL,   # alias for _API_BASE_URL (backward compat)
    _SUPABASE_ANON,  # empty string — JWT Bearer used instead
    LICENSE_SECRET,
    appdata_dir,
    compute_hwid,
    normalize_hwid,
)

ACCOUNT_FILE = "account.json"


# ── Encryption (mirrors license_check.py) ─────────────────────────────────────

def _envelope_key() -> bytes:
    material = LICENSE_SECRET + normalize_hwid(compute_hwid()).encode("utf-8")
    return hashlib.sha256(material).digest()


def _xor_stream(data: bytes, key: bytes) -> bytes:
    out = bytearray()
    nonce = data[:16]
    body  = data[16:]
    counter = 0
    while len(out) < len(body):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(b ^ s for b, s in zip(body, out[: len(body)]))


def _encrypt(plaintext: bytes) -> str:
    key   = _envelope_key()
    nonce = secrets.token_bytes(16)
    ct    = _xor_stream(nonce + plaintext, key)
    tag   = hashlib.sha256(key + nonce + ct).digest()[:16]
    return base64.b64encode(nonce + ct + tag).decode("ascii")


def _decrypt(blob_b64: str) -> bytes | None:
    try:
        blob = base64.b64decode(blob_b64.encode("ascii"))
    except Exception:
        return None
    if len(blob) < 32:
        return None
    nonce, rest      = blob[:16], blob[16:]
    ciphertext, tag  = rest[:-16], rest[-16:]
    key = _envelope_key()
    if not secrets.compare_digest(tag, hashlib.sha256(key + nonce + ciphertext).digest()[:16]):
        return None
    return _xor_stream(nonce + ciphertext, key)


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _post(endpoint: str, body: dict, *, token: str | None = None, timeout: float = 10.0) -> dict:
    from urllib import request as _req, error as _err
    url  = f"{_API_BASE_URL}{endpoint}"
    data = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = _req.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with _req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except _err.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


def _get(endpoint: str, token: str, *, timeout: float = 10.0):
    from urllib import request as _req, error as _err
    url  = f"{_API_BASE_URL}{endpoint}"
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    req  = _req.Request(url, headers=hdrs)
    try:
        with _req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except _err.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return []
    except Exception:
        return []


# ── Session file ───────────────────────────────────────────────────────────────

def account_path() -> Path:
    return appdata_dir() / ACCOUNT_FILE


def load_session() -> dict | None:
    """Load and decrypt saved session. Auto-refreshes if token near expiry.
    Returns None if no session or session refresh failed."""
    try:
        p = account_path()
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        if "blob" in raw:
            dec = _decrypt(raw["blob"])
            if dec is None:
                return None
            sess = json.loads(dec.decode("utf-8"))
        else:
            sess = raw  # plain-text migration path

        expires_at = float(sess.get("expires_at", 0))
        if expires_at and time.time() > expires_at - 300:
            refreshed = _do_refresh(sess.get("refresh_token", ""), sess)
            return refreshed  # None if refresh failed
        return sess
    except Exception:
        return None


def save_session(sess: dict) -> None:
    try:
        blob = _encrypt(json.dumps(sess, ensure_ascii=False).encode("utf-8"))
        account_path().write_text(json.dumps({"blob": blob}), encoding="utf-8")
    except Exception:
        pass


def clear_session() -> None:
    try:
        p = account_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass


# ── Auth ──────────────────────────────────────────────────────────────────────

def _do_refresh(refresh_token: str, old_sess: dict) -> dict | None:
    if not refresh_token:
        return None
    resp = _post("/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token})
    if "access_token" not in resp:
        return None
    user = resp.get("user") or {}
    sess = {
        **old_sess,
        "access_token":  resp["access_token"],
        "refresh_token": resp.get("refresh_token", refresh_token),
        "expires_at":    time.time() + float(resp.get("expires_in", 3600)),
        "user_id":       user.get("id") or old_sess.get("user_id", ""),
        "email":         user.get("email") or old_sess.get("email", ""),
    }
    save_session(sess)
    return sess


def login(email: str, password: str) -> tuple[bool, str, dict]:
    """Sign in with email + password.
    Returns (success, error_message, session_dict).
    """
    resp = _post(
        "/auth/v1/token?grant_type=password",
        {"email": email.strip(), "password": password},
    )
    if "access_token" not in resp:
        msg = (
            resp.get("error_description")
            or resp.get("message")
            or resp.get("error")
            or "Đăng nhập thất bại"
        )
        return False, str(msg), {}
    user = resp.get("user") or {}
    sess: dict = {
        "access_token":    resp["access_token"],
        "refresh_token":   resp.get("refresh_token", ""),
        "expires_at":      time.time() + float(resp.get("expires_in", 3600)),
        "user_id":         user.get("id", ""),
        "email":           user.get("email", email),
        "full_name":       "",
        "referral_code":   "",
        "referral_points": 0,
    }
    save_session(sess)
    return True, "", sess


def logout(access_token: str) -> None:
    """Revoke session server-side and wipe local file."""
    try:
        _post("/auth/v1/logout", {}, token=access_token)
    except Exception:
        pass
    clear_session()


# ── Profile sync ──────────────────────────────────────────────────────────────

def fetch_user_license_key(token: str, *, timeout: float = 10.0) -> str | None:
    """Call get_user_license_key() RPC on Supabase.
    Returns the license key string for the authenticated user, or None.
    """
    result = _post("/rest/v1/rpc/get_user_license_key", {}, token=token, timeout=timeout)
    # PostgREST scalar RPC returns the value directly (str or None on null)
    if isinstance(result, str) and result.strip():
        return result.strip()
    return None


def fetch_and_merge_profile(sess: dict, cfg: dict) -> dict:
    """Fetch profile from Supabase, merge into sess + local cfg.
    Returns updated session dict (does NOT save to disk — caller does that).
    """
    token   = sess.get("access_token", "")
    user_id = sess.get("user_id", "")
    if not token:
        return sess

    # Resolve missing user_id / email via /auth/v1/user (needed after OAuth JWT decode failures)
    if not user_id or not sess.get("email"):
        user_data = _get("/auth/v1/user", token)
        if isinstance(user_data, dict) and user_data.get("id"):
            user_id = user_data.get("id") or user_id
            sess = {
                **sess,
                "user_id": user_id,
                "email": user_data.get("email") or sess.get("email", ""),
            }

    if not user_id:
        return sess

    rows = _get(
        f"/rest/v1/profiles"
        f"?id=eq.{user_id}"
        f"&select=full_name,referral_code,referral_points",
        token,
    )
    if not (isinstance(rows, list) and rows):
        return sess

    p = rows[0]
    sess = {
        **sess,
        "full_name":       p.get("full_name")       or sess.get("full_name", ""),
        "referral_code":   p.get("referral_code")   or sess.get("referral_code", ""),
        "referral_points": p.get("referral_points") or sess.get("referral_points", 0),
    }
    if sess.get("referral_code"):
        cfg["referral_code"] = sess["referral_code"]
    return sess


# ── Referral claim (first app launch) ─────────────────────────────────────────

def claim_pending_referral(hwid: str, public_ip: str, *, timeout: float = 8.0) -> dict:
    """Call the claim-referral Edge Function.

    Should be called once on app startup (after public IP is known).
    The backend is idempotent — repeated calls with the same HWID return
    ``{ ok: false, reason: "already_claimed" }`` without side effects.

    Returns the parsed JSON dict from the Edge Function, or ``{"error": ...}``
    on network failure.
    """
    from urllib import request as _req, error as _err
    hwid_norm = "".join(ch for ch in (hwid or "").upper() if ch.isalnum())
    ip = (public_ip or "").strip()
    if not hwid_norm or not ip:
        return {"ok": False, "reason": "missing_hwid_or_ip"}
    url = f"{_API_BASE_URL}/functions/v1/claim-referral"
    payload = json.dumps({"hwid": hwid_norm, "public_ip": ip}).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = _req.Request(url, data=payload, headers=hdrs, method="POST")
    try:
        with _req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except _err.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ── OAuth (Google / Discord) ───────────────────────────────────────────────────

_OAUTH_CALLBACK_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>WWM Overlay Login</title>
<style>
body{font-family:system-ui,sans-serif;display:flex;align-items:center;
     justify-content:center;min-height:100vh;margin:0;background:#f0f4f8}
.card{background:#fff;border-radius:14px;padding:48px 40px;text-align:center;
      box-shadow:0 4px 32px #0002;max-width:360px}
h2{margin:0 0 8px;color:#1a1a2e;font-size:1.4rem}
p{color:#666;margin:0;font-size:.95rem}
</style></head><body><div class="card">
<h2 id="msg">Đang xử lý đăng nhập...</h2>
<p  id="sub"></p>
</div>
<script>
(function () {
  var hash = window.location.hash.slice(1);
  var qs   = window.location.search.slice(1);
  var payload = hash || qs;
  if (!payload) {
    document.getElementById('msg').textContent = 'Lỗi: không nhận được dữ liệu.';
    return;
  }
  fetch('/session', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: payload
  }).then(function () {
    document.getElementById('msg').textContent = '✓ Đăng nhập thành công!';
    document.getElementById('sub').textContent = 'Bạn có thể đóng tab này.';
  }).catch(function () {
    document.getElementById('msg').textContent = 'Lỗi kết nối. Thử lại.';
  });
})();
</script></body></html>"""


def login_oauth(provider: str) -> tuple[bool, str, dict]:
    """Open browser OAuth flow (Google/Discord via Supabase), wait for callback.
    Returns (success, error_message, session_dict).

    Prerequisites: add http://127.0.0.1 (or http://localhost) to the
    allowed redirect URLs in your Supabase project's Auth settings.
    """
    import http.server
    import queue as _q_mod
    import socket
    import threading as _th
    import urllib.parse
    import webbrowser as _wb

    # Find a free local port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.bind(("", 0))
        port = _s.getsockname()[1]

    redirect_uri = f"http://127.0.0.1:{port}/callback"
    result: _q_mod.Queue = _q_mod.Queue()

    _html = _OAUTH_CALLBACK_HTML.encode("utf-8")

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/callback"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_html)

        def do_POST(self):
            if self.path == "/session":
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n).decode("utf-8")
                result.put(urllib.parse.parse_qs(body, keep_blank_values=True))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    server.timeout = 1

    def _serve() -> None:
        deadline = time.time() + 120
        while time.time() < deadline and result.empty():
            server.handle_request()
        server.server_close()

    _th.Thread(target=_serve, daemon=True, name=f"OAuthSrv-{provider}").start()

    oauth_url = (
        f"{_API_BASE_URL}/auth/v1/authorize"
        f"?provider={provider}"
        f"&redirect_to={urllib.parse.quote(redirect_uri, safe='')}"
    )
    _wb.open(oauth_url, new=2)

    try:
        params = result.get(timeout=120)
    except _q_mod.Empty:
        return False, "Hết thời gian chờ. Vui lòng thử lại.", {}

    access_token  = (params.get("access_token")  or [""])[0]
    refresh_token = (params.get("refresh_token") or [""])[0]
    expires_in    = (params.get("expires_in")    or ["3600"])[0]

    if not access_token:
        err = (
            params.get("error_description")
            or params.get("error")
            or [("OAuth thất bại.")]
        )
        return False, str((err or ["OAuth thất bại."])[0] if isinstance(err, list) else err), {}

    # Decode user info from the JWT payload (no signature check needed here)
    user_id = ""
    email   = ""
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        jwt_data = json.loads(base64.b64decode(payload_b64.encode("ascii")).decode("utf-8"))
        user_id = jwt_data.get("sub", "")
        email   = jwt_data.get("email", "")
    except Exception:
        pass

    sess: dict = {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_at":    time.time() + float(expires_in),
        "user_id":       user_id,
        "email":         email,
        "full_name":     "",
        "referral_code": "",
        "referral_points": 0,
    }
    save_session(sess)
    return True, "", sess
