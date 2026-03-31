# Changelog

All notable changes to HTML RenderFriend are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.2.0] - 2026-03-31

### Added

- **PDF export** — `take_full_pdf()` renders any URL or local HTML file to a
  paginated PDF via Playwright's `page.pdf()` API.  No new dependencies — the
  same headless Chromium instance already used for PNG screenshots produces the
  PDF.  `emulate_media("screen")` is applied before export so the PDF matches
  the PNG visually rather than defaulting to `@media print` stylesheets.

- **Split-button group** replaces the single green "Screenshot ▶" button in the GUI:
  - Main button shows **"Save .PNG  ▶"** (bright green `#00ffaa`) or
    **"Save .PDF  ▶"** (teal-green `#00cc99`) depending on active mode.
  - Adjacent **▼** arrow opens a two-item dropdown to switch between modes.
  - Mode is persisted to `~/.htmlrf_config.json` (`export_mode` key) and
    restored on the next launch.

- **CLI PDF output** — `htmlrf page.html -o report.pdf` auto-detects the `.pdf`
  extension and calls `take_full_pdf()` with no extra flag required.

- **`--format` CLI flag** — selects PDF paper size: `A4` (default), `Letter`,
  `Legal`, `Tabloid`.  Ignored when the output file is not `.pdf`.

- **Ctrl+S** keyboard shortcut works in both PNG and PDF modes (triggers
  whichever mode is currently active).

- **Save As…** dialog filter and default extension update dynamically
  when export mode is switched (`.png` ↔ `.pdf`).

### Changed

- `_prepare_page()` private helper extracted from `take_full_screenshot()` to
  share identical navigation, scroll, and settle logic with `take_full_pdf()`.
- Window title updated to **v2.2**.
- `pyproject.toml` description updated to mention PDF rendering.

---

## [2.1.0] - 2026-03-31

### Project

- **AI-Firstified** — repository structure, CLAUDE.md, skills, and workflow
  conventions were overhauled to align with AI-first development principles:
  sprint discipline, inline provenance comments (`# CHANGED:` / `# WHY:` /
  `# BUG FIX:`), skill-driven automation (`/run-tests`, `/build-exe`), and
  session-initialization hooks.  No functional changes were made as part of
  this overhaul.

### Changed

- **Save As… placeholder filename** — the initial filename shown in the
  *Save As…* dialog now reflects the user's configured Filename Template
  (from Screenshot Settings) instead of the old hardcoded
  `screenshot_YYYYMMDD_HHMMSS` boilerplate.
  - Time-based tokens (`{date}`, `{time}`, `{ts}`, `{year}`, `{month}`,
    `{day}`) and `{width}` are resolved to real values at dialog-open time.
  - Source-dependent tokens (`{name}`, `{domain}`, `{title}`) and the
    collision-dependent token (`{seq}`) are shown as their bare token-name
    (e.g. `name`, `domain`) since they require the page to load first.
  - Example with default template `{name}_{date}_{time}`:
    dialog now shows `name_2026-03-31_14-30-00.png` instead of
    `screenshot_20260331_143000.png`.

---

## [2.0.0] - 2026-03-28

### Added
- **Named viewport presets in GUI** — dropdown now shows descriptive labels:
  HD (1280), HD+ (1440), Full HD (1920), QHD (2560), 4K (3840).
- **"Custom..." viewport option** — selecting it opens a dialog where any
  width between 320 and 7680 px can be entered. The custom value persists
  across sessions in `~/.htmlrf_config.json`.
- **Arbitrary CLI viewport widths** — `--width` / `-w` now accepts any
  integer in the 320–7680 range instead of being locked to four presets.
  Out-of-range values produce a clear error message.
- **4K (3840 px) preset** — added to both the GUI dropdown and the
  suggested widths in the README.
- 10 new unit tests covering CLI range validation, preset mapping
  integrity, custom-width forwarding through Playwright, and bounds
  constants.

### Changed
- GUI title bar updated from v1.0 to v2.0.
- Viewport dropdown widened from 90 px to 150 px to accommodate the
  longer preset labels.
- Viewport selection and last-used custom width are now saved to config
  (`viewport_preset`, `custom_viewport` keys).

### Fixed
- **CTkOptionMenu construction callback** — added a `_ui_ready` guard so
  the `command=` callback is not fired during widget construction, which
  could open a blocking dialog before the main loop starts.

---

## [1.0.0] - 2026-03-26

Initial public release.

### Features
- Full-page PNG screenshots of any URL or local HTML file via headless
  Chromium (Playwright).
- Dual interface: CLI (`htmlrf`) and GUI (`htmlrf-gui`) with
  drag-and-drop, paste-HTML tab, and URL entry.
- Configurable viewport widths (1280, 1440, 1920, 2560 px).
- 2x Retina device scale factor for crisp output.
- Filename template engine with variables: `{name}`, `{domain}`,
  `{date}`, `{time}`, `{ts}`, `{title}`, `{seq}`, `{width}`.
- Auto-increment `{seq}` collision avoidance.
- HTTPS auto-upgrade for bare hostnames, with HTTP fallback prompt.
- Persistent settings (output directory, filename template) via
  `~/.htmlrf_config.json`.
- Cross-platform support: Windows, macOS, Linux (fonts, folder opener,
  dark-mode detection via `darkdetect`).
- Startup Chromium health check with user-friendly warnings.
- Modern PEP 621 packaging with `hatchling` build backend and `src/`
  layout.
