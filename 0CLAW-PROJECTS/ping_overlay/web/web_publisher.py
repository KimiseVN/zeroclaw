"""
WebPublisher — GUI tool to publish WWM Overlay website to FTP hosting.
Buttons: Publish (upload out/ only) | Build + Publish (npm build then upload)
"""

import sys
import threading
import ftplib
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

# ── Paths (works both as .py and frozen .exe) ─────────────────────────────────
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

LOCAL_DIR = APP_DIR / "out"          # Next.js static export output
WEB_DIR   = APP_DIR                  # directory containing package.json

# ── FTP Config ────────────────────────────────────────────────────────────────
FTP_HOST = "153.92.8.124"
FTP_PORT = 21
FTP_USER = "u888361453.wwmoverlay.com"
FTP_PASS = 'Thuylinh@"()8601!'

# ── Theme ─────────────────────────────────────────────────────────────────────
BG      = "#0d1220"
BG2     = "#111826"
SURFACE = "#151c2c"
SRF2    = "#1a2236"
BORDER  = "#1e2d45"
CYAN    = "#00E5FF"
GREEN   = "#22d3a0"
RED     = "#FF4466"
YELLOW  = "#FFD700"
TEXT    = "#e8edf5"
DIM     = "#7a8ba0"
MUTED   = "#4a5870"

F_UI  = ("Segoe UI", 10)
F_SM  = ("Segoe UI", 9)
F_MON = ("Consolas", 9)
F_H   = ("Segoe UI Semibold", 11)


# ── FTP Helpers ───────────────────────────────────────────────────────────────
def ftp_connect() -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)
    return ftp


def ftp_list_recursive(ftp: ftplib.FTP, remote_path: str = "", result=None):
    """Return list of (kind, path) — kind is 'dir' or 'file'."""
    if result is None:
        result = []
    try:
        entries = list(ftp.mlsd(remote_path or None))
    except Exception:
        return result
    for name, facts in entries:
        if name in (".", ".."):
            continue
        path = f"{remote_path}/{name}" if remote_path else name
        kind = facts.get("type", "file")
        if kind == "dir":
            result.append(("dir", path))
            ftp_list_recursive(ftp, path, result)
        else:
            result.append(("file", path))
    return result


def ftp_upload_dir(ftp, local_path, remote_base, counter, total, on_progress, on_log):
    """Recursively upload local_path into remote_base (empty = FTP root)."""
    for item in sorted(local_path.iterdir()):
        rpath = f"{remote_base}/{item.name}" if remote_base else item.name
        if item.is_dir():
            try:
                ftp.mkd(rpath)
            except ftplib.error_perm as e:
                if "550" not in str(e):
                    raise
            ftp_upload_dir(ftp, item, rpath, counter, total, on_progress, on_log)
        else:
            with open(item, "rb") as f:
                ftp.storbinary(f"STOR {rpath}", f)
            counter[0] += 1
            pct = int(counter[0] / total * 100)
            on_log(f"[{counter[0]:>3}/{total}] {item.relative_to(LOCAL_DIR)}\n", "ok")
            on_progress(pct)


# ── Main Application ──────────────────────────────────────────────────────────
class WebPublisher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WWM Overlay — Web Publisher")
        self.geometry("1060x660")
        self.minsize(820, 520)
        self.configure(bg=BG)
        self._busy = False
        self._build_ui()
        self.after(200, self._refresh_ftp)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG2, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="WWM Overlay", font=("Segoe UI Semibold", 13),
                 bg=BG2, fg=TEXT).pack(side="left", padx=18)
        tk.Label(hdr, text="Web Publisher", font=F_UI,
                 bg=BG2, fg=DIM).pack(side="left")
        tk.Label(hdr, text=f"{FTP_HOST}", font=F_MON,
                 bg=BG2, fg=MUTED).pack(side="right", padx=18)
        tk.Frame(hdr, bg=BORDER, width=1).pack(side="right", fill="y")

        # ── Paned window ──
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=BORDER, sashwidth=4, sashrelief="flat",
                              bd=0, relief="flat")
        pane.pack(fill="both", expand=True)

        # Left panel — FTP tree
        left = tk.Frame(pane, bg=SURFACE, bd=0)
        pane.add(left, width=340, minsize=200)

        lhdr = tk.Frame(left, bg=BG2, height=34)
        lhdr.pack(fill="x")
        lhdr.pack_propagate(False)
        tk.Label(lhdr, text="FTP Files", font=F_SM,
                 bg=BG2, fg=DIM, padx=12).pack(side="left", fill="y")
        self._refresh_btn = tk.Button(
            lhdr, text="↻ Refresh", font=F_SM,
            bg=BG2, fg=CYAN, activebackground=BG2, activeforeground=CYAN,
            relief="flat", cursor="hand2", padx=8, pady=0,
            command=self._refresh_ftp,
        )
        self._refresh_btn.pack(side="right", padx=6, pady=4)

        tree_frame = tk.Frame(left, bg=SURFACE)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("FTP.Treeview",
            background=SURFACE, foreground=DIM,
            fieldbackground=SURFACE, rowheight=20,
            font=F_MON, borderwidth=0, relief="flat",
        )
        style.configure("FTP.Treeview.Heading",
            background=BG2, foreground=MUTED,
            font=F_SM, borderwidth=0, relief="flat",
        )
        style.map("FTP.Treeview",
            background=[("selected", SRF2)],
            foreground=[("selected", CYAN)],
        )
        style.configure("Pub.Horizontal.TProgressbar",
            troughcolor=SURFACE, background=CYAN,
            thickness=5, borderwidth=0,
        )

        self._tree = ttk.Treeview(tree_frame, style="FTP.Treeview",
                                   show="tree", selectmode="none")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True, padx=(2, 0))
        self._tree.tag_configure("dir",  foreground=CYAN)
        self._tree.tag_configure("file", foreground=DIM)

        # tree status label
        self._tree_status = tk.Label(left, text="", font=F_SM,
                                     bg=SURFACE, fg=MUTED, pady=4)
        self._tree_status.pack()

        # Right panel — log
        right = tk.Frame(pane, bg=BG, bd=0)
        pane.add(right, minsize=340)

        rhdr = tk.Frame(right, bg=BG2, height=34)
        rhdr.pack(fill="x")
        rhdr.pack_propagate(False)
        tk.Label(rhdr, text="Upload Log", font=F_SM,
                 bg=BG2, fg=DIM, padx=12).pack(side="left", fill="y")
        self._clear_btn = tk.Button(
            rhdr, text="Clear", font=F_SM,
            bg=BG2, fg=MUTED, activebackground=BG2, activeforeground=TEXT,
            relief="flat", cursor="hand2", padx=8,
            command=self._clear_log,
        )
        self._clear_btn.pack(side="right", padx=6, pady=4)

        log_wrap = tk.Frame(right, bg=BG)
        log_wrap.pack(fill="both", expand=True, padx=2, pady=2)

        self._log = tk.Text(
            log_wrap, bg=BG, fg=DIM, font=F_MON,
            insertbackground=CYAN, relief="flat", bd=0,
            state="disabled", wrap="none",
        )
        lvsb = ttk.Scrollbar(log_wrap, orient="vertical",   command=self._log.yview)
        lhsb = ttk.Scrollbar(log_wrap, orient="horizontal", command=self._log.xview)
        self._log.configure(yscrollcommand=lvsb.set, xscrollcommand=lhsb.set)
        lvsb.pack(side="right", fill="y")
        lhsb.pack(side="bottom", fill="x")
        self._log.pack(fill="both", expand=True)

        self._log.tag_configure("ok",    foreground=GREEN)
        self._log.tag_configure("warn",  foreground=YELLOW)
        self._log.tag_configure("err",   foreground=RED)
        self._log.tag_configure("info",  foreground=CYAN)
        self._log.tag_configure("muted", foreground=MUTED)
        self._log.tag_configure("head",  foreground=TEXT)

        # ── Bottom bar ──
        bot = tk.Frame(self, bg=BG2)
        bot.pack(fill="x", side="bottom")
        tk.Frame(bot, bg=BORDER, height=1).pack(fill="x")

        prog_row = tk.Frame(bot, bg=BG2)
        prog_row.pack(fill="x", padx=14, pady=(8, 3))

        self._status_var = tk.StringVar(value="Ready")
        self._pct_var    = tk.StringVar(value="")
        tk.Label(prog_row, textvariable=self._status_var,
                 font=F_SM, bg=BG2, fg=DIM, anchor="w").pack(side="left")
        tk.Label(prog_row, textvariable=self._pct_var,
                 font=("Segoe UI Semibold", 9), bg=BG2, fg=CYAN,
                 anchor="e", width=5).pack(side="right")

        self._progress = ttk.Progressbar(
            bot, style="Pub.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100,
        )
        self._progress.pack(fill="x", padx=14, pady=(0, 6))

        btn_row = tk.Frame(bot, bg=BG2)
        btn_row.pack(fill="x", padx=14, pady=(0, 12))

        self._pub_btn = tk.Button(
            btn_row, text="  Publish  ",
            font=("Segoe UI Semibold", 10),
            bg=CYAN, fg="#000000",
            activebackground="#33eeff", activeforeground="#000000",
            relief="flat", cursor="hand2", padx=20, pady=7,
            command=self._start_publish,
        )
        self._pub_btn.pack(side="right", padx=(4, 0))

        self._bp_btn = tk.Button(
            btn_row, text="  Build + Publish  ",
            font=("Segoe UI Semibold", 10),
            bg=SURFACE, fg=CYAN,
            activebackground=SRF2, activeforeground=CYAN,
            relief="flat", cursor="hand2", padx=20, pady=7,
            highlightthickness=1, highlightbackground=BORDER,
            command=self._start_build_publish,
        )
        self._bp_btn.pack(side="right", padx=(0, 4))

        tk.Label(btn_row, text="http://wwmoverlay.com",
                 font=F_SM, bg=BG2, fg=MUTED).pack(side="left")

    # ── FTP Tree ──────────────────────────────────────────────────────────────
    def _refresh_ftp(self):
        if self._busy:
            return
        self._refresh_btn.configure(state="disabled")
        self._tree_status.configure(text="Loading ...", fg=YELLOW)
        threading.Thread(target=self._ftp_list_worker, daemon=True).start()

    def _ftp_list_worker(self):
        try:
            ftp  = ftp_connect()
            cwd  = ftp.pwd()
            self._log_write(f"FTP connected  root={cwd}\n", "info")
            items = ftp_list_recursive(ftp)
            ftp.quit()
            n_files = sum(1 for k, _ in items if k == "file")
            n_dirs  = sum(1 for k, _ in items if k == "dir")
            self.after(0, lambda: self._populate_tree(items))
            self.after(0, lambda: self._tree_status.configure(
                text=f"{n_files} files · {n_dirs} folders", fg=MUTED))
        except Exception as exc:
            self._log_write(f"[FTP ERROR] {exc}\n", "err")
            self.after(0, lambda: self._tree_status.configure(
                text=f"Error: {exc}", fg=RED))
        finally:
            self.after(0, lambda: self._refresh_btn.configure(state="normal"))

    def _populate_tree(self, items):
        self._tree.delete(*self._tree.get_children())
        nodes: dict[str, str] = {"": ""}  # path -> treeview node id

        for kind, path in sorted(items, key=lambda x: (x[1].count("/"), x[1])):
            parts  = path.split("/")
            parent = "/".join(parts[:-1])
            name   = parts[-1]
            pid    = nodes.get(parent, "")
            icon   = "▶ " if kind == "dir" else "  "
            nid    = self._tree.insert(
                pid, "end",
                text=f"{icon}{name}",
                open=len(parts) <= 1,
                tags=(kind,),
            )
            nodes[path] = nid

    # ── Publish ───────────────────────────────────────────────────────────────
    def _start_publish(self):
        if self._busy:
            return
        if not LOCAL_DIR.exists():
            messagebox.showerror(
                "No build output",
                f"Folder not found:\n{LOCAL_DIR}\n\nUse 'Build + Publish' instead.",
            )
            return
        self._run(build=False)

    def _start_build_publish(self):
        if self._busy:
            return
        self._run(build=True)

    def _run(self, build: bool):
        self._busy = True
        self._set_busy(True)
        self._clear_log()
        self._set_progress(0)
        threading.Thread(target=self._worker, args=(build,), daemon=True).start()

    def _worker(self, build: bool):
        try:
            # ── 1. npm run build ──────────────────────────────────────────
            if build:
                self._set_status("Building Next.js ...", YELLOW)
                self._log_write("=== npm run build ===\n", "head")
                result = subprocess.run(
                    "npm run build",
                    cwd=str(WEB_DIR),
                    capture_output=True, text=True, shell=True,
                )
                for line in result.stdout.splitlines():
                    self._log_write(line + "\n", "muted")
                if result.returncode != 0:
                    for line in result.stderr.splitlines():
                        self._log_write(line + "\n", "err")
                    raise RuntimeError("npm run build failed (see log)")
                self._log_write("Build complete.\n\n", "ok")

            # ── 2. Count local files ──────────────────────────────────────
            all_files = [f for f in LOCAL_DIR.rglob("*") if f.is_file()]
            total = len(all_files)
            if total == 0:
                raise RuntimeError("out/ folder is empty — run build first")

            # ── 3. FTP Upload ─────────────────────────────────────────────
            self._set_status("Connecting to FTP ...", YELLOW)
            ftp = ftp_connect()
            cwd = ftp.pwd()
            self._log_write(f"=== FTP Upload · {total} files → {cwd} ===\n", "head")

            counter = [0]
            self._set_status("Uploading ...", CYAN)
            ftp_upload_dir(
                ftp, LOCAL_DIR, "",
                counter, total,
                on_progress=self._set_progress,
                on_log=self._log_write,
            )
            ftp.quit()

            # ── 4. Done ───────────────────────────────────────────────────
            self._set_progress(100)
            self._log_write(f"\nDone — {total} files published.\n", "ok")
            self._log_write("http://wwmoverlay.com\n", "info")
            self._set_status(f"Published {total} files", GREEN)
            self.after(800, self._refresh_ftp)

        except Exception as exc:
            self._log_write(f"\n[ERROR] {exc}\n", "err")
            self._set_status(f"Error: {exc}", RED)
        finally:
            self._busy = False
            self.after(0, lambda: self._set_busy(False))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _set_busy(self, on: bool):
        s = "disabled" if on else "normal"
        self._pub_btn.configure(state=s)
        self._bp_btn.configure(state=s)
        self._refresh_btn.configure(state=s)

    def _set_status(self, msg: str, color: str = TEXT):
        self.after(0, lambda: (
            self._status_var.set(msg),
        ))

    def _set_progress(self, pct: int):
        def _upd():
            self._progress["value"] = pct
            self._pct_var.set(f"{pct}%")
        self.after(0, _upd)

    def _log_write(self, msg: str, tag: str = ""):
        def _w():
            self._log.configure(state="normal")
            self._log.insert("end", msg, tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _w)

    def _clear_log(self):
        def _w():
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.configure(state="disabled")
        self.after(0, _w)


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = WebPublisher()
    app.mainloop()
