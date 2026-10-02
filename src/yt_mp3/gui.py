"""CustomTkinter main window: Material 3 look, same structure as the Android app."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import warnings

import customtkinter as ctk

from . import __version__
from .icons import SPINNER_FRAMES, Icons
from .settings import BITRATES, Settings
from .util import resource_path
from .worker import JobOptions, Worker

POLL_MS = 100
# icons are tk.PhotoImages rendered at the window's DPI scale (no Pillow -> no CTkImage)
warnings.filterwarnings("ignore", message=".*is not CTkImage.*")

# Material 3 baseline color scheme (seed #6750A4) + a green "success" role: (light, dark)
M3 = {
    "primary": ("#6750A4", "#D0BCFF"),
    "on_primary": ("#FFFFFF", "#381E72"),
    "secondary_container": ("#E8DEF8", "#4A4458"),
    "on_secondary_container": ("#1D192B", "#E8DEF8"),
    "surface": ("#FEF7FF", "#141218"),
    "surface_container": ("#F3EDF7", "#211F26"),
    "surface_highest": ("#E6E0E9", "#36343B"),
    "on_surface": ("#1D1B20", "#E6E0E9"),
    "on_surface_variant": ("#49454F", "#CAC4D0"),
    "outline": ("#79747E", "#938F99"),
    "outline_variant": ("#CAC4D0", "#49454F"),
    "error": ("#B3261E", "#F2B8B5"),
    "on_error": ("#FFFFFF", "#601410"),
    "success": ("#1E7B3A", "#7DD99B"),
    "on_success": ("#FFFFFF", "#00391B"),
}


def _mix(a: str, b: str, t: float) -> str:
    """Color a with a t-opacity layer of b (Material state layers)."""
    ca, cb = (tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for c in (a, b))
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def state(base: str, over: str = "on_surface", t: float = 0.08):
    """Hover color: `over` at 8% on top of `base`, for both themes."""
    return tuple(_mix(M3[base][i], M3[over][i], t) for i in (0, 1))


def _load_fonts() -> str:
    """Register the bundled fonts for this process only (Windows); return the UI font family."""
    if sys.platform == "win32":
        try:
            import ctypes

            for name in ("Roboto-Regular.ttf", "Roboto-Bold.ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(str(resource_path(f"assets/{name}")), 0x10, 0)  # FR_PRIVATE
        except Exception:
            pass
    return "Roboto"


def _track_kind(text: str) -> str:
    if text.startswith("Error"):
        return "error"
    if text == "Done":
        return "done"
    if text.startswith(("Skipped", "Cancelled")):
        return "skipped"
    if text.startswith(("Downloading", "Converting")):
        return "active"
    return "queued"


class App(ctk.CTk):
    def __init__(self):
        family = _load_fonts()
        super().__init__(fg_color=M3["surface"])
        if family not in tkfont.families(self):
            family = "Segoe UI"
        self.family = family
        self.settings = Settings.load()
        self.events: queue.Queue = queue.Queue()
        self.worker: Worker | None = None
        self.rows: dict[int, str] = {}  # worker key -> treeview item id
        self.active: set[str] = set()  # rows showing the spinner
        self.spin_frame = 0

        self.title(f"YT to MP3  {__version__}")
        self.geometry("880x660")
        self.minsize(720, 540)
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            self.iconbitmap(str(icon))

        self.dark = ctk.get_appearance_mode() == "Dark"
        self.colors = {k: v[1 if self.dark else 0] for k, v in M3.items()}
        self.icons = Icons(self, self.colors)
        scale = ctk.ScalingTracker.get_window_scaling(self)
        self.px = lambda v: round(v * scale)  # ttk widgets and images are not scaled by CTk

        self._build()
        self._style_trees()
        self.show_page("download")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll)

    # -- small widget factories -------------------------------------------------

    def font(self, size=13, weight="normal"):
        return ctk.CTkFont(family=self.family, size=size, weight=weight)

    def label(self, master, text="", size=13, color="on_surface", weight="normal", **kw):
        return ctk.CTkLabel(master, text=text, font=self.font(size, weight), text_color=M3[color], **kw)

    def button(self, master, text, command, kind="filled", icon=None, **kw):
        """Material buttons: filled, tonal, outlined, text, chip, icon."""
        style = {
            "filled": dict(fg_color=M3["primary"], hover_color=state("primary", "on_primary"),
                           text_color=M3["on_primary"], height=40, corner_radius=20),
            "tonal": dict(fg_color=M3["secondary_container"], text_color=M3["on_secondary_container"],
                          hover_color=state("secondary_container", "on_secondary_container"),
                          height=40, corner_radius=20),
            "outlined": dict(fg_color="transparent", border_width=1, border_color=M3["outline"],
                             text_color=M3["primary"], hover_color=state("surface", "primary"),
                             height=40, corner_radius=20),
            "text": dict(fg_color="transparent", text_color=M3["primary"], hover_color=state("surface", "primary"),
                         height=40, corner_radius=20),
            "chip": dict(fg_color="transparent", border_width=1, border_color=M3["outline_variant"],
                         text_color=M3["on_surface"], hover_color=state("surface"), height=32, corner_radius=8),
            "icon": dict(fg_color="transparent", hover_color=state("surface"), text_color=M3["on_surface_variant"],
                         width=40, height=40, corner_radius=20),
        }[kind]
        style["text_color_disabled"] = tuple(_mix(M3["surface"][i], M3["on_surface"][i], 0.38) for i in (0, 1))
        style.update(kw)
        if icon is not None:
            style.update(image=icon, compound="left")
        if kind != "icon":
            style.setdefault("width", 0)
        return ctk.CTkButton(master, text=text, command=command,
                             font=self.font(13 if kind == "chip" else 14, "bold" if kind != "chip" else "normal"),
                             **style)

    def card(self, master, **kw):
        return ctk.CTkFrame(master, fg_color=M3["surface_container"], corner_radius=16, **kw)

    # -- layout -----------------------------------------------------------------

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_rail()
        self.pages = {"download": self._build_download(), "library": self._build_library()}

    def _build_rail(self):
        rail = ctk.CTkFrame(self, fg_color=M3["surface"], corner_radius=0, width=88)
        rail.grid(row=0, column=0, sticky="ns")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        tk.Label(rail, image=self.icons.app(self.px(36)), bg=self.colors["surface"], bd=0).grid(
            row=0, column=0, pady=(20, 28))
        self.nav = {}
        for i, (name, icon, text) in enumerate((("download", "download", "Download"),
                                               ("library", "library", "Library"))):
            pill = ctk.CTkButton(rail, text="", width=56, height=32, corner_radius=16, fg_color="transparent",
                                 hover_color=state("surface"), command=lambda n=name: self.show_page(n))
            pill.grid(row=1 + 2 * i, column=0)
            lbl = self.label(rail, text, size=12, color="on_surface_variant")
            lbl.grid(row=2 + 2 * i, column=0, pady=(4, 16))
            lbl.bind("<Button-1>", lambda e, n=name: self.show_page(n))
            self.nav[name] = (pill, lbl, icon)

    def show_page(self, name):
        for page in self.pages.values():
            page.grid_remove()
        self.pages[name].grid(row=0, column=1, sticky="nsew", padx=(0, 24), pady=(16, 20))
        self.page = name
        for n, (pill, lbl, icon) in self.nav.items():
            on = n == name
            role = "on_secondary_container" if on else "on_surface_variant"
            pill.configure(image=self.icons.glyph(icon, self.px(22), role),
                           fg_color=M3["secondary_container"] if on else "transparent",
                           hover_color=state("secondary_container" if on else "surface"))
            lbl.configure(text_color=M3["on_surface" if on else "on_surface_variant"],
                          font=self.font(12, "bold" if on else "normal"))
        if name == "library":
            self.refresh_library()

    def _build_download(self):
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(6, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.label(head, "YT to MP3", size=24).pack(side="left")
        self.label(head, f"  {__version__}", size=12, color="on_surface_variant").pack(side="left", pady=(8, 0))

        # links
        self.label(page, "YouTube links  ·  video or playlist, one per line", size=12,
                   color="on_surface_variant", anchor="w").grid(row=1, column=0, sticky="ew", padx=4)
        self.urls = ctk.CTkTextbox(page, height=76, wrap="none", corner_radius=8, border_width=1,
                                   border_color=M3["outline"], fg_color=M3["surface"], text_color=M3["on_surface"],
                                   font=self.font(13))
        self.urls.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        self.urls.bind("<Button-3>", self._paste_menu)
        chips = ctk.CTkFrame(page, fg_color="transparent")
        chips.grid(row=3, column=0, sticky="w")
        icon = self.px(18)
        self.button(chips, "Paste", self._paste, "chip", self.icons.glyph("paste", icon, "primary")).pack(side="left")
        self.button(chips, "Clear", lambda: self.urls.delete("1.0", "end"), "chip",
                    self.icons.glyph("close", icon, "primary")).pack(side="left", padx=(8, 0))

        # options card
        opts = self.card(page)
        opts.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        opts.grid_columnconfigure(1, weight=1)
        self.label(opts, "Save to", color="on_surface_variant").grid(row=0, column=0, sticky="w", padx=(20, 12),
                                                                     pady=(18, 0))
        self.out_dir = ctk.StringVar(value=self.settings.out_dir)
        ctk.CTkEntry(opts, textvariable=self.out_dir, height=40, corner_radius=8, border_width=1,
                     border_color=M3["outline"], fg_color=M3["surface"], text_color=M3["on_surface"],
                     font=self.font(13)).grid(row=0, column=1, sticky="ew", pady=(18, 0))
        self.button(opts, "Browse", self._browse, "tonal",
                    self.icons.glyph("folder", icon, "on_secondary_container")).grid(
            row=0, column=2, padx=(8, 0), pady=(18, 0))
        self.button(opts, "Open", self._open_folder, "text",
                    self.icons.glyph("open", icon, "primary")).grid(row=0, column=3, padx=(4, 16), pady=(18, 0))

        self.label(opts, "Quality", color="on_surface_variant").grid(row=1, column=0, sticky="w", padx=(20, 12),
                                                                     pady=(14, 0))
        self.bitrate = ctk.StringVar(value=f"{self.settings.bitrate_kbps} kbps")
        ctk.CTkSegmentedButton(opts, values=[f"{b} kbps" for b in BITRATES], variable=self.bitrate,
                               height=36, corner_radius=18, border_width=1, fg_color=M3["outline_variant"],
                               selected_color=M3["secondary_container"],
                               selected_hover_color=state("secondary_container", "on_secondary_container"),
                               unselected_color=M3["surface_container"], unselected_hover_color=state("surface_container"),
                               text_color=M3["on_surface"], font=self.font(13)).grid(
            row=1, column=1, sticky="w", pady=(14, 0))

        switches = ctk.CTkFrame(opts, fg_color="transparent")
        switches.grid(row=2, column=0, columnspan=4, sticky="w", padx=(16, 0), pady=(10, 14))
        self.subfolder = ctk.BooleanVar(value=self.settings.playlist_subfolder)
        self.skip = ctk.BooleanVar(value=self.settings.skip_existing)
        for var, text in ((self.subfolder, "Playlists into their own folder"), (self.skip, "Skip existing files")):
            ctk.CTkSwitch(switches, text=text, variable=var, switch_width=44, switch_height=24,
                          fg_color=M3["surface_highest"], progress_color=M3["primary"],
                          button_color=M3["on_primary"], button_hover_color=M3["on_primary"],
                          border_width=2, border_color=M3["outline"], text_color=M3["on_surface"],
                          font=self.font(13)).pack(side="left", padx=(4, 28))

        # actions
        btns = ctk.CTkFrame(page, fg_color="transparent")
        btns.grid(row=5, column=0, sticky="ew", pady=12)
        self.start_btn = self.button(btns, "Download MP3", self._start, "filled",
                                     self.icons.glyph("download", self.px(20), "on_primary"), width=190, height=44,
                                     corner_radius=22)
        self.start_btn.pack(side="left")
        self.cancel_btn = self.button(btns, "Cancel", self._cancel, "outlined", height=44, corner_radius=22,
                                      width=110, text_color=M3["error"], state="disabled")
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.button(btns, "Clear list", self._clear, "text").pack(side="right")

        # progress + track list
        prog = ctk.CTkFrame(page, fg_color="transparent")
        prog.grid(row=6, column=0, sticky="nsew")
        prog.grid_columnconfigure(0, weight=1)
        prog.grid_rowconfigure(2, weight=1)
        self.progress = ctk.CTkProgressBar(prog, height=6, corner_radius=3, fg_color=M3["secondary_container"],
                                           progress_color=M3["primary"])
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.status = self.label(prog, "Ready.", color="on_surface_variant", anchor="w")
        self.status.grid(row=1, column=0, sticky="ew", pady=(4, 8))

        box = self.card(prog)
        box.grid(row=2, column=0, sticky="nsew")
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(box, columns=("status",), show="tree", style="M3.Treeview", selectmode="browse")
        self.tree.column("#0", stretch=True, width=480)
        self.tree.column("status", anchor="w", stretch=False, width=self.px(240))
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        sb = ctk.CTkScrollbar(box, command=self.tree.yview, button_color=M3["outline_variant"])
        sb.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 4))
        self.tree.configure(yscrollcommand=sb.set)
        self.empty = self.label(box, "Downloaded tracks show up here.", color="on_surface_variant",
                                fg_color=M3["surface_container"])
        self.empty.place(relx=0.5, rely=0.5, anchor="center")
        return page

    def _build_library(self):
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        head.grid_columnconfigure(0, weight=1)
        self.label(head, "Library", size=24, anchor="w").grid(row=0, column=0, sticky="w")
        self.lib_where = self.label(head, "", size=12, color="on_surface_variant", anchor="w")
        self.lib_where.grid(row=1, column=0, sticky="w")
        self.button(head, "", self.refresh_library, "icon",
                    self.icons.glyph("refresh", self.px(22))).grid(row=0, column=1, rowspan=2, padx=(0, 8))
        self.button(head, "Open folder", self._open_folder, "tonal",
                    self.icons.glyph("folder", self.px(18), "on_secondary_container")).grid(
            row=0, column=2, rowspan=2)

        box = self.card(page)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)
        self.lib = ttk.Treeview(box, columns=("size", "date"), show="tree headings", style="Lib.Treeview",
                                selectmode="browse")
        self.lib.heading("#0", text="Name", anchor="w")
        self.lib.heading("size", text="Size", anchor="w")
        self.lib.heading("date", text="Modified", anchor="w")
        self.lib.column("#0", stretch=True, width=420)
        self.lib.column("size", anchor="w", stretch=False, width=self.px(100))
        self.lib.column("date", anchor="w", stretch=False, width=self.px(130))
        self.lib.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        sb = ctk.CTkScrollbar(box, command=self.lib.yview, button_color=M3["outline_variant"])
        sb.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 4))
        self.lib.configure(yscrollcommand=sb.set)
        self.lib.bind("<<TreeviewOpen>>", self._lib_expand)
        self.lib.bind("<Double-1>", self._lib_activate)
        self.lib.bind("<Return>", self._lib_activate)
        self.lib.bind("<Button-3>", self._lib_menu)
        self.lib_paths: dict[str, Path] = {}
        self.lib_empty = self.label(box, "No MP3s here yet.", color="on_surface_variant",
                                    fg_color=M3["surface_container"])
        self.label(page, "Double-click a track to play it. Right-click for more.", size=12,
                   color="on_surface_variant", anchor="w").grid(row=2, column=0, sticky="w", padx=4, pady=(8, 0))
        return page

    def _style_trees(self):
        c = self.colors
        style = ttk.Style(self)
        style.theme_use("clam")
        font = tkfont.Font(family=self.family, size=10)
        line = font.metrics("linespace")
        for name, height in (("M3.Treeview", line * 2 + 6), ("Lib.Treeview", line * 2 + 4)):
            style.configure(name, background=c["surface_container"], fieldbackground=c["surface_container"],
                            foreground=c["on_surface"], rowheight=height, borderwidth=0, font=font,
                            bordercolor=c["surface_container"], lightcolor=c["surface_container"],
                            darkcolor=c["surface_container"], indent=self.px(20))
            style.map(name, background=[("selected", c["secondary_container"])],
                      foreground=[("selected", c["on_secondary_container"])])
            style.layout(name, [("Treeview.treearea", {"sticky": "nswe"})])  # no focus/border frame
        style.configure("Lib.Treeview.Heading", background=c["surface_container"], foreground=c["on_surface_variant"],
                        relief="flat", font=(self.family, 9, "bold"), padding=(4, 6),
                        bordercolor=c["surface_container"], lightcolor=c["surface_container"],
                        darkcolor=c["surface_container"])
        style.map("Lib.Treeview.Heading", background=[("active", c["surface_container"])])
        self.icon_px = round(line * 1.5)
        for tree in (self.tree, self.lib):
            tree.tag_configure("muted", foreground=c["on_surface_variant"])
            tree.tag_configure("error", foreground=c["error"])
            tree.tag_configure("info", foreground=c["on_surface_variant"])

    # -- download actions -------------------------------------------------------

    def _paste(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        existing = self.urls.get("1.0", "end").strip()
        new = [u for u in text.split() if u.startswith("http") and u not in existing]
        if new:
            self.urls.insert("end", ("\n" if existing else "") + "\n".join(new))

    def _paste_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Paste", command=self._paste)
        menu.add_command(label="Clear", command=lambda: self.urls.delete("1.0", "end"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.home()), mustexist=False)
        if d:
            self.out_dir.set(os.path.normpath(d))
            if self.page == "library":
                self.refresh_library()

    def _open_folder(self):
        d = self.out_dir.get().strip()
        if d and Path(d).is_dir():
            os.startfile(d)

    def _clear(self):
        if self.worker and self.worker.is_alive():
            return
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.active.clear()
        self.progress.set(0)
        self.status.configure(text="Ready.")
        self.empty.place(relx=0.5, rely=0.5, anchor="center")

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
        self.after(80, self._spin)

    def _cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_btn.configure(state="disabled")
            self.status.configure(text="Cancelling...")

    def _spin(self):
        self.spin_frame = (self.spin_frame + 1) % SPINNER_FRAMES
        img = self.icons.status("active", self.icon_px, self.spin_frame)
        for item in self.active:
            self.tree.item(item, image=img)
        if self.worker and self.worker.is_alive():
            self.after(80, self._spin)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("YT to MP3", "Downloads are in progress. Cancel them and exit?", parent=self):
                return
            self.worker.cancel.set()
            self.worker.join(timeout=5)
        self._save_settings()
        self.destroy()

    # -- library ----------------------------------------------------------------

    def refresh_library(self):
        root = Path(self.out_dir.get().strip() or Path.home())
        self.lib_where.configure(text=str(root))
        self.lib.delete(*self.lib.get_children())
        self.lib_paths.clear()
        self._lib_fill("", root)
        if self.lib.get_children():
            self.lib_empty.place_forget()
        else:
            self.lib_empty.place(relx=0.5, rely=0.5, anchor="center")

    def _lib_fill(self, parent, folder: Path):
        """Insert one folder level: subfolders (by name, loaded on expand), then MP3s newest first."""
        dirs, files = [], []
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for e in entries:
            try:
                if e.is_dir() and not e.name.startswith("."):
                    dirs.append(e)
                elif e.name.lower().endswith(".mp3"):
                    files.append((e.stat().st_mtime, e.stat().st_size, e))
            except OSError:
                continue
        folder_img = self.icons.glyph("folder", self.icon_px, "primary")
        music_img = self.icons.glyph("music", self.icon_px, "on_surface_variant")
        for e in sorted(dirs, key=lambda d: d.name.lower()):
            try:
                n = sum(1 for f in os.scandir(e.path) if f.name.lower().endswith(".mp3"))
            except OSError:
                n = 0
            item = self.lib.insert(parent, "end", text=f"  {e.name}", image=folder_img,
                                   values=(f"{n} track{'s' if n != 1 else ''}" if n else "", ""), tags=("info",))
            self.lib_paths[item] = Path(e.path)
            self.lib.insert(item, "end", text="")  # placeholder so the folder can be expanded
        for mtime, size, e in sorted(files, key=lambda f: f[0], reverse=True):
            item = self.lib.insert(parent, "end", text=f"  {e.name[:-4]}", image=music_img,
                                   values=(f"{size / 1e6:.1f} MB", time.strftime("%d %b %Y", time.localtime(mtime))))
            self.lib_paths[item] = Path(e.path)

    def _lib_expand(self, event=None):
        item = self.lib.focus()
        kids = self.lib.get_children(item)
        if len(kids) == 1 and not self.lib.item(kids[0], "text"):
            self.lib.delete(kids[0])
            self._lib_fill(item, self.lib_paths[item])

    def _lib_activate(self, event=None):
        item = self.lib.focus()
        path = self.lib_paths.get(item)
        if path and path.is_file():
            os.startfile(path)

    def _lib_menu(self, event):
        item = self.lib.identify_row(event.y)
        path = self.lib_paths.get(item)
        if not path:
            return
        self.lib.selection_set(item)
        self.lib.focus(item)
        menu = tk.Menu(self, tearoff=0)
        if path.is_file():
            menu.add_command(label="Play", command=lambda: os.startfile(path))
        else:
            menu.add_command(label="Open", command=lambda: os.startfile(path))
        menu.add_command(label="Show in Explorer", command=lambda: subprocess.Popen(["explorer", "/select,", str(path)]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # -- worker events ----------------------------------------------------------

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
            self.empty.place_forget()
            self.rows[key] = self.tree.insert("", "end", text=f"  {title}", values=("Waiting",),
                                              image=self.icons.status("queued", self.icon_px), tags=("muted",))
        elif kind == "track":
            _, key, text = event
            item = self.rows.get(key)
            if item:
                state_ = _track_kind(text)
                tags = {"error": ("error",), "skipped": ("muted",), "queued": ("muted",)}.get(state_, ())
                if state_ == "active":
                    self.active.add(item)
                    img = self.icons.status("active", self.icon_px, self.spin_frame)
                else:
                    self.active.discard(item)
                    img = self.icons.status(state_, self.icon_px)
                self.tree.item(item, values=(text,), tags=tags, image=img)
                if state_ == "active":
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
            self.active.clear()
            if self.page == "library":
                self.refresh_library()


def main():
    try:  # own taskbar icon instead of python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yt-mp3.app")
    except Exception:
        pass
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    App().mainloop()
