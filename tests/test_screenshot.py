"""
tests/test_screenshot.py
Validates core screenshot.py invariants: URL resolution, file-URI construction,
and the public take_full_screenshot() interface.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure the project root is importable when pytest is run from any directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from screenshot import _resolve_url, take_full_screenshot


# ── _resolve_url ───────────────────────────────────────────────────────────────

class TestResolveUrl:
    def test_http_passthrough(self):
        url, upgraded = _resolve_url("http://example.com")
        assert url == "http://example.com"
        assert not upgraded

    def test_https_passthrough(self):
        url, upgraded = _resolve_url("https://example.com/page?q=1")
        assert url == "https://example.com/page?q=1"
        assert not upgraded

    def test_file_scheme_passthrough(self):
        url, upgraded = _resolve_url("file:///tmp/test.html")
        assert url == "file:///tmp/test.html"
        assert not upgraded

    def test_bare_hostname_upgraded_to_https(self):
        url, upgraded = _resolve_url("example.com")
        assert url == "https://example.com"
        assert upgraded

    def test_bare_hostname_with_path_upgraded(self):
        url, upgraded = _resolve_url("example.com/path/page")
        assert url == "https://example.com/path/page"
        assert upgraded

    def test_local_file_passthrough(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<h1>test</h1>")
        url, upgraded = _resolve_url(str(f))
        assert url == str(f)
        assert not upgraded

    def test_nonexistent_path_treated_as_hostname(self):
        """A non-existent path string that looks like a host gets upgraded."""
        url, upgraded = _resolve_url("/nonexistent/path/that/does/not/exist.html")
        # os.path.isfile returns False for non-existent paths → https:// prepended
        assert url.startswith("https://")
        assert upgraded


# ── File URI construction ──────────────────────────────────────────────────────

class TestFileUri:
    """
    Verifies that Path.as_uri() produces the correct three-slash file:/// URI
    on all platforms (regression test for the windows-file-uri-missing-slash bug).
    """

    def test_posix_path_as_uri_has_triple_slash(self, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<p>hi</p>")
        uri = f.resolve().as_uri()
        assert uri.startswith("file:///"), (
            f"Expected triple-slash file URI, got: {uri}"
        )

    def test_uri_does_not_use_as_posix_f_string(self, tmp_path):
        """Regression: the old f'file://{path.as_posix()}' produced file://C:/... on
        Windows (only two slashes).  as_uri() must be used instead."""
        f = tmp_path / "test.html"
        f.write_text("<p>hi</p>")
        bad_uri  = f"file://{f.resolve().as_posix()}"
        good_uri = f.resolve().as_uri()
        # On POSIX they happen to be equal (path starts with /), but on Windows
        # the bad form has only two slashes while good_uri has three.
        assert good_uri.count("/") >= bad_uri.count("/"), (
            "as_uri() should produce at least as many slashes as the f-string form"
        )
        # The canonical check: as_uri() always starts with file:///
        assert good_uri.startswith("file:///")


# ── take_full_screenshot (mocked Playwright) ──────────────────────────────────

class TestTakeFullScreenshot:
    """Uses unittest.mock to avoid spawning a real Chromium process in CI."""

    def _make_playwright_mock(self, page_title: str = "Test Page"):
        """Return a nested mock that satisfies the sync_playwright context manager."""
        mock_page = MagicMock()
        mock_page.title.return_value = page_title
        mock_page.goto.return_value  = None
        mock_page.evaluate.return_value = None
        mock_page.wait_for_function.return_value = None
        mock_page.screenshot.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_browser.close.return_value = None

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        # Support the `with sync_playwright() as p:` context-manager protocol.
        mock_pw.__enter__ = MagicMock(return_value=mock_pw)
        mock_pw.__exit__  = MagicMock(return_value=False)

        mock_sync = MagicMock(return_value=mock_pw)
        return mock_sync, mock_page

    def test_returns_title_and_path(self, tmp_path):
        out = str(tmp_path / "out.png")
        mock_sync, mock_page = self._make_playwright_mock("Hello World")

        with patch("screenshot.sync_playwright", mock_sync):
            title, path = take_full_screenshot("https://example.com", out)

        assert title == "Hello World"
        assert path  == out

    def test_callable_output_receives_page_title(self, tmp_path):
        received = []

        def resolver(title: str) -> str:
            received.append(title)
            return str(tmp_path / f"{title}.png")

        mock_sync, _ = self._make_playwright_mock("My Page")
        with patch("screenshot.sync_playwright", mock_sync):
            title, path = take_full_screenshot("https://example.com", resolver)

        assert received == ["My Page"]
        assert path.endswith("My Page.png")

    def test_local_html_uses_file_uri(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>test</p>")
        out = str(tmp_path / "out.png")

        mock_sync, mock_page = self._make_playwright_mock()
        with patch("screenshot.sync_playwright", mock_sync):
            take_full_screenshot(str(f), out)

        # The goto call should have received a file:/// URI, not a raw path.
        goto_args = mock_page.goto.call_args
        nav_url = goto_args[0][0]
        assert nav_url.startswith("file:///"), (
            f"Expected file:/// URI, got: {nav_url}"
        )

    def test_timeout_parameter_forwarded(self, tmp_path):
        out = str(tmp_path / "out.png")
        mock_sync, mock_page = self._make_playwright_mock()

        with patch("screenshot.sync_playwright", mock_sync):
            take_full_screenshot("https://example.com", out, timeout_ms=5_000)

        goto_kwargs = mock_page.goto.call_args[1]
        assert goto_kwargs.get("timeout") == 5_000

    def test_empty_title_on_untitled_page(self, tmp_path):
        out = str(tmp_path / "out.png")
        mock_sync, mock_page = self._make_playwright_mock("")
        mock_page.title.return_value = ""

        with patch("screenshot.sync_playwright", mock_sync):
            title, _ = take_full_screenshot("https://example.com", out)

        assert title == ""
