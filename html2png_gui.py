#!/usr/bin/env python3
"""
html2png_gui.py — Drag-and-drop GUI for the HTML → PNG screenshotter.

How to test:
    1.  Run:            python html2png_gui.py
    2.  Drag an .html file onto the drop zone — screenshot fires automatically.
    3.  Or type/paste a URL into the entry field → click Screenshot.
    4.  Or switch to the "Paste HTML" tab, paste raw markup, click Screenshot.
    5.  Output defaults to Desktop/screenshot_<timestamp>.png.
        Use "Save As…" or the menu to choose a fixed path.

Dependencies (install once):
    pip install customtkinter tkinterdnd2 playwright
    playwright install chromium

PyInstaller single-file EXE (run from project root after pip install pyinstaller):
    pyinstaller --onefile --windowed --name html2png_gui \
        --add-data "screenshot.py;." html2png_gui.py
"""

import os
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

from screenshot import take_full_screenshot

# ── Design tokens ──────────────────────────────────────────────────────────────
_ACCENT       = "#00ffaa"
_ACCENT_HOVER = "#00cc88"
_BORDER_IDLE  = "#444444"
_BORDER_HOT   = _ACCENT
_DROP_IDLE    = "#1e1e1e"
_DROP_HOT     = "#0d2a1c"

VIEWPORT_OPTIONS = ["1280", "1440", "1920", "2560"]
DEFAULT_VIEWPORT = "1920"


# ── Main application window ────────────────────────────────────────────────────

class HTML2PNGApp(ctk.CTk, TkinterDnD.DnDWrapper):
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
        # Inject TkinterDnD protocol support into this CTk window.
        self.TkdndVersion = TkinterDnD._require(self)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("HTML2PNG • Full-Page Screenshotter v1.0")
        self.geometry("800x660")
        self.resizable(False, False)

        # ── State ──────────────────────────────────────────────────────────────
        self._input_source   = tk.StringVar()   # URL or file path (Drop/URL tab)
        self._viewport_var   = tk.StringVar(value=DEFAULT_VIEWPORT)
        self._saved_output   = tk.StringVar()   # Persists chosen "Save As" path
        self._worker_running = False             # Guard against double-triggers
        self._tmp_html_path: str | None = None  # Temp file for pasted HTML

        self._build_ui()
        self._bind_shortcuts()
        self._log("Ready — drop a file, enter a URL, or paste HTML.")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)   # Log pane takes spare vertical space

        self._build_topbar(row=0)
        self._build_tabs(row=1)
        self._build_controls(row=2)
        self._build_progress(row=3)
        self._build_log(row=4)
        self._build_statusbar(row=5)

    def _build_topbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent", height=44)
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 0))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar,
            text="HTML2PNG  •  Full-Page Screenshotter",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self._theme_switch = ctk.CTkSwitch(
            bar,
            text="Dark mode",
            onvalue="dark",
            offvalue="light",
            command=self._toggle_theme,
        )
        self._theme_switch.select()   # Start in dark mode
        self._theme_switch.grid(row=0, column=1, sticky="e")

    def _build_tabs(self, row: int) -> None:
        self._tabview = ctk.CTkTabview(self, height=260)
        self._tabview.grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._tabview.grid_columnconfigure(0, weight=1)

        self._tabview.add("Drop / URL")
        self._tabview.add("Paste HTML")

        self._build_drop_tab(self._tabview.tab("Drop / URL"))
        self._build_paste_tab(self._tabview.tab("Paste HTML"))

    def _build_drop_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        # Drop zone —————————————————————————————————————————————————————————
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
            font=ctk.CTkFont("Segoe UI", 19, "bold"),
            text_color=_ACCENT,
        )
        self._drop_label.grid(row=0, column=0)

        # Register both the frame and label as drop targets (the label covers
        # most of the frame's visible area and would otherwise swallow events).
        for widget in (self._drop_frame, self._drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>",      self._on_drop)
            widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

        # URL / file-path entry ——————————————————————————————————————————————
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

    def _build_paste_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="Paste raw HTML below, then click Screenshot:",
            anchor="w",
            font=ctk.CTkFont("Segoe UI", 12),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._html_box = ctk.CTkTextbox(
            parent,
            height=178,
            font=ctk.CTkFont("Cascadia Code", 11),
            wrap="none",
        )
        self._html_box.grid(row=1, column=0, sticky="nsew")
        self._html_box.insert("0.0", "<!-- Paste your HTML here -->\n")

    def _build_controls(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
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
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
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
            text="Save As…",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._choose_output,
        ).pack(side="right")

    def _build_progress(self, row: int) -> None:
        self._progress = ctk.CTkProgressBar(self, mode="indeterminate", height=8)
        self._progress.grid(row=row, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._progress.set(0)

    def _build_log(self, row: int) -> None:
        frame = ctk.CTkFrame(self)
        frame.grid(row=row, column=0, sticky="nsew", padx=16, pady=(10, 0))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="Log",
            anchor="w",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))

        self._log_box = ctk.CTkTextbox(
            frame,
            height=120,
            font=ctk.CTkFont("Cascadia Code", 10),
            state="disabled",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 4))

    def _build_statusbar(self, row: int) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent", height=36)
        bar.grid(row=row, column=0, sticky="ew", padx=16, pady=(6, 12))
        bar.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            bar,
            text="Ready.",
            anchor="w",
            font=ctk.CTkFont("Segoe UI", 11),
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
        # Ctrl+S → screenshot; Ctrl+D → paste clipboard as source; Esc → quit.
        self.bind("<Control-s>", lambda _: self._trigger_screenshot())
        self.bind("<Control-d>", self._paste_clipboard)
        self.bind("<Escape>",    lambda _: self.quit())

    # ── Drag-and-drop handlers ─────────────────────────────────────────────────

    def _on_drag_enter(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._drop_frame.configure(border_color=_BORDER_HOT, fg_color=_DROP_HOT)
        self._drop_label.configure(text="Release to screenshot!", text_color="#ffffff")

    def _on_drag_leave(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._reset_drop_zone()

    def _on_drop(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        # tkinterdnd2 wraps paths that contain spaces in curly braces.
        raw = event.data.strip().lstrip("{").rstrip("}")
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
        """Ctrl+D — paste clipboard text as the URL/path source."""
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
        """Prompt once for a fixed output path; reused until changed."""
        path = filedialog.asksaveasfilename(
            title="Save screenshot as…",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            initialdir=str(Path.home() / "Desktop"),
            initialfile=f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png",
        )
        if path:
            self._saved_output.set(path)
            self._log(f"Output path set: {path}")

    # ── Screenshot orchestration ───────────────────────────────────────────────

    def _trigger_screenshot(self) -> None:
        """Resolve source + output, then launch background worker thread."""
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

        # ── Resolve output ────────────────────────────────────────────────────
        fixed = self._saved_output.get().strip()
        if fixed:
            output = fixed
        else:
            desktop = Path.home() / "Desktop"
            desktop.mkdir(exist_ok=True)
            output = str(desktop / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")

        viewport = int(self._viewport_var.get())

        # ── Dispatch ──────────────────────────────────────────────────────────
        self._set_busy(True)
        self._log(f"Rendering  [{viewport}px]  {source[:90]}")

        threading.Thread(
            target=self._worker,
            args=(source, output, viewport),
            daemon=True,   # Thread dies automatically when the window closes.
        ).start()

    def _worker(self, source: str, output: str, viewport: int) -> None:
        """
        Runs on the background thread.
        Calls the synchronous Playwright API without blocking the GUI event loop.
        All Tkinter updates are deferred to the main thread via self.after(0, …).
        """
        try:
            take_full_screenshot(source, output, viewport)
            self.after(0, lambda: self._on_success(output))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.after(0, lambda: self._on_error(msg))
        finally:
            # Clean up the temp file created for pasted HTML.
            if self._tmp_html_path and os.path.exists(self._tmp_html_path):
                try:
                    os.unlink(self._tmp_html_path)
                except OSError:
                    pass

    # ── Post-worker callbacks (run on main thread) ─────────────────────────────

    def _on_success(self, output: str) -> None:
        self._set_busy(False)
        self._saved_output.set("")         # Reset so next run gets a fresh timestamp
        self._last_output = output
        self._log(f"✓  Saved: {output}")
        self._status_label.configure(text=f"Saved → {output}", text_color=_ACCENT)
        self._open_folder_btn.configure(state="normal")

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
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
        """Append a timestamped entry to the log pane. Always call from main thread."""
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}]  {message}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _open_output_folder(self) -> None:
        """Open the folder containing the last saved PNG in Windows Explorer."""
        folder = str(Path(self._last_output).parent)
        os.startfile(folder)    # Windows-only; safe on the Win 10 target platform

    def mainloop(self, n: int = 0) -> None:  # type: ignore[override]
        super().mainloop(n)


if __name__ == "__main__":
    app = HTML2PNGApp()
    app.mainloop()
