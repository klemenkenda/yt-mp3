"""CustomTkinter main window."""
from __future__ import annotations

import os
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import customtkinter as ctk

from . import __version__
from .settings import BITRATES, Settings
from .util import resource_path
from .worker import JobOptions, Worker

POLL_MS = 100


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.events: queue.Queue = queue.Queue()
        self.worker: Worker | None = None
        self.rows: dict[int, str] = {}  # worker key -> treeview item id

        self.title(f"YT to MP3  {__version__}")
        self.geometry("820x640")
        self.minsize(640, 480)
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            self.iconbitmap(str(icon))

        self._build()
        self._style_tree()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll)

    # -- layout ---------------------------------------------------------------

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        pad = {"padx": 16}

        ctk.CTkLabel(self, text="YouTube links (video or playlist, one per line)", anchor="w").grid(
            row=0, column=0, sticky="ew", pady=(14, 4), **pad)
        self.urls = ctk.CTkTextbox(self, height=100, wrap="none")
        self.urls.grid(row=1, column=0, sticky="ew", **pad)
        self.urls.bind("<Button-3>", self._paste_menu)

        # destination + options
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=2, column=0, sticky="ew", pady=(12, 0), **pad)
        opts.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(opts, text="Save to").grid(row=0, column=0, padx=(0, 8))
        self.out_dir = ctk.StringVar(value=self.settings.out_dir)
        ctk.CTkEntry(opts, textvariable=self.out_dir).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(opts, text="Browse...", width=90, command=self._browse).grid(row=0, column=2, padx=(8, 0))
        ctk.CTkButton(opts, text="Open", width=60, command=self._open_folder,
                      fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90")).grid(row=0, column=3, padx=(8, 0))

        row2 = ctk.CTkFrame(opts, fg_color="transparent")
        row2.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(row2, text="Quality").pack(side="left", padx=(0, 8))
        self.bitrate = ctk.StringVar(value=f"{self.settings.bitrate_kbps} kbps")
        ctk.CTkOptionMenu(row2, values=[f"{b} kbps" for b in BITRATES], variable=self.bitrate,
                          width=110).pack(side="left")
        self.subfolder = ctk.BooleanVar(value=self.settings.playlist_subfolder)
        ctk.CTkCheckBox(row2, text="Playlists into their own folder", variable=self.subfolder).pack(
            side="left", padx=(20, 0))
        self.skip = ctk.BooleanVar(value=self.settings.skip_existing)
        ctk.CTkCheckBox(row2, text="Skip existing files", variable=self.skip).pack(side="left", padx=(20, 0))

        # buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", pady=12, **pad)
        self.start_btn = ctk.CTkButton(btns, text="Download MP3", width=160, height=36, command=self._start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(btns, text="Cancel", width=100, height=36, state="disabled",
                                        fg_color="#b23b3b", hover_color="#8f2e2e", command=self._cancel)
        self.cancel_btn.pack(side="left", padx=(10, 0))
        ctk.CTkButton(btns, text="Clear list", width=90, height=36, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._clear).pack(side="right")

        # track list
        frame = ctk.CTkFrame(self)
        frame.grid(row=4, column=0, sticky="nsew", **pad)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=("title", "status"), show="headings", style="Tracks.Treeview")
        self.tree.heading("title", text="Title", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        self.tree.column("title", anchor="w", stretch=True, width=480)
        self.tree.column("status", anchor="w", stretch=False, width=230)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb = ctk.CTkScrollbar(frame, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self.tree.configure(yscrollcommand=sb.set)

        # progress
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(12, 4), **pad)
        self.status = ctk.CTkLabel(self, text="Ready.", anchor="w")
        self.status.grid(row=6, column=0, sticky="ew", pady=(0, 12), **pad)

    def _style_tree(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg, head = ("#2b2b2b", "#e6e6e6", "#333333") if dark else ("#f5f5f5", "#1a1a1a", "#e2e2e2")
        sel = "#1f6aa5"
        style = ttk.Style(self)
        style.theme_use("clam")
        font = tkfont.Font(family="Segoe UI", size=10)
        style.configure("Tracks.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                        rowheight=font.metrics("linespace") + 8, borderwidth=0, font=font,
                        bordercolor=bg, lightcolor=bg, darkcolor=bg)
        style.map("Tracks.Treeview", background=[("selected", sel)], foreground=[("selected", "white")])
        style.configure("Tracks.Treeview.Heading", background=head, foreground=fg, relief="flat",
                        font=("Segoe UI Semibold", 10), bordercolor=head, lightcolor=head, darkcolor=head)
        style.map("Tracks.Treeview.Heading", background=[("active", head)])
        self.tree.tag_configure("error", foreground="#e05555" if dark else "#b00020")
        self.tree.tag_configure("done", foreground="#5cb85c" if dark else "#1e7b34")
        self.tree.tag_configure("muted", foreground="#9a9a9a" if dark else "#707070")

    # -- actions --------------------------------------------------------------

    def _paste_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Paste", command=lambda: self.urls.insert("insert", self.clipboard_get()))
        menu.add_command(label="Clear", command=lambda: self.urls.delete("1.0", "end"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.home()), mustexist=False)
        if d:
            self.out_dir.set(os.path.normpath(d))

    def _open_folder(self):
        d = self.out_dir.get().strip()
        if d and Path(d).is_dir():
            os.startfile(d)

    def _clear(self):
        if self.worker and self.worker.is_alive():
            return
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.progress.set(0)
        self.status.configure(text="Ready.")

    def _save_settings(self):
        self.settings.out_dir = self.out_dir.get().strip()
        self.settings.bitrate_kbps = int(self.bitrate.get().split()[0])
        self.settings.playlist_subfolder = bool(self.subfolder.get())
        self.settings.skip_existing = bool(self.skip.get())
        self.settings.save()

    def _start(self):
        urls = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("YT to MP3", "Paste at least one YouTube link.", parent=self)
            return
        out = self.out_dir.get().strip()
        if not out:
            messagebox.showinfo("YT to MP3", "Choose a destination folder.", parent=self)
            return
        try:
            Path(out).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("YT to MP3", f"Cannot use folder:\n{e}", parent=self)
            return
        self._save_settings()
        self._clear()
        self.worker = Worker(
            JobOptions(
                urls=urls,
                out_dir=Path(out),
                bitrate_kbps=self.settings.bitrate_kbps,
                playlist_subfolder=self.settings.playlist_subfolder,
                skip_existing=self.settings.skip_existing,
            ),
            self.events,
        )
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status.configure(text="Starting...")
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_btn.configure(state="disabled")
            self.status.configure(text="Cancelling...")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("YT to MP3", "Downloads are in progress. Cancel them and exit?", parent=self):
                return
            self.worker.cancel.set()
            self.worker.join(timeout=5)
        self._save_settings()
        self.destroy()

    # -- worker events --------------------------------------------------------

    def _poll(self):
        try:
            for _ in range(500):
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _handle(self, event):
        kind = event[0]
        if kind == "add":
            _, key, title = event
            self.rows[key] = self.tree.insert("", "end", values=(title, ""))
        elif kind == "track":
            _, key, text = event
            item = self.rows.get(key)
            if item:
                tag = ("error",) if text.startswith("Error") else ("done",) if text == "Done" else \
                    ("muted",) if text.startswith(("Skipped", "Cancelled")) else ()
                self.tree.item(item, values=(self.tree.set(item, "title"), text), tags=tag)
                if text in ("Downloading", "Converting"):
                    self.tree.see(item)
        elif kind == "overall":
            _, frac, text = event
            if frac is not None:
                self.progress.set(frac)
            if text:
                self.status.configure(text=text)
        elif kind == "log":
            pass  # warnings are surfaced per row; keep the UI quiet
        elif kind == "done":
            self.status.configure(text=event[1])
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")


def main():
    try:  # own taskbar icon instead of python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yt-mp3.app")
    except Exception:
        pass
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    App().mainloop()
