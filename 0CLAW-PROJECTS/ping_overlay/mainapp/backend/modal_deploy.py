"""
Modal deployment for WWM Overlay API.
Deploy: python -m modal deploy backend/modal_deploy.py
"""
import modal

# ── Image with all dependencies ────────────────────────────────────────────────
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi>=0.111",
        "uvicorn[standard]>=0.29",
        "PyJWT>=2.8",
        "bcrypt>=4.1",
        "psycopg2-binary>=2.9",
    )
)

# ── Secrets — create these in Modal dashboard before deploying ─────────────────
# modal secret create wwm-api \
#   NEON_DATABASE_URL="postgresql://..." \
#   JWT_SECRET="..."  \
#   ADMIN_TOKEN="..."  \
#   CLIENT_TOKEN="..." \
#   API_BASE_URL="https://thuytk--wwm-api-fastapi-app.modal.run" \
#   GOOGLE_CLIENT_ID="..."  \
#   GOOGLE_CLIENT_SECRET="..." \
#   DISCORD_CLIENT_ID="..." \
#   DISCORD_CLIENT_SECRET="..."
secrets = [modal.Secret.from_name("wwm-api")]

app = modal.App("wwm-api")


@app.function(image=image, secrets=secrets, allow_concurrent_inputs=100)
@modal.asgi_app()
def fastapi_app():
    from api import app as fastapi_app
    return fastapi_app
