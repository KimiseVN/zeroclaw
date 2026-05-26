"""
FTP Deploy -- uploads Next.js static export (out/) directly to FTP root.
The FTP server logs in to public_html/ already, so no subdirectory prefix needed.
Usage: python ftp_deploy.py
"""

import ftplib
import sys
from pathlib import Path

# -- Config -------------------------------------------------------------------
FTP_HOST  = "153.92.8.124"
FTP_PORT  = 21
FTP_USER  = "u888361453.wwmoverlay.com"
FTP_PASS  = 'Thuylinh@"()8601!'
LOCAL_DIR = Path(__file__).parent / "out"

# -- Helpers ------------------------------------------------------------------
def upload_dir(ftp, local_path, remote_base, counter):
    """Recursively upload local_path into remote_base on the FTP server.
    Pass remote_base="" to upload directly into the current FTP working directory.
    """
    for item in sorted(local_path.iterdir()):
        # Build the remote path — omit the base prefix when it's empty
        remote_path = f"{remote_base}/{item.name}" if remote_base else item.name

        if item.is_dir():
            # Create the remote sub-directory (550 = already exists, skip)
            try:
                ftp.mkd(remote_path)
            except ftplib.error_perm as e:
                if "550" not in str(e):
                    raise
            upload_dir(ftp, item, remote_path, counter)
        else:
            with open(item, "rb") as f:
                ftp.storbinary(f"STOR {remote_path}", f)
            counter[0] += 1
            rel = str(item.relative_to(LOCAL_DIR))
            print(f"  [{counter[0]:>3}] {rel}")

# -- Main ---------------------------------------------------------------------
def main():
    if not LOCAL_DIR.exists():
        print(f"[ERROR] Build output not found: {LOCAL_DIR}")
        print("        Run  npm run build  first.")
        sys.exit(1)

    total = sum(1 for f in LOCAL_DIR.rglob("*") if f.is_file())
    print(f"Connecting to {FTP_HOST}:{FTP_PORT} ...")

    with ftplib.FTP() as ftp:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)

        cwd = ftp.pwd()
        print(f"FTP working dir after login: {cwd}")
        print(f"Uploading {total} files ...\n")

        counter = [0]
        # remote_base="" -> files land directly in the current FTP directory
        upload_dir(ftp, LOCAL_DIR, "", counter)

    print(f"\nDone! {counter[0]} files uploaded.")
    print("Website: http://wwmoverlay.com\n")

if __name__ == "__main__":
    main()
