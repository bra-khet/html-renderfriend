"""
tests/test_gui.py
Smoke tests for UX-critical GUI invariants that do NOT require a display.

Tests are skipped automatically when no display is available (CI without Xvfb,
headless Windows Server, etc.) using the `display_required` fixture.

Run locally:  pytest tests/test_gui.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures & helpers ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def display_available() -> bool:
    """True when a Tk display is reachable."""
    try:
        import tkinter as tk
        r = tk.Tk()
        r.destroy()
        return True
    except Exception:
        return False


@pytest.fixture
def skip_no_display(display_available):
    if not display_available:
        pytest.skip("No display available — Tkinter smoke tests skipped")


# ── _default_output_dir ───────────────────────────────────────────────────────

class TestDefaultOutputDir:
    """Runs without a display — pure path logic."""

    def test_returns_path_object(self):
        from htmlrf_gui import _default_output_dir
        result = _default_output_dir()
        assert isinstance(result, Path)

    def test_returns_existing_directory(self):
        from htmlrf_gui import _default_output_dir
        result = _default_output_dir()
        assert result.is_dir(), f"_default_output_dir() returned non-existent dir: {result}"

    def test_fallback_when_desktop_absent(self, tmp_path, monkeypatch):
        """When Desktop does not exist, should fall back to home."""
        import htmlrf_gui
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        # No Desktop subfolder — only home exists
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        result = htmlrf_gui._default_output_dir()
        assert result == fake_home

    def test_uses_desktop_when_it_exists(self, tmp_path, monkeypatch):
        import htmlrf_gui
        fake_home = tmp_path / "fakehome"
        desktop   = fake_home / "Desktop"
        desktop.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        result = htmlrf_gui._default_output_dir()
        assert result == desktop


# ── _open_folder (platform dispatch) ─────────────────────────────────────────

class TestOpenFolder:
    """Runs without a display."""

    def test_windows_uses_startfile(self, tmp_path, monkeypatch):
        import htmlrf_gui
        monkeypatch.setattr(sys, "platform", "win32")
        calls = []
        monkeypatch.setattr(htmlrf_gui.os, "startfile", lambda p: calls.append(p),
                            raising=False)
        f = tmp_path / "out.png"
        htmlrf_gui._open_folder(f)
        assert calls == [str(tmp_path)]

    def test_macos_uses_open(self, tmp_path, monkeypatch):
        import htmlrf_gui
        monkeypatch.setattr(sys, "platform", "darwin")
        captured = []
        monkeypatch.setattr(
            htmlrf_gui.subprocess, "Popen",
            lambda args: captured.append(args)
        )
        f = tmp_path / "out.png"
        htmlrf_gui._open_folder(f)
        assert captured == [["open", str(tmp_path)]]

    def test_linux_uses_xdg_open(self, tmp_path, monkeypatch):
        import htmlrf_gui
        monkeypatch.setattr(sys, "platform", "linux")
        captured = []
        monkeypatch.setattr(
            htmlrf_gui.subprocess, "Popen",
            lambda args: captured.append(args)
        )
        f = tmp_path / "out.png"
        htmlrf_gui._open_folder(f)
        assert captured == [["xdg-open", str(tmp_path)]]


# ── SettingsDialog.result property ───────────────────────────────────────────

class TestSettingsDialogResult:
    """Validates the public result property without instantiating the dialog."""

    def test_result_property_exists(self):
        from htmlrf_gui import SettingsDialog
        assert hasattr(SettingsDialog, "result"), (
            "SettingsDialog must expose a public 'result' property"
        )

    def test_result_property_is_property(self):
        from htmlrf_gui import SettingsDialog
        assert isinstance(
            SettingsDialog.__dict__["result"], property
        ), "'result' must be a @property, not a plain attribute"


# ── App smoke test (display required) ────────────────────────────────────────

class TestAppSmoke:
    def test_app_instantiates_without_error(self, skip_no_display):
        """
        Verifies the app constructs without raising.  The startup health-check
        background thread is mocked to avoid a real Playwright call.
        """
        import threading
        from unittest.mock import patch

        started_threads: list = []
        original_start = threading.Thread.start

        def mock_start(self_thread):
            # Skip the daemon startup-health-check thread but allow others
            if getattr(self_thread, "_target", None) and \
               getattr(self_thread._target, "__name__", "") == "_startup_health_check":
                return
            original_start(self_thread)

        with patch.object(threading.Thread, "start", mock_start):
            import htmlrf_gui
            app = htmlrf_gui.HTMLRenderFriendApp()
            app.after(0, app.quit)   # schedule immediate quit
            app.mainloop()
