# WWM Overlay API — Deploy to Modal

## 1. Setup Modal (one-time)

```powershell
python -m modal token new          # authenticate in browser
```

## 2. Create secrets in Modal

```powershell
python -m modal secret create wwm-api `
  NEON_DATABASE_URL="postgresql://neondb_owner:npg_NfEiHF4yhZ7G@ep-dry-cherry-aodkr4j7.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require" `
  JWT_SECRET="823bd06ab2f396aeb4ca8312c522c306c4f289283ee31205b085dd93b8a74556" `
  ADMIN_TOKEN="d63f83ca969fbdbd52092f5082f7fe80bf5b05a2aaf3abf8" `
  CLIENT_TOKEN="a7ea9e8e1c1c4837e5f611e69c63f23c" `
  API_BASE_URL="https://kimisevn--wwm-api-fastapi-app.modal.run" `
  GOOGLE_CLIENT_ID="<from Google Cloud Console>" `
  GOOGLE_CLIENT_SECRET="<from Google Cloud Console>" `
  DISCORD_CLIENT_ID="<from Discord Developer Portal>" `
  DISCORD_CLIENT_SECRET="<from Discord Developer Portal>"
```

Note: API_BASE_URL format = `https://<modal-username>--wwm-api-fastapi-app.modal.run`
(The Modal username for thuytk.cod@gmail.com — check after first deploy)

## 3. Deploy

```powershell
cd mainapp
python -m modal deploy backend/modal_deploy.py
```

After deploy, the URL will be shown. Update:
- `API_BASE_URL` in Modal secrets if different
- `_API_BASE_URL` in `license_lib.py` with the actual URL

## 4. OAuth setup (optional — for Google/Discord login)

### Google OAuth
1. Go to https://console.cloud.google.com/
2. APIs & Services → Credentials → Create OAuth 2.0 Client
3. Application type: Web application
4. Authorized redirect URIs: `https://kimisevn--wwm-api-fastapi-app.modal.run/auth/v1/callback/google`
5. Copy Client ID and Client Secret → add to Modal secrets

### Discord OAuth
1. Go to https://discord.com/developers/applications
2. Create application → OAuth2 → General
3. Add redirect: `https://kimisevn--wwm-api-fastapi-app.modal.run/auth/v1/callback/discord`
4. Copy Client ID and Secret → add to Modal secrets

## 5. Update heartbeat endpoint in app config

In the app's Settings (License Admin section), update `endpoint_url` to:
```
https://kimisevn--wwm-api-fastapi-app.modal.run/api/heartbeat
```

## 6. Test

```powershell
# Health check
Invoke-WebRequest "https://kimisevn--wwm-api-fastapi-app.modal.run/health"

# Trial settings
Invoke-WebRequest "https://kimisevn--wwm-api-fastapi-app.modal.run/rest/v1/site_settings?key=eq.trial&select=value"

# Heartbeat test
$b = @{action="test_heartbeat"; client_token="a7ea9e8e1c1c4837e5f611e69c63f23c"} | ConvertTo-Json
Invoke-WebRequest "https://kimisevn--wwm-api-fastapi-app.modal.run/api/heartbeat" -Method POST -Body $b -ContentType "application/json"
```

## Secrets reference

| Key | Value |
|-----|-------|
| NEON_DATABASE_URL | postgresql://neondb_owner:npg_... |
| JWT_SECRET | 823bd06ab2f396aeb... |
| ADMIN_TOKEN | d63f83ca969fbdbd... |
| CLIENT_TOKEN | a7ea9e8e1c1c4837... |
| API_BASE_URL | https://kimisevn--wwm-api-fastapi-app.modal.run |
