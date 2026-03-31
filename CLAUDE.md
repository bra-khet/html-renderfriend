# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**html-renderfriend** — Python 3.11+ CLI + GUI tool that renders HTML files and URLs to full-page PNG
screenshots via headless Playwright/Chromium.

Entry points: `htmlrf` (CLI) and `htmlrf-gui` (drag-and-drop GUI).

## Architecture

Three layers, each with a distinct responsibility:

1. **`src/htmlrf/screenshot.py`** — Core public API: `take_full_screenshot(input_source, output_png, viewport_width, *, timeout_ms)`.
   - `output_png` accepts a `str` path **or** a `Callable[[str], str]` (page_title → path) for template-based naming.
   - `_resolve_url()` normalizes bare hostnames to `https://`; also imported by the GUI.

2. **`src/htmlrf/gui.py`** — CustomTkinter + TkinterDnD2 window.
   - Playwright runs in a **daemon worker thread**; all GUI updates use `self.after(0, callback)` for Tkinter thread-safety.
   - Viewport preset dict (`VIEWPORT_PRESETS`) uses a `None` sentinel for the "Custom…" entry.
   - Config persisted to `~/.htmlrf_config.json`.

3. **`pyproject.toml`** — Hatchling build, entry-point declarations, runtime + dev dependencies.

## Commands

```bash
# Setup
pip install -e .[dev]
playwright install chromium

# Tests
pytest                                     # all tests
pytest tests/test_screenshot.py -v        # single file
pytest -k "TestResolveFilename"           # single class

# Run
htmlrf https://example.com -o out.png     # CLI  (--width 320–7680, --timeout ms)
htmlrf-gui                                 # GUI  (Ctrl+S screenshot, Ctrl+D paste, Esc quit)

# Build standalone EXE
pip install pyinstaller && pip install -e .
pyinstaller --onefile --windowed --name htmlrf src/htmlrf/gui.py
# Output: dist\htmlrf.exe  (Chromium not bundled; run `playwright install chromium` on target)
```

## Key Patterns

- **Logging over print()**: Use `_log = logging.getLogger(__name__)`. `print()` is silently discarded
  in `--windowed` PyInstaller builds.
- **File URIs**: Use `Path.as_uri()`. Manual `f"file://{path.as_posix()}"` produces a malformed URI
  on Windows (missing the required leading `/`).
- **Comment conventions** (enforced project-wide — see global CLAUDE.md):
  - Non-trivial edits: `# CHANGED: …` / `# WHY: …`
  - Bug fixes: `# BUG FIX: <name>` / `# Fix: …` / `# Sync: …`

## Skills

- `/run-tests` — Run the test suite with scope options
- `/build-exe` — Build the PyInstaller standalone EXE

## Branches

Active feature branch: `v2.0-dev` → PR to `main`.
Sprint commits follow: `Sprint: <description>`. History in `docs/CHANGELOG.md`.
