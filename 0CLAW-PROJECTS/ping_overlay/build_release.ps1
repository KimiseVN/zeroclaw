param(
    [switch]$SkipCompileCheck
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionFile = Join-Path $root "app_version.py"
$specFile = Join-Path $root "PingOverlay.spec"
$assetPrefix = "PingOverlay-v"
$assetExtension = ".exe"

if (-not (Test-Path $versionFile)) {
    throw "Missing version file: $versionFile"
}

$original = Get-Content $versionFile -Raw
$m = [regex]::Match($original, '__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"')
if (-not $m.Success) {
    throw "Could not parse __version__ from $versionFile"
}

$major = [int]$m.Groups[1].Value
$minor = [int]$m.Groups[2].Value
$patch = [int]$m.Groups[3].Value
$nextVersion = "$major.$minor." + ($patch + 1)
$updated = [regex]::Replace(
    $original,
    '__version__\s*=\s*"\d+\.\d+\.\d+"',
    "__version__ = `"$nextVersion`"",
    1
)

Set-Content -Path $versionFile -Value $updated -Encoding UTF8

Push-Location $root
try {
    if (-not $SkipCompileCheck) {
        python -m py_compile autostart.py config.py fps.py hotkey.py main.py metrics.py net_utils.py overlay.py window_utils.py updater.py app_version.py
        if ($LASTEXITCODE -ne 0) {
            throw "py_compile failed"
        }
    }

    python -m PyInstaller --noconfirm --clean $specFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed"
    }

    $distExe = Join-Path $root "dist\PingOverlay.exe"
    if (-not (Test-Path $distExe)) {
        throw "Build finished but artifact missing: $distExe"
    }

    Get-ChildItem -Path (Join-Path $root "dist") -Filter ($assetPrefix + "*" + $assetExtension) -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $versionedAsset = Join-Path $root ("dist\" + $assetPrefix + $nextVersion + $assetExtension)
    Copy-Item -LiteralPath $distExe -Destination $versionedAsset -Force

    Write-Host "Built PingOverlay version $nextVersion"
    Write-Host "Artifact: $distExe"
    Write-Host "Versioned artifact: $versionedAsset"
}
catch {
    Set-Content -Path $versionFile -Value $original -Encoding UTF8
    throw
}
finally {
    Pop-Location
}
