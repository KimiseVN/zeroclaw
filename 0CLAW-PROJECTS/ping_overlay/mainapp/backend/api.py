"""
WWM Overlay API — replaces Supabase REST / Auth / Edge Functions
============================================================
Endpoints mirror the Supabase interface so the app changes are minimal.

Auth:
  POST /auth/v1/token?grant_type=password      email+password login
  POST /auth/v1/token?grant_type=refresh_token refresh session
  POST /auth/v1/logout                         revoke session
  GET  /auth/v1/user                           current user info
  GET  /auth/v1/authorize                      OAuth redirect (Google/Discord)
  GET  /auth/v1/callback/{provider}            OAuth callback

REST (PostgREST-compatible):
  GET  /rest/v1/site_settings                  settings rows
  GET  /rest/v1/profiles                       user profile
  POST /rest/v1/rpc/get_user_license_key       active license key

Edge Functions:
  POST /functions/v1/claim-referral            claim referral

Heartbeat (replaces Google Apps Script backend):
  POST /api/heartbeat                          client heartbeat + admin actions

Admin helpers:
  POST /api/admin/set-password                 set user password (admin only)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import socket
import time
import urllib.parse
import urllib.request
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import psycopg2
import psycopg2.extras
import psycopg2.pool
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

# ── Config ─────────────────────────────────────────────────────────────────────

DB_URL               = os.environ.get("SUPABASE_DB_URL", os.environ.get("NEON_DATABASE_URL", ""))
JWT_SECRET           = os.environ.get("JWT_SECRET", "CHANGEME_generate_with_secrets.token_hex(32)")
ADMIN_TOKEN          = os.environ.get("ADMIN_TOKEN", "")
CLIENT_TOKEN         = os.environ.get("CLIENT_TOKEN", "")   # heartbeat client auth (optional)
API_BASE_URL         = os.environ.get("API_BASE_URL", "https://api.wwmoverlay.com")

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
DISCORD_CLIENT_ID    = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET= os.environ.get("DISCORD_CLIENT_SECRET", "")

JWT_ALGORITHM          = "HS256"
ACCESS_TOKEN_EXPIRE_S  = 3_600          # 1 h
REFRESH_TOKEN_EXPIRE_S = 30 * 24 * 3_600  # 30 days

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"
DISCORD_AUTH_URL  = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL  = "https://discord.com/api/users/@me"


# ── DB pool ────────────────────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not DB_URL:
            raise RuntimeError("SUPABASE_DB_URL not set")
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DB_URL)
    return _pool


@contextmanager
def _db():
    conn = _get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)


def _one(sql: str, params=()) -> dict | None:
    with _db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def _all(sql: str, params=()) -> list[dict]:
    with _db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def _exec(sql: str, params=()) -> None:
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _make_access_token(user_id: str, email: str) -> str:
    return jwt.encode(
        {"sub": user_id, "email": email,
         "iat": int(time.time()),
         "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_S},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )


def _make_refresh_token(user_id: str) -> str:
    token = secrets.token_urlsafe(48)
    h     = hashlib.sha256(token.encode()).hexdigest()
    exp   = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_EXPIRE_S)
    _exec(
        "INSERT INTO refresh_tokens (token_hash, user_id, expires_at)"
        " VALUES (%s, %s, %s) ON CONFLICT (token_hash) DO NOTHING",
        (h, user_id, exp),
    )
    return token


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token_expired")
    except Exception:
        raise HTTPException(401, "invalid_token")


def _auth_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return _decode_jwt(auth[7:])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_response(user_id: str, email: str) -> dict:
    return {
        "access_token":  _make_access_token(user_id, email),
        "refresh_token": _make_refresh_token(user_id),
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_EXPIRE_S,
        "user":          {"id": user_id, "email": email},
    }


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="WWM Overlay API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH  /auth/v1/*
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/v1/token")
async def auth_token(request: Request):
    grant = request.query_params.get("grant_type", "")
    body  = await request.json()

    # ── Email + password ───────────────────────────────────────────────────────
    if grant == "password":
        email = (body.get("email") or "").strip().lower()
        pw    = (body.get("password") or "")
        if not email or not pw:
            return JSONResponse(
                {"error": "invalid_grant",
                 "error_description": "Email và mật khẩu không được để trống"},
                status_code=400,
            )
        row = _one(
            "SELECT p.id::text AS id, p.email, ua.password_hash"
            " FROM profiles p JOIN user_auth ua ON ua.user_id = p.id"
            " WHERE p.email = %s AND ua.password_hash IS NOT NULL",
            (email,),
        )
        bad_creds = JSONResponse(
            {"error": "invalid_grant",
             "error_description": "Email hoặc mật khẩu không đúng"},
            status_code=400,
        )
        if not row:
            return bad_creds
        if not bcrypt.checkpw(pw.encode(), row["password_hash"].encode()):
            return bad_creds
        return _token_response(row["id"], row["email"])

    # ── Refresh token ──────────────────────────────────────────────────────────
    if grant == "refresh_token":
        raw = (body.get("refresh_token") or "").strip()
        if not raw:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Refresh token bị thiếu"},
                status_code=400,
            )
        h   = hashlib.sha256(raw.encode()).hexdigest()
        row = _one(
            "SELECT rt.user_id::text, p.email"
            " FROM refresh_tokens rt JOIN profiles p ON p.id = rt.user_id"
            " WHERE rt.token_hash = %s AND rt.expires_at > now()",
            (h,),
        )
        if not row:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Refresh token hết hạn"},
                status_code=400,
            )
        _exec("DELETE FROM refresh_tokens WHERE token_hash = %s", (h,))
        return _token_response(row["user_id"], row["email"])

    raise HTTPException(400, f"unsupported grant_type: {grant!r}")


@app.post("/auth/v1/logout")
async def auth_logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            claims = _decode_jwt(auth[7:])
            _exec("DELETE FROM refresh_tokens WHERE user_id = %s", (claims["sub"],))
        except Exception:
            pass
    return {}


@app.get("/auth/v1/user")
async def auth_get_user(request: Request):
    claims = _auth_user(request)
    return {"id": claims["sub"], "email": claims.get("email", "")}


# ── OAuth ─────────────────────────────────────────────────────────────────────

@app.get("/auth/v1/authorize")
async def auth_authorize(provider: str, redirect_to: str):
    state = base64.urlsafe_b64encode(
        json.dumps({"r": redirect_to, "n": secrets.token_hex(8)}).encode()
    ).decode().rstrip("=")

    cb = f"{API_BASE_URL}/auth/v1/callback/{provider}"

    if provider == "google":
        if not GOOGLE_CLIENT_ID:
            raise HTTPException(503, "Google OAuth not configured — set GOOGLE_CLIENT_ID")
        qs = urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID, "redirect_uri": cb,
            "response_type": "code", "scope": "openid email profile",
            "state": state, "access_type": "offline", "prompt": "select_account",
        })
        return RedirectResponse(f"{GOOGLE_AUTH_URL}?{qs}")

    if provider == "discord":
        if not DISCORD_CLIENT_ID:
            raise HTTPException(503, "Discord OAuth not configured — set DISCORD_CLIENT_ID")
        qs = urllib.parse.urlencode({
            "client_id": DISCORD_CLIENT_ID, "redirect_uri": cb,
            "response_type": "code", "scope": "identify email", "state": state,
        })
        return RedirectResponse(f"{DISCORD_AUTH_URL}?{qs}")

    raise HTTPException(400, f"unsupported provider: {provider!r}")


@app.get("/auth/v1/callback/{provider}")
async def auth_callback(provider: str, code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(400, f"OAuth error: {error}")

    # Decode state
    try:
        pad  = "=" * (-len(state) % 4)
        obj  = json.loads(base64.urlsafe_b64decode((state + pad).encode()))
        redirect_to = obj.get("r", "")
    except Exception:
        raise HTTPException(400, "invalid state")

    cb = f"{API_BASE_URL}/auth/v1/callback/{provider}"

    if provider == "google":
        tr = _http_post(GOOGLE_TOKEN_URL, {
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code, "redirect_uri": cb, "grant_type": "authorization_code",
        })
        # Decode user info from id_token
        id_tok = tr.get("id_token", "")
        email = name = avatar = ""
        try:
            seg = id_tok.split(".")[1]
            seg += "=" * (-len(seg) % 4)
            info   = json.loads(base64.b64decode(seg).decode())
            email  = info.get("email", "")
            name   = info.get("name", "")
            avatar = info.get("picture", "")
        except Exception:
            info   = _http_get(GOOGLE_USER_URL, bearer=tr.get("access_token", ""))
            email  = info.get("email", "")
            name   = info.get("name", "")
            avatar = info.get("picture", "")

    elif provider == "discord":
        tr = _http_post(DISCORD_TOKEN_URL, {
            "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
            "code": code, "redirect_uri": cb, "grant_type": "authorization_code",
        }, form=True)
        info  = _http_get(DISCORD_USER_URL, bearer=tr.get("access_token", ""))
        email  = info.get("email", "")
        name   = info.get("username", "")
        did    = info.get("id", "")
        av     = info.get("avatar", "")
        avatar = f"https://cdn.discordapp.com/avatars/{did}/{av}.png" if av else ""
    else:
        raise HTTPException(400, "unsupported provider")

    if not email:
        raise HTTPException(400, "could not get email from provider")

    user_id = _upsert_oauth_user(email, name, avatar)
    access  = _make_access_token(user_id, email)
    refresh = _make_refresh_token(user_id)

    qs = urllib.parse.urlencode({
        "access_token": access, "refresh_token": refresh,
        "expires_in": ACCESS_TOKEN_EXPIRE_S, "token_type": "bearer",
    })
    sep = "&" if "?" in redirect_to else "?"
    return RedirectResponse(f"{redirect_to}{sep}{qs}")


def _upsert_oauth_user(email: str, name: str, avatar: str) -> str:
    row = _one("SELECT id::text FROM profiles WHERE email = %s", (email,))
    if row:
        uid = row["id"]
        _exec(
            "UPDATE profiles"
            " SET full_name  = COALESCE(NULLIF(full_name,''),  %s),"
            "     avatar_url = COALESCE(NULLIF(avatar_url,''), %s)"
            " WHERE id = %s",
            (name, avatar, uid),
        )
        return uid
    uid = str(_uuid.uuid4())
    _exec(
        "INSERT INTO profiles (id, email, full_name, avatar_url, is_admin, created_at)"
        " VALUES (%s, %s, %s, %s, false, now())",
        (uid, email, name, avatar),
    )
    return uid


# ══════════════════════════════════════════════════════════════════════════════
#  REST API  /rest/v1/*
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/rest/v1/site_settings")
async def rest_site_settings(request: Request):
    key_filter = request.query_params.get("key", "")   # "eq.trial"
    select     = request.query_params.get("select", "value")
    col = "value" if "value" in select else "*"
    if key_filter.startswith("eq."):
        row = _one(f"SELECT {col} FROM site_settings WHERE key = %s", (key_filter[3:],))
    else:
        row = _one(f"SELECT {col} FROM site_settings LIMIT 1")
    return JSONResponse([row] if row else [])


@app.get("/rest/v1/profiles")
async def rest_profiles(request: Request):
    claims  = _auth_user(request)
    user_id = claims["sub"]

    # Safe column whitelist
    select   = request.query_params.get("select", "full_name,referral_code,referral_points")
    safe     = {"full_name", "referral_code", "referral_points", "email", "avatar_url", "is_admin"}
    cols     = [c.strip() for c in select.split(",") if c.strip() in safe] or \
               ["full_name", "referral_code", "referral_points"]

    row = _one(
        f"SELECT {', '.join(cols)} FROM profiles WHERE id = %s::uuid",
        (user_id,),
    )
    return JSONResponse([row] if row else [])


@app.post("/rest/v1/rpc/get_user_license_key")
async def rpc_license_key(request: Request):
    claims  = _auth_user(request)
    user_id = claims["sub"]
    row = _one(
        "SELECT license_key FROM licenses"
        " WHERE user_id = %s::uuid AND status = 'active'"
        " ORDER BY issued_at DESC LIMIT 1",
        (user_id,),
    )
    return JSONResponse(row["license_key"] if row else None)


# ══════════════════════════════════════════════════════════════════════════════
#  EDGE FUNCTIONS  /functions/v1/*
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/functions/v1/claim-referral")
async def fn_claim_referral(request: Request):
    body      = await request.json()
    hwid      = "".join(c for c in (body.get("hwid") or "").upper() if c.isalnum())
    public_ip = (body.get("public_ip") or "").strip()

    if not hwid or not public_ip:
        return {"ok": False, "reason": "missing_hwid_or_ip"}

    pending = _one(
        "SELECT id, referrer_id FROM pending_referrals"
        " WHERE (client_ip = %s OR claimed_hwid = %s)"
        "   AND claimed = false AND created_at > now() - interval '30 days'"
        " ORDER BY created_at DESC LIMIT 1",
        (public_ip, hwid),
    )
    if not pending:
        return {"ok": False, "reason": "no_pending_referral"}

    pid         = pending["id"]
    referrer_id = str(pending["referrer_id"])

    cfg_row = _one("SELECT value FROM site_settings WHERE key = 'referral_config'")
    pts = int((cfg_row.get("value") or {}).get("points_per_download", 1)) if cfg_row else 1

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_referrals SET claimed = true, claimed_hwid = %s,"
                " claimed_at = now() WHERE id = %s",
                (hwid, pid),
            )
            cur.execute(
                "UPDATE profiles SET referral_points = referral_points + %s WHERE id = %s::uuid",
                (pts, referrer_id),
            )
            cur.execute(
                "INSERT INTO referral_events (id, referrer_id, event_type, points_awarded)"
                " VALUES (%s, %s::uuid, 'download', %s)",
                (str(_uuid.uuid4()), referrer_id, pts),
            )
    return {"ok": True, "reason": "claimed", "points": pts}


# ══════════════════════════════════════════════════════════════════════════════
#  HEARTBEAT  /api/heartbeat
#  Replaces Google Apps Script backend
# ══════════════════════════════════════════════════════════════════════════════

def _require_admin(body: dict) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(503, "admin not configured")
    if (body.get("admin_token") or "").strip() != ADMIN_TOKEN:
        raise HTTPException(403, "invalid admin_token")


def _require_client(body: dict) -> None:
    if CLIENT_TOKEN and (body.get("client_token") or "").strip() != CLIENT_TOKEN:
        raise HTTPException(403, "invalid client_token")


@app.post("/api/heartbeat")
async def api_heartbeat(request: Request):
    body   = await request.json()
    action = (body.get("action") or "heartbeat").lower()

    # test_heartbeat — validate connectivity without writing
    if action == "test_heartbeat":
        _require_client(body)
        return {"ok": True}

    # ── Admin actions ──────────────────────────────────────────────────────────
    if action == "list":
        _require_admin(body)
        rows = _all(
            "SELECT hwid, last_seen, app_version, public_ip, hostname,"
            "  licensed_local, license_error, expires_at_local, duration,"
            "  licensed_db, license_db_expires, license_db_plan,"
            "  banned, ban_reason, force_update, blocked_versions,"
            "  trial_started_at, trial_expires_at, updated_at"
            " FROM clients ORDER BY last_seen DESC"
        )
        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()
        return {"ok": True, "clients": rows}

    if action == "add_license":
        _require_admin(body)
        hwid    = "".join(c for c in (body.get("hwid") or "").upper() if c.isalnum())
        lic_key = (body.get("license_key") or "").strip()
        plan_id = (body.get("plan_id") or "custom").strip()
        plan_lb = (body.get("plan_label") or plan_id).strip()
        expires = body.get("expires_at")
        note    = (body.get("note") or "").strip()
        user_r  = _one("SELECT user_id FROM licenses WHERE hwid = %s LIMIT 1", (hwid,))
        uid     = str(user_r["user_id"]) if user_r else None
        _exec(
            "INSERT INTO licenses (id, user_id, license_key, hwid, plan_id,"
            "  plan_label, issued_at, expires_at, status, note)"
            " VALUES (%s, %s::uuid, %s, %s, %s, %s, now(), %s, 'active', %s)"
            " ON CONFLICT (license_key) DO NOTHING",
            (str(_uuid.uuid4()), uid, lic_key, hwid, plan_id, plan_lb, expires, note),
        )
        return {"ok": True}

    if action == "set_ban":
        _require_admin(body)
        hwid_n = "".join(c for c in (body.get("hwid_norm") or body.get("hwid") or "").upper() if c.isalnum())
        _exec(
            "UPDATE clients SET banned = %s, ban_reason = %s, updated_at = now()"
            " WHERE hwid = %s",
            (bool(body.get("banned")), (body.get("reason") or "").strip(), hwid_n),
        )
        return {"ok": True}

    if action == "set_update_policy":
        _require_admin(body)
        hwid_n = "".join(c for c in (body.get("hwid_norm") or body.get("hwid") or "").upper() if c.isalnum())
        sets, params = ["updated_at = now()"], []
        if body.get("force_update") is not None:
            sets.append("force_update = %s"); params.append(bool(body["force_update"]))
        if body.get("lock_version"):
            sets.append("blocked_versions = array_append(blocked_versions, %s)"); params.append(str(body["lock_version"]))
        if body.get("unlock_version"):
            sets.append("blocked_versions = array_remove(blocked_versions, %s)"); params.append(str(body["unlock_version"]))
        params.append(hwid_n)
        _exec(f"UPDATE clients SET {', '.join(sets)} WHERE hwid = %s", params)
        return {"ok": True}

    # ── Client heartbeat ───────────────────────────────────────────────────────
    _require_client(body)

    hwid       = "".join(c for c in (body.get("hwid_norm") or body.get("hwid") or "").upper() if c.isalnum())
    app_ver    = (body.get("app_version") or "").strip()
    public_ip  = (body.get("public_ip") or "").strip()
    hostname   = (body.get("hostname") or "").strip() or socket.gethostname()
    licensed   = bool(body.get("licensed"))
    has_key    = bool(body.get("has_saved_key"))
    lic_error  = (body.get("license_error") or "")
    exp_at     = (body.get("expires_at") or "")
    duration   = (body.get("duration") or "")

    if not hwid:
        raise HTTPException(400, "hwid required")

    now = datetime.now(timezone.utc)

    # Upsert client
    _exec(
        "INSERT INTO clients"
        "  (hwid, last_seen, app_version, public_ip, hostname,"
        "   licensed_local, license_error, expires_at_local, duration, updated_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (hwid) DO UPDATE SET"
        "   last_seen        = EXCLUDED.last_seen,"
        "   app_version      = EXCLUDED.app_version,"
        "   public_ip        = EXCLUDED.public_ip,"
        "   hostname         = EXCLUDED.hostname,"
        "   licensed_local   = EXCLUDED.licensed_local,"
        "   license_error    = EXCLUDED.license_error,"
        "   expires_at_local = EXCLUDED.expires_at_local,"
        "   duration         = EXCLUDED.duration,"
        "   updated_at       = EXCLUDED.updated_at",
        (hwid, now, app_ver, public_ip, hostname,
         licensed, lic_error, exp_at, duration, now),
    )

    client = _one("SELECT * FROM clients WHERE hwid = %s", (hwid,))
    if not client:
        raise HTTPException(500, "client upsert failed")

    # Ban / update policy flags
    banned     = bool(client.get("banned"))
    ban_reason = str(client.get("ban_reason") or "")
    force_upd  = bool(client.get("force_update"))
    blocked    = list(client.get("blocked_versions") or [])
    ver_blocked= bool(app_ver and app_ver in blocked)

    # Trial management (only when unlicensed and no saved key)
    trial_active = False
    trial_start  = ""
    trial_end    = ""
    trial_secs   = 0

    if not licensed and not has_key:
        days_row   = _one("SELECT value FROM site_settings WHERE key = 'trial'")
        trial_days = int((days_row.get("value") or {}).get("days", 1)) if days_row else 1

        if not client.get("trial_started_at"):
            t_start = now
            t_end   = now + timedelta(days=trial_days)
            _exec(
                "UPDATE clients SET trial_started_at = %s, trial_expires_at = %s WHERE hwid = %s",
                (t_start, t_end, hwid),
            )
            client["trial_started_at"] = t_start
            client["trial_expires_at"] = t_end

        t_s = client.get("trial_started_at")
        t_e = client.get("trial_expires_at")
        if t_s and t_e:
            if isinstance(t_e, str):
                t_e = datetime.fromisoformat(t_e)
            if t_e.tzinfo is None:
                t_e = t_e.replace(tzinfo=timezone.utc)
            remaining    = max(0, int((t_e - now).total_seconds()))
            trial_active = remaining > 0
            trial_start  = t_s.isoformat() if hasattr(t_s, "isoformat") else str(t_s)
            trial_end    = t_e.isoformat()
            trial_secs   = remaining

    # Server-side license check from Neon
    lic_row   = _one(
        "SELECT license_key, plan_id, expires_at FROM licenses"
        " WHERE hwid = %s AND status = 'active' ORDER BY issued_at DESC LIMIT 1",
        (hwid,),
    )
    licensed_server   = False
    expires_at_server = ""
    plan_id_server    = ""

    if lic_row:
        exp = lic_row.get("expires_at")
        is_valid = exp is None or (isinstance(exp, datetime) and
                                   (exp.tzinfo is None and exp > datetime.utcnow() or
                                    exp.tzinfo is not None and exp > now))
        if is_valid:
            licensed_server   = True
            expires_at_server = exp.isoformat() if isinstance(exp, datetime) else ("lifetime" if exp is None else str(exp))
            plan_id_server    = str(lic_row.get("plan_id") or "")
            _exec(
                "UPDATE clients SET licensed_db = true, license_db_expires = %s,"
                "  license_db_plan = %s WHERE hwid = %s",
                (expires_at_server, plan_id_server, hwid),
            )

    return {
        "ok":                      True,
        "banned":                  banned,
        "ban_reason":              ban_reason,
        "checked_at":              _utc_now(),
        "trial_active":            trial_active,
        "trial_started_at":        trial_start,
        "trial_expires_at":        trial_end,
        "trial_seconds_remaining": trial_secs,
        "force_update":            force_upd,
        "version_blocked":         ver_blocked,
        "command_reason":          "",
        "licensed_server":         licensed_server,
        "expires_at_server":       expires_at_server,
        "plan_id":                 plan_id_server,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN HELPERS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/admin/set-password")
async def admin_set_password(request: Request):
    """Set bcrypt password for a user (admin-only)."""
    body = await request.json()
    if not ADMIN_TOKEN or (body.get("admin_token") or "").strip() != ADMIN_TOKEN:
        raise HTTPException(403, "forbidden")
    email = (body.get("email") or "").strip().lower()
    pw    = (body.get("password") or "").strip()
    if not email or not pw:
        raise HTTPException(400, "email and password required")
    row = _one("SELECT id::text FROM profiles WHERE email = %s", (email,))
    if not row:
        raise HTTPException(404, "user not found")
    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    _exec(
        "INSERT INTO user_auth (user_id, password_hash) VALUES (%s::uuid, %s)"
        " ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash",
        (row["id"], pw_hash),
    )
    return {"ok": True}


@app.post("/api/admin/upload-image")
async def admin_upload_image(request: Request, file: UploadFile = File(...)):
    """Upload a demo image to Hostinger via FTP and return public URL. Admin only."""
    import ftplib, io as _io

    uid, is_admin = _optional_auth(request)
    if not is_admin:
        raise HTTPException(403, "admin required")

    ftp_host = os.environ.get("FTP_HOST", "153.92.8.124")
    ftp_user = os.environ.get("FTP_USER", "u888361453.wwmoverlay.com")
    ftp_pass = os.environ.get("FTP_PASS", "")
    if not ftp_pass:
        raise HTTPException(503, "FTP_PASS not configured in Modal secrets")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "file too large (max 10 MB)")

    fname    = (file.filename or "image.jpg").replace("/", "-").replace("\\", "-")
    ext      = fname.rsplit(".", 1)[-1].lower()[:8] if "." in fname else "jpg"
    if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
        ext = "jpg"
    filename = f"{int(time.time())}-{secrets.token_hex(4)}.{ext}"

    try:
        with ftplib.FTP() as ftp:
            ftp.connect(ftp_host, 21, timeout=30)
            ftp.login(ftp_user, ftp_pass)
            ftp.set_pasv(True)
            # Create upload dirs if needed (FTP CWD = public_html/ after login)
            for d in ("uploads", "uploads/demo-images"):
                try:
                    ftp.mkd(d)
                except ftplib.error_perm:
                    pass  # already exists
            ftp.storbinary(f"STOR uploads/demo-images/{filename}", _io.BytesIO(content))
    except ftplib.all_errors as e:
        raise HTTPException(500, f"FTP upload failed: {e}")

    return {"ok": True, "url": f"https://wwmoverlay.com/uploads/demo-images/{filename}"}


@app.get("/health")
async def health():
    return {"ok": True, "ts": _utc_now()}


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH EXTRAS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/v1/signup")
async def auth_signup(request: Request):
    """Register a new user with email + password."""
    body     = await request.json()
    email    = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    full_name = body.get("full_name") or None

    if not email or not password:
        raise HTTPException(400, "email and password required")
    if len(password) < 6:
        raise HTTPException(400, "password must be at least 6 characters")

    existing = _one("SELECT id FROM profiles WHERE email = %s", (email,))
    if existing:
        raise HTTPException(400, "User already registered")

    user_id = _upsert_oauth_user(email, full_name or "", "")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    _exec(
        "INSERT INTO user_auth (user_id, password_hash) VALUES (%s::uuid, %s)"
        " ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash",
        (user_id, pw_hash),
    )
    return {"message": "Account created. You can now sign in."}


@app.post("/auth/v1/user/password")
async def auth_update_password(request: Request):
    """Update password for the authenticated user."""
    claims   = _auth_user(request)
    body     = await request.json()
    password = (body.get("password") or "").strip()
    if len(password) < 6:
        raise HTTPException(400, "password must be at least 6 characters")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    _exec(
        "INSERT INTO user_auth (user_id, password_hash) VALUES (%s::uuid, %s)"
        " ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash",
        (claims["sub"], pw_hash),
    )
    return {"message": "Password updated"}


# ══════════════════════════════════════════════════════════════════════════════
#  GENERIC POSTGREST-COMPATIBLE REST LAYER  /rest/v1/{table}
# ══════════════════════════════════════════════════════════════════════════════

import re as _re

# Row-level rules per table
_TABLE_RULES: dict[str, dict] = {
    # public_read: anon users can GET
    # user_col:    column that links a row to its owner (RLS key)
    # user_write:  owner can PATCH their own rows
    # user_insert: authenticated users can POST
    "site_settings":   dict(public_read=True,  user_col=None,           user_write=False, user_insert=False),
    "profiles":        dict(public_read=False, user_col="id",           user_write=True,  user_insert=False),
    "licenses":        dict(public_read=False, user_col="user_id",      user_write=False, user_insert=False),
    "orders":          dict(public_read=False, user_col="user_id",      user_write=True,  user_insert=True),
    "notifications":   dict(public_read=False, user_col="user_id",      user_write=True,  user_insert=False),
    "referral_events": dict(public_read=False, user_col="referrer_id",  user_write=False, user_insert=False),
    "payment_config":  dict(public_read=True,  user_col=None,           user_write=False, user_insert=False),
    "faq":             dict(public_read=True,  user_col=None,           user_write=False, user_insert=False),
    "demo_images":     dict(public_read=True,  user_col=None,           user_write=False, user_insert=False),
    "blacklist":       dict(public_read=False, user_col=None,           user_write=False, user_insert=False),
    "clients":         dict(public_read=False, user_col=None,           user_write=False, user_insert=False),
    "visits":          dict(public_read=False, user_col=None,           user_write=False, user_insert=False),
}

_IDENT_RE = _re.compile(r'^[a-z_][a-z0-9_]*$')


def _safe_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise HTTPException(400, f"invalid identifier: {name!r}")
    return name


def _parse_postgrest(params: dict, exclude: set | None = None) -> tuple[list, list]:
    """Parse PostgREST filter params → (where_clauses, values)."""
    skip = (exclude or set()) | {"select", "order", "limit", "offset"}
    clauses, values = [], []
    for key, raw in params.items():
        if key in skip:
            continue
        _safe_ident(key)
        if raw.startswith("eq."):
            clauses.append(f"{key} = %s")
            values.append(raw[3:])
        elif raw.startswith("neq."):
            clauses.append(f"{key} != %s")
            values.append(raw[4:])
        elif raw.startswith("in.(") and raw.endswith(")"):
            vals = [v.strip() for v in raw[4:-1].split(",") if v.strip()]
            if vals:
                clauses.append(f"{key} IN ({','.join(['%s']*len(vals))})")
                values.extend(vals)
        elif raw == "is.null":
            clauses.append(f"{key} IS NULL")
        elif raw in ("is.not.null", "not.is.null"):
            clauses.append(f"{key} IS NOT NULL")
        elif raw.startswith("gte."):
            clauses.append(f"{key} >= %s"); values.append(raw[4:])
        elif raw.startswith("lte."):
            clauses.append(f"{key} <= %s"); values.append(raw[4:])
        elif raw.startswith("gt."):
            clauses.append(f"{key} > %s"); values.append(raw[3:])
        elif raw.startswith("lt."):
            clauses.append(f"{key} < %s"); values.append(raw[3:])
        elif raw.startswith("ilike."):
            clauses.append(f"{key} ILIKE %s"); values.append(raw[6:])
        elif raw.startswith("like."):
            clauses.append(f"{key} LIKE %s"); values.append(raw[5:])
    return clauses, values


def _optional_auth(request: Request) -> tuple[str | None, bool]:
    """Return (user_id, is_admin). Both falsy when not authenticated."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, False
    try:
        claims  = _decode_jwt(auth[7:])
        uid     = claims.get("sub")
        if uid:
            row = _one("SELECT is_admin FROM profiles WHERE id = %s::uuid", (uid,))
            return uid, bool(row and row.get("is_admin"))
    except Exception:
        pass
    return None, False


@app.get("/rest/v1/{table}")
async def rest_get(table: str, request: Request):
    if table == "site_settings" or table == "profiles":
        # Handled by specific routes above — but FastAPI matches specific routes first,
        # so this branch is only hit for other tables.
        pass
    if table not in _TABLE_RULES:
        raise HTTPException(404, "table not found")
    rules = _TABLE_RULES[table]

    uid, is_admin = _optional_auth(request)
    if not rules["public_read"] and not uid:
        raise HTTPException(401, "authentication required")

    params     = dict(request.query_params)
    select_raw = params.get("select", "*")
    order_raw  = params.get("order", "")
    limit_raw  = params.get("limit", "")

    select_sql = "*" if select_raw == "*" else ", ".join(
        _safe_ident(c.strip()) for c in select_raw.split(",") if c.strip()
    )

    where, vals = _parse_postgrest(params)

    # RLS: non-admin users see only their own rows
    if not is_admin and rules["user_col"] and uid:
        where.append(f'{rules["user_col"]} = %s::uuid')
        vals.append(uid)
    elif not is_admin and rules["user_col"] and not uid:
        return []  # no uid → empty result for user-owned tables

    sql = f"SELECT {select_sql} FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if order_raw:
        parts = order_raw.split(".")
        col   = _safe_ident(parts[0])
        direction = "DESC" if len(parts) > 1 and parts[1].lower() == "desc" else "ASC"
        sql += f" ORDER BY {col} {direction}"
    if limit_raw:
        try:
            sql += f" LIMIT {int(limit_raw)}"
        except ValueError:
            pass

    return _all(sql, vals)


@app.post("/rest/v1/{table}")
async def rest_insert(table: str, request: Request):
    if table not in _TABLE_RULES:
        raise HTTPException(404, "table not found")
    rules = _TABLE_RULES[table]

    uid, is_admin = _optional_auth(request)
    if not is_admin:
        if not rules["user_insert"]:
            raise HTTPException(403, "insert not allowed")
        if not uid:
            raise HTTPException(401, "authentication required")

    body = await request.json()

    # RLS: force owner column to current user
    if not is_admin and uid and rules["user_col"]:
        body[rules["user_col"]] = uid

    cols         = [_safe_ident(c) for c in body.keys()]
    placeholders = ", ".join(["%s"] * len(cols))
    vals         = [body[c] for c in cols]

    # Upsert support: ?prefer=upsert&on_conflict=<col>
    prefer      = request.query_params.get("prefer", "")
    on_conflict = request.query_params.get("on_conflict", "")

    if prefer == "upsert" and on_conflict:
        conflict_col = _safe_ident(on_conflict)
        update_cols  = [c for c in cols if c != conflict_col]
        if update_cols:
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
                f" ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause} RETURNING *"
            )
        else:
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
                f" ON CONFLICT ({conflict_col}) DO NOTHING RETURNING *"
            )
        row = _one(sql, vals)
    else:
        row = _one(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) RETURNING *",
            vals,
        )
    return row


@app.patch("/rest/v1/{table}")
async def rest_update(table: str, request: Request):
    if table not in _TABLE_RULES:
        raise HTTPException(404, "table not found")
    rules = _TABLE_RULES[table]

    uid, is_admin = _optional_auth(request)
    if not is_admin:
        if not rules["user_write"]:
            raise HTTPException(403, "write not allowed")
        if not uid:
            raise HTTPException(401, "authentication required")

    body   = await request.json()
    params = dict(request.query_params)

    set_cols   = [_safe_ident(c) for c in body.keys()]
    set_clause = ", ".join(f"{c} = %s" for c in set_cols)
    set_vals   = [body[c] for c in set_cols]

    where, where_vals = _parse_postgrest(params)
    if not is_admin and uid and rules["user_col"]:
        where.append(f'{rules["user_col"]} = %s::uuid')
        where_vals.append(uid)

    if not where:
        raise HTTPException(400, "update requires at least one filter")

    rows = _all(
        f"UPDATE {table} SET {set_clause} WHERE {' AND '.join(where)} RETURNING *",
        set_vals + where_vals,
    )
    return rows


@app.delete("/rest/v1/{table}")
async def rest_delete_table(table: str, request: Request):
    if table not in _TABLE_RULES:
        raise HTTPException(404, "table not found")

    _, is_admin = _optional_auth(request)
    if not is_admin:
        raise HTTPException(403, "delete requires admin")

    params = dict(request.query_params)
    where, vals = _parse_postgrest(params)
    if not where:
        raise HTTPException(400, "delete requires at least one filter")

    rows = _all(
        f"DELETE FROM {table} WHERE {' AND '.join(where)} RETURNING id",
        vals,
    )
    return rows


# ── Visit tracking ─────────────────────────────────────────────────────────────

@app.post("/functions/v1/track-visit")
async def track_visit(request: Request):
    """Record a page visit (replaces Supabase Edge Function)."""
    try:
        body     = await request.json()
        page     = (body.get("page") or "/")[:200]
        referral = (body.get("referral_code") or None)
        ip       = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or None
        _exec(
            "INSERT INTO visits (page, referral_code, ip, visited_at)"
            " VALUES (%s, %s, %s, NOW())"
            " ON CONFLICT DO NOTHING",
            (page, referral, ip),
        )
    except Exception:
        pass  # fire-and-forget — never block the user
    return {"ok": True}


@app.post("/rest/v1/rpc/public_visit_stats")
async def rpc_visit_stats(request: Request):
    """Public visitor stats for the homepage globe."""
    try:
        body      = await request.json()
        days_back = int(body.get("days_back", 30))
    except Exception:
        days_back = 30
    rows = _all(
        "SELECT COUNT(*) AS total_visits,"
        " COUNT(DISTINCT ip) AS unique_ips"
        " FROM visits WHERE visited_at >= NOW() - make_interval(days => %s)",
        (days_back,),
    )
    return rows[0] if rows else {"total_visits": 0, "unique_ips": 0}


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP HELPERS FOR OAUTH
# ══════════════════════════════════════════════════════════════════════════════

def _http_post(url: str, data: dict, *, form: bool = False) -> dict:
    if form:
        encoded = urllib.parse.urlencode(data).encode()
        ct = "application/x-www-form-urlencoded"
    else:
        encoded = json.dumps(data).encode()
        ct = "application/json"
    req = urllib.request.Request(
        url, data=encoded,
        headers={"Content-Type": ct, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def _http_get(url: str, *, bearer: str = "") -> dict:
    hdrs = {"Accept": "application/json"}
    if bearer:
        hdrs["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


# ── Local dev entry-point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
