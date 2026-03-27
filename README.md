# HTML RenderFriend

**Full-page PNG screenshot utility for HTML files and URLs — CLI + drag-and-drop GUI**

Renders any web page or local `.html` file into a complete, scroll-captured PNG using the same Chromium engine as Google Chrome. Includes both a command-line tool and a modern drag-and-drop graphical interface.

---

## How it works

Producing a screenshot that captures the *entire* page height requires a full browser engine. Playwright launches a headless Chromium instance, navigates to your content, waits for all resources and JavaScript to settle, scrolls the page, then captures everything — including overflow content that would only appear after scrolling. This is fundamentally different from static converters that ignore JS-driven layout.

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

## Installation (Windows 10)

### One-click setup

```bat
git clone https://github.com/bra-khet/html-renderfriend.git
cd html-renderfriend
setup.bat
```

`setup.bat` creates a virtual environment, installs all pip packages, and downloads the Chromium browser (~150 MB, once).

### Manual setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -e .
playwright install chromium
```

Requirements: **Python 3.11+**. Check with `python --version`.

---

## Usage

### Graphical interface (recommended)

```bat
gui.bat
```

Or double-click `gui.bat`. The window opens with three ways to provide input:

| Input method | How |
|---|---|
| **Drag and drop** | Drag any `.html` file from Windows Explorer onto the green drop zone |
| **URL / path** | Type or paste into the entry field on the "Drop / URL" tab |
| **Paste HTML** | Switch to the "Paste HTML" tab, paste raw markup, click Screenshot |

Keyboard shortcuts: `Ctrl+S` screenshot · `Ctrl+D` paste clipboard as source · `Esc` quit

Output defaults to `Desktop/screenshot_<timestamp>.png`. Use **Save As…** to pin a fixed path.

---

### Command-line interface

```powershell
# Activate the venv first
venv\Scripts\activate

# Remote URL
htmlrf https://example.com -o example.png

# Local HTML file
htmlrf "C:\MyPages\report.html" -o report.png --width 1440

# See all options
htmlrf --help
```

**Drag-and-drop CLI:** drag an `.html` file onto `screenshot.bat` for an instant screenshot saved as `screenshot.png` in the same directory.

#### Options

| Flag | Default | Description |
|---|---|---|
| `input` | *(required)* | URL or path to `.html` / `.htm` file |
| `-o` / `--output` | `screenshot.png` | Output PNG path |
| `-w` / `--width` | `1920` | Viewport width: `1280`, `1440`, `1920`, `2560` |

---

## Project structure

```
html-renderfriend/
├── src/
│   └── htmlrf/
│       ├── __init__.py
│       ├── screenshot.py    # Core CLI + take_full_screenshot() shared with GUI
│       └── gui.py           # Drag-and-drop GUI (CustomTkinter + TkinterDnD2)
├── tests/
├── pyproject.toml           # Build metadata and dependencies (hatchling)
├── setup.bat                # One-click install script
├── screenshot.bat           # CLI drag-and-drop wrapper
├── gui.bat                  # GUI launcher
├── .gitignore
├── LICENSE                  # MIT
└── README.md
```

---

## Building a standalone EXE (optional)

```powershell
pip install pyinstaller
pip install -e .
pyinstaller --onefile --windowed --name htmlrf src/htmlrf/gui.py
```

The resulting `dist\htmlrf.exe` bundles everything except the Chromium browser, which Playwright downloads on first run.

---

## Roadmap

- [ ] Batch processing — screenshot a list of URLs from a `.txt` file
- [ ] PDF export alongside PNG
- [ ] Configurable wait conditions and CSS injection
- [ ] GitHub Actions CI for cross-platform testing

---

## License

MIT — see [LICENSE](LICENSE).

---

*Last updated: March 26, 2026*
