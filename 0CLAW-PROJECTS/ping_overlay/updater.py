"""GitHub Releases updater for PingOverlay.

Flow:
  1. Check latest release metadata from GitHub Releases.
  2. Compare semantic version against local build version.
  3. Download release asset `PingOverlay.exe` to a temp file.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


GITHUB_API_BASE = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "PingOverlay-Updater",
    "X-GitHub-Api-Version": "2022-11-28",
}


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


def _json_get(url: str) -> Any:
    req = request.Request(url, headers=API_HEADERS)
    with request.urlopen(req, timeout=12) as resp:
        return json.load(resp)


def _asset_from_release(
    release: dict,
    asset_name: str | None,
    asset_prefix: str,
    asset_extension: str,
    version: str,
) -> dict | None:
    assets = release.get("assets") or []
    expected_names: list[str] = []
    if asset_prefix and asset_extension:
        expected_names.append(f"{asset_prefix}{version}{asset_extension}")
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
    return None


def _release_candidates(repo: str, include_prerelease: bool) -> list[dict]:
    # Use the releases list even for stable-only mode so we can filter by
    # a product-specific tag prefix inside a monorepo.
    url = f"{GITHUB_API_BASE}/repos/{repo}/releases?per_page=20"
    data = _json_get(url)
    return data if isinstance(data, list) else []


def check_for_update(cfg: dict, current_version: str) -> UpdateInfo | None:
    update_cfg = cfg.get("update") or {}
    if not update_cfg.get("enabled", True):
        return None

    repo = (update_cfg.get("repo") or "").strip()
    tag_prefix = (update_cfg.get("tag_prefix") or "").strip().lower()
    asset_name = (update_cfg.get("asset_name") or "").strip() or None
    asset_prefix = (update_cfg.get("asset_prefix") or "PingOverlay-v").strip()
    asset_extension = (update_cfg.get("asset_extension") or ".exe").strip()
    include_prerelease = bool(update_cfg.get("include_prerelease", False))
    if not repo or (not asset_name and not asset_prefix):
        return None

    current = _parse_version(current_version)
    if not current:
        return None

    try:
        releases = _release_candidates(repo, include_prerelease)
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
            asset_extension,
            version_string,
        )
        if asset is None:
            print(
                "[update] latest release "
                f"{tag} has no matching asset for version {version_string}"
            )
            return None
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


def download_update(info: UpdateInfo) -> Path:
    suffix = Path(info.asset_name).suffix or ".bin"
    fd, temp_name = tempfile.mkstemp(prefix="pingoverlay-update-", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)

    hasher = hashlib.sha256()
    req = request.Request(info.asset_url, headers={"User-Agent": API_HEADERS["User-Agent"]})
    try:
        with request.urlopen(req, timeout=30) as resp, open(temp_path, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

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

    return temp_path


def install_downloaded_update(download_path: Path) -> None:
    if not is_supported_runtime():
        raise RuntimeError("Auto-update is only supported from the packaged .exe build")

    target_exe = Path(sys.executable).resolve()
    log_path = Path(tempfile.gettempdir()) / f"pingoverlay-updater-{os.getpid()}.log"
    helper_path = Path(tempfile.gettempdir()) / f"pingoverlay-apply-update-{os.getpid()}.ps1"
    helper_path.write_text(
        "\n".join(
            [
                "param(",
                "  [int]$WaitPid,",
                "  [string]$SourcePath,",
                "  [string]$TargetPath,",
                "  [string]$LogPath",
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
                "$backup = \"$TargetPath.old\"",
                "$staged = \"$TargetPath.new\"",
                "$failed = \"$TargetPath.bad\"",
                "Write-Log ('target=' + $TargetPath)",
                "if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Force }",
                "Copy-Item -LiteralPath $SourcePath -Destination $staged -Force",
                "Write-Log 'copied update to staged path'",
                "if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }",
                "if (Test-Path -LiteralPath $TargetPath) { Move-Item -LiteralPath $TargetPath -Destination $backup -Force }",
                "Move-Item -LiteralPath $staged -Destination $TargetPath -Force",
                "Write-Log 'swapped executable'",
                "Start-Sleep -Seconds 2",
                "$started = $false",
                "for ($attempt = 1; $attempt -le 3; $attempt++) {",
                "  try {",
                "    Write-Log ('launch attempt ' + $attempt)",
                "    $proc = Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir -PassThru",
                "    Start-Sleep -Seconds 6",
                "    if (-not $proc.HasExited) {",
                "      $started = $true",
                "      Write-Log 'launch appears successful'",
                "      break",
                "    }",
                "    Write-Log ('launch exited early with code ' + $proc.ExitCode)",
                "  } catch {",
                "    Write-Log ('launch error: ' + $_.Exception.Message)",
                "  }",
                "  Start-Sleep -Seconds 3",
                "}",
                "if (-not $started -and (Test-Path -LiteralPath $backup)) {",
                "  Write-Log 'new build failed to stay up; rolling back backup'",
                "  if (Test-Path -LiteralPath $failed) { Remove-Item -LiteralPath $failed -Force }",
                "  if (Test-Path -LiteralPath $TargetPath) { Move-Item -LiteralPath $TargetPath -Destination $failed -Force }",
                "  Move-Item -LiteralPath $backup -Destination $TargetPath -Force",
                "  Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir",
                "}",
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
            str(target_exe),
            str(log_path),
        ],
        close_fds=True,
        creationflags=creationflags,
    )
