#!/usr/bin/env pwsh
# WWM Overlay API — one-shot deploy script
# Run from mainapp/ directory: .\backend\deploy.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

# ── Secrets ───────────────────────────────────────────────────────────────────
$neonUrl      = "postgresql://neondb_owner:npg_NfEiHF4yhZ7G@ep-dry-cherry-aodkr4j7.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
$jwtSecret    = "823bd06ab2f396aeb4ca8312c522c306c4f289283ee31205b085dd93b8a74556"
$adminToken   = "d63f83ca969fbdbd52092f5082f7fe80bf5b05a2aaf3abf8"
$clientToken  = "a7ea9e8e1c1c4837e5f611e69c63f23c"

# Will be updated after first deploy — check Modal dashboard
$modalUser    = "kimisevn"  # Modal username
$apiBaseUrl   = "https://${modalUser}--wwm-api-fastapi-app.modal.run"

# OAuth — fill in from Google Cloud Console / Discord Developer Portal
$googleId     = $env:GOOGLE_CLIENT_ID     ?? ""
$googleSecret = $env:GOOGLE_CLIENT_SECRET ?? ""
$discordId    = $env:DISCORD_CLIENT_ID    ?? ""
$discordSec   = $env:DISCORD_CLIENT_SECRET ?? ""

# Hostinger FTP — used for demo image upload (lands in public_html/uploads/demo-images/)
$ftpHost = "153.92.8.124"
$ftpUser = "u888361453.wwmoverlay.com"
$ftpPass = $env:FTP_PASS ?? 'Thuylinh@"()8601!'

Write-Host "Creating Modal secret 'wwm-api'..."
python -m modal secret create wwm-api `
    "NEON_DATABASE_URL=$neonUrl" `
    "JWT_SECRET=$jwtSecret" `
    "ADMIN_TOKEN=$adminToken" `
    "CLIENT_TOKEN=$clientToken" `
    "API_BASE_URL=$apiBaseUrl" `
    "GOOGLE_CLIENT_ID=$googleId" `
    "GOOGLE_CLIENT_SECRET=$googleSecret" `
    "DISCORD_CLIENT_ID=$discordId" `
    "DISCORD_CLIENT_SECRET=$discordSec" `
    "FTP_HOST=$ftpHost" `
    "FTP_USER=$ftpUser" `
    "FTP_PASS=$ftpPass"

Write-Host ""
Write-Host "Deploying to Modal..."
python -m modal deploy backend/modal_deploy.py

Write-Host ""
Write-Host "=== Deploy complete ==="
Write-Host "API URL: $apiBaseUrl"
Write-Host ""
Write-Host "Test with:"
Write-Host "  Invoke-WebRequest '$apiBaseUrl/health'"
