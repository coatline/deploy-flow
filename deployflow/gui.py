from __future__ import annotations

import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path
from typing import Any

from .config import (create_project, update_project, get_project, delete_project,
                     load_all_projects, detect_engine, find_export_presets, get_project_version, migrate_old_projects)
from .settings import load_settings, save_settings, get_all_settings
from .engine import build_godot, build_unity, zip_build, BuildError
from .uploaders import push_itch, push_steam, UploadError
from .recent import load_recent_ids, add_recent, remove_recent

GEOMETRY_FILE = "window_geometry.txt"


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str, delay: int = 400) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)

    def _schedule(self, event: tk.Event) -> None:
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip_window = tk.Toplevel(self.widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")
        self._tip_window.configure(bg="#2a2a4a")
        tk.Label(
            self._tip_window, text=self.text,
            bg="#2a2a4a", fg="#e0e0e0", font=("Segoe UI", 8),
            wraplength=280, padx=8, pady=4,
        ).pack()

    def _hide(self, event: tk.Event) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


class DeployFlowApp:
    BG = "#1a1a2e"
    FG = "#e0e0e0"
    ACCENT = "#16213e"
    SIDEBAR_BG = "#12122a"
    BTN_BG_ITCH = "#7b2ff2"
    BTN_BG_STEAM = "#0a6c74"
    BTN_ACTIVE_ITCH = "#9b4dff"
    BTN_ACTIVE_STEAM = "#0d8c8c"
    ENTRY_BG = "#2a2a4a"
    LOG_BG = "#0f0f23"
    LABEL_FG = "#a0a0c0"
    WARN_BG = "#4a3800"
    WARN_FG = "#ffcc00"

    def __init__(self, root: tk.Tk, project_id: str | None = None) -> None:
        self.root = root
        self.project_id = project_id or ""
        migrate_old_projects()
        if not self.project_id:
            ids = load_recent_ids()
            if ids:
                self.project_id = ids[0]
        if not self.project_id:
            self.project_id = create_project(str(Path.cwd()))
        self._ensure_project_exists()
        self.config = get_project(self.project_id)
        self._running = False
        self.entries: dict[str, tk.Entry | ttk.Combobox | tk.Text] = {}
        self._warn_visible = False
        self.log_text: scrolledtext.ScrolledText | None = None
        self.status_var = tk.StringVar(value="Ready")
        self.timer_var = tk.StringVar(value="")
        self._timer_id: str | None = None
        self._step_start: float = 0.0
        self._steps = ["Build", "Package", "Upload", "Done"]
        self._step_labels: list[tk.Label] = []
        self._step_dots: list[tk.Label] = []
        self.progress_bar: ttk.Progressbar | None = None
        self.btn_itch: tk.Button | None = None
        self.btn_steam: tk.Button | None = None
        self.btn_build: tk.Button | None = None
        self.btn_run: tk.Button | None = None
        self.build_status_label: tk.Label | None = None
        self.version_label: tk.Label | None = None
        self.preset_var = tk.StringVar()
        self.preset_combo: ttk.Combobox | None = None
        self._web_server: socketserver.TCPServer | None = None

        root.title("DeployFlow")
        root.geometry(self._load_geometry() or "960x680")
        root.configure(bg=self.BG)
        root.resizable(True, True)
        root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._build_ui()
        self._load_fields()
        self._refresh_sidebar()
        self._check_warnings()
        self._update_version_display()
        add_recent(self.project_id)

    def _ensure_project_exists(self) -> None:
        all_data = load_all_projects()
        if self.project_id not in all_data.get("projects", {}):
            new_id = create_project(str(Path.cwd()))
            self.project_id = new_id

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.FG, font=("Segoe UI", 10))
        style.configure("Sub.TLabel", background=self.BG, foreground=self.LABEL_FG, font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 11, "bold"), padding=12)

        # ── Main layout: sidebar + content ────────────────────────
        self._root_pane = tk.PanedWindow(
            self.root, orient="horizontal", bg=self.BG,
            sashwidth=4, sashrelief="flat", borderwidth=0,
        )
        self._root_pane.pack(fill="both", expand=True)

        # ── Sidebar ──────────────────────────────────────────────
        sidebar = tk.Frame(self._root_pane, bg=self.SIDEBAR_BG, width=200)
        self._root_pane.add(sidebar, minsize=160, width=200)

        tk.Label(
            sidebar, text=" Projects", bg=self.SIDEBAR_BG,
            fg="#ffffff", font=("Segoe UI", 11, "bold"),
        ).pack(fill="x", padx=10, pady=(12, 6))

        self.sidebar_frame = tk.Frame(sidebar, bg=self.SIDEBAR_BG)
        self.sidebar_frame.pack(fill="both", expand=True, padx=6)

        tk.Button(
            sidebar, text="+ Add Project", bg="#2d6a4f", fg="#ffffff",
            activebackground="#40916c", font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", command=self._add_new_project,
        ).pack(fill="x", padx=10, pady=(6, 4), ipady=4)

        tk.Button(
            sidebar, text="Settings", bg="#3a3a5a", fg=self.FG,
            activebackground="#4a4a6a", font=("Segoe UI", 9),
            relief="flat", cursor="hand2", command=self._show_settings,
        ).pack(fill="x", padx=10, pady=(0, 10), ipady=4)

        # ── Content area ─────────────────────────────────────────
        self._content_frame = tk.Frame(self._root_pane, bg=self.BG)
        self._root_pane.add(self._content_frame, minsize=500)
        self._build_main_view()

    # ── Main view ─────────────────────────────────────────────────────

    def _build_main_view(self) -> None:
        for w in self._content_frame.winfo_children():
            w.destroy()
        self._step_dots.clear()
        self._step_labels.clear()

        # Warning banner
        self._warn_frame = tk.Frame(self._content_frame, bg=self.WARN_BG)
        self._warn_label = tk.Label(
            self._warn_frame, text="", bg=self.WARN_BG,
            fg=self.WARN_FG, font=("Segoe UI", 9, "bold"),
            anchor="w", padx=8, pady=4,
        )
        self._warn_label.pack(fill="x")
        self._warn_visible = False

        # Split: config + log
        self._inner_pane = tk.PanedWindow(
            self._content_frame, orient="horizontal", bg=self.BG,
            sashwidth=3, sashrelief="flat", borderwidth=0,
        )
        self._inner_pane.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        cfg_outer = tk.Frame(self._inner_pane, bg=self.BG)
        self._inner_pane.add(cfg_outer, minsize=300)
        self._build_config_tab(cfg_outer)

        log_outer = tk.Frame(self._inner_pane, bg=self.BG)
        self._inner_pane.add(log_outer, minsize=250)
        self._build_log_area(log_outer)

        # Bottom bar: status | steps | build status | progress+timer | Build | Itch.io | Steam
        bottom = tk.Frame(self._content_frame, bg=self.ACCENT)
        bottom.pack(fill="x", side="bottom")

        tk.Label(
            bottom, textvariable=self.status_var, bg=self.ACCENT,
            fg=self.LABEL_FG, anchor="w", padx=6, font=("Segoe UI", 8),
        ).pack(side="left")

        for i, name in enumerate(self._steps):
            dot = tk.Label(bottom, text="\u25cb", bg=self.ACCENT, fg="#555577", font=("Segoe UI", 10))
            dot.pack(side="left", padx=(2, 0))
            self._step_dots.append(dot)
            lbl = tk.Label(bottom, text=name, bg=self.ACCENT, fg="#555577", font=("Segoe UI", 8))
            lbl.pack(side="left", padx=(0, 4))
            self._step_labels.append(lbl)
            if i < len(self._steps) - 1:
                tk.Label(bottom, text="\u2192", bg=self.ACCENT, fg="#3a3a5a", font=("Segoe UI", 7)).pack(side="left")

        self.build_status_label = tk.Label(
            bottom, text="", bg=self.ACCENT, fg="#40916c",
            font=("Segoe UI", 8, "bold"),
        )
        self.build_status_label.pack(side="left", padx=(4, 0))

        self.progress_bar = ttk.Progressbar(bottom, mode="indeterminate", length=80)
        self.progress_bar.pack(side="left", padx=(4, 2))
        self.timer_label = tk.Label(bottom, textvariable=self.timer_var, bg=self.ACCENT, fg=self.LABEL_FG, font=("Consolas", 7))
        self.timer_label.pack(side="left", padx=(0, 4))

        self._load_fields()
        self._check_warnings()
        self._update_build_status()
        self._update_version_display()
        self._refresh_presets()

    # ── Config panel (left side) ──────────────────────────────────────

    PLATFORMS = ["", "web", "win", "linux", "mac", "android"]
    PLATFORM_CHANNELS = {"web": "html5", "win": "windows", "linux": "linux", "mac": "mac", "android": "android"}
    PLATFORM_DEPOT_LABELS = {"web": "Web Depot ID", "win": "Windows Depot ID", "linux": "Linux Depot ID", "mac": "Mac Depot ID", "android": "Android Depot ID"}

    def _build_config_tab(self, parent: tk.Frame) -> None:
        inner = tk.Frame(parent, bg=self.BG)
        inner.pack(fill="both", expand=True, padx=4, pady=4)

        self.entries: dict[str, tk.Entry | ttk.Combobox | tk.Text] = {}
        pad = {"padx": 10, "pady": (2, 0)}

        # ── Engine + Platform side by side ─────────────────────────
        ep_row = tk.Frame(inner, bg=self.BG)
        ep_row.pack(fill="x", **pad)
        # Engine column
        eng_col = tk.Frame(ep_row, bg=self.BG)
        eng_col.pack(side="left", fill="x", expand=True)
        ttk.Label(eng_col, text="Engine", font=("Segoe UI", 8)).pack(anchor="w")
        engine_w = ttk.Combobox(eng_col, values=["godot", "unity"], state="readonly", font=("Consolas", 9))
        engine_w.pack(fill="x", ipady=1)
        engine_w.bind("<<ComboboxSelected>>", lambda _e: self._auto_save_field("engine"))
        self.entries["engine"] = engine_w
        # Platform column
        plat_col = tk.Frame(ep_row, bg=self.BG)
        plat_col.pack(side="right", fill="x", expand=True, padx=(6, 0))
        ttk.Label(plat_col, text="Platform", font=("Segoe UI", 8)).pack(anchor="w")
        plat_w = ttk.Combobox(plat_col, values=self.PLATFORMS, state="readonly", font=("Consolas", 9))
        plat_w.pack(fill="x", ipady=1)
        plat_w.bind("<<ComboboxSelected>>", lambda _e: self._on_platform_change())
        self.entries["platform"] = plat_w

        # ── Project Path ──────────────────────────────────────────
        ttk.Label(inner, text="Project Path", font=("Segoe UI", 8)).pack(anchor="w", **pad)
        proj_row = tk.Frame(inner, bg=self.BG)
        proj_row.pack(fill="x", **pad)
        proj_w = tk.Entry(proj_row, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        proj_w.pack(side="left", fill="x", expand=True, ipady=1)
        tk.Button(proj_row, text="Browse", bg=self.ACCENT, fg=self.FG, relief="flat", cursor="hand2", font=("Segoe UI", 8),
                  command=self._browse_project).pack(side="right", padx=(4, 0), ipadx=4, ipady=1)
        proj_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("project_path"))
        self.entries["project_path"] = proj_w

        # ── Build Output Path ─────────────────────────────────────
        ttk.Label(inner, text="Build Output Path", font=("Segoe UI", 8)).pack(anchor="w", **pad)
        bld_row = tk.Frame(inner, bg=self.BG)
        bld_row.pack(fill="x", **pad)
        bld_w = tk.Entry(bld_row, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        bld_w.pack(side="left", fill="x", expand=True, ipady=1)
        tk.Button(bld_row, text="Browse", bg=self.ACCENT, fg=self.FG, relief="flat", cursor="hand2", font=("Segoe UI", 8),
                  command=self._browse_build).pack(side="right", padx=(4, 0), ipadx=4, ipady=1)
        bld_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("build_path"))
        self.entries["build_path"] = bld_w

        # ── Separator ─────────────────────────────────────────────
        tk.Frame(inner, height=1, bg="#3a3a5a").pack(fill="x", padx=10, pady=(8, 4))

        # ── Itch.io Section ───────────────────────────────────────
        ttk.Label(inner, text="itch.io", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(0, 2))
        ttk.Label(inner, text="Target (user/game)", font=("Segoe UI", 8)).pack(anchor="w", **pad)
        itch_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        itch_w.pack(fill="x", ipady=1, **pad)
        itch_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("itch_target"))
        ToolTip(itch_w, "Format: user/game\nChannel is auto-filled from the selected platform.\nExample: myuser/mygame")
        self.entries["itch_target"] = itch_w

        ttk.Label(inner, text="itch.io Page URL (opens after deploy)", font=("Segoe UI", 8)).pack(anchor="w", **pad)
        itch_url_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        itch_url_w.pack(fill="x", ipady=1, **pad)
        itch_url_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("itch_url"))
        self.entries["itch_url"] = itch_url_w

        # ── Separator ─────────────────────────────────────────────
        tk.Frame(inner, height=1, bg="#3a3a5a").pack(fill="x", padx=10, pady=(8, 4))

        # ── Steam Section ─────────────────────────────────────────
        self.steam_header = ttk.Label(inner, text="Steam", font=("Segoe UI", 9, "bold"))
        self.steam_header.pack(anchor="w", padx=10, pady=(0, 2))

        # Steam App ID (label toggles between App ID / Demo App ID)
        self.steam_app_id_label = ttk.Label(inner, text="Steam App ID", font=("Segoe UI", 8))
        self.steam_app_id_label.pack(anchor="w", **pad)
        self.steam_app_id_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        self.steam_app_id_w.pack(fill="x", ipady=1, **pad)
        self.steam_app_id_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("steam_app_id"))
        self.entries["steam_app_id"] = self.steam_app_id_w

        # Steam Demo App ID (hidden by default)
        self.steam_demo_label = ttk.Label(inner, text="Steam Demo App ID", font=("Segoe UI", 8))
        self.steam_demo_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        self.entries["steam_demo_app_id"] = self.steam_demo_w

        # Per-platform Steam depot fields
        self.depot_entries: dict[str, tk.Entry] = {}
        self.depot_labels: dict[str, ttk.Label] = {}
        for plat_key, label in self.PLATFORM_DEPOT_LABELS.items():
            lbl = ttk.Label(inner, text=label, font=("Segoe UI", 8))
            lbl.pack(anchor="w", **pad)
            self.depot_labels[plat_key] = lbl
            dep_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
            dep_w.pack(fill="x", ipady=1, **pad)
            dep_w.bind("<KeyRelease>", lambda _e, k=plat_key: self._save_depot_field(k))
            self.depot_entries[plat_key] = dep_w

        self.steam_url_label = ttk.Label(inner, text="Steam Store URL (opens after deploy)", font=("Segoe UI", 8))
        self.steam_url_label.pack(anchor="w", **pad)
        self.steam_url_w = tk.Entry(inner, bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG, font=("Consolas", 9), relief="flat", bd=4)
        self.steam_url_w.pack(fill="x", ipady=1, **pad)
        self.steam_url_w.bind("<KeyRelease>", lambda _e: self._auto_save_field("steam_url"))
        self.entries["steam_url"] = self.steam_url_w

        # ── Preset (hidden for Unity) ─────────────────────────────
        self._preset_frame = tk.Frame(inner, bg=self.BG)
        self._preset_frame.pack(fill="x")
        tk.Frame(self._preset_frame, height=1, bg="#3a3a5a").pack(fill="x", padx=10, pady=(8, 4))
        preset_label_frame = tk.Frame(self._preset_frame, bg=self.BG)
        preset_label_frame.pack(fill="x", padx=10)
        ttk.Label(preset_label_frame, text="Godot Export Preset", font=("Segoe UI", 9)).pack(side="left")
        preset_help = tk.Label(preset_label_frame, text=" ?", bg=self.BG, fg="#5b8def", font=("Segoe UI", 9, "bold"), cursor="hand2")
        preset_help.pack(side="left", padx=(4, 0))
        ToolTip(preset_help, "Which export preset to use when building.\nAuto-filtered by selected platform.\nPresets are defined in your Godot project's File > Export dialog.")
        self.preset_combo = ttk.Combobox(self._preset_frame, textvariable=self.preset_var, state="readonly", font=("Consolas", 10))
        self.preset_combo.pack(fill="x", padx=10, ipady=2)
        tk.Button(self._preset_frame, text="Refresh Presets", bg=self.ACCENT, fg=self.FG,
                  relief="flat", cursor="hand2", font=("Segoe UI", 8),
                  command=self._refresh_presets,
        ).pack(anchor="w", padx=10, pady=(4, 6), ipadx=4, ipady=1)

        # Toggle preset visibility on engine change
        def _on_engine_change(*_args: Any) -> None:
            eng = self.entries.get("engine", None)
            eng_val = eng.get() if eng else ""
            visible = eng_val == "godot"
            self._preset_frame.pack_forget()
            if visible:
                self._preset_frame.pack(fill="x")
                self._refresh_presets()
        engine_w.bind("<<ComboboxSelected>>", _on_engine_change)
        self.root.after(50, _on_engine_change)

        # ── Version + action buttons ──────────────────────────────
        self.version_label = tk.Label(inner, text="", bg=self.BG, fg=self.LABEL_FG, font=("Segoe UI", 10, "bold"))
        self.version_label.pack(side="bottom", pady=(0, 4))

        btn_frame = tk.Frame(inner, bg=self.BG)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.btn_build = tk.Button(btn_frame, text="Build", bg="#4a4a4a", fg="#ffffff",
            activebackground="#666666", font=("Segoe UI", 8, "bold"),
            relief="flat", cursor="hand2", command=self._build_only)
        self.btn_build.pack(side="left", padx=(0, 2), ipadx=8, ipady=2)

        self.btn_run = tk.Button(btn_frame, text="Run", bg="#2d6a4f", fg="#ffffff",
            activebackground="#40916c", font=("Segoe UI", 8, "bold"),
            relief="flat", cursor="hand2", command=self._run_build_output)
        self.btn_run.pack(side="left", padx=(2, 0), ipadx=8, ipady=2)

        self.btn_itch = tk.Button(btn_frame, text="Itch.io", bg=self.BTN_BG_ITCH, fg="#ffffff",
            activebackground=self.BTN_ACTIVE_ITCH, activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
            command=lambda: self._deploy("itch"))
        self.btn_itch.pack(side="left", padx=(2, 0), ipadx=6, ipady=2)

        self.btn_steam = tk.Button(btn_frame, text="Steam", bg=self.BTN_BG_STEAM, fg="#ffffff",
            activebackground=self.BTN_ACTIVE_STEAM, activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
            command=lambda: self._deploy("steam"))
        self.btn_steam.pack(side="left", padx=(2, 0), ipadx=6, ipady=2)

        # Demo checkbox in the button area
        self.demo_var = tk.BooleanVar(value=bool(self.config.get("demo_build", False)))
        self.demo_cb = tk.Checkbutton(
            btn_frame, text="Demo", variable=self.demo_var,
            bg=self.BG, fg=self.FG, selectcolor=self.ENTRY_BG,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 8), anchor="w",
            command=self._on_demo_toggle,
        )
        self.demo_cb.pack(side="left", padx=(8, 0))
        ToolTip(self.demo_cb, "When checked:\n- Zip filenames get '(demo)' suffix\n- Steam Demo App ID field is used instead of App ID")

    def _on_platform_change(self) -> None:
        self._auto_save_field("engine")
        plat = self.entries.get("platform", None)
        plat_val = plat.get() if plat else ""

        # Auto-update export preset
        self._refresh_presets()

        # Auto-update itch.io channel
        itch = self.entries.get("itch_target", None)
        if itch and plat_val:
            current = itch.get().strip()
            channel = self.PLATFORM_CHANNELS.get(plat_val, "")
            if channel:
                if ":" in current:
                    base = current.rsplit(":", 1)[0]
                else:
                    base = current
                new_target = f"{base}:{channel}"
                if new_target != current:
                    itch.delete(0, "end")
                    itch.insert(0, new_target)
                    self._auto_save_field("itch_target")

        # Show/hide Steam section and depot fields based on platform
        self._refresh_depot_visibility()

    def _on_demo_toggle(self) -> None:
        self._auto_save_field("demo_build")
        self._refresh_steam_app_id_visibility()

    def _refresh_steam_app_id_visibility(self) -> None:
        self._refresh_depot_visibility()

    def _refresh_depot_visibility(self) -> None:
        plat_w = self.entries.get("platform", None)
        plat = plat_w.get().strip() if plat_w else ""
        hide_steam = plat == "web"

        # Hide/show all Steam-related widgets
        steam_widgets = [
            self.steam_header,
            self.steam_app_id_label, self.steam_app_id_w,
            self.steam_demo_label, self.steam_demo_w,
            self.steam_url_label, self.steam_url_w,
        ]
        for w in steam_widgets:
            if w and w.winfo_exists():
                w.pack_forget()

        # Hide all depot labels/entries
        for pk in self.PLATFORM_DEPOT_LABELS:
            lbl = self.depot_labels.get(pk)
            ent = self.depot_entries.get(pk)
            if lbl and lbl.winfo_exists():
                lbl.pack_forget()
            if ent and ent.winfo_exists():
                ent.pack_forget()

        if hide_steam:
            return

        # Show Steam header and relevant fields
        self.steam_header.pack(anchor="w", padx=10, pady=(0, 2))
        # Show correct App ID field
        demo = self.demo_var.get() if hasattr(self, "demo_var") else False
        if demo:
            self.steam_demo_label.pack(anchor="w", **{"padx": 10, "pady": (2, 0)})
            self.steam_demo_w.pack(fill="x", ipady=1, **{"padx": 10, "pady": (2, 0)})
        else:
            self.steam_app_id_label.pack(anchor="w", **{"padx": 10, "pady": (2, 0)})
            self.steam_app_id_w.pack(fill="x", ipady=1, **{"padx": 10, "pady": (2, 0)})
        # Show depot for current platform
        if plat and plat in self.depot_entries:
            lbl = self.depot_labels.get(plat)
            ent = self.depot_entries.get(plat)
            if lbl and lbl.winfo_exists():
                lbl.pack(anchor="w", **{"padx": 10, "pady": (2, 0)})
            if ent and ent.winfo_exists():
                ent.pack(fill="x", ipady=1, **{"padx": 10, "pady": (2, 0)})
        # Show Steam URL
        self.steam_url_label.pack(anchor="w", **{"padx": 10, "pady": (2, 0)})
        self.steam_url_w.pack(fill="x", ipady=1, **{"padx": 10, "pady": (2, 0)})

    def _save_depot_field(self, plat_key: str) -> None:
        w = self.depot_entries.get(plat_key)
        val = w.get().strip() if w else ""
        cfg = self._collect_config()
        depots = dict(cfg.get("steam_depots", {}))
        if val:
            depots[plat_key] = val
        else:
            depots.pop(plat_key, None)
        cfg["steam_depots"] = depots
        update_project(self.project_id, cfg)
        self.config = get_project(self.project_id)

        # Version + action buttons at the bottom of config panel
        self.version_label = tk.Label(
            inner, text="", bg=self.BG, fg=self.LABEL_FG,
            font=("Segoe UI", 10, "bold"),
        )
        self.version_label.pack(side="bottom", pady=(0, 4))

        btn_frame = tk.Frame(inner, bg=self.BG)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.btn_build = tk.Button(
            btn_frame, text="Build",
            bg="#4a4a4a", fg="#ffffff",
            activebackground="#666666", font=("Segoe UI", 8, "bold"),
            relief="flat", cursor="hand2", command=self._build_only,
        )
        self.btn_build.pack(side="left", padx=(0, 2), ipadx=8, ipady=2)

        self.btn_run = tk.Button(
            btn_frame, text="Run",
            bg="#2d6a4f", fg="#ffffff",
            activebackground="#40916c", font=("Segoe UI", 8, "bold"),
            relief="flat", cursor="hand2", command=self._run_build_output,
        )
        self.btn_run.pack(side="left", padx=(2, 0), ipadx=8, ipady=2)

        self.btn_itch = tk.Button(
            btn_frame, text="Itch.io",
            bg=self.BTN_BG_ITCH, fg="#ffffff",
            activebackground=self.BTN_ACTIVE_ITCH, activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
            command=lambda: self._deploy("itch"),
        )
        self.btn_itch.pack(side="left", padx=(2, 0), ipadx=6, ipady=2)

        self.btn_steam = tk.Button(
            btn_frame, text="Steam",
            bg=self.BTN_BG_STEAM, fg="#ffffff",
            activebackground=self.BTN_ACTIVE_STEAM, activeforeground="#ffffff",
            font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
            command=lambda: self._deploy("steam"),
        )
        self.btn_steam.pack(side="left", padx=(2, 0), ipadx=6, ipady=2)

    # ── Log panel (right side) ────────────────────────────────────────

    def _build_log_area(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=self.BG)
        header.pack(fill="x", padx=8, pady=(4, 2))
        tk.Label(
            header, text="Log", bg=self.BG, fg=self.LABEL_FG,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).pack(side="left")

        def _open_zips() -> None:
            build_path = self.config.get("build_path", "")
            if build_path:
                zips_dir = Path(build_path) / "zips"
                if zips_dir.is_dir():
                    import os
                    os.startfile(str(zips_dir))
                else:
                    messagebox.showinfo("DeployFlow", "No zips directory yet. Build something first!")

        tk.Button(
            header, text="Open Zips", bg=self.ACCENT, fg=self.FG,
            relief="flat", cursor="hand2", font=("Segoe UI", 8),
            command=_open_zips,
        ).pack(side="right", padx=(2, 0), ipadx=4, ipady=0)

        tk.Button(
            header, text="Clear", bg=self.ACCENT, fg=self.FG,
            relief="flat", cursor="hand2", font=("Segoe UI", 8),
            command=self._clear_log,
        ).pack(side="right", padx=(2, 0), ipadx=4, ipady=0)

        self.log_text = scrolledtext.ScrolledText(
            parent, bg=self.LOG_BG, fg="#00ff88",
            insertbackground=self.FG, font=("Consolas", 9),
            relief="flat", state="disabled", wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ── Settings view ─────────────────────────────────────────────────

    def _show_settings(self) -> None:
        if self._running:
            return
        for w in self._content_frame.winfo_children():
            w.destroy()

        tk.Label(
            self._content_frame, text="Global Settings", bg=self.BG,
            fg="#ffffff", font=("Segoe UI", 13, "bold"),
        ).pack(padx=16, pady=(14, 2), anchor="w")

        tk.Label(
            self._content_frame, text="These settings apply to all projects.", bg=self.BG,
            fg=self.LABEL_FG, font=("Segoe UI", 9),
        ).pack(padx=16, anchor="w")

        tk.Frame(self._content_frame, height=1, bg="#3a3a5a").pack(fill="x", padx=16, pady=(10, 10))

        fields_frame = tk.Frame(self._content_frame, bg=self.BG)
        fields_frame.pack(fill="both", expand=True, padx=16)

        settings = get_all_settings()
        settings_entries: dict[str, tk.Entry] = {}

        def _add_section(title: str) -> None:
            tk.Frame(fields_frame, height=1, bg="#3a3a5a").pack(fill="x", pady=(10, 4))
            tk.Label(
                fields_frame, text=title, bg=self.BG, fg="#7b8cff",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 2))

        def _add_field(label: str, key: str, hidden: bool = False) -> None:
            tk.Label(
                fields_frame, text=label, bg=self.BG, fg=self.LABEL_FG,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(6, 0))
            row = tk.Frame(fields_frame, bg=self.BG)
            row.pack(fill="x")
            e = tk.Entry(
                row, bg=self.ENTRY_BG, fg=self.FG,
                insertbackground=self.FG, font=("Consolas", 10),
                relief="flat", bd=4, show="*" if hidden else "",
            )
            e.pack(side="left", fill="x", expand=True, ipady=3)
            e.insert(0, settings.get(key, ""))
            settings_entries[key] = e

        def _add_browse_field(label: str, key: str, file: bool = True) -> None:
            tk.Label(
                fields_frame, text=label, bg=self.BG, fg=self.LABEL_FG,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(6, 0))
            row = tk.Frame(fields_frame, bg=self.BG)
            row.pack(fill="x")
            e = tk.Entry(
                row, bg=self.ENTRY_BG, fg=self.FG,
                insertbackground=self.FG, font=("Consolas", 10),
                relief="flat", bd=4,
            )
            e.pack(side="left", fill="x", expand=True, ipady=3)
            e.insert(0, settings.get(key, ""))
            settings_entries[key] = e
            browse_text = "Browse File" if file else "Browse Folder"
            tk.Button(
                row, text=browse_text, bg=self.ACCENT, fg=self.FG,
                relief="flat", cursor="hand2", font=("Segoe UI", 8),
                command=lambda k=key, entry=e: _browse_path(k, entry, file),
            ).pack(side="left", padx=(4, 0), ipadx=4, ipady=1)

        def _browse_path(key: str, entry: tk.Entry, is_file: bool) -> None:
            if is_file:
                path = filedialog.askopenfilename(title=f"Select {key}")
            else:
                path = filedialog.askdirectory(title=f"Select {key}")
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)

        _add_section("Executables")
        _add_browse_field("Godot (blank = auto-detect from PATH)", "godot_executable")
        _add_browse_field("Unity (blank = auto-detect from PATH)", "unity_executable")

        _add_section("itch.io")
        _add_field("API Key (optional, for private games)", "itch_api_key", hidden=True)
        api_entry = settings_entries.get("itch_api_key")
        if api_entry:
            ToolTip(api_entry, "Your itch.io API key for butler.\nGet it at itch.io > Settings > API Keys\nor run: butler login")

        _add_section("Steam")
        _add_field("Username", "steam_username")
        _add_field("Login Token", "steam_token", hidden=True)
        token_entry = settings_entries.get("steam_token")
        if token_entry:
            ToolTip(token_entry, "Steam login token.\nGenerate at: https://steamcommunity.com/dev/managegameservers")
        _add_browse_field("SteamCMD path (blank = auto-detect)", "steam_script_path")
        script_entry = settings_entries.get("steam_script_path")
        if script_entry:
            ToolTip(script_entry, "Path to steamcmd.exe on your system.\nLeave blank to auto-detect from PATH.\nDownload: https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip")

        tk.Frame(fields_frame, height=8, bg=self.BG).pack()

        # ── Bottom buttons ────────────────────────────────────────
        btn_frame = tk.Frame(self._content_frame, bg=self.BG)
        btn_frame.pack(fill="x", padx=16, pady=(10, 14))

        def _save() -> None:
            new_settings: dict[str, str] = {}
            for key, entry in settings_entries.items():
                new_settings[key] = entry.get().strip()
            save_settings(new_settings)
            self._check_warnings()
            messagebox.showinfo("Settings", "Settings saved.")

        tk.Button(
            btn_frame, text="Help", bg="#3a3a5a", fg="#ffffff",
            activebackground="#4a4a6a", font=("Segoe UI", 9),
            relief="flat", cursor="hand2", command=self._show_help,
        ).pack(side="left", ipadx=10, ipady=3)

        tk.Button(
            btn_frame, text="Save", bg="#2d6a4f", fg="#ffffff",
            activebackground="#40916c", font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2", command=_save,
        ).pack(side="right", ipadx=12, ipady=4)

        tk.Button(
            btn_frame, text="Back", bg="#4a4a4a", fg="#ffffff",
            activebackground="#666666", font=("Segoe UI", 10),
            relief="flat", cursor="hand2", command=self._show_main,
        ).pack(side="right", padx=(0, 8), ipadx=12, ipady=4)

    # ── Help view ─────────────────────────────────────────────────────

    def _show_help(self) -> None:
        for w in self._content_frame.winfo_children():
            w.destroy()

        tk.Label(
            self._content_frame, text="How DeployFlow Works", bg=self.BG,
            fg="#ffffff", font=("Segoe UI", 13, "bold"),
        ).pack(padx=16, pady=(14, 4), anchor="w")

        tk.Frame(self._content_frame, height=1, bg="#3a3a5a").pack(fill="x", padx=16, pady=(4, 10))

        text = tk.Text(
            self._content_frame, bg=self.BG, fg="#cccccc",
            font=("Segoe UI", 9), relief="flat", wrap="word",
            highlightthickness=0, bd=0,
        )
        text.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        help_text = """\
Overview
DeployFlow is a one-click deploy tool for Godot and Unity games. It handles the full pipeline: build your game, zip the output, and upload to itch.io or Steam.

Step 1: Project Config (left panel)
Set your engine, project path, and build output path. These tell DeployFlow where your game project lives and where to put the exported build files.

  Engine — Select Godot or Unity. If you leave this blank and open a project folder, DeployFlow will auto-detect which engine it is.

  Project Path — The root folder of your game project (the one containing project.godot or the .sln file).

  Build Output Path — Where the exported/packaged files end up. If left blank, a "build" folder is created inside your project path.

Step 2: Deploy Target
Enter your itch.io or Steam target info, then click the deploy button.

  itch.io — Set "user/game:channel" (e.g. "myuser/mygame:html5"). DeployFlow runs butler push to upload the zip.

  Steam — Set your App ID. DeployFlow runs steamcmd to upload a depot. You need your Steam Username and Login Token set in Settings.

Step 3: What Happens on Deploy
1. Build — Runs Godot or Unity export to produce the game files.
2. Package — Zips the build output into a single file.
3. Upload — Pushes the zip to itch.io (butler) or Steam (steamcmd).
4. Done — If a page URL is configured, it opens in your browser.

Settings (Global)
Access via the Settings button in the sidebar. This is where you set:
  • Godot / Unity executable paths (if not in PATH)
  • itch.io API key (for private games)
  • Steam username, login token, and SteamCMD path

Tips
  • If Godot or Unity is on your system PATH, you can leave the executable fields blank.
  • You can have multiple projects open — use the sidebar to switch between them.
  • Each project's config is saved as deployflow.json inside the project folder.
  • Credentials (API keys, tokens) are stored securely in your OS keyring."""

        text.insert("1.0", help_text)
        text.configure(state="disabled")

        tk.Button(
            self._content_frame, text="Back", bg="#4a4a4a", fg="#ffffff",
            activebackground="#666666", font=("Segoe UI", 10),
            relief="flat", cursor="hand2", command=self._show_main,
        ).pack(pady=(0, 14), ipadx=12, ipady=4)

    # ── View switching ────────────────────────────────────────────────

    def _show_main(self) -> None:
        self._build_main_view()

    # ── Warnings ───────────────────────────────────────────────────────

    def _check_warnings(self) -> None:
        if not hasattr(self, "_warn_frame") or self._warn_frame is None or not self._warn_frame.winfo_exists():
            return
        settings = load_settings()
        engine = self.config.get("engine", "")
        warnings: list[str] = []

        if engine == "godot":
            exe = settings.get("godot_executable", "")
            if exe and not Path(exe).is_file():
                warnings.append(f"Godot executable not found: {exe}")
            elif not exe and not shutil.which("godot") and not shutil.which("godot4"):
                warnings.append("Godot not found in PATH. Set path in Settings.")
        elif engine == "unity":
            exe = settings.get("unity_executable", "")
            if exe and not Path(exe).is_file():
                warnings.append(f"Unity executable not found: {exe}")
            elif not exe and not shutil.which("Unity"):
                warnings.append("Unity not found in PATH. Set path in Settings.")

        steam_id = self.config.get("steam_app_id", "")
        if steam_id:
            if not settings.get("steam_username", ""):
                warnings.append("Steam App ID set but Steam Username is empty (Settings).")

        if self._warn_visible:
            self._warn_frame.pack_forget()
            self._warn_visible = False

        if warnings:
            self._warn_label.configure(text="  \u26a0  " + "  |  ".join(warnings))
            self._warn_frame.pack(fill="x", padx=8, pady=(0, 2), before=self._inner_pane)
            self._warn_visible = True

    # ── Helpers ────────────────────────────────────────────────────────

    def _auto_save_field(self, key: str) -> None:
        cfg = self._collect_config()
        if key == "demo_build":
            cfg["demo_build"] = self.demo_var.get()
        update_project(self.project_id, cfg)
        self.config = get_project(self.project_id)
        self._check_warnings()
        self._update_build_status()
        if key == "project_path" and cfg.get("engine") == "godot":
            self._refresh_presets()

    def _load_fields(self) -> None:
        for key, widget in self.entries.items():
            val = self.config.get(key, "")
            if isinstance(widget, ttk.Combobox):
                widget.set(val)
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", "end")
                if isinstance(val, dict):
                    widget.insert("1.0", "\n".join(f"{k}={v}" for k, v in val.items()))
                else:
                    widget.insert("1.0", str(val))
            else:
                widget.delete(0, "end")
                widget.insert(0, str(val))
        # Auto-fill itch_target if empty
        itch = self.entries.get("itch_target")
        if itch and not itch.get().strip():
            default_name = self.config.get("name", "").lower().replace(" ", "-") or "game-name"
            itch.delete(0, "end")
            itch.insert(0, f"user/{default_name}")
        if self.demo_var and "demo_build" in self.config:
            self.demo_var.set(bool(self.config["demo_build"]))
        # Populate per-platform depot entries
        depots = self.config.get("steam_depots", {})
        if isinstance(depots, dict):
            for plat_key, w in self.depot_entries.items():
                w.delete(0, "end")
                w.insert(0, depots.get(plat_key, ""))
        # Refresh Steam App ID / Demo App ID field visibility
        if hasattr(self, "demo_var"):
            self._refresh_steam_app_id_visibility()
        self._refresh_depot_visibility()

    def _collect_config(self) -> dict[str, Any]:
        cfg: dict[str, Any] = {}
        for key, widget in self.entries.items():
            if isinstance(widget, ttk.Combobox):
                cfg[key] = widget.get()
            elif isinstance(widget, tk.Text):
                raw = widget.get("1.0", "end").strip()
                d: dict[str, str] = {}
                for line in raw.splitlines():
                    line = line.strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        d[k.strip()] = v.strip()
                cfg[key] = d
            else:
                cfg[key] = widget.get().strip()
        cfg["demo_build"] = self.demo_var.get() if hasattr(self, "demo_var") else False
        # Collect per-platform depot entries into steam_depots dict
        depots: dict[str, str] = {}
        for plat_key, w in self.depot_entries.items():
            val = w.get().strip()
            if val:
                depots[plat_key] = val
        cfg["steam_depots"] = depots
        # Collect the correct steam app id
        if cfg.get("demo_build", False):
            cfg["steam_app_id"] = self.steam_demo_w.get().strip()
        return cfg

    def _save_config(self, silent: bool = False) -> None:
        cfg = self._collect_config()
        update_project(self.project_id, cfg)
        self.config = get_project(self.project_id)
        self._check_warnings()
        if not silent:
            self._log("Configuration saved.")
            messagebox.showinfo("DeployFlow", "Configuration saved.")

    def _log(self, msg: str) -> None:
        if self.log_text is None:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        if self.log_text is None:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_step(self, step: int) -> None:
        for i in range(len(self._steps)):
            if i < step:
                self._step_dots[i].configure(text="\u2714", fg="#40916c")
                self._step_labels[i].configure(fg="#40916c")
            elif i == step:
                self._step_dots[i].configure(text="\u25cf", fg="#ffffff")
                self._step_labels[i].configure(fg="#ffffff")
            else:
                self._step_dots[i].configure(text="\u25cb", fg="#555577")
                self._step_labels[i].configure(fg="#555577")

    def _reset_steps(self) -> None:
        for i in range(len(self._steps)):
            self._step_dots[i].configure(text="\u25cb", fg="#555577")
            self._step_labels[i].configure(fg="#555577")

    def _start_progress(self) -> None:
        if self.progress_bar:
            self.progress_bar.start(15)
        self._step_start = time.monotonic()
        self._tick_timer()

    def _stop_progress(self) -> None:
        if self.progress_bar:
            self.progress_bar.stop()
        if self._timer_id is not None:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
        self.timer_var.set("")

    def _tick_timer(self) -> None:
        elapsed = time.monotonic() - self._step_start
        mins, secs = divmod(int(elapsed), 60)
        self.timer_var.set(f"{mins:02d}:{secs:02d}")
        self._timer_id = self.root.after(200, self._tick_timer)

    def _browse_project(self) -> None:
        current = self.entries.get("project_path", None)
        initial = current.get().strip() if current and current.get().strip() else None
        path = filedialog.askdirectory(title="Select Project Directory", initialdir=initial)
        if path and "project_path" in self.entries:
            w = self.entries["project_path"]
            w.delete(0, "end")
            w.insert(0, path)
            self._auto_save_field("project_path")

    def _add_new_project(self) -> None:
        path = filedialog.askdirectory(title="Select Project Directory")
        if path:
            pid = create_project(path)
            self._switch_project(pid)

    def _browse_build(self) -> None:
        current = self.entries.get("build_path", None)
        initial = current.get().strip() if current and current.get().strip() else None
        path = filedialog.askdirectory(title="Select Build Output Directory", initialdir=initial)
        if path and "build_path" in self.entries:
            w = self.entries["build_path"]
            w.delete(0, "end")
            w.insert(0, path)
            self._auto_save_field("build_path")

    def _refresh_presets(self) -> None:
        if "project_path" not in self.entries:
            return
        proj = self.entries["project_path"].get().strip()
        if not proj or not self.preset_combo:
            return
        presets = find_export_presets(Path(proj))
        # Filter by selected platform
        plat = self.entries.get("platform", None)
        plat_val = plat.get().strip() if plat else ""
        if plat_val:
            filtered = [p for p in presets if plat_val in p.lower()]
        else:
            filtered = presets
        self.preset_combo["values"] = filtered
        current = self.preset_var.get()
        if current and (not filtered or current not in filtered):
            self.preset_var.set("")
        if not self.preset_var.get() and filtered:
            self.preset_var.set(filtered[0])

    # ── Sidebar ────────────────────────────────────────────────────────

    def _refresh_sidebar(self) -> None:
        for widget in self.sidebar_frame.winfo_children():
            widget.destroy()

        data = load_all_projects()
        all_projects = data.get("projects", {})
        order = data.get("order", [])

        for pid in order:
            proj = all_projects.get(pid)
            if not proj:
                continue
            name = proj.get("name", "untitled")
            path_str = proj.get("project_path", "")
            is_active = pid == self.project_id

            row = tk.Frame(self.sidebar_frame, bg=self.SIDEBAR_BG)
            row.pack(fill="x")

            indicator = tk.Frame(row, width=3, bg="#5b8def" if is_active else self.SIDEBAR_BG)
            indicator.pack(side="left", fill="y")

            col = tk.Frame(row, bg="#1e1e3a" if is_active else self.SIDEBAR_BG)
            col.pack(side="left", fill="both", expand=True)

            btn = tk.Button(
                col, text=name,
                bg="#1e1e3a" if is_active else self.SIDEBAR_BG,
                fg="#ffffff" if is_active else self.LABEL_FG,
                activebackground="#2a2a4a", activeforeground="#ffffff",
                anchor="w", font=("Segoe UI", 9, "bold" if is_active else "normal"),
                relief="flat", cursor="hand2",
                command=lambda p=pid: self._switch_project(p),
            )
            btn.pack(fill="x", ipady=3)

            path_label = tk.Label(
                col, text=path_str,
                bg="#1e1e3a" if is_active else self.SIDEBAR_BG,
                fg="#5b8def" if is_active else "#666688",
                anchor="w", font=("Consolas", 7),
            )
            path_label.pack(fill="x", padx=(0, 4))

            def _make_menu(pid_val: str, btn_widget: tk.Button) -> None:
                menu = tk.Menu(btn_widget, tearoff=0)
                menu.add_command(label="Remove from list", command=lambda: self._remove_from_sidebar(pid_val))
                btn_widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
            _make_menu(pid, btn)

        if not order:
            tk.Label(
                self.sidebar_frame, text="No projects yet.\nClick + Add Project.",
                bg=self.SIDEBAR_BG, fg="#555577", font=("Segoe UI", 9), justify="center",
            ).pack(pady=20)

    def _remove_from_sidebar(self, pid: str) -> None:
        remove_recent(pid)
        self._refresh_sidebar()
        # Also clean up orphaned per-project deployflow.json to keep things tidy
        proj = get_project(pid)
        old_config = Path(proj.get("project_path", "")) / "deployflow.json"
        if old_config.exists():
            try:
                old_config.unlink()
            except OSError:
                pass

    # ── Project switching ──────────────────────────────────────────────

    def _switch_project(self, pid: str) -> None:
        if self._running:
            messagebox.showwarning("DeployFlow", "Cannot switch projects while a build is in progress.")
            return
        self.project_id = pid
        self.config = get_project(pid)
        project_path = Path(self.config.get("project_path", ""))
        if project_path and not project_path.is_dir():
            messagebox.showerror("DeployFlow", f"Project not found:\n{project_path}")
            remove_recent(pid)
            self._refresh_sidebar()
            return
        if not self.config.get("engine"):
            detected = detect_engine(project_path)
            if detected:
                self.config["engine"] = detected
                update_project(pid, {"engine": detected})
        add_recent(pid)
        self._show_main()
        self._refresh_sidebar()
        self._set_status(f"Loaded: {self.config.get('name', pid)}")
        self._load_fields()
        self._update_version_display()

    # ── Build & Deploy ────────────────────────────────────────────────

    @staticmethod
    def _format_time_ago(iso_time: str) -> str:
        if not iso_time:
            return ""
        try:
            then = time.strptime(iso_time, "%Y-%m-%dT%H:%M:%S")
            then_ts = time.mktime(then)
            diff = time.time() - then_ts
        except (ValueError, OverflowError):
            return ""
        if diff < 0:
            return "just now"
        mins = int(diff // 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"

    @staticmethod
    def _export_subdir(preset: str, engine: str = "") -> str:
        if engine == "unity":
            return "win"
        pl = preset.lower()
        if "web" in pl:
            return "web"
        if "win" in pl or "windows" in pl:
            return "win"
        if "linux" in pl or "x11" in pl:
            return "linux"
        if "mac" in pl or "osx" in pl:
            return "mac"
        if "android" in pl:
            return "android"
        return "build"

    def _find_build_output(self) -> Path | None:
        build_path = self.config.get("build_path", "")
        if not build_path:
            return None
        bp = Path(build_path)
        if not bp.is_dir():
            return None
        for dirpath in bp.iterdir():
            if not dirpath.is_dir():
                continue
            exes = list(dirpath.rglob("*.exe"))
            if exes:
                return exes[0]
        for dirpath in bp.iterdir():
            if not dirpath.is_dir():
                continue
            htmls = list(dirpath.rglob("index.html"))
            if htmls:
                return htmls[0]
        return None

    def _update_build_status(self) -> None:
        if not self.build_status_label or not self.build_status_label.winfo_exists():
            return
        t = self.config.get("last_build_time", "")
        ok = self.config.get("last_build_success", False)
        has_output = self._find_build_output() is not None
        if self.btn_run and self.btn_run.winfo_exists():
            self.btn_run.configure(state="normal" if (ok and has_output) else "disabled")
        if t and ok:
            age = self._format_time_ago(t)
            self.build_status_label.configure(text=f"\u2713 {age}", fg="#40916c")
        elif t and not ok:
            self.build_status_label.configure(text="\u2717 failed", fg="#e74c3c")
        else:
            self.build_status_label.configure(text="")
        # Disable deploy buttons when their targets aren't configured
        itch_target = self.config.get("itch_target", "")
        steam_id = self.config.get("steam_app_id", "")
        if self.btn_itch and self.btn_itch.winfo_exists():
            self.btn_itch.configure(state="normal" if itch_target else "disabled")
        if self.btn_steam and self.btn_steam.winfo_exists():
            self.btn_steam.configure(state="normal" if steam_id else "disabled")

    def _update_version_display(self) -> None:
        if not self.version_label or not self.version_label.winfo_exists():
            return
        proj = Path(self.config.get("project_path", ""))
        if not proj.is_dir():
            self.version_label.configure(text="")
            return
        ver = get_project_version(proj)
        if ver:
            label = f"\u2502 v{ver}"
            t = self.config.get("last_build_time", "")
            ok = self.config.get("last_build_success", False)
            if t and ok:
                age = self._format_time_ago(t)
                label += f" (built {age})"
            self.version_label.configure(text=label, fg=self.LABEL_FG)
        else:
            self.version_label.configure(text="")

    def _run_build_output(self) -> None:
        output = self._find_build_output()
        if not output:
            messagebox.showerror("DeployFlow", "No build output found. Build the project first.")
            return
        try:
            if output.suffix == ".exe":
                self._log(f"Launching: {output}")
                subprocess.Popen([str(output)], cwd=str(output.parent))
            elif output.name == "index.html":
                self._log(f"Starting local server for: {output.parent}")
                port = self._start_web_server(output.parent)
                webbrowser.open(f"http://127.0.0.1:{port}/")
        except Exception as exc:
            messagebox.showerror("DeployFlow", f"Failed to launch: {exc}")

    def _start_web_server(self, directory: Path) -> int:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        self._web_server = httpd
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        self._log(f"Web server started on http://127.0.0.1:{port}/")
        return port

    def _shutdown_web_server(self) -> None:
        if self._web_server is not None:
            try:
                self._web_server.shutdown()
            except Exception:
                pass
            self._web_server = None

    def _on_closing(self) -> None:
        self._save_geometry()
        self._shutdown_web_server()
        self.root.destroy()

    @staticmethod
    def _geom_path() -> Path:
        p = Path.home() / "AppData" / "Local" / "DeployFlow"
        p.mkdir(parents=True, exist_ok=True)
        return p / GEOMETRY_FILE

    def _save_geometry(self) -> None:
        try:
            geo = self.root.geometry()
            self._geom_path().write_text(geo, encoding="utf-8")
        except Exception:
            pass

    def _load_geometry(self) -> str | None:
        try:
            p = self._geom_path()
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return None

    def _preflight_checks(self, cfg: dict[str, Any], target: str) -> bool:
        if not cfg.get("project_path") or not cfg.get("build_path"):
            messagebox.showerror("DeployFlow", "Project path and build path are required.")
            return False
        settings = load_settings()
        engine = cfg.get("engine", "")
        if engine == "godot":
            exe = settings.get("godot_executable", "")
            if not exe and not shutil.which("godot") and not shutil.which("godot4"):
                messagebox.showerror("DeployFlow", "Godot not found.\nSet the executable path in Settings, or add godot to PATH.")
                return False
        elif engine == "unity":
            exe = settings.get("unity_executable", "")
            if not exe and not shutil.which("Unity"):
                messagebox.showerror("DeployFlow", "Unity not found.\nSet the executable path in Settings, or add Unity to PATH.")
                return False
        if target == "steam":
            if not cfg.get("steam_app_id"):
                messagebox.showerror("DeployFlow", "Steam App ID is required for Steam uploads.")
                return False
            if not settings.get("steam_username", ""):
                messagebox.showerror("DeployFlow", "Steam Username is required.\nSet it in Settings.")
                return False
        return True

    def _begin_work(self) -> None:
        self._running = True
        self._clear_log()
        self._set_status("Working...")
        self._toggle_buttons(False)
        self._reset_steps()
        self._start_progress()

    def _record_build(self, success: bool) -> None:
        self.config["last_build_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.config["last_build_success"] = success
        update_project(self.project_id, self.config)
        self.root.after(0, self._update_build_status)

    def _build_only(self) -> None:
        if self._running:
            return
        cfg = self._collect_config()
        if not self._preflight_checks(cfg, "build"):
            return
        self._save_config(silent=True)
        proj_path = Path(cfg["project_path"])
        add_recent(self.project_id)
        self._refresh_sidebar()

        self._begin_work()
        self._set_status("Building...")
        self._set_step(0)
        preset = self.preset_var.get()
        thread = threading.Thread(target=self._run_build, args=(cfg, preset), daemon=True)
        thread.start()

    def _run_build(self, cfg: dict[str, Any], preset: str) -> None:
        settings = load_settings()
        try:
            project = Path(cfg["project_path"])
            base_build = Path(cfg["build_path"])
            engine = cfg.get("engine", "")
            if not engine:
                engine = detect_engine(project)
                if not engine:
                    raise BuildError("Could not auto-detect engine. Set 'engine' in config.")

            subdir = self._export_subdir(preset, engine)
            version = get_project_version(project)
            version_dir = version if version else ""
            if version_dir:
                self.root.after(0, lambda: self._log(f"[version] Detected: {version_dir}"))
            build = base_build / subdir / version_dir
            build.mkdir(parents=True, exist_ok=True)

            self.root.after(0, lambda: self._log(f"[engine] Detected: {engine}"))
            self.root.after(0, lambda: self._log(f"[project] {project}"))
            self.root.after(0, lambda: self._log(f"[build dir] {build}"))

            if engine == "godot":
                self.root.after(0, lambda: self._log(f"[build] Godot export preset: {preset or '(none)'}"))
                output = build_godot(
                    project, preset, build,
                    godot_exe=settings.get("godot_executable", ""),
                    log=lambda msg: self.root.after(0, self._log, msg),
                )
            elif engine == "unity":
                self.root.after(0, lambda: self._log("[build] Unity build (Windows x64)"))
                output = build_unity(
                    project, build,
                    unity_exe=settings.get("unity_executable", ""),
                    log=lambda msg: self.root.after(0, self._log, msg),
                )
            else:
                raise BuildError(f"Unsupported engine: {engine}")

            self.root.after(0, lambda: self._set_step(1))
            self.root.after(0, lambda: self._set_status("Packaging..."))
            parts = [project.name, subdir]
            if version_dir:
                parts.append(version_dir)
            if cfg.get("demo_build", False):
                parts[-1] = f"{parts[-1]} (demo)"
            zip_dir = base_build / "zips"
            zip_dir.mkdir(parents=True, exist_ok=True)
            zip_path = zip_dir / f"{'-'.join(parts)}.zip"
            zip_build(output, zip_path, log=lambda msg: self.root.after(0, self._log, msg))

            self._record_build(True)
            self.root.after(0, lambda: self._set_step(2))

            def _done() -> None:
                self._stop_progress()
                self._log(f"\n{'='*50}")
                self._log("Build complete!")
                self._set_status("Build succeeded")
                messagebox.showinfo("DeployFlow", "Build completed successfully!")
            self.root.after(0, _done)
        except BuildError as exc:
            err_msg = str(exc)
            self._record_build(False)
            def _err() -> None:
                self._stop_progress()
                self._log(f"\n[ERROR] {err_msg}")
                self._set_status("Build failed")
                messagebox.showerror("DeployFlow", err_msg)
            self.root.after(0, _err)
        except Exception as exc:
            err_msg = f"Unexpected error: {exc}"
            self._record_build(False)
            def _err() -> None:
                self._stop_progress()
                self._log(f"\n[ERROR] {err_msg}")
                self._set_status("Build failed")
                messagebox.showerror("DeployFlow", err_msg)
            self.root.after(0, _err)
        finally:
            self._running = False
            self.root.after(0, lambda: self._toggle_buttons(True))

    def _deploy(self, target: str) -> None:
        if self._running:
            messagebox.showwarning("DeployFlow", "A build is already in progress.")
            return
        cfg = self._collect_config()
        if not self._preflight_checks(cfg, target):
            return

        self._save_config(silent=True)
        proj_path = Path(cfg["project_path"])
        add_recent(self.project_id)
        self._refresh_sidebar()

        # Check if we have a successful build to reuse
        base_build = Path(cfg["build_path"])
        subdir = self._export_subdir(self.preset_var.get(), cfg.get("engine", ""))
        version = get_project_version(proj_path)
        version_dir = version if version else ""
        t = self.config.get("last_build_time", "")
        ok = self.config.get("last_build_success", False)
        skip_build = ok and t and (base_build / subdir / version_dir).exists()

        self._begin_work()
        if skip_build:
            self._set_status("Reusing previous build...")
            self._set_step(1)
        else:
            self._set_status("Building...")
            self._set_step(0)

        preset = self.preset_var.get()
        thread = threading.Thread(target=self._run_publish, args=(target, cfg, preset, skip_build), daemon=True)
        thread.start()

    def _toggle_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        if self.btn_itch:
            self.btn_itch.configure(state=state)
        if self.btn_steam:
            self.btn_steam.configure(state=state)
        if self.btn_build:
            self.btn_build.configure(state=state)
        if self.btn_run:
            self.btn_run.configure(state=state)

    def _run_publish(self, target: str, cfg: dict[str, Any], preset: str, skip_build: bool = False) -> None:
        settings = load_settings()
        try:
            project = Path(cfg["project_path"])
            base_build = Path(cfg["build_path"])
            engine = cfg.get("engine", "")
            subdir = self._export_subdir(preset, engine)
            version = get_project_version(project)
            version_dir = version if version else ""
            if version_dir:
                self.root.after(0, lambda: self._log(f"[version] Detected: {version_dir}"))
            build = base_build / subdir / version_dir

            if not skip_build:
                if not engine:
                    engine = detect_engine(project)
                    if not engine:
                        raise BuildError("Could not auto-detect engine. Set 'engine' in config.")

                build.mkdir(parents=True, exist_ok=True)

                self.root.after(0, lambda: self._log(f"[engine] Detected: {engine}"))
                self.root.after(0, lambda: self._log(f"[project] {project}"))
                self.root.after(0, lambda: self._log(f"[build dir] {build}"))

                if engine == "godot":
                    self.root.after(0, lambda: self._log(f"[build] Godot export preset: {preset or '(none)'}"))
                    output = build_godot(
                        project, preset, build,
                        godot_exe=settings.get("godot_executable", ""),
                        log=lambda msg: self.root.after(0, self._log, msg),
                    )
                elif engine == "unity":
                    self.root.after(0, lambda: self._log("[build] Unity build (Windows x64)"))
                    output = build_unity(
                        project, build,
                        unity_exe=settings.get("unity_executable", ""),
                        log=lambda msg: self.root.after(0, self._log, msg),
                    )
                else:
                    raise BuildError(f"Unsupported engine: {engine}")

                self._record_build(True)
                self.root.after(0, lambda: self._set_step(1))
            else:
                t = self.config.get("last_build_time", "")
                age = self._format_time_ago(t) if t else ""
                msg = f"[build] Using previous build" + (f" from {age}" if age else "")
                self.root.after(0, lambda m=msg: self._log(m))
                output = build

            self.root.after(0, lambda: self._set_status("Packaging..."))
            parts = [project.name, subdir]
            if version_dir:
                parts.append(version_dir)
            if cfg.get("demo_build", False):
                parts[-1] = f"{parts[-1]} (demo)"
            zip_dir = base_build / "zips"
            zip_dir.mkdir(parents=True, exist_ok=True)
            zip_path = zip_dir / f"{'-'.join(parts)}.zip"
            zip_build(output, zip_path, log=lambda msg: self.root.after(0, self._log, msg))

            self.root.after(0, lambda: self._set_step(2))
            self.root.after(0, lambda: self._set_status("Uploading..."))
            if target == "itch":
                push_itch(zip_path, cfg.get("itch_target", ""), log=lambda msg: self.root.after(0, self._log, msg))
            elif target == "steam":
                steam_script = settings.get("steam_script_path", "")
                script_p = Path(steam_script) if steam_script else None
                depot_override = cfg.get("steam_depots", {}).get(cfg.get("platform", ""), "")
                push_steam(cfg["steam_app_id"], output, script_p, depot_id=depot_override or None, log=lambda msg: self.root.after(0, self._log, msg))

            self.root.after(0, lambda: self._set_step(3))

            def _on_success() -> None:
                self._stop_progress()
                self._log(f"\n{'='*50}")
                self._log(f"Done! Deployed to {target.upper()}")
                self._set_status(f"Deployed to {target}!")
                messagebox.showinfo("DeployFlow", f"Successfully deployed to {target}!")
                url = cfg.get("itch_url" if target == "itch" else "steam_url", "")
                if url:
                    webbrowser.open(url)
            self.root.after(0, _on_success)
        except (BuildError, UploadError) as exc:
            err_msg = str(exc)
            def _on_build_error() -> None:
                self._stop_progress()
                self._log(f"\n[ERROR] {err_msg}")
                self._set_status("Failed")
                messagebox.showerror("DeployFlow", err_msg)
            self.root.after(0, _on_build_error)
        except Exception as exc:
            err_msg = f"Unexpected error: {exc}"
            def _on_error() -> None:
                self._stop_progress()
                self._log(f"\n[ERROR] {err_msg}")
                self._set_status("Failed")
                messagebox.showerror("DeployFlow", err_msg)
            self.root.after(0, _on_error)
        finally:
            self._running = False
            self.root.after(0, lambda: self._toggle_buttons(True))


def run(project_id: str | None = None) -> None:
    if project_id is None:
        ids = load_recent_ids()
        if ids:
            project_id = ids[0]
    root = tk.Tk()
    root.withdraw()
    root.after(100, root.deiconify)
    DeployFlowApp(root, project_id)
    root.mainloop()
