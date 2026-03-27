# HTML RenderFriend

**Full-page PNG screenshots from HTML files and URLs — CLI + drag-and-drop GUI**

---

## Install

```
pip install html-renderfriend
playwright install chromium
```

That's it.

---

## Quick start

```powershell
# CLI
htmlrf https://example.com -o example.png
htmlrf "C:\MyPages\report.html" -o report.png --width 1440

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
| Configurable viewport width | ✓ | ✓ |
| Retina 2× output (deviceScaleFactor) | ✓ | ✓ |
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
| `-o` / `--output` | `screenshot.png` | Output PNG path |
| `-w` / `--width` | `1920` | Viewport width: `1280`, `1440`, `1920`, `2560` |

---

## GUI

Launch with `htmlrf-gui`. Three input methods:

| Method | How |
|---|---|
| **Drag and drop** | Drag any `.html` file from Windows Explorer onto the drop zone |
| **URL / path** | Type or paste into the entry field on the "Drop / URL" tab |
| **Paste HTML** | Switch to the "Paste HTML" tab, paste raw markup, click Screenshot |

Shortcuts: `Ctrl+S` screenshot · `Ctrl+D` paste clipboard as source · `Esc` quit

Output defaults to `Desktop/screenshot_<timestamp>.png`. Use **Save As…** to pin a fixed path.

---

## How it works

Playwright launches a headless Chromium instance, navigates to the target, waits for JS and resources to settle, then captures the full scrollable page height as PNG. Static converters that skip JS-driven layout produce different results.

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
│       ├── screenshot.py    # Core renderer + take_full_screenshot()
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
- [ ] PDF export alongside PNG
- [ ] Configurable wait conditions and CSS injection
- [ ] GitHub Actions CI for cross-platform testing

---

## License

MIT — see [LICENSE](LICENSE).
