"""Apply auth_tables.sql to Neon and generate config secrets."""
import hashlib, io, os, secrets, sys
import psycopg2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CONN_STR = (
    "postgresql://neondb_owner:npg_NfEiHF4yhZ7G"
    "@ep-dry-cherry-aodkr4j7.c-2.ap-southeast-1.aws.neon.tech"
    "/neondb?sslmode=require"
)

SQL = open(os.path.join(os.path.dirname(__file__), "auth_tables.sql"), encoding="utf-8").read()

def main():
    conn = psycopg2.connect(CONN_STR)
    conn.autocommit = True
    cur = conn.cursor()
    print("Applying auth_tables.sql ...")
    try:
        cur.execute(SQL)
        print("  OK")
    except Exception as e:
        print(f"  ERR: {e}")

    # Print fresh secrets to copy into Modal
    print()
    print("=" * 60)
    print("Copy these into the Modal secret 'wwm-api':")
    print(f"  JWT_SECRET     = {secrets.token_hex(32)}")
    print(f"  ADMIN_TOKEN    = {secrets.token_hex(24)}")
    print(f"  CLIENT_TOKEN   = {secrets.token_hex(16)}")
    print(f"  NEON_DATABASE_URL = {CONN_STR}")
    print("=" * 60)
    print()
    print("After deploying to Modal, update:")
    print("  API_BASE_URL = https://<modal-user>--wwm-api-fastapi-app.modal.run")
    print()
    print("Also set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,")
    print("         DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET")
    print("from your OAuth app dashboards.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
