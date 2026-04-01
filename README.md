# HTML RenderFriend

**Full-page PNG/PDF renders from HTML files and URLs — CLI + drag-and-drop GUI**

---

## Install

```
pip install html-renderfriend
playwright install chromium
```

Pypi project page: https://pypi.org/project/html-renderfriend/2.2.0/


---

## Quick start

```powershell
# CLI — PNG (default)
htmlrf https://example.com -o example.png
htmlrf "C:\MyPages\report.html" -o report.png --width 1440

# CLI — PDF (auto-detected from .pdf extension)
htmlrf https://example.com -o report.pdf
htmlrf "C:\MyPages\report.html" -o report.pdf --format Letter

# GUI
htmlrf-gui
```

---

## Features

| Feature | CLI | GUI |
|---|---|---|
| Remote URLs (http/https) | ✓ | ✓ |
| Local `.html` / `.htm` files | ✓ | ✓ |
| Paste raw HTML directly | — | ✓ |
| Drag-and-drop from Explorer | — | ✓ |
| **PDF export** (`page.pdf()`, WYSIWYG) | ✓ | ✓ |
| Configurable viewport width (320–7680 px) | ✓ | ✓ |
| Retina 2× output (deviceScaleFactor) | ✓ | — |
| Full-page scroll capture | ✓ | ✓ |
| Timestamped log pane | — | ✓ |
| Dark / light theme toggle | — | ✓ |
| Open output folder in Explorer | — | ✓ |

---

## CLI reference

```
htmlrf <input> [options]
```

| Flag | Default | Description |
|---|---|---|
| `input` | *(required)* | URL or path to `.html` / `.htm` file |
| `-o` / `--output` | `screenshot.png` | Output path — `.png` for PNG, `.pdf` for PDF (auto-detected) |
| `-w` / `--width` | `1920` | Viewport width in px (320–7680) |
| `--format` | `A4` | PDF paper size: `A4`, `Letter`, `Legal`, `Tabloid` (ignored for PNG) |
| `--timeout` | `30000` | Page load timeout in milliseconds |

---

## GUI

Launch with `htmlrf-gui`. Three input methods:

| Method | How |
|---|---|
| **Drag and drop** | Drag any `.html` file from Windows Explorer onto the drop zone |
| **URL / path** | Type or paste into the entry field on the "Drop / URL" tab |
| **Paste HTML** | Switch to the "Paste HTML" tab, paste raw markup, click the export button |

The green **Save .PNG ▶** button exports a PNG. Click **▼** to switch to **Save .PDF ▶** mode
(teal-green); the mode persists across sessions. **Save As…** updates its file filter automatically.

Shortcuts: `Ctrl+S` export (PNG or PDF) · `Ctrl+D` paste clipboard as source · `Esc` quit

Output defaults to `Desktop/screenshot_<timestamp>.png` (or `.pdf`). Use **Save As…** to pin a fixed path.

---

## How it works

Playwright launches a headless Chromium instance, navigates to the target, waits for JS and resources to settle, then captures the full scrollable page height as a PNG or paginated PDF.

For PDF export, `emulate_media("screen")` is applied before rendering so the output matches the
PNG visually — Chromium's default `@media print` stylesheet (which can hide backgrounds and alter
fonts) is intentionally bypassed. No extra dependencies are required; the same Chromium instance
handles both formats.

---

## Alternative install (from source)

```powershell
git clone https://github.com/bra-khet/html-renderfriend.git
cd html-renderfriend
python -m venv venv
venv\Scripts\activate
pip install -e .
playwright install chromium
```

Requires **Python 3.11+**.

---

## Building a standalone EXE

```powershell
pip install pyinstaller
pip install -e .
pyinstaller --onefile --windowed --name htmlrf src/htmlrf/gui.py
```

`dist\htmlrf.exe` bundles everything except Chromium, which Playwright downloads on first run.

---

## Project structure

```
html-renderfriend/
├── src/
│   └── htmlrf/
│       ├── __init__.py
│       ├── screenshot.py    # Core renderer: take_full_screenshot(), take_full_pdf()
│       └── gui.py           # Drag-and-drop GUI (CustomTkinter + TkinterDnD2)
├── tests/
├── pyproject.toml
├── setup.bat
├── screenshot.bat
├── gui.bat
├── .gitignore
├── LICENSE
└── README.md
```

---

## Roadmap

- [ ] Batch processing from a URL list file
- [ ] Configurable wait conditions and CSS injection
- [ ] GitHub Actions CI for cross-platform testing

---

## License

MIT — see [LICENSE](LICENSE).
