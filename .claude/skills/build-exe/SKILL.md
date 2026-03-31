---
name: build-exe
description: "Build a standalone PyInstaller Windows EXE for htmlrf-gui"
---

# Build Standalone EXE

## Steps

1. Activate venv and install prerequisites:
   ```
   venv\Scripts\activate
   pip install pyinstaller
   pip install -e .
   ```

2. Build:
   ```
   pyinstaller --onefile --windowed --name htmlrf src/htmlrf/gui.py
   ```

3. Output lands at `dist\htmlrf.exe`.

4. On the target machine, run once to fetch Chromium:
   ```
   playwright install chromium
   ```

5. Smoke-test: launch `dist\htmlrf.exe`, drop an `.html` file onto the drop zone,
   confirm a PNG saves to the Desktop.

## Notes

- `--windowed` suppresses the console window (required for a GUI-only EXE).
- `--onefile` bundles all Python dependencies into a single portable file.
- Chromium is intentionally **not** bundled — it is too large and must be
  installed separately via `playwright install chromium` on each target machine.
