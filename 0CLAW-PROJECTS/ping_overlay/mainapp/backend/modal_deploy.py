"""
Modal deployment for WWM Overlay API.
Deploy: python -m modal deploy backend/modal_deploy.py
(run from mainapp/ directory)
"""
import modal
from pathlib import Path

# ── Image with all dependencies ────────────────────────────────────────────────
# add_local_file copies api.py into /root/api.py inside the container image
# so `from api import app` resolves at runtime.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi>=0.111",
        "uvicorn[standard]>=0.29",
        "PyJWT>=2.8",
        "bcrypt>=4.1",
        "psycopg2-binary>=2.9",
        "python-multipart>=0.0.9",
    )
    .add_local_file(
        local_path=str(Path(__file__).parent / "api.py"),
        remote_path="/root/api.py",
    )
)

# ── Secrets — create these in Modal dashboard before deploying ─────────────────
# modal secret create wwm-api \
#   NEON_DATABASE_URL="postgresql://..." \
#   JWT_SECRET="..."  \
#   ADMIN_TOKEN="..."  \
#   CLIENT_TOKEN="..." \
#   API_BASE_URL="https://kimisevn--wwm-api-fastapi-app.modal.run" \
#   GOOGLE_CLIENT_ID="..."  \
#   GOOGLE_CLIENT_SECRET="..." \
#   DISCORD_CLIENT_ID="..." \
#   DISCORD_CLIENT_SECRET="..."
secrets = [modal.Secret.from_name("wwm-api")]

app = modal.App("wwm-api")


@app.function(image=image, secrets=secrets)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    from api import app as fastapi_app
    return fastapi_app
