"""GitHub Releases updater for PingOverlay.

Flow:
  1. Check latest release metadata from GitHub Releases.
  2. Compare semantic version against local build version.
  3. Download release asset `PingOverlay-vX.Y.Z.exe` to a temp file.
  4. Verify SHA-256 digest when GitHub provides `digest`.
  5. Spawn a hidden PowerShell helper that waits for current PID to exit,
     replaces the old exe, and relaunches the app.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from github_api import github_headers
from release_gateway import fetch_asset_chunk, latest_update_info, is_enabled as release_gateway_enabled


GITHUB_API_BASE = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "PingOverlay-Updater",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Public update-repo for the installer (onedir) edition.
# Files are served via raw.githubusercontent.com — no auth, no rate-limit.
UPDATE_REPO_RAW = "https://raw.githubusercontent.com/KimiseVN/wwmoverlay-update/main"

# Skip-marker: written before the update helper is spawned so that if the
# copy fails (e.g. files still locked) the app does not loop-prompt on the
# next launch.  Expires after 5 minutes — long enough to survive a relaunch,
# short enough that a genuinely retry-able failure isn't suppressed forever.
_UPDATE_SKIP_MARKER = Path(tempfile.gettempdir()) / "pingoverlay-update-skip.txt"
_SKIP_MARKER_TTL    = 300  # seconds


@dataclass
class UpdateInfo:
    version: str
    tag: str
    repo: str
    release_url: str
    asset_name: str
    asset_url: str
    asset_size: int
    asset_digest: str | None
    via_gateway: bool = False
    # Incremental (onedir/installer) path — set when using the update repo
    incremental: bool = False
    manifest: dict | None = None


def is_supported_runtime() -> bool:
    return bool(getattr(sys, "frozen", False)) and sys.executable.lower().endswith(".exe")


def cleanup_stale_update_artifacts() -> None:
    if not is_supported_runtime():
        return
    target_exe = Path(sys.executable).resolve()
    stale_paths = [
        Path(str(target_exe) + ".new"),
        Path(str(target_exe) + ".bad"),
    ]
    for path in stale_paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    backup = Path(str(target_exe) + ".old")
    try:
        if backup.exists() and target_exe.exists():
            backup.unlink(missing_ok=True)
    except Exception:
        pass


def _parse_version(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+)+)", text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _read_update_skip() -> str:
    """Return the version stored in the skip-marker if it is still fresh, else ''."""
    try:
        if not _UPDATE_SKIP_MARKER.exists():
            return ""
        age = time.time() - _UPDATE_SKIP_MARKER.stat().st_mtime
        if age > _SKIP_MARKER_TTL:
            return ""
        return _UPDATE_SKIP_MARKER.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _write_update_skip(version: str) -> None:
    """Persist a skip-marker so repeated update prompts are suppressed."""
    try:
        _UPDATE_SKIP_MARKER.write_text(version, encoding="utf-8")
    except Exception:
        pass


def _json_get(url: str, cfg: dict | None = None) -> Any:
    req = request.Request(url, headers=github_headers(cfg, user_agent=API_HEADERS["User-Agent"]))
    with request.urlopen(req, timeout=12) as resp:
        return json.load(resp)


def _asset_from_release(
    release: dict,
    asset_name: str | None,
    asset_prefix: str,
    fallback_asset_prefixes: list[str] | None,
    asset_extension: str,
    version: str,
) -> dict | None:
    assets = release.get("assets") or []
    expected_names: list[str] = []
    if asset_prefix and asset_extension:
        expected_names.append(f"{asset_prefix}{version}{asset_extension}")
    for prefix in fallback_asset_prefixes or []:
        prefix = str(prefix or "").strip()
        if prefix and asset_extension:
            expected_names.append(f"{prefix}{version}{asset_extension}")
    if asset_name:
        expected_names.append(asset_name)
    for expected_name in expected_names:
        for asset in assets:
            if (asset.get("name") or "") == expected_name:
                return asset
        expected_name_lower = expected_name.lower()
        for asset in assets:
            if (asset.get("name") or "").lower() == expected_name_lower:
                return asset
    version_lower = version.lower()
    prefix_lower = asset_prefix.lower()
    extension_lower = asset_extension.lower()
    for asset in assets:
        name = str(asset.get("name") or "")
        name_lower = name.lower()
        if (
            name_lower.endswith(extension_lower)
            and version_lower in name_lower
            and (not prefix_lower or name_lower.startswith(prefix_lower))
        ):
            return asset
    return None


def _release_candidates(repo: str, include_prerelease: bool, cfg: dict | None = None) -> list[dict]:
    # Use the releases list even for stable-only mode so we can filter by
    # a product-specific tag prefix inside a monorepo.
    url = f"{GITHUB_API_BASE}/repos/{repo}/releases?per_page=20"
    data = _json_get(url, cfg)
    return data if isinstance(data, list) else []


def _public_asset_download_url(
    repo: str,
    tag: str,
    asset_name: str,
    cfg: dict | None = None,
) -> str:
    """Resolve a public GitHub release asset to browser_download_url.

    The Apps Script gateway is still the source of truth for "latest version",
    but public repositories do not need to proxy a 30MB EXE through Apps
    Script. Resolving the public asset URL here keeps tokens out of the app
    and makes downloads substantially faster.
    """
    repo = str(repo or "").strip()
    tag = str(tag or "").strip()
    asset_name = str(asset_name or "").strip()
    if not repo or not tag or not asset_name:
        return ""
    try:
        release = _json_get(
            f"{GITHUB_API_BASE}/repos/{repo}/releases/tags/{tag}",
            cfg,
        )
    except Exception as exc:
        print(f"[update] public release URL resolve failed: {exc}")
        return ""
    if not isinstance(release, dict):
        return ""
    for asset in release.get("assets") or []:
        if str(asset.get("name") or "").lower() == asset_name.lower():
            return str(asset.get("browser_download_url") or "").strip()
    return ""


def check_for_update(cfg: dict, current_version: str) -> UpdateInfo | None:
    update_cfg = cfg.get("update") or {}
    if not update_cfg.get("enabled", True):
        return None

    repo = (update_cfg.get("repo") or "").strip()
    tag_prefix = (update_cfg.get("tag_prefix") or "").strip().lower()
    asset_name = (update_cfg.get("asset_name") or "").strip() or None
    asset_prefix = (update_cfg.get("asset_prefix") or "PingOverlay-v").strip()
    raw_fallback_prefixes = update_cfg.get("fallback_asset_prefixes") or []
    fallback_asset_prefixes = [
        str(prefix).strip()
        for prefix in raw_fallback_prefixes
        if str(prefix or "").strip()
    ] if isinstance(raw_fallback_prefixes, list) else ["WWMOverlay-v"]
    asset_extension = (update_cfg.get("asset_extension") or ".exe").strip()
    include_prerelease = bool(update_cfg.get("include_prerelease", False))
    if not repo or (not asset_name and not asset_prefix):
        return None

    current = _parse_version(current_version)
    if not current:
        return None

    try:
        metadata_timeout = float(update_cfg.get("metadata_timeout_seconds", 8.0))
    except (TypeError, ValueError):
        metadata_timeout = 8.0
    metadata_timeout = max(3.0, min(15.0, metadata_timeout))

    gateway_is_enabled = release_gateway_enabled(cfg)
    gateway_failed = False
    try:
        gateway_info = latest_update_info(current_version, cfg=cfg, timeout=metadata_timeout)
    except Exception as exc:
        print(f"[update] release gateway check failed: {exc}")
        gateway_info = None
        gateway_failed = True
    if gateway_info:
        gateway_asset_name = str(gateway_info.get("asset_name") or "")
        direct_asset_url = str(gateway_info.get("asset_url") or gateway_info.get("browser_download_url") or "").strip()
        if not direct_asset_url:
            direct_asset_url = _public_asset_download_url(
                str(gateway_info.get("repo") or repo),
                str(gateway_info.get("tag") or ""),
                gateway_asset_name,
                cfg,
            )
        return UpdateInfo(
            version=str(gateway_info.get("version") or ""),
            tag=str(gateway_info.get("tag") or ""),
            repo=str(gateway_info.get("repo") or repo),
            release_url=str(gateway_info.get("release_url") or ""),
            asset_name=gateway_asset_name,
            asset_url=direct_asset_url or ("gateway:" + gateway_asset_name),
            asset_size=int(gateway_info.get("asset_size") or 0),
            asset_digest=str(gateway_info.get("asset_digest") or "") or None,
            via_gateway=not bool(direct_asset_url),
        )
    if gateway_is_enabled and not gateway_failed:
        return None

    try:
        releases = _release_candidates(repo, include_prerelease, cfg)
    except error.HTTPError as e:
        if e.code == 404:
            print(f"[update] releases not found for repo {repo}")
            return None
        raise

    for release in releases:
        if not include_prerelease and release.get("prerelease"):
            continue
        tag = (release.get("tag_name") or release.get("name") or "").strip()
        tag_lower = tag.lower()
        if tag_prefix and not tag_lower.startswith(tag_prefix):
            continue
        version_text = tag[len(tag_prefix):] if tag_prefix and tag_lower.startswith(tag_prefix) else tag
        latest = _parse_version(version_text)
        if not latest or latest <= current:
            continue
        version_string = ".".join(str(part) for part in latest)
        asset = _asset_from_release(
            release,
            asset_name,
            asset_prefix,
            fallback_asset_prefixes,
            asset_extension,
            version_string,
        )
        if asset is None:
            print(
                "[update] latest release "
                f"{tag} has no matching asset for version {version_string}; checking older releases"
            )
            continue
        return UpdateInfo(
            version=version_string,
            tag=tag,
            repo=repo,
            release_url=release.get("html_url") or "",
            asset_name=asset.get("name") or asset_name or f"{asset_prefix}{version_string}{asset_extension}",
            asset_url=asset.get("browser_download_url") or "",
            asset_size=int(asset.get("size") or 0),
            asset_digest=asset.get("digest"),
        )
    return None


def download_update(info: UpdateInfo, cfg: dict | None = None) -> Path:
    suffix = Path(info.asset_name).suffix or ".bin"
    fd, temp_name = tempfile.mkstemp(prefix="pingoverlay-update-", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)

    hasher = hashlib.sha256()
    if info.via_gateway:
        _download_update_via_gateway(info, cfg, temp_path, hasher)
        _verify_downloaded_update(info, temp_path, hasher)
        return temp_path

    req = request.Request(info.asset_url, headers=github_headers(cfg, user_agent=API_HEADERS["User-Agent"]))
    try:
        with request.urlopen(req, timeout=30) as resp, open(temp_path, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(
            f"Failed to download update from {info.asset_url}: {exc}"
        ) from exc

    _verify_downloaded_update(info, temp_path, hasher)
    return temp_path


def _verify_downloaded_update(info: UpdateInfo, temp_path: Path, hasher: hashlib._Hash) -> None:
    digest = (info.asset_digest or "").strip()
    if digest.startswith("sha256:"):
        expected = digest.split(":", 1)[1].lower()
        actual = hasher.hexdigest().lower()
        if actual != expected:
            temp_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded update failed SHA-256 verification")

    if info.asset_size > 0 and temp_path.stat().st_size != info.asset_size:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded update size does not match release metadata")


def _download_update_via_gateway(
    info: UpdateInfo,
    cfg: dict | None,
    temp_path: Path,
    hasher: hashlib._Hash,
) -> None:
    # Apps Script JSON responses and intermediates are unreliable with
    # multi-megabyte base64 payloads. Keep chunks modest; newer gateway
    # deployments cap older clients to the same safe size server-side.
    chunk_size = 512 * 1024
    offset = 0
    try:
        with open(temp_path, "wb") as out:
            while True:
                data = fetch_asset_chunk(
                    info.asset_name,
                    offset,
                    chunk_size,
                    cfg=cfg,
                    timeout=45.0,
                )
                raw_b64 = str(data.get("data_b64") or "")
                if not raw_b64:
                    raise RuntimeError("release gateway returned an empty update chunk")
                chunk = base64.b64decode(raw_b64)
                if not chunk:
                    raise RuntimeError("release gateway returned an empty decoded update chunk")
                out.write(chunk)
                hasher.update(chunk)
                offset += len(chunk)
                total_size = int(data.get("asset_size") or info.asset_size or 0)
                if total_size and total_size != info.asset_size:
                    info.asset_size = total_size
                if bool(data.get("done")) or (info.asset_size > 0 and offset >= info.asset_size):
                    break
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ── Incremental (onedir / setup-edition) update helpers ──────────────────────

def check_incremental_update(current_version: str) -> "UpdateInfo | None":
    """Check the public update-repo manifest for a newer installer-edition build.

    Returns an UpdateInfo with ``incremental=True`` and ``manifest`` populated
    when a newer version is available, or None when already up to date.
    No config required — the update repo is always public.
    """
    # Read skip-marker first so we can suppress re-prompting when a previous
    # update attempt was already dispatched but the copy may not have landed yet.
    skip_version = _read_update_skip()

    try:
        url = f"{UPDATE_REPO_RAW}/manifest.json"
        req = request.Request(url, headers={"User-Agent": API_HEADERS["User-Agent"]})
        with request.urlopen(req, timeout=10) as resp:
            manifest: dict = json.load(resp)
    except Exception as exc:
        print(f"[update] incremental manifest fetch failed: {exc}")
        return None

    remote_version = str(manifest.get("version") or "").strip()
    if not remote_version:
        return None
    remote_parsed = _parse_version(remote_version)
    current_parsed = _parse_version(current_version)
    if not remote_parsed or remote_parsed <= current_parsed:
        return None

    # Suppress the prompt if we already dispatched an update for this version.
    # The marker expires in _SKIP_MARKER_TTL seconds, so a genuine failure
    # will surface again on the next cold launch.
    if skip_version and skip_version == remote_version:
        print(f"[update] skip-marker active for {remote_version}; not prompting (marker expires in {_SKIP_MARKER_TTL}s)")
        return None

    print(f"[update] incremental update available: {current_version} -> {remote_version}")
    return UpdateInfo(
        version=remote_version,
        tag=remote_version,
        repo="KimiseVN/wwmoverlay-update",
        release_url="https://github.com/KimiseVN/wwmoverlay-update",
        asset_name="incremental",
        asset_url=UPDATE_REPO_RAW,
        asset_size=0,
        asset_digest=None,
        via_gateway=False,
        incremental=True,
        manifest=manifest,
    )


def download_incremental_from_repo(
    manifest: dict,
    install_dir: Path,
    progress_cb: Any = None,
) -> Path:
    """Download only files that differ from what's in ``install_dir``.

    Files are fetched from ``UPDATE_REPO_RAW/{rel_path}`` — raw GitHub URLs
    support directory paths so the update folder's tree maps 1-to-1.

    Returns the staging directory.  The caller passes it to
    ``install_incremental_update()`` which applies it after the process exits.
    """
    manifest_files: dict[str, dict] = manifest.get("files", {})
    local_hashes = compute_local_hashes(install_dir)

    to_download: list[tuple[str, dict]] = []
    for rel_path, meta in manifest_files.items():
        # manifest.json is not in the files dict (generated after hash loop),
        # but guard here anyway; it is staged separately below.
        if rel_path == "manifest.json":
            continue
        expected_hash = str(meta.get("sha256") or "").lower()
        local_hash    = local_hashes.get(rel_path, "").lower()
        if expected_hash and local_hash == expected_hash:
            continue  # file unchanged
        to_download.append((rel_path, meta))

    print(f"[update] incremental: {len(to_download)} of {len(manifest_files)} files to download")

    stage_dir = Path(tempfile.mkdtemp(prefix="pingoverlay-stage-"))

    for i, (rel_path, meta) in enumerate(to_download):
        if progress_cb:
            try:
                progress_cb(i, len(to_download), rel_path)
            except Exception:
                pass

        # URL-encode the path so filenames with '+' (e.g. GMT+0) or spaces
        # (e.g. "Lorem ipsum.txt") don't get misinterpreted by the CDN.
        # safe='/' preserves path separators while encoding everything else.
        url  = f"{UPDATE_REPO_RAW}/{parse.quote(rel_path, safe='/')}"
        dest = stage_dir / rel_path.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(3):
            try:
                req = request.Request(url, headers={"User-Agent": API_HEADERS["User-Agent"]})
                with request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
                    hasher = hashlib.sha256()
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        hasher.update(chunk)
                expected = str(meta.get("sha256") or "").lower()
                if expected and hasher.hexdigest().lower() != expected:
                    raise RuntimeError(f"Hash mismatch for {rel_path}")
                break  # success
            except Exception as exc:
                if attempt == 2:
                    try:
                        import shutil
                        shutil.rmtree(stage_dir, ignore_errors=True)
                    except Exception:
                        pass
                    raise RuntimeError(f"Failed to download {rel_path}: {exc}") from exc
                time.sleep(2 ** attempt)  # 1s, 2s back-off

    # Always stage manifest.json so the installed copy is updated after patch.
    # This ensures compute_local_hashes on the next check compares against the
    # correct new manifest and avoids re-downloading unchanged files.
    try:
        (stage_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[update] warning: could not stage manifest.json: {exc}")

    return stage_dir


def is_onedir_install() -> bool:
    """True when running as an installed onedir build (not onefile portable).

    In onedir builds, sys._MEIPASS is a subdirectory of the EXE's folder
    (e.g. %ProgramFiles%\\PingOverlay\\_internal\\).
    In onefile builds, sys._MEIPASS is an unrelated temp directory.
    """
    if not getattr(sys, "frozen", False):
        return False
    meipass = Path(getattr(sys, "_MEIPASS", ""))
    exe_dir = Path(sys.executable).parent.resolve()
    try:
        meipass.resolve().relative_to(exe_dir)
        return True
    except ValueError:
        return False


def fetch_release_manifest(release: dict, repo: str, cfg: dict | None = None) -> dict | None:
    """Try to fetch manifest.json from a GitHub release's assets.

    Returns the parsed JSON dict, or None if not present.
    """
    for asset in release.get("assets") or []:
        if str(asset.get("name") or "").lower() == "manifest.json":
            url = str(asset.get("browser_download_url") or "").strip()
            if not url:
                continue
            try:
                req = request.Request(
                    url,
                    headers=github_headers(cfg, user_agent=API_HEADERS["User-Agent"]),
                )
                with request.urlopen(req, timeout=10) as resp:
                    data = json.load(resp)
                if isinstance(data, dict) and "files" in data:
                    return data
            except Exception as exc:
                print(f"[update] manifest.json fetch failed: {exc}")
    return None


def compute_local_hashes(install_dir: Path) -> dict[str, str]:
    """Return {relative_path: sha256_hex} for every file under install_dir."""
    result: dict[str, str] = {}
    for f in install_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(install_dir).as_posix()
        try:
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            result[rel] = h
        except Exception:
            pass
    return result


def download_incremental_update(
    manifest: dict,
    install_dir: Path,
    repo: str,
    tag: str,
    cfg: dict | None = None,
    progress_cb: Any = None,
) -> Path:
    """Download only files that differ from the manifest, into a staging dir.

    Returns the staging directory path.  The caller then calls
    install_incremental_update() to apply those files.
    """
    manifest_files: dict[str, dict] = manifest.get("files", {})
    local_hashes = compute_local_hashes(install_dir)

    # Determine which files need downloading
    to_download: list[tuple[str, dict]] = []
    for rel_path, meta in manifest_files.items():
        if rel_path == "manifest.json":
            continue
        expected_hash = str(meta.get("sha256") or "").lower()
        local_hash    = local_hashes.get(rel_path, "").lower()
        if expected_hash and local_hash == expected_hash:
            continue  # file unchanged
        to_download.append((rel_path, meta))

    print(f"[update] incremental: {len(to_download)} of {len(manifest_files)} files need updating")

    if not to_download:
        # Nothing to download — but still return a staging dir so caller
        # can apply manifest.json itself.
        stage_dir = Path(tempfile.mkdtemp(prefix="pingoverlay-stage-"))
        return stage_dir

    stage_dir = Path(tempfile.mkdtemp(prefix="pingoverlay-stage-"))
    base_release_url = f"https://github.com/{repo}/releases/download/{tag}"

    for i, (rel_path, meta) in enumerate(to_download):
        if progress_cb:
            try:
                progress_cb(i, len(to_download), rel_path)
            except Exception:
                pass

        url = f"{base_release_url}/{parse.quote(rel_path, safe='/')}"
        dest = stage_dir / rel_path.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(3):
            try:
                req = request.Request(
                    url,
                    headers=github_headers(cfg, user_agent=API_HEADERS["User-Agent"]),
                )
                with request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
                    hasher = hashlib.sha256()
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        hasher.update(chunk)

                expected = str(meta.get("sha256") or "").lower()
                if expected and hasher.hexdigest().lower() != expected:
                    raise RuntimeError(f"Hash mismatch for {rel_path}")
                break  # success
            except Exception as exc:
                if attempt == 2:
                    try:
                        import shutil
                        shutil.rmtree(stage_dir, ignore_errors=True)
                    except Exception:
                        pass
                    raise RuntimeError(f"Failed to download {rel_path}: {exc}") from exc
                time.sleep(2)

    return stage_dir


def install_incremental_update(
    stage_dir: Path,
    install_dir: Path,
    target_version: str = "",
) -> None:
    """Apply staged incremental update files by spawning a PowerShell helper.

    The helper:
      1. Waits for the current Python process (WaitPid) to exit.
      2. Kills ALL remaining PingOverlay.exe instances (autostart-race fix).
      3. Copies every file from stage_dir into install_dir, logging errors.
      4. Relaunches PingOverlay.exe.

    A skip-marker is written before the helper starts so that if the copy
    fails (e.g. a file was still locked) the app does not loop-prompt on the
    very next launch.
    """
    if not is_supported_runtime():
        raise RuntimeError("Incremental update only supported in packaged build")

    # Write skip-marker now so the next launch won't prompt for the same
    # version even if the copy fails (marker expires after _SKIP_MARKER_TTL s).
    if target_version:
        _write_update_skip(target_version)

    exe = Path(sys.executable).resolve()
    log_path    = Path(tempfile.gettempdir()) / f"pingoverlay-patch-{os.getpid()}.log"
    stamp_path  = Path(tempfile.gettempdir()) / f"pingoverlay-startup-{os.getpid()}.ok"
    helper_path = Path(tempfile.gettempdir()) / f"pingoverlay-patch-apply-{os.getpid()}.ps1"

    script_lines = [
        "param([int]$WaitPid,[string]$StageDir,[string]$InstallDir,[string]$ExePath,[string]$LogPath,[string]$StampPath)",
        "$ErrorActionPreference = 'Continue'",
        "function Write-Log([string]$msg) { Add-Content -LiteralPath $LogPath -Value ((Get-Date -Format o)+' '+$msg) }",
        "Write-Log 'patch helper started'",
        # Step 1: wait for the original process to exit
        "for ($i=0;$i-lt 240;$i++) { if (-not (Get-Process -Id $WaitPid -EA SilentlyContinue)) { break }; Start-Sleep -ms 500 }",
        "Write-Log 'original process exited'",
        # Step 2: kill ALL remaining PingOverlay instances (autostart race).
        # Any copy attempt while PingOverlay.exe is running will silently fail
        # because the launcher EXE and the .pkg archive are locked.
        "Write-Log 'stopping any remaining PingOverlay processes'",
        "Get-Process -Name 'PingOverlay' -EA SilentlyContinue | ForEach-Object { Write-Log ('killing pid='+$_.Id); Stop-Process -Id $_.Id -Force -EA SilentlyContinue }",
        "Start-Sleep -Milliseconds 1500",
        # Step 3: copy staged files, logging individual failures
        "Write-Log 'copying staged files'",
        "$copyErrors = 0",
        "Get-ChildItem -Path $StageDir -Recurse -File | ForEach-Object {",
        "  $rel = $_.FullName.Substring($StageDir.Length+1)",
        "  $dst = Join-Path $InstallDir $rel",
        "  $dstDir = Split-Path -Parent $dst",
        "  if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }",
        "  try {",
        "    Copy-Item -LiteralPath $_.FullName -Destination $dst -Force -EA Stop",
        "    Write-Log ('patched: '+$rel)",
        "  } catch {",
        "    Write-Log ('FAILED: '+$rel+' -- '+$_.Exception.Message)",
        "    $copyErrors++",
        "  }",
        "}",
        "Remove-Item -LiteralPath $StageDir -Recurse -Force -EA SilentlyContinue",
        "if ($copyErrors -gt 0) { Write-Log ('WARNING: '+$copyErrors+' file(s) failed to copy; update may be incomplete') }",
        "Write-Log 'patch done; relaunching'",
        # Step 4: relaunch
        "if (Test-Path -LiteralPath $StampPath) { Remove-Item -LiteralPath $StampPath -Force -EA SilentlyContinue }",
        "$proc = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath) -PassThru",
        "Write-Log ('relaunched pid='+$proc.Id)",
        "Remove-Item -LiteralPath $PSCommandPath -Force -EA SilentlyContinue",
    ]
    helper_path.write_text("\n".join(script_lines), encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", str(helper_path),
            str(os.getpid()), str(stage_dir), str(install_dir),
            str(exe), str(log_path), str(stamp_path),
        ],
        close_fds=True,
        creationflags=creationflags,
    )


def install_downloaded_update(download_path: Path, target_asset_name: str) -> None:
    if not is_supported_runtime():
        raise RuntimeError("Auto-update is only supported from the packaged .exe build")

    current_exe = Path(sys.executable).resolve()
    target_exe = current_exe.with_name(target_asset_name)
    log_path = Path(tempfile.gettempdir()) / f"pingoverlay-updater-{os.getpid()}.log"
    stamp_path = Path(tempfile.gettempdir()) / f"pingoverlay-startup-{os.getpid()}.ok"
    helper_path = Path(tempfile.gettempdir()) / f"pingoverlay-apply-update-{os.getpid()}.ps1"
    helper_path.write_text(
        "\n".join(
            [
                "param(",
                "  [int]$WaitPid,",
                "  [string]$SourcePath,",
                "  [string]$CurrentPath,",
                "  [string]$TargetPath,",
                "  [string]$LogPath,",
                "  [string]$StampPath",
                ")",
                "$ErrorActionPreference = 'Continue'",
                "function Write-Log([string]$Message) {",
                "  Add-Content -Path $LogPath -Value ((Get-Date -Format o) + ' ' + $Message)",
                "}",
                "Write-Log 'helper started'",
                "for ($i = 0; $i -lt 240; $i++) {",
                "  if (-not (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue)) { break }",
                "  Start-Sleep -Milliseconds 500",
                "}",
                "$targetDir = Split-Path -Parent $TargetPath",
                "$currentEqualsTarget = ([System.StringComparer]::OrdinalIgnoreCase.Equals($CurrentPath, $TargetPath))",
                "$backup = \"$TargetPath.old\"",
                "$staged = \"$TargetPath.new\"",
                "$failed = \"$TargetPath.bad\"",
                "$oldFailed = \"$CurrentPath.bad\"",
                "Write-Log ('current=' + $CurrentPath)",
                "Write-Log ('target=' + $TargetPath)",
                "if (Test-Path -LiteralPath $StampPath) { Remove-Item -LiteralPath $StampPath -Force }",
                "if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Force }",
                "Copy-Item -LiteralPath $SourcePath -Destination $staged -Force",
                "Write-Log 'copied update to staged path'",
                "if ($currentEqualsTarget) {",
                "  if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }",
                "  if (Test-Path -LiteralPath $TargetPath) { Move-Item -LiteralPath $TargetPath -Destination $backup -Force }",
                "} else {",
                "  if (Test-Path -LiteralPath $TargetPath) { Remove-Item -LiteralPath $TargetPath -Force }",
                "}",
                "Move-Item -LiteralPath $staged -Destination $TargetPath -Force",
                "Write-Log 'swapped executable'",
                "Start-Sleep -Seconds 2",
                "$started = $false",
                "for ($attempt = 1; $attempt -le 3; $attempt++) {",
                "  try {",
                "    Write-Log ('launch attempt ' + $attempt)",
                "    if (Test-Path -LiteralPath $StampPath) { Remove-Item -LiteralPath $StampPath -Force }",
                "    $proc = Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir -ArgumentList @('--update-stamp', $StampPath) -PassThru",
                "    for ($wait = 0; $wait -lt 30; $wait++) {",
                "      Start-Sleep -Seconds 1",
                "      if (Test-Path -LiteralPath $StampPath) {",
                "        $started = $true",
                "        break",
                "      }",
                "      if ($proc.HasExited) { break }",
                "    }",
                "    if ($started) {",
                "      $started = $true",
                "      Write-Log 'startup stamp received; launch successful'",
                "      break",
                "    }",
                "    if (-not $proc.HasExited) {",
                "      Write-Log 'process did not report startup stamp; terminating failed launch'",
                "      Stop-Process -Id $proc.Id -Force",
                "    } else {",
                "      Write-Log ('launch exited early with code ' + $proc.ExitCode)",
                "    }",
                "  } catch {",
                "    Write-Log ('launch error: ' + $_.Exception.Message)",
                "  }",
                "  Start-Sleep -Seconds 3",
                "}",
                "if ($started) {",
                "  Write-Log 'update finalized'",
                "  if (-not $currentEqualsTarget -and (Test-Path -LiteralPath $CurrentPath)) {",
                "    try { Remove-Item -LiteralPath $CurrentPath -Force } catch { Write-Log ('old exe cleanup failed: ' + $_.Exception.Message) }",
                "  }",
                "  if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }",
                "} elseif ($currentEqualsTarget -and (Test-Path -LiteralPath $backup)) {",
                "  Write-Log 'new build failed to stay up; rolling back backup'",
                "  if (Test-Path -LiteralPath $failed) { Remove-Item -LiteralPath $failed -Force }",
                "  if (Test-Path -LiteralPath $TargetPath) { Move-Item -LiteralPath $TargetPath -Destination $failed -Force }",
                "  Move-Item -LiteralPath $backup -Destination $TargetPath -Force",
                "  Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir",
                "} elseif (-not $currentEqualsTarget) {",
                "  Write-Log 'new version failed to start; preserving old exe and discarding new one'",
                "  if (Test-Path -LiteralPath $failed) { Remove-Item -LiteralPath $failed -Force }",
                "  if (Test-Path -LiteralPath $TargetPath) { Move-Item -LiteralPath $TargetPath -Destination $failed -Force }",
                "  if (Test-Path -LiteralPath $CurrentPath) { Start-Process -FilePath $CurrentPath -WorkingDirectory (Split-Path -Parent $CurrentPath) }",
                "}",
                "try { Remove-Item -LiteralPath $StampPath -Force } catch {}",
                "try { Remove-Item -LiteralPath $SourcePath -Force } catch {}",
                "Remove-Item -LiteralPath $PSCommandPath -Force",
            ]
        ),
        encoding="utf-8",
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(helper_path),
            str(os.getpid()),
            str(download_path),
            str(current_exe),
            str(target_exe),
            str(log_path),
            str(stamp_path),
        ],
        close_fds=True,
        creationflags=creationflags,
    )


def install_via_installer_setup(installer_path: Path) -> None:
    """Bridge transition: spawn a PS helper that cleans up old onefile exes and runs the installer.

    The helper:
      1. Waits for the current PID to exit.
      2. Kills all remaining PingOverlay.exe processes.
      3. Scans Desktop + Downloads for ``PingOverlay-v*.exe`` → deletes ALL.
      4. Launches the installer (Setup exe) silently.
    """
    if not is_supported_runtime():
        raise RuntimeError("Bridge install is only supported from a packaged build")

    log_path    = Path(tempfile.gettempdir()) / f"pingoverlay-bridge-{os.getpid()}.log"
    helper_path = Path(tempfile.gettempdir()) / f"pingoverlay-bridge-install-{os.getpid()}.ps1"

    script_lines = [
        "param([int]$WaitPid,[string]$InstallerPath,[string]$LogPath)",
        "$ErrorActionPreference = 'Continue'",
        "function Write-Log([string]$msg) { Add-Content -LiteralPath $LogPath -Value ((Get-Date -Format o)+' '+$msg) }",
        "Write-Log 'bridge helper started'",
        # Step 1: wait for the current process to exit (up to 2 minutes)
        "for ($i=0;$i-lt 240;$i++) { if (-not (Get-Process -Id $WaitPid -EA SilentlyContinue)) { break }; Start-Sleep -ms 500 }",
        "Write-Log 'original process exited'",
        # Step 2: kill any remaining PingOverlay instances
        "Get-Process -Name 'PingOverlay' -EA SilentlyContinue | ForEach-Object { Write-Log ('killing pid='+$_.Id); Stop-Process -Id $_.Id -Force -EA SilentlyContinue }",
        "Start-Sleep -Milliseconds 1000",
        # Step 3: scan Desktop + Downloads for PingOverlay-v*.exe and delete all
        "Write-Log 'scanning Desktop + Downloads for PingOverlay-v*.exe'",
        "$searchDirs = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Downloads'))",
        "foreach ($dir in $searchDirs) {",
        "  if (-not (Test-Path $dir)) { continue }",
        "  Get-ChildItem -Path $dir -Filter 'PingOverlay-v*.exe' -EA SilentlyContinue | ForEach-Object {",
        "    try { Remove-Item -LiteralPath $_.FullName -Force -EA Stop; Write-Log ('deleted: '+$_.FullName) }",
        "    catch { Write-Log ('delete failed: '+$_.FullName+' -- '+$_.Exception.Message) }",
        "  }",
        "}",
        # Step 4: launch the installer
        "Write-Log ('launching installer: '+$InstallerPath)",
        "Start-Process -FilePath $InstallerPath",
        "Write-Log 'installer launched'",
        "Remove-Item -LiteralPath $PSCommandPath -Force -EA SilentlyContinue",
    ]
    helper_path.write_text("\n".join(script_lines), encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", str(helper_path),
            str(os.getpid()), str(installer_path), str(log_path),
        ],
        close_fds=True,
        creationflags=creationflags,
    )
