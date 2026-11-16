#!/usr/bin/env python3
"""
YT Downloader - a dark-themed Tkinter GUI around yt-dlp.

Features
- Multi-URL queue (one URL per line), playlists optional
- Quality / audio-only selection
- Large-file friendly: resumable .part files, chunked HTTP, fragment retries,
    exponential backoff, disk-space pre-check
- Sign-in for restricted videos via your browser's logged-in Google session
    (cookies) or an exported cookies.txt - no password is ever typed into or
    stored by this app (includes an automated cookie-request tool)
- "Polite client" settings that lower the odds of rate limiting / IP bans:
    speed cap, randomized delays, backoff, optional proxy

Requirements
  pip install -U yt-dlp
  ffmpeg on your PATH (needed for merging video+audio and for MP3 extraction)

Only download content you own, that is freely licensed, or that you otherwise
have the right to save. Respect the terms of the sites you use.
"""

import os
import queue
import random
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import yt_dlp
    from yt_dlp.cookies import extract_cookies_from_browser
    from yt_dlp.utils import DownloadCancelled
except ImportError:  # pragma: no cover
    raise SystemExit("yt-dlp is not installed. Run:  pip install -U yt-dlp")

# ----------------------------------------------------------------- theme ---
BG = "#14151a"
PANEL = "#1d1f27"
FIELD = "#262935"
FG = "#e8e9ef"
MUTED = "#8b8fa3"
ACCENT = "#ff4d5e"
ACCENT_HOVER = "#ff6b79"
OK = "#4ade80"

QUALITIES = {
    "Best available": None,
    "2160p (4K)": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
    "Audio only - MP3": "mp3",
    "Audio only - M4A": "m4a",
}
BROWSERS = [
    "none", "chrome", "firefox", "edge", "brave", "opera", "vivaldi",
    "chromium", "safari",
]

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def human_bytes(n):
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


def human_time(s):
    if s is None:
        return "?"
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


class GuiLogger:
    """Routes yt-dlp's log output into the GUI queue."""

    def __init__(self, q):
        self.q = q

    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self.q.put(("log", msg))

    def info(self, msg):
        self.q.put(("log", msg))

    def warning(self, msg):
        self.q.put(("log", f"WARNING: {msg}"))

    def error(self, msg):
        self.q.put(("log", f"ERROR: {msg}"))


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker = None

        root.title("YT Downloader")
        root.geometry("820x910")
        root.minsize(760, 780)
        root.configure(bg=BG)

        self.setup_style()
        self.build_vars()
        self.build_ui()
        self.root.after(100, self.poll)

        if not HAS_FFMPEG:
            self.log("ffmpeg not found on PATH. Merging separate video/audio "
                     "streams and MP3 conversion will be unavailable; "
                     "single-file formats will be used instead.")

    # ------------------------------------------------------------ styling --
    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                    bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL,
                    font=("Segoe UI", 10))
        s.configure("Panel.TLabelframe", background=PANEL, bordercolor=FIELD)
        s.configure("Panel.TLabelframe.Label", background=PANEL,
                    foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("Panel.TLabel", background=PANEL, foreground=FG)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED,
                    font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=BG, foreground=FG,
                    font=("Segoe UI", 20, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground=MUTED)
        s.configure("Panel.TCheckbutton", background=PANEL, foreground=FG)
        s.map("Panel.TCheckbutton", background=[("active", PANEL)])
        s.configure("TEntry", insertcolor=FG, padding=5)
        s.configure("TCombobox", padding=4, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", FG)])
        s.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=("Segoe UI", 11, "bold"), padding=(18, 8),
                    borderwidth=0)
        s.map("Accent.TButton",
              background=[("active", ACCENT_HOVER), ("disabled", FIELD)],
              foreground=[("disabled", MUTED)])
        s.configure("Ghost.TButton", background=FIELD, foreground=FG,
                    padding=(12, 6), borderwidth=0)
        s.map("Ghost.TButton", background=[("active", "#33374a")])
        s.configure("Red.Horizontal.TProgressbar", troughcolor=FIELD,
                    background=ACCENT, bordercolor=FIELD, lightcolor=ACCENT,
                    darkcolor=ACCENT, thickness=14)
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def build_vars(self):
        self.v_folder = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.v_quality = tk.StringVar(value="1080p")
        self.v_playlist = tk.BooleanVar(value=False)
        self.v_subs = tk.BooleanVar(value=False)
        self.v_thumb = tk.BooleanVar(value=False)
        self.v_browser = tk.StringVar(value="none")
        self.v_cookiefile = tk.StringVar()
        self.v_proxy = tk.StringVar()
        self.v_ratelimit = tk.StringVar(value="0")  # MiB/s, 0 = unlimited
        self.v_delay_min = tk.StringVar(value="2")
        self.v_delay_max = tk.StringVar(value="6")
        self.v_fragments = tk.StringVar(value="2")
        self.v_status = tk.StringVar(value="Idle")
        self.v_speed = tk.StringVar(value="")
        self.v_progress = tk.DoubleVar(value=0)
        self.v_queue_info = tk.StringVar(value="")

    # ---------------------------------------------------------------- UI --
    def build_ui(self):
        pad = {"padx": 18}
        ttk.Label(self.root, text="YT Downloader", style="Title.TLabel").pack(
            anchor="w", padx=18, pady=(14, 0))
        ttk.Label(self.root, text="Powered by yt-dlp  |  resumable, "
                                  "large-file friendly", style="Sub.TLabel").pack(
            anchor="w", padx=18, pady=(0, 8))

        # URLs
        f = ttk.LabelFrame(self.root, text="  Video URLs (one per line)  ",
                           style="Panel.TLabelframe", padding=10)
        f.pack(fill="x", **pad, pady=4)
        self.txt_urls = tk.Text(f, height=4, bg=FIELD, fg=FG, bd=0,
                                insertbackground=FG, relief="flat",
                                font=("Consolas", 10), padx=8, pady=6)
        self.txt_urls.pack(fill="x")

        # Download options
        f = ttk.LabelFrame(self.root, text="  Download  ",
                           style="Panel.TLabelframe", padding=10)
        f.pack(fill="x", **pad, pady=4)
        r = ttk.Frame(f, style="Panel.TFrame")
        r.pack(fill="x")
        ttk.Label(r, text="Save to", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(r, textvariable=self.v_folder).grid(
            row=0, column=1, sticky="ew", padx=8)
        ttk.Button(r, text="Browse", style="Ghost.TButton",
                   command=self.pick_folder).grid(row=0, column=2)
        ttk.Label(r, text="Quality", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(r, textvariable=self.v_quality, state="readonly",
                     values=list(QUALITIES)).grid(
            row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        r.columnconfigure(1, weight=1)
        c = ttk.Frame(f, style="Panel.TFrame")
        c.pack(fill="x", pady=(8, 0))
        for text, var in (("Download whole playlists", self.v_playlist),
                          ("Subtitles", self.v_subs),
                          ("Save thumbnail", self.v_thumb)):
            ttk.Checkbutton(c, text=text, variable=var,
                            style="Panel.TCheckbutton").pack(
                side="left", padx=(0, 16))

        # Sign-in
        f = ttk.LabelFrame(self.root, text="  Sign in (age / members / "
                                           "private videos)  ",
                           style="Panel.TLabelframe", padding=10)
        f.pack(fill="x", **pad, pady=4)
        r = ttk.Frame(f, style="Panel.TFrame")
        r.pack(fill="x")
        ttk.Label(r, text="Use my signed-in browser", style="Panel.TLabel"
                  ).grid(row=0, column=0, sticky="w")
        ttk.Combobox(r, textvariable=self.v_browser, state="readonly",
                     values=BROWSERS, width=12).grid(
            row=0, column=1, sticky="w", padx=8)
        ttk.Button(r, text="Request Cookies", style="Ghost.TButton",
                   command=self.request_cookies_file).grid(
            row=0, column=2, padx=8, sticky="w")
        ttk.Label(r, text="or cookies.txt", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(r, textvariable=self.v_cookiefile).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(r, text="Browse", style="Ghost.TButton",
                   command=self.pick_cookies).grid(
            row=1, column=2, padx=8, pady=(8, 0))
        r.columnconfigure(1, weight=1)
        ttk.Label(f, text="Log into YouTube in your normal browser first. "
                          "Your Google password is never entered here or stored. "
                          "Tip: 'Request Cookies' extracts your browser session into a cookies.txt file.",
                  style="Muted.TLabel", wraplength=740).pack(anchor="w", pady=(6, 0))

        # Polite-client / network
        f = ttk.LabelFrame(self.root, text="  Network & politeness  ",
                           style="Panel.TLabelframe", padding=10)
        f.pack(fill="x", **pad, pady=4)
        r = ttk.Frame(f, style="Panel.TFrame")
        r.pack(fill="x")
        ttk.Label(r, text="Speed cap (MiB/s, 0 = off)",
                  style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(r, textvariable=self.v_ratelimit, width=6).grid(
            row=0, column=1, padx=8)
        ttk.Label(r, text="Delay between videos (s)",
                  style="Panel.TLabel").grid(row=0, column=2, padx=(16, 0))
        ttk.Entry(r, textvariable=self.v_delay_min, width=4).grid(
            row=0, column=3, padx=(8, 2))
        ttk.Label(r, text="to", style="Panel.TLabel").grid(row=0, column=4)
        ttk.Entry(r, textvariable=self.v_delay_max, width=4).grid(
            row=0, column=5, padx=2)
        ttk.Label(r, text="Parallel fragments", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(r, textvariable=self.v_fragments, state="readonly",
                     values=["1", "2", "3", "4"], width=4).grid(
            row=1, column=1, padx=8, pady=(8, 0))
        ttk.Label(r, text="Proxy (optional)", style="Panel.TLabel").grid(
            row=1, column=2, padx=(16, 0), pady=(8, 0))
        ttk.Entry(r, textvariable=self.v_proxy).grid(
            row=1, column=3, columnspan=3, sticky="ew", padx=8, pady=(8, 0))
        ttk.Label(f, text="Slower, steadier traffic with backoff on errors "
                          "makes throttling and temporary blocks less likely. "
                          "Proxy format: http://host:port or socks5://host:port. "
                          "Nothing here guarantees you won't be rate-limited.",
                  style="Muted.TLabel", wraplength=740).pack(
            anchor="w", pady=(6, 0))

        # Controls
        b = ttk.Frame(self.root)
        b.pack(fill="x", **pad, pady=(8, 2))
        self.btn_start = ttk.Button(b, text="Download", style="Accent.TButton",
                                    command=self.start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(b, text="Cancel", style="Ghost.TButton",
                                     command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        ttk.Label(b, textvariable=self.v_queue_info, style="Sub.TLabel"
                  ).pack(side="right")

        # Progress
        ttk.Progressbar(self.root, variable=self.v_progress, maximum=100,
                        style="Red.Horizontal.TProgressbar").pack(
            fill="x", **pad, pady=(6, 2))
        row = ttk.Frame(self.root)
        row.pack(fill="x", **pad)
        ttk.Label(row, textvariable=self.v_status, style="Sub.TLabel"
                  ).pack(side="left")
        ttk.Label(row, textvariable=self.v_speed, style="Sub.TLabel"
                  ).pack(side="right")

        # Log
        lf = ttk.Frame(self.root)
        lf.pack(fill="both", expand=True, **pad, pady=(6, 14))
        self.log_box = tk.Text(lf, bg=PANEL, fg=MUTED, bd=0, relief="flat",
                               font=("Consolas", 9), wrap="word",
                               state="disabled", padx=8, pady=6, height=6)
        sb = ttk.Scrollbar(lf, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)

    # ----------------------------------------------------------- helpers --
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.v_folder.get())
        if d:
            self.v_folder.set(d)

    def pick_cookies(self):
        p = filedialog.askopenfilename(
            filetypes=[("Cookies", "*.txt"), ("All files", "*.*")])
        if p:
            self.v_cookiefile.set(p)

    def request_cookies_file(self):
        browser = self.v_browser.get()
        if browser == "none":
            messagebox.showwarning(
                "Browser Required",
                "Please select a browser dropdown option first (e.g., chrome, firefox) to extract cookies from.",
            )
            return

        out_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="cookies.txt",
            title="Save Exported Cookies File As",
        )
        if not out_path:
            return

        def task():
            self.q.put(("status", f"Requesting cookies from {browser}..."))
            self.q.put(("log", f"Exporting cookies from browser: {browser} -> {out_path}"))
            try:
                jar = extract_cookies_from_browser(browser, logger=GuiLogger(self.q))
                jar.save(out_path, ignore_discard=True, ignore_expires=True)

                if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                    self.q.put(("log", f"Successfully exported cookies to {out_path}"))
                    self.q.put(("status", "Cookies requested successfully!"))
                    self.q.put(("cookies_saved", out_path))
                else:
                    raise RuntimeError("Cookie export file is empty or was not generated.")
            except Exception as e:
                self.q.put(("log", f"Cookie request failed: {e}"))
                self.q.put(("status", "Cookie request failed"))
                self.q.put((
                    "dialog_error",
                    "Error",
                    f"Could not request cookies from {browser}.\n"
                    f"Make sure the browser is fully closed and try again.\n\nDetails: {e}",
                ))

        threading.Thread(target=task, daemon=True).start()

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg.rstrip() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def read_float(self, var, default, lo=0, hi=10_000):
        try:
            return max(lo, min(hi, float(var.get())))
        except ValueError:
            return default

    # ----------------------------------------------------------- control --
    def start(self):
        urls = [u.strip() for u in self.txt_urls.get("1.0", "end").splitlines()
                if u.strip()]
        if not urls:
            messagebox.showwarning("No URLs", "Paste at least one URL.")
            return
        folder = self.v_folder.get().strip()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Folder error", str(e))
            return
        if self.v_cookiefile.get().strip() and not os.path.isfile(
                self.v_cookiefile.get().strip()):
            messagebox.showerror("Cookies", "cookies.txt file not found.")
            return

        self.cancel_flag.clear()
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.v_progress.set(0)
        settings = self.collect_settings(folder)
        self.worker = threading.Thread(
            target=self.run_queue, args=(urls, settings), daemon=True)
        self.worker.start()

    def cancel(self):
        self.cancel_flag.set()
        self.v_status.set("Cancelling...")

    def collect_settings(self, folder):
        dmin = self.read_float(self.v_delay_min, 2, 0, 600)
        dmax = max(dmin, self.read_float(self.v_delay_max, 6, 0, 600))
        return {
            "folder": folder,
            "quality": QUALITIES[self.v_quality.get()],
            "playlist": self.v_playlist.get(),
            "subs": self.v_subs.get(),
            "thumb": self.v_thumb.get(),
            "browser": self.v_browser.get(),
            "cookiefile": self.v_cookiefile.get().strip(),
            "proxy": self.v_proxy.get().strip(),
            "ratelimit": self.read_float(self.v_ratelimit, 0, 0, 10_000),
            "delay_min": dmin,
            "delay_max": dmax,
            "fragments": int(self.v_fragments.get()),
        }

    # ------------------------------------------------------------ worker --
    def build_opts(self, st):
        quality = st["quality"]
        opts = {
            "outtmpl": os.path.join(
                st["folder"], "%(title).150B [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "noplaylist": not st["playlist"],
            "logger": GuiLogger(self.q),
            "progress_hooks": [self.hook],
            "noprogress": True,
            "quiet": True,
            "no_warnings": False,

            # --- large files / reliability ---
            "continuedl": True,  # resume .part files
            "nooverwrites": True,
            "http_chunk_size": 10 * 1024 * 1024,  # 10 MiB ranged chunks
            "concurrent_fragment_downloads": st["fragments"],
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 5,
            "extractor_retries": 5,
            "socket_timeout": 30,
            "retry_sleep_functions": {  # exponential backoff, capped at 60s
                "http": lambda n: min(2 ** n, 60),
                "fragment": lambda n: min(2 ** n, 60),
                "extractor": lambda n: min(2 ** n, 60),
            },

            # --- polite client ---
            "sleep_interval_requests": 1,
            "sleep_interval": st["delay_min"],
            "max_sleep_interval": st["delay_max"],
        }
        if st["ratelimit"] > 0:
            opts["ratelimit"] = int(st["ratelimit"] * 1024 * 1024)
        if st["proxy"]:
            opts["proxy"] = st["proxy"]

        # --- sign-in: reuse the browser's own logged-in session ---
        if st["cookiefile"]:
            opts["cookiefile"] = st["cookiefile"]
        elif st["browser"] != "none":
            opts["cookiesfrombrowser"] = (st["browser"],)

        # --- format selection ---
        if quality in ("mp3", "m4a"):
            opts["format"] = "bestaudio/best/b"
            if HAS_FFMPEG:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": quality,
                    "preferredquality": "0",
                }]
        else:
            cap = f"[height<={quality}]" if quality else ""
            if HAS_FFMPEG:
                # last "/b" = fall back to whatever best single file exists
                opts["format"] = f"bv*{cap}+ba/b{cap}/bv*+ba/b"
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = f"b{cap}/b"

        pps = opts.setdefault("postprocessors", [])
        if st["subs"]:
            opts.update(writesubtitles=True, subtitleslangs=["en.*"])
            if HAS_FFMPEG and quality != "mp3":
                pps.append({"key": "FFmpegEmbedSubtitle"})
        if st["thumb"]:
            opts["writethumbnail"] = True
        return opts

    def hook(self, d):
        if self.cancel_flag.is_set():
            raise DownloadCancelled("Cancelled by user")
        if d["status"] == "downloading":
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = (done / total * 100) if total else 0
            text = f"{human_bytes(done)} / {human_bytes(total)}"
            speed = (f"{human_bytes(d.get('speed'))}/s   "
                     f"ETA {human_time(d.get('eta'))}"
                     if d.get("speed") else "")
            self.q.put(("progress", pct, text, speed))
        elif d["status"] == "finished":
            self.q.put(("progress", 100, "Post-processing...", ""))

    def check_disk_space(self, info, folder):
        """Warn early if a single video clearly won't fit on disk."""
        if info.get("_type") == "playlist":
            return True
        size = info.get("filesize") or info.get("filesize_approx")
        if not size:
            reqs = info.get("requested_formats") or []
            size = sum((f.get("filesize") or f.get("filesize_approx") or 0)
                       for f in reqs)
        if not size:
            return True
        free = shutil.disk_usage(folder).free
        # leave headroom for merge step (~2x temporarily)
        if free < size * 2.1:
            self.q.put(("log", f"Not enough free disk space: need about "
                               f"{human_bytes(size * 2.1)}, have {human_bytes(free)}"))
            return False
        return True

    def run_queue(self, urls, st):
        ok = fail = 0
        total = len(urls)
        for i, url in enumerate(urls, 1):
            if self.cancel_flag.is_set():
                break
            self.q.put(("queue", f"Item {i} of {total}"))
            self.q.put(("status", f"Fetching info: {url}"))
            try:
                with yt_dlp.YoutubeDL(self.build_opts(st)) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        raise RuntimeError("No information returned")
                    title = info.get("title", url)
                    self.q.put(("status", f"Downloading: {title}"))
                    if not self.check_disk_space(info, st["folder"]):
                        raise RuntimeError("Insufficient disk space")
                    ydl.process_ie_result(info, download=True)
                ok += 1
                self.q.put(("log", f"Done: {title}"))
            except DownloadCancelled:
                self.q.put(("log", "Download cancelled. Partial files are "
                                   "kept so you can resume later."))
                break
            except Exception as e:  # noqa: BLE001
                fail += 1
                self.q.put(("log", f"Failed: {url}\n    {e}"))
                if "429" in str(e) or "Too Many Requests" in str(e):
                    self.q.put(("log", "The server is rate-limiting you. "
                                       "Lower the speed cap, raise the delays, "
                                       "and wait a while before retrying."))
                    break
            # randomized pause between items
            if i < total and not self.cancel_flag.is_set():
                pause = random.uniform(st["delay_min"], st["delay_max"])
                self.q.put(("status", f"Waiting {pause:.1f}s before next..."))
                end = time.time() + pause
                while time.time() < end and not self.cancel_flag.is_set():
                    time.sleep(0.2)
        self.q.put(("finished", ok, fail))

    # -------------------------------------------------------------- poll --
    def poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "log":
                    self.log(m[1])
                elif kind == "status":
                    self.v_status.set(m[1])
                elif kind == "queue":
                    self.v_queue_info.set(m[1])
                elif kind == "progress":
                    self.v_progress.set(m[1])
                    self.v_status.set(m[2])
                    self.v_speed.set(m[3])
                elif kind == "cookies_saved":
                    out_path = m[1]
                    self.v_cookiefile.set(out_path)
                    messagebox.showinfo(
                        "Success",
                        f"Cookies successfully extracted and saved to:\n{out_path}",
                    )
                elif kind == "dialog_error":
                    messagebox.showerror(m[1], m[2])
                elif kind == "finished":
                    self.btn_start.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    self.v_speed.set("")
                    self.v_queue_info.set("")
                    self.v_status.set(
                        f"Finished: {m[1]} succeeded, {m[2]} failed")
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()