param(
    [switch]$SkipCompileCheck,
    [switch]$SkipInstaller,      # skip Inno Setup step (build onedir only)
    [switch]$SkipVersionBump,    # keep current version (for re-run after failure)
    [switch]$SkipSign            # skip code signing (use before cert is ready)
)

$ErrorActionPreference = "Stop"

# UTF-8 without BOM — compatible with PS 5.1 and PS 7+
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
function Write-Utf8NoBOM([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

# ── Code signing via AzureSignTool ─────────────────────────────────────────
# Signs one or more PE files using Azure Trusted Signing.
# Auth priority: AZURE_* env vars (service principal) → az login (CLI session).
# Skips gracefully if AzureSignTool is not installed or signing.json is missing.
function Invoke-AzureSign {
    param(
        [string[]]$Files,
        [string]   $ConfigPath
    )

    # Tool check
    if (-not (Get-Command AzureSignTool -ErrorAction SilentlyContinue)) {
        Write-Warning "AzureSignTool not installed — skipping signing."
        Write-Warning "  Install: dotnet tool install --global AzureSignTool"
        return
    }

    # Config check
    if (-not (Test-Path $ConfigPath)) {
        Write-Warning "signing.json not found — skipping signing."
        Write-Warning "  Copy signing.json.example -> signing.json and fill in values."
        return
    }
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

    # Build base arguments
    $tsUrl   = if ($cfg.timestamp_url)   { $cfg.timestamp_url }   else { "http://timestamp.acs.microsoft.com" }
    $desc    = if ($cfg.description)     { $cfg.description }     else { "WWM Overlay" }
    $descUrl = if ($cfg.description_url) { $cfg.description_url } else { "https://wwmoverlay.com" }

    $baseArgs = @(
        "sign",
        "-kvu", $cfg.endpoint,
        "-kvc", $cfg.cert_profile,
        "-tr",  $tsUrl,
        "-td",  "sha256",
        "-fd",  "sha256",
        "-d",   $desc,
        "-du",  $descUrl,
        "-v"
    )

    # Authentication: service principal (env vars) or Azure CLI fallback
    $tenantId     = $env:AZURE_TENANT_ID
    $clientId     = $env:AZURE_CLIENT_ID
    $clientSecret = $env:AZURE_CLIENT_SECRET

    if ($tenantId -and $clientId -and $clientSecret) {
        $baseArgs += @("-kvt", $tenantId, "-kvi", $clientId, "-kvs", $clientSecret)
        Write-Host "  Auth: service principal ($clientId)"
    } else {
        Write-Host "  Auth: Azure CLI (az login)"
        $token = az account get-access-token --resource "https://codesigning.azure.net" --query accessToken -o tsv 2>$null
        if (-not $token) {
            throw "Azure CLI auth failed. Run 'az login' first, or set AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET env vars."
        }
        $baseArgs += @("-kva", $token)
    }

    # Sign each file
    foreach ($f in $Files) {
        if (-not (Test-Path $f)) {
            Write-Warning "  Sign: file not found, skipping: $f"
            continue
        }
        Write-Host "Signing: $(Split-Path -Leaf $f) ..."
        & AzureSignTool @baseArgs $f
        if ($LASTEXITCODE -ne 0) { throw "AzureSignTool failed for $(Split-Path -Leaf $f) (exit $LASTEXITCODE)" }
        Write-Host "  OK: $(Split-Path -Leaf $f)"
    }
}
# ───────────────────────────────────────────────────────────────────────────

$root           = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionFile    = Join-Path $root "app_version.py"
$specFile       = Join-Path $root "PingOverlay-setup.spec"
$optizSpecFile  = Join-Path $root "OptizNW.spec"
$issFile        = Join-Path $root "PingOverlay-setup.iss"
$distDir        = Join-Path $root "dist\PingOverlay"
$optizExe       = Join-Path $root "dist\OptizNW.exe"
$signingCfg     = Join-Path $root "signing.json"

# 1. Read + bump version
if (-not (Test-Path $versionFile)) { throw "Missing version file: $versionFile" }
$original = Get-Content $versionFile -Raw
$m = [regex]::Match($original, '__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"')
if (-not $m.Success) { throw "Could not parse __version__ from $versionFile" }

$major = [int]$m.Groups[1].Value
$minor = [int]$m.Groups[2].Value
$patch = [int]$m.Groups[3].Value

if ($SkipVersionBump) {
    $nextVersion = ("{0}.{1}.{2:D2}" -f $major, $minor, $patch)
    Write-Host "Re-using version $nextVersion (version bump skipped)"
} else {
    if ($major -eq 0) {
        $nextVersion = "1.0.00"
    } else {
        if ($patch -ge 99) { $minor += 1; $patch = 0 } else { $patch += 1 }
        $nextVersion = ("{0}.{1}.{2:D2}" -f $major, $minor, $patch)
    }
    $updated = [regex]::Replace(
        $original,
        '__version__\s*=\s*"\d+\.\d+\.\d+"',
        "__version__ = `"$nextVersion`"",
        1
    )
    Write-Utf8NoBOM $versionFile $updated
    Write-Host "Version bumped -> $nextVersion"
}

Push-Location $root
try {
    # 2. Compile check
    if (-not $SkipCompileCheck) {
        Write-Host "Compile-checking Python sources..."
        python -m py_compile autostart.py config.py events.py fps.py hotkey.py `
            license_lib.py license_check.py license_admin.py release_gateway.py `
            main.py metrics.py net_utils.py overlay.py window_utils.py updater.py `
            app_version.py system_tweaks.py account_sync.py ui_runtime.py resources.py `
            optiz_nw.py `
            wwm_tales\cli.py wwm_tales\gui.py wwm_tales\hotkeys.py `
            wwm_tales\html_extract.py wwm_tales\library.py wwm_tales\ocr.py `
            wwm_tales\overlay.py wwm_tales\scraper.py wwm_tales\window_capture.py `
            wwm_quest\scraper.py wwm_quest\library.py `
            wwm_encounter\scraper.py wwm_encounter\library.py
        if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }
        Write-Host "Compile check OK."
    }

    # 3. PyInstaller onedir build (PingOverlay)
    Write-Host "Building onedir with PyInstaller..."
    python -m PyInstaller --noconfirm --clean $specFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    # 3.5. PyInstaller onefile build (OptizNW companion)
    if (Test-Path $optizSpecFile) {
        Write-Host "Building OptizNW.exe with PyInstaller (onefile)..."
        python -m PyInstaller --noconfirm --clean $optizSpecFile
        if ($LASTEXITCODE -ne 0) { throw "OptizNW PyInstaller build failed" }
        # Copy OptizNW.exe into the PingOverlay dist dir so installer picks it up
        if (Test-Path $optizExe) {
            Copy-Item -LiteralPath $optizExe -Destination $distDir -Force
            Write-Host "OptizNW.exe copied to dist\PingOverlay\"
        } else {
            Write-Warning "OptizNW.exe not found at $optizExe — skipping copy"
        }
    } else {
        Write-Warning "OptizNW.spec not found — skipping OptizNW build"
    }

    # 4. Verify artifact
    $exePath = Join-Path $distDir "PingOverlay.exe"
    if (-not (Test-Path $exePath)) { throw "Build finished but PingOverlay.exe missing: $exePath" }

    # Remove unwanted files dropped by PyInstaller into _internal root
    Remove-Item -LiteralPath (Join-Path $distDir "_internal\config.json")         -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $distDir "_internal\internal_config.json") -Force -ErrorAction SilentlyContinue

    # Strip unused PIL binary extensions
    $pilDir = Join-Path $distDir "_internal\PIL"
    foreach ($stem in @('_avif', '_webp', '_imagingcms')) {
        Get-ChildItem -Path $pilDir -Filter "$stem*" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
    Write-Host "PIL strip done: removed _avif / _webp / _imagingcms from _internal\PIL\"

    # 4.5. Sign PingOverlay.exe + OptizNW.exe BEFORE manifest generation
    #      (manifest must hash the signed binaries, not the unsigned ones)
    if (-not $SkipSign) {
        Write-Host ""
        Write-Host "--- Code signing: PingOverlay.exe + OptizNW.exe ---"
        $filesToSign = @($exePath)
        $optizInDist = Join-Path $distDir "OptizNW.exe"
        if (Test-Path $optizInDist) { $filesToSign += $optizInDist }
        Invoke-AzureSign -Files $filesToSign -ConfigPath $signingCfg
        Write-Host "--- Code signing complete ---"
        Write-Host ""
    }

    # 5. Generate manifest.json (hash index for incremental updater)
    Write-Host "Generating manifest.json..."
    $manifest = [ordered]@{
        version    = $nextVersion
        build_type = "setup"
        files      = [ordered]@{}
    }

    Get-ChildItem -Path $distDir -Recurse -File | Sort-Object FullName | ForEach-Object {
        $rel  = $_.FullName.Substring($distDir.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLower()
        $manifest.files[$rel] = [ordered]@{
            sha256 = $hash
            size   = $_.Length
        }
    }

    $manifestPath = Join-Path $distDir "manifest.json"
    Write-Utf8NoBOM $manifestPath ($manifest | ConvertTo-Json -Depth 5)
    Write-Host "manifest.json written ($($manifest.files.Count) files)"

    # 5.5. Sync changed files into /update/ (mirrors dist\PingOverlay\)
    Write-Host "Syncing changed files to update/ ..."
    $updateDir          = Join-Path $root "update"
    $updateManifestPath = Join-Path $updateDir "manifest.json"
    if (-not (Test-Path $updateDir)) { New-Item -ItemType Directory -Path $updateDir -Force | Out-Null }

    # Load previous manifest hashes (empty if first run)
    $prevHashes = @{}
    if (Test-Path $updateManifestPath) {
        try {
            $prevManifestContent = Get-Content $updateManifestPath -Raw | ConvertFrom-Json
            foreach ($p in $prevManifestContent.files.PSObject.Properties) {
                $prevHashes[$p.Name] = $p.Value.sha256
            }
        } catch { $prevHashes = @{} }
    }

    # Copy files whose hash changed
    $syncCount   = 0
    $currentPaths = @{}
    foreach ($p in $manifest.files.GetEnumerator()) {
        $rel     = $p.Key
        $newHash = $p.Value.sha256
        $currentPaths[$rel] = $true
        if ($prevHashes[$rel] -ne $newHash) {
            $src = Join-Path $distDir ($rel.Replace('/', '\'))
            $dst = Join-Path $updateDir ($rel.Replace('/', '\'))
            New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
            Copy-Item -LiteralPath $src -Destination $dst -Force
            $syncCount++
        }
    }

    # Remove files from update/ that no longer exist in dist
    if (Test-Path $updateDir) {
        Get-ChildItem -Path $updateDir -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($updateDir.Length + 1).Replace('\', '/')
            if ($rel -ne "manifest.json" -and -not $rel.StartsWith(".git") -and -not $currentPaths.ContainsKey($rel)) {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-Host "  removed from update/: $rel"
            }
        }
    }

    # Always refresh manifest.json in update/
    Copy-Item -LiteralPath $manifestPath -Destination $updateManifestPath -Force
    Write-Host "update/ synced: $syncCount file(s) changed"

    # 6. Inno Setup installer
    $setupExe = $null
    if (-not $SkipInstaller) {
        $isccCmd = Get-Command iscc -ErrorAction SilentlyContinue
        $isccCandidates = @(
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        if ($isccCmd) { $isccCandidates += $isccCmd.Source }
        $iscc = $isccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

        if (-not $iscc) {
            Write-Warning "Inno Setup (ISCC.exe) not found - skipping installer creation."
            Write-Warning "Install from https://jrsoftware.org/isdownload.php then re-run."
        } else {
            Write-Host "Building installer with Inno Setup..."
            & $iscc $issFile /DAppVersion=$nextVersion
            if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

            $setupExe = Join-Path $root "dist\PingOverlay-Setup-v${nextVersion}.exe"
            if (Test-Path $setupExe) {
                Write-Host "Installer: $setupExe"
            }
        }
    }

    # 6.5. Sign installer EXE
    if (-not $SkipSign -and $setupExe -and (Test-Path $setupExe)) {
        Write-Host ""
        Write-Host "--- Code signing: installer EXE ---"
        Invoke-AzureSign -Files @($setupExe) -ConfigPath $signingCfg
        Write-Host "--- Code signing complete ---"
        Write-Host ""
    }

    Write-Host ""
    Write-Host "=== Setup build complete - v$nextVersion ==="
    Write-Host "  Onedir:   $distDir"
    Write-Host "  Manifest: $manifestPath"
    if (-not $SkipInstaller -and $setupExe) {
        Write-Host "  Installer: dist\PingOverlay-Setup-v${nextVersion}.exe"
        $signed = if ($SkipSign) { "(unsigned)" } else { "(signed)" }
        Write-Host "  Signing:   $signed"
    }
}
catch {
    # Roll back version bump on failure
    if (-not $SkipVersionBump) {
        Write-Utf8NoBOM $versionFile $original
        Write-Warning "Build failed - version rolled back."
    }
    throw
}
finally {
    Pop-Location
}
