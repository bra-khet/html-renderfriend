#!/usr/bin/env python3
"""
htmlrf_gui.py — Drag-and-drop GUI for the HTML → PNG screenshotter.

How to test:
    1.  Run:            python htmlrf_gui.py
    2.  Drag an .html file onto the drop zone — screenshot fires automatically.
    3.  Or type/paste a URL into the entry field → click Screenshot.
    4.  Or switch to the "Paste HTML" tab, paste raw markup, click Screenshot.
    5.  Output defaults to Desktop/<template>.png (template configurable via Settings).
        Use "Save As…" to pin a specific path for the current session.

Dependencies (install once):
    pip install customtkinter tkinterdnd2 playwright
    playwright install chromium

PyInstaller single-file EXE (run from project root after pip install pyinstaller):
    pyinstaller --onefile --windowed --name htmlrf_gui \
        --add-data "screenshot.py{sep}." htmlrf_gui.py
    # {sep} is ";" on Windows and ":" on macOS/Linux (os.pathsep)
"""

import json
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time as _time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

# CHANGED: absolute import updated for src/ layout migration
# WHY: package is now htmlrf.screenshot, not a root-level module
from htmlrf.screenshot import take_full_screenshot, _resolve_url

_log = logging.getLogger(__name__)

# ── Platform-adaptive font tokens ──────────────────────────────────────────────
# CHANGED: replace hardcoded "Segoe UI" / "Cascadia Code" with per-OS fallbacks
# WHY: those fonts are Windows-only; macOS and Linux would silently fall back to
#      an arbitrary system font, producing inconsistent UI on non-Windows builds.
_SYSTEM    = platform.system()   # "Windows" | "Darwin" | "Linux"
_FONT_BODY = (
    "Segoe UI"      if _SYSTEM == "Windows" else
    "SF Pro Text"   if _SYSTEM == "Darwin"  else
    "Ubuntu"
)
_FONT_MONO = (
    "Cascadia Code" if _SYSTEM == "Windows" else
    "SF Mono"       if _SYSTEM == "Darwin"  else
    "DejaVu Sans Mono"
)

# ── Design tokens ──────────────────────────────────────────────────────────────
_ACCENT       = "#00ffaa"
_ACCENT_HOVER = "#00cc88"
_BORDER_IDLE  = "#444444"
_BORDER_HOT   = _ACCENT
_DROP_IDLE    = "#1e1e1e"
_DROP_HOT     = "#0d2a1c"

VIEWPORT_OPTIONS = ["1280", "1440", "1920", "2560"]
DEFAULT_VIEWPORT = "1920"

# Log pane: trim to this many lines to prevent unbounded memory growth.
# CHANGED: add line cap for the log textbox
# WHY: in long sessions (batch use, repeat renders) the log grew without bound.
_MAX_LOG_LINES = 400

# ── System theme detection ─────────────────────────────────────────────────────
# CHANGED: detect OS dark/light preference instead of hardcoding dark mode
# WHY: users on light-mode systems were forced into dark mode on every launch.
try:
    import darkdetect as _dd
    _INITIAL_DARK: bool = _dd.isDark() is not False   # None → assume dark
except ImportError:
    _INITIAL_DARK = True


# ── Config persistence ─────────────────────────────────────────────────────────
_CONFIG_PATH = Path.home() / ".htmlrf_config.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(data: dict) -> None:
    _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Cross-platform output directory default ────────────────────────────────────
# CHANGED: replace bare Path.home() / "Desktop" with a helper that checks
#          whether Desktop actually exists.
# WHY: on many Linux distros the Desktop folder does not exist by default;
#      writing to a non-existent directory raises FileNotFoundError at runtime.
def _default_output_dir() -> Path:
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


# ── Cross-platform folder opener ───────────────────────────────────────────────
# CHANGED: replace os.startfile() with a platform-dispatching helper
# WHY: os.startfile is Windows-only; calling it on macOS/Linux raises AttributeError.
def _open_folder(path: str | Path) -> None:
    folder = str(Path(path).parent)
    if sys.platform == "win32":
        os.startfile(folder)           # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


# ── Local-time helper (single call-site for tz awareness) ─────────────────────
# CHANGED: centralise datetime.now() into one helper
# WHY: all callers use local-naive time today; if tz-aware output is later needed
#      (e.g. UTC filenames for server deployments) this is the only place to change.
def _now() -> datetime:
    return datetime.now()


# ── Filename template engine ───────────────────────────────────────────────────
DEFAULT_TEMPLATE = "{name}_{date}_{time}"

# (token, description, example value shown in Settings dialog)
_TEMPLATE_VARS = [
    ("{name}",   "Hostname (no www.) or file stem",   "github"),
    ("{domain}", "Full hostname",                      "www.github.com"),
    ("{date}",   "Date  YYYY-MM-DD",                  "2026-03-26"),
    ("{year}",   "Year",                               "2026"),
    ("{month}",  "Month",                              "03"),
    ("{day}",    "Day",                                "26"),
    ("{time}",   "Time  HH-MM-SS",                    "14-30-00"),
    ("{ts}",     "Unix timestamp",                     "1743000000"),
    ("{title}",  "Page <title> tag",                  "My Page"),
    ("{seq}",    "Auto-increment  001, 002 …",         "001"),
    ("{width}",  "Viewport width (px)",                "1920"),
]

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _sanitize(s: str, max_len: int = 80) -> str:
    """Replace filesystem-unsafe characters and truncate."""
    s = _UNSAFE.sub("-", s).strip("-. ")
    return s[:max_len] or "untitled"


def _resolve_filename(
    template: str,
    source: str,
    viewport: int,
    page_title: str = "",
    output_dir: str | Path = "",
) -> str:
    """
    Expand template variables into a concrete filename (with .png extension).
    Handles {seq} by scanning output_dir for collisions.
    """
    now = _now()

    if os.path.isfile(source):
        name   = Path(source).stem
        domain = ""
    else:
        try:
            parsed = urlparse(source if "://" in source else f"https://{source}")
            domain = parsed.hostname or ""
            name   = re.sub(r"^www\.", "", domain)
        except Exception:
            name = domain = "screenshot"

    safe_title = _sanitize(page_title) if page_title else (name or "screenshot")

    subs = {
        "{name}":   _sanitize(name)   or "screenshot",
        "{domain}": _sanitize(domain) or name or "screenshot",
        "{date}":   now.strftime("%Y-%m-%d"),
        "{year}":   now.strftime("%Y"),
        "{month}":  now.strftime("%m"),
        "{day}":    now.strftime("%d"),
        "{time}":   now.strftime("%H-%M-%S"),
        "{ts}":     str(int(_time.time())),
        "{title}":  safe_title,
        "{width}":  str(viewport),
    }

    stem = template
    for token, val in subs.items():
        stem = stem.replace(token, val)

    # {seq} — find next non-colliding sequence number
    if "{seq}" in stem:
        seq = 1
        if output_dir:
            # CHANGED: construct the candidate filename the same way the final
            #          name is built (via _sanitize on the full stem with {seq}
            #          already substituted), rather than using base+seq concatenation.
            # WHY: BUG FIX — when {seq} appears anywhere except the end of the
            #      template, "base + seq_formatted" produced a different string
            #      than "stem.replace({seq}, seq_formatted)", so the collision
            #      check tested the wrong file and seq always returned 001.
            # BUG FIX: seq-collision-check-wrong-filename
            # Fix: replaced f"{base}{seq:03d}.png" with _sanitize(stem.replace(...))
            while Path(
                output_dir,
                _sanitize(stem.replace("{seq}", f"{seq:03d}")) + ".png",
            ).exists():
                seq += 1
        stem = stem.replace("{seq}", f"{seq:03d}")

    stem = _sanitize(stem) or "screenshot"
    return stem + ".png"


# ── Settings dialog ────────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    """Modal dialog for persistent output directory and filename template."""

    def __init__(self, parent: ctk.CTk, config: dict) -> None:
        super().__init__(parent)
        self._config  = config
        self._result: dict | None = None

        self.title("Screenshot Settings")
        self.geometry("540x680")
        self.resizable(True, True)
        self.minsize(480, 620)
        self.grab_set()
        self.focus_set()

        self._dir_var  = tk.StringVar(
            value=config.get("output_dir", str(_default_output_dir()))
        )
        self._tmpl_var = tk.StringVar(
            value=config.get("filename_template", DEFAULT_TEMPLATE)
        )

        self._build_ui()
        self._tmpl_var.trace_add("write", self._update_preview)
        self._update_preview()

        self.wait_window(self)   # block caller until dialog closes

    # CHANGED: expose _result via a public property
    # WHY: the parent accessed self._result directly (private attribute from
    #      outside the class), which tightly couples the two classes and will
    #      silently break if the attribute is renamed internally.
    @property
    def result(self) -> dict | None:
        return self._result

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # ── Output directory ──────────────────────────────────────────────────
        s1 = ctk.CTkFrame(self, fg_color="transparent")
        s1.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 0))
        s1.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            s1, text="Output Directory",
            font=ctk.CTkFont(_FONT_BODY, 12, "bold"), anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ctk.CTkEntry(
            s1, textvariable=self._dir_var, height=34,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        ctk.CTkButton(
            s1, text="Browse…", width=90, height=34,
            command=self._browse_dir,
        ).grid(row=1, column=1, sticky="e", padx=(6, 0), pady=(4, 0))

        # ── Filename template ─────────────────────────────────────────────────
        s2 = ctk.CTkFrame(self, fg_color="transparent")
        s2.grid(row=1, column=0, sticky="ew", padx=22, pady=(18, 0))
        s2.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            s2, text="Filename Template",
            font=ctk.CTkFont(_FONT_BODY, 12, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            s2, text="Use {variables} below — .png is appended automatically.",
            font=ctk.CTkFont(_FONT_BODY, 10), text_color="gray", anchor="w",
        ).grid(row=1, column=0, sticky="w")

        ctk.CTkEntry(
            s2, textvariable=self._tmpl_var,
            font=ctk.CTkFont(_FONT_MONO, 12), height=34,
        ).grid(row=2, column=0, sticky="ew", pady=(4, 0))

        self._preview_label = ctk.CTkLabel(
            s2, text="", anchor="w",
            font=ctk.CTkFont(_FONT_MONO, 10), text_color="gray",
        )
        self._preview_label.grid(row=3, column=0, sticky="w", pady=(4, 0))

        # ── Variable reference ─────────────────────────────────────────────────
        s3 = ctk.CTkFrame(self)
        s3.grid(row=2, column=0, sticky="ew", padx=22, pady=(16, 0))
        s3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            s3, text="Available Variables",
            font=ctk.CTkFont(_FONT_BODY, 11, "bold"), anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 2))

        for i, (token, desc, example) in enumerate(_TEMPLATE_VARS):
            row_bg = "#1e1e1e" if i % 2 == 0 else "transparent"
            ctk.CTkLabel(
                s3, text=token,
                font=ctk.CTkFont(_FONT_MONO, 11), text_color=_ACCENT,
                fg_color=row_bg, anchor="w",
            ).grid(row=i + 1, column=0, sticky="ew", padx=(10, 8), pady=1)
            ctk.CTkLabel(
                s3, text=desc,
                font=ctk.CTkFont(_FONT_BODY, 11),
                fg_color=row_bg, anchor="w",
            ).grid(row=i + 1, column=1, sticky="ew", pady=1)
            ctk.CTkLabel(
                s3, text=example,
                font=ctk.CTkFont(_FONT_MONO, 10), text_color="gray",
                fg_color=row_bg, anchor="e",
            ).grid(row=i + 1, column=2, sticky="e", padx=(8, 10), pady=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=22, pady=(16, 20))

        ctk.CTkButton(
            btns, text="Reset to Default", width=140,
            fg_color="transparent", border_width=1,
            command=self._reset,
        ).pack(side="left")

        ctk.CTkButton(
            btns, text="Save",
            width=90, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
            text_color="#000000", font=ctk.CTkFont(_FONT_BODY, 12, "bold"),
            command=self._save,
        ).pack(side="right")

        ctk.CTkButton(
            btns, text="Cancel", width=90,
            fg_color="transparent", border_width=1,
            command=self.destroy,
        ).pack(side="right", padx=(0, 6))

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(
            title="Select default output directory",
            initialdir=self._dir_var.get() or str(_default_output_dir()),
            parent=self,
        )
        if d:
            self._dir_var.set(d)

    def _update_preview(self, *_) -> None:
        tmpl = self._tmpl_var.get().strip() or DEFAULT_TEMPLATE
        filename = _resolve_filename(
            tmpl, "https://github.com", 1920, "My Sample Page", ""
        )
        self._preview_label.configure(text=f"Preview:  {filename}")

    def _reset(self) -> None:
        self._tmpl_var.set(DEFAULT_TEMPLATE)
        self._dir_var.set(str(_default_output_dir()))

    def _save(self) -> None:
        d = self._dir_var.get().strip()
        t = self._tmpl_var.get().strip() or DEFAULT_TEMPLATE
        if not d:
            messagebox.showwarning(
                "No Directory", "Please select an output directory.", parent=self,
            )
            return
        self._result = {"output_dir": d, "filename_template": t}
        self.destroy()


# ── Main application window ────────────────────────────────────────────────────

class HTMLRenderFriendApp(ctk.CTk, TkinterDnD.DnDWrapper):
    """
    Dual-inherits CTk (CustomTkinter themed window) + TkinterDnD.DnDWrapper so
    that Windows-native OLE drag-and-drop works alongside CTk theming.

    Architecture:
        • Main thread  → Tkinter event loop + all widget updates
        • Worker thread → Playwright (blocking I/O); communicates back via
                          self.after(0, callback) to avoid Tkinter thread-safety
                          violations and "Not Responding" states.
    """

    def __init__(self) -> None:
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        # CHANGED: use "system" appearance mode so the app respects the OS theme
        # WHY: hardcoded "dark" forced dark mode on every launch regardless of the
        #      user's OS light/dark preference — friction for light-mode users.
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("HTML Renderfriend • Full-Page Screenshotter v1.0")
        self.geometry("800x660")
        self.resizable(True, True)
        self.minsize(700, 560)

        # ── State ──────────────────────────────────────────────────────────────
        self._config         = _load_config()
        self._config.pop("output_path", None)   # remove legacy fixed-path override
        self._input_source   = tk.StringVar()   # URL or file path (Drop/URL tab)
        self._viewport_var   = tk.StringVar(value=DEFAULT_VIEWPORT)
        self._saved_output   = tk.StringVar()   # session-only; cleared on relaunch
        self._worker_running = False             # Guard against double-triggers
        self._tmp_html_path: str | None = None  # Temp file for pasted HTML

        self._build_ui()
        self._bind_shortcuts()
        self._log("Ready — drop a file, enter a URL, or paste HTML.")

        # CHANGED: run a background Playwright health check at startup
        # WHY: without this, a missing Chromium installation only surfaces as a
        #      cryptic Playwright error after the user triggers their first render.
        threading.Thread(target=self._startup_health_check, daemon=True).start()

    # ── Startup health check ───────────────────────────────────────────────────

    def _startup_health_check(self) -> None:
        """Background check: warn early if Chromium is not installed."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                if not Path(pw.chromium.executable_path).exists():
                    self.after(0, lambda: self._log(
                        "⚠  Chromium not found — run: playwright install chromium"
                    ))
        except ImportError:
            self.after(0, lambda: self._log(
                "⚠  Playwright not installed — run: pip install playwright"
            ))
        except Exception:
            pass   # Will fail loudly on first render attempt with a clear error

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Root window holds only the bezel frame — one grid cell, fills all space.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Bezel / decorative border ──────────────────────────────────────────
        # A bordered inner frame gives a clean inset look and visually extends
        # the native resize-grab area around the window edges (padx/y 5 px).
        # Performance note: corner_radius=0 avoids per-frame anti-alias math,
        # which is the largest CTK contributor to resize lag.
        self._main_frame = ctk.CTkFrame(
            self,
            border_width=2,
            border_color=_BORDER_IDLE,
            corner_radius=0,
        )
        self._main_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self._main_frame.grid_columnconfigure(0, weight=1)
        self._main_frame.grid_rowconfigure(4, weight=1, minsize=80)

        self._build_topbar(row=0)
        self._build_tabs(row=1)
        self._build_controls(row=2)
        self._build_progress(row=3)
        self._build_log(row=4)
        self._build_statusbar(row=5)

    def _build_topbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self._main_frame, fg_color="transparent", height=44)
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 0))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar,
            text="HTML Renderfriend  •  Full-Page Screenshotter",
            font=ctk.CTkFont(_FONT_BODY, 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self._theme_switch = ctk.CTkSwitch(
            bar,
            text="Dark mode",
            onvalue="dark",
            offvalue="light",
            command=self._toggle_theme,
        )
        # CHANGED: sync initial switch state to the detected OS theme
        # WHY: with "system" appearance mode the switch label would say "Dark mode"
        #      while the app was actually running in light mode on light-mode systems.
        if _INITIAL_DARK:
            self._theme_switch.select()
        else:
            self._theme_switch.deselect()
            self._theme_switch.configure(text="Light mode")
        self._theme_switch.grid(row=0, column=1, sticky="e")

    def _build_tabs(self, row: int) -> None:
        self._tabview = ctk.CTkTabview(self._main_frame, height=260)
        self._tabview.grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._tabview.grid_columnconfigure(0, weight=1)

        self._tabview.add("Drop / URL")
        self._tabview.add("Paste HTML")

        self._build_drop_tab(self._tabview.tab("Drop / URL"))
        self._build_paste_tab(self._tabview.tab("Paste HTML"))

    def _build_drop_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        self._drop_frame = ctk.CTkFrame(
            parent,
            height=148,
            border_width=3,
            border_color=_BORDER_IDLE,
            fg_color=_DROP_IDLE,
            corner_radius=12,
        )
        self._drop_frame.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        self._drop_frame.grid_propagate(False)
        self._drop_frame.grid_columnconfigure(0, weight=1)
        self._drop_frame.grid_rowconfigure(0, weight=1)

        self._drop_label = ctk.CTkLabel(
            self._drop_frame,
            text="DROP  .html  FILE  HERE",
            font=ctk.CTkFont(_FONT_BODY, 19, "bold"),
            text_color=_ACCENT,
        )
        self._drop_label.grid(row=0, column=0)

        for widget in (self._drop_frame, self._drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>",      self._on_drop)
            widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

        ef = ctk.CTkFrame(parent, fg_color="transparent")
        ef.grid(row=1, column=0, sticky="ew")
        ef.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ef, text="URL or file path:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=2,
        )
        self._url_entry = ctk.CTkEntry(
            ef,
            textvariable=self._input_source,
            placeholder_text="https://example.com  or  C:\\path\\to\\file.html",
            height=36,
        )
        self._url_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Enter key triggers screenshot on the URL/Drop tab only.
        # The Paste HTML tab textbox intentionally has no such binding.
        self._url_entry.bind("<Return>", lambda _e: self._trigger_screenshot())

    def _build_paste_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="Paste raw HTML below, then click Screenshot:",
            anchor="w",
            font=ctk.CTkFont(_FONT_BODY, 12),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._html_box = ctk.CTkTextbox(
            parent,
            height=178,
            font=ctk.CTkFont(_FONT_MONO, 11),
            wrap="none",
        )
        self._html_box.grid(row=1, column=0, sticky="nsew")
        self._html_box.insert("0.0", "<!-- Paste your HTML here -->\n")

    def _build_controls(self, row: int) -> None:
        bar = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(10, 0))

        ctk.CTkButton(
            bar, text="Select HTML File…", width=158,
            command=self._open_file_dialog,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar,
            text="Screenshot  ▶",
            width=158,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(_FONT_BODY, 13, "bold"),
            command=self._trigger_screenshot,
        ).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(bar, text="Viewport:").pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(
            bar,
            variable=self._viewport_var,
            values=VIEWPORT_OPTIONS,
            width=90,
        ).pack(side="left")

        ctk.CTkButton(
            bar,
            text="Settings…",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._open_settings,
        ).pack(side="right")

        ctk.CTkButton(
            bar,
            text="Save As…",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._choose_output,
        ).pack(side="right", padx=(0, 6))

    def _build_progress(self, row: int) -> None:
        self._progress = ctk.CTkProgressBar(self._main_frame, mode="indeterminate", height=8)
        self._progress.grid(row=row, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._progress.set(0)

    def _build_log(self, row: int) -> None:
        frame = ctk.CTkFrame(self._main_frame)
        frame.grid(row=row, column=0, sticky="nsew", padx=16, pady=(10, 0))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Log",
            anchor="w",
            font=ctk.CTkFont(_FONT_BODY, 11, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))

        self._log_box = ctk.CTkTextbox(
            frame,
            height=120,
            font=ctk.CTkFont(_FONT_MONO, 10),
            state="disabled",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 4))

    def _build_statusbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self._main_frame, fg_color="transparent", height=36)
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(6, 12))
        bar.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            bar,
            text="Ready.",
            anchor="w",
            font=ctk.CTkFont(_FONT_BODY, 11),
            text_color="gray",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        self._open_folder_btn = ctk.CTkButton(
            bar,
            text="Open Output Folder",
            width=155,
            state="disabled",
            command=self._open_output_folder,
        )
        self._open_folder_btn.grid(row=0, column=1, sticky="e")

    # ── Keyboard shortcuts ─────────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-s>", lambda _: self._trigger_screenshot())
        self.bind("<Control-d>", self._paste_clipboard)
        # CHANGED: Escape now checks whether a render is in progress before quitting
        # WHY: previously Escape quit unconditionally mid-render, leaving orphaned
        #      temp files and giving no user feedback about the abrupt termination.
        self.bind("<Escape>",    self._on_escape)

    def _on_escape(self, _event: object = None) -> None:
        if self._worker_running:
            self._log("Render in progress — press Escape again or wait for it to finish.")
            self.bind("<Escape>", lambda _: self.quit())   # second press quits
        else:
            self.quit()

    # ── Drag-and-drop handlers ─────────────────────────────────────────────────

    def _on_drag_enter(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._drop_frame.configure(border_color=_BORDER_HOT, fg_color=_DROP_HOT)
        self._drop_label.configure(text="Release to screenshot!", text_color="#ffffff")

    def _on_drag_leave(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._reset_drop_zone()

    def _on_drop(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        # CHANGED: use self.tk.splitlist() to parse the Tcl file-list correctly
        # WHY: BUG FIX — the previous lstrip("{")/rstrip("}") approach failed for
        #      multiple files (e.g. "{path1} {path2}") and for single paths with
        #      spaces wrapped in braces by TkinterDnD2.  splitlist() is the correct
        #      Tcl-list parser that handles all quoting/bracing edge cases.
        # BUG FIX: multi-file-drop-parsing
        # Fix: replaced manual lstrip/rstrip with self.tk.splitlist(event.data)
        try:
            paths = self.tk.splitlist(event.data)
        except tk.TclError:
            paths = [event.data.strip()]

        if not paths:
            self._reset_drop_zone()
            return

        if len(paths) > 1:
            self._log(
                f"Multiple files dropped — using first of {len(paths)}: {paths[0]}"
            )

        raw = paths[0]
        self._input_source.set(raw)
        self._reset_drop_zone()
        self._tabview.set("Drop / URL")
        self._log(f"Dropped: {raw}")
        self._trigger_screenshot()

    def _reset_drop_zone(self) -> None:
        self._drop_frame.configure(border_color=_BORDER_IDLE, fg_color=_DROP_IDLE)
        self._drop_label.configure(text="DROP  .html  FILE  HERE", text_color=_ACCENT)

    # ── User-action handlers ───────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        mode = self._theme_switch.get()
        ctk.set_appearance_mode(mode)
        self._theme_switch.configure(text=f"{mode.capitalize()} mode")

    def _paste_clipboard(self, _event: object = None) -> None:
        try:
            text = self.clipboard_get().strip()
            self._input_source.set(text)
            self._tabview.set("Drop / URL")
            self._log(f"Pasted from clipboard: {text[:100]}")
        except tk.TclError:
            self._log("Clipboard is empty or not text.")

    def _open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Select HTML file",
            filetypes=[("HTML files", "*.html *.htm"), ("All files", "*.*")],
        )
        if path:
            self._input_source.set(path)
            self._tabview.set("Drop / URL")
            self._log(f"Selected: {path}")

    def _choose_output(self) -> None:
        """Prompt for a one-shot output path used for the NEXT screenshot only.
        ⚠ OUTPUT-PATH SYNC NOTE: _saved_output is a one-shot StringVar.
          It is set here and MUST be cleared in _on_success/_on_error after use.
          If you add any other place that reads or persists the output path
          (e.g. _load_config / _save_config / settings dialog), verify this
          clear-after-use contract still holds, or stale-path bugs will recur.
        """
        path = filedialog.asksaveasfilename(
            title="Save screenshot as…",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            initialdir=self._config.get("output_dir", str(_default_output_dir())),
            initialfile=f"screenshot_{_now():%Y%m%d_%H%M%S}.png",
        )
        if path:
            self._saved_output.set(path)
            self._log(f"Output override set (next screenshot only): {path}")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self, self._config)
        # CHANGED: access result via the public property instead of _result
        # WHY: avoids cross-class private-attribute coupling; see SettingsDialog.result
        if dlg.result:
            self._config.update(dlg.result)
            _save_config(self._config)
            self._log(
                f"Settings saved — "
                f"dir: {dlg.result['output_dir']}  "
                f"template: {dlg.result['filename_template']}"
            )

    # ── Screenshot orchestration ───────────────────────────────────────────────

    def _trigger_screenshot(self) -> None:
        """Resolve source + output resolver, then launch background worker thread."""
        if self._worker_running:
            self._log("Already running — please wait.")
            return

        tab = self._tabview.get()

        # ── Resolve source ────────────────────────────────────────────────────
        if tab == "Paste HTML":
            html = self._html_box.get("0.0", "end").strip()
            if not html or html == "<!-- Paste your HTML here -->":
                messagebox.showwarning("No HTML", "Paste some HTML first.")
                return
            tmp = tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8"
            )
            tmp.write(html)
            tmp.close()
            source = tmp.name
            self._tmp_html_path = source
        else:
            source = self._input_source.get().strip()
            if not source:
                messagebox.showwarning(
                    "No Input",
                    "Enter a URL, file path, or drop an HTML file onto the drop zone.",
                )
                return
            self._tmp_html_path = None

        viewport = int(self._viewport_var.get())

        # ── Build output resolver ─────────────────────────────────────────────
        fixed = self._saved_output.get().strip()
        if fixed:
            # Save As override — use the exact path regardless of template.
            output_resolver = lambda _title: fixed
        else:
            output_dir = self._config.get("output_dir", str(_default_output_dir()))
            template   = self._config.get("filename_template", DEFAULT_TEMPLATE)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            def output_resolver(page_title: str, _src=source, _vp=viewport,
                                 _tmpl=template, _dir=output_dir) -> str:
                fname = _resolve_filename(_tmpl, _src, _vp, page_title, _dir)
                return str(Path(_dir) / fname)

        # ── Dispatch ──────────────────────────────────────────────────────────
        self._set_busy(True)
        self._log(f"Rendering  [{viewport}px]  {source[:90]}")

        threading.Thread(
            target=self._worker,
            args=(source, output_resolver, viewport),
            daemon=True,
        ).start()

    def _worker(self, source: str, output_resolver, viewport: int) -> None:
        """
        Background thread.  Handles protocol auto-detection and HTTPS → HTTP
        fallback with a main-thread confirmation dialog via threading.Event.
        """
        resolved_source, was_upgraded = _resolve_url(source)
        if was_upgraded:
            self.after(0, lambda: self._log(
                f"No protocol specified — trying HTTPS: {resolved_source}"
            ))

        try:
            _title, final_path = take_full_screenshot(
                resolved_source, output_resolver, viewport
            )
            self.after(0, lambda: self._on_success(final_path))
            return
        except Exception as exc:
            if not was_upgraded and not resolved_source.startswith("https://"):
                # Not an upgraded URL — no HTTP fallback to offer.
                msg = str(exc)
                self.after(0, lambda: self._on_error(msg))
                self._cleanup_tmp()
                return
            https_exc = exc

        # HTTPS failed — ask user whether to retry with HTTP.
        retry_event  = threading.Event()
        retry_result = [False]

        def _ask() -> None:
            retry_result[0] = messagebox.askyesno(
                "HTTPS Connection Failed",
                f"Could not connect over HTTPS.\n\n"
                f"Retry with HTTP (unencrypted)?\n\n"
                f"URL: {resolved_source}",
                icon="warning",
            )
            retry_event.set()

        self.after(0, _ask)
        retry_event.wait()   # blocks worker thread; GUI thread remains responsive

        if not retry_result[0]:
            msg = str(https_exc)
            self.after(0, lambda: self._on_error(msg))
            self._cleanup_tmp()
            return

        # HTTP retry
        http_source = "http://" + resolved_source.removeprefix("https://")
        self.after(0, lambda: self._log(f"Retrying over HTTP: {http_source}"))

        try:
            _title, final_path = take_full_screenshot(
                http_source, output_resolver, viewport
            )
            self.after(0, lambda: self._on_success(final_path))
        except Exception as exc2:
            msg = str(exc2)
            self.after(0, lambda: self._on_error(msg))
        finally:
            self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        if self._tmp_html_path and os.path.exists(self._tmp_html_path):
            try:
                os.unlink(self._tmp_html_path)
            except OSError:
                pass

    # ── Post-worker callbacks (run on main thread) ─────────────────────────────

    def _on_success(self, output: str) -> None:
        self._set_busy(False)
        self._last_output = output
        # BUG FIX (stale-output): clear the one-shot Save-As override so the
        # next render uses the template from Settings instead of repeating this
        # exact path. See _choose_output docstring for the sync contract.
        self._saved_output.set("")
        # Re-arm the single-press Escape guard (cleared on error path too).
        self.bind("<Escape>", self._on_escape)
        self._log(f"✓  Saved: {output}")
        self._status_label.configure(text=f"Saved → {output}", text_color=_ACCENT)
        self._open_folder_btn.configure(state="normal")

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        # BUG FIX (stale-output): also clear on error so a failed render does
        # not silently consume the Save-As override, leaving it stale.
        self._saved_output.set("")
        self.bind("<Escape>", self._on_escape)
        self._log(f"✗  Error: {message}")
        self._status_label.configure(text="Error — see log.", text_color="#ff5555")
        self._drop_frame.configure(border_color="#ff5555")
        self.after(2000, self._reset_drop_zone)
        messagebox.showerror("Screenshot failed", message)

    # ── UI helpers ─────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._worker_running = busy
        if busy:
            self._progress.configure(mode="indeterminate")
            self._progress.start()
            self._status_label.configure(text="Rendering…", text_color="gray")
        else:
            self._progress.stop()
            self._progress.set(0)

    def _log(self, message: str) -> None:
        ts   = _now().strftime("%H:%M:%S")
        line = f"[{ts}]  {message}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line)

        # CHANGED: trim the log pane to _MAX_LOG_LINES to cap memory usage
        # WHY: in long sessions or repeat renders the textbox grew without bound,
        #      consuming memory and slowing down text-widget redraws.
        line_count = int(self._log_box.index("end-1c").split(".")[0])
        if line_count > _MAX_LOG_LINES:
            excess = line_count - _MAX_LOG_LINES
            self._log_box.delete("1.0", f"{excess + 1}.0")

        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _open_output_folder(self) -> None:
        # CHANGED: use _open_folder() instead of os.startfile()
        # WHY: os.startfile is Windows-only; _open_folder dispatches to the
        #      correct platform command (open on macOS, xdg-open on Linux).
        _open_folder(self._last_output)

    def mainloop(self, n: int = 0) -> None:  # type: ignore[override]
        super().mainloop(n)


def main() -> None:
    """Entry point for [project.gui-scripts] — launched via `htmlrf` after install."""
    app = HTMLRenderFriendApp()
    app.mainloop()


if __name__ == "__main__":
    main()
