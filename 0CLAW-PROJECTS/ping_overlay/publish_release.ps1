param(
    [string]$Repo = "KimiseVN/zeroclaw",
    [string]$TagPrefix = "ping-overlay-v",
    [string]$AssetPrefix = "PingOverlay-v",
    [string]$AssetExtension = ".exe",
    [switch]$Draft,
    [switch]$Prerelease,
    [switch]$SkipBuild,
    [switch]$SkipCompileCheck,
    [switch]$AllowDirty,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionFile = Join-Path $root "app_version.py"
$buildScript = Join-Path $root "build_release.ps1"

function Get-VersionedAssetName {
    param(
        [string]$Version,
        [string]$Prefix,
        [string]$Extension
    )
    return "$Prefix$Version$Extension"
}

function Get-AppVersion {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Missing version file: $Path"
    }
    $raw = Get-Content $Path -Raw
    $m = [regex]::Match($raw, '__version__\s*=\s*"(\d+\.\d+\.\d+)"')
    if (-not $m.Success) {
        throw "Could not parse __version__ from $Path"
    }
    return $m.Groups[1].Value
}

function Assert-CleanWorktree {
    param([switch]$AllowDirty)
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed"
    }
    if ($AllowDirty) {
        return
    }
    if ($status) {
        throw "Working tree is dirty. Commit/stash changes first, or pass -AllowDirty to override."
    }
}

function Assert-GhReady {
    $null = Get-Command gh -ErrorAction Stop
    gh auth status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run: gh auth login"
    }
}

Push-Location $root
try {
    Assert-CleanWorktree -AllowDirty:$AllowDirty
    Assert-GhReady

    if (-not $SkipBuild) {
        $buildArgs = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $buildScript
        )
        if ($SkipCompileCheck) {
            $buildArgs += "-SkipCompileCheck"
        }
        & powershell @buildArgs
        if ($LASTEXITCODE -ne 0) {
            throw "build_release.ps1 failed"
        }
    }

    $version = Get-AppVersion -Path $versionFile
    $tag = "$TagPrefix$version"
    $title = "PingOverlay v$version"
    $assetName = Get-VersionedAssetName -Version $version -Prefix $AssetPrefix -Extension $AssetExtension
    $distExe = Join-Path $root ("dist\" + $assetName)

    if (-not (Test-Path $distExe)) {
        throw "Missing release artifact: $distExe"
    }

    $checkCmd = 'gh release view "{0}" --repo "{1}" --json tagName >nul 2>nul' -f $tag, $Repo
    cmd /c $checkCmd | Out-Null
    if ($LASTEXITCODE -eq 0) {
        throw "Release tag already exists: $tag"
    }

    $sha256 = (Get-FileHash -Algorithm SHA256 -Path $distExe).Hash.ToLowerInvariant()
    $checksumPath = Join-Path $root ("dist\" + $assetName + ".sha256.txt")
    Set-Content -Path $checksumPath -Value "$sha256  $assetName" -Encoding ascii

    $notesLines = @(
        "PingOverlay release $version",
        '',
        'Assets:',
        "- $assetName",
        "- ${assetName}.sha256.txt",
        '',
        'SHA-256',
        '```text',
        "$sha256  $assetName",
        '```'
    )
    $notesPath = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("pingoverlay-release-notes-" + $version + ".md")
    Set-Content -Path $notesPath -Value ($notesLines -join [Environment]::NewLine) -Encoding utf8

    $cmd = @(
        "release", "create", $tag,
        $distExe,
        $checksumPath,
        "--repo", $Repo,
        "--title", $title,
        "--target", (git rev-parse HEAD).Trim(),
        "--notes-file", $notesPath
    )
    if ($Draft) {
        $cmd += "--draft"
    }
    if ($Prerelease) {
        $cmd += "--prerelease"
    }
    else {
        $cmd += "--latest"
    }

    if ($DryRun) {
        Write-Host "Dry run only. Command:"
        Write-Host ("gh " + ($cmd -join " "))
        Write-Host "Artifact: $distExe"
        Write-Host "Checksum: $checksumPath"
        Write-Host "Version: $version"
        Write-Host "Tag: $tag"
        exit 0
    }

    gh @cmd
    if ($LASTEXITCODE -ne 0) {
        throw "gh release create failed"
    }

    $releasesJson = gh api ("repos/" + $Repo + "/releases?per_page=100")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list existing releases for cleanup"
    }
    $releases = $releasesJson | ConvertFrom-Json
    foreach ($release in $releases) {
        $oldTag = [string]$release.tag_name
        if ([string]::IsNullOrWhiteSpace($oldTag)) {
            continue
        }
        if (-not $oldTag.StartsWith($TagPrefix)) {
            continue
        }
        if ($oldTag -eq $tag) {
            continue
        }
        gh release delete $oldTag --repo $Repo --cleanup-tag -y
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to delete old release: $oldTag"
        }
        Write-Host "Deleted old release $oldTag"
    }

    Write-Host "Published release $tag"
    Write-Host "Repo: $Repo"
    Write-Host "Artifact: $distExe"
}
finally {
    Pop-Location
}
