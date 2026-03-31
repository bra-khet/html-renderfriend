"""
tests/test_screenshot.py
Validates core screenshot.py invariants: URL resolution, file-URI construction,
and the public take_full_screenshot() interface.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from htmlrf.screenshot import _resolve_url, take_full_screenshot, take_full_pdf


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

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            title, path = take_full_screenshot("https://example.com", out)

        assert title == "Hello World"
        assert path  == out

    def test_callable_output_receives_page_title(self, tmp_path):
        received = []

        def resolver(title: str) -> str:
            received.append(title)
            return str(tmp_path / f"{title}.png")

        mock_sync, _ = self._make_playwright_mock("My Page")
        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            title, path = take_full_screenshot("https://example.com", resolver)

        assert received == ["My Page"]
        assert path.endswith("My Page.png")

    def test_local_html_uses_file_uri(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>test</p>")
        out = str(tmp_path / "out.png")

        mock_sync, mock_page = self._make_playwright_mock()
        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
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

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_screenshot("https://example.com", out, timeout_ms=5_000)

        goto_kwargs = mock_page.goto.call_args[1]
        assert goto_kwargs.get("timeout") == 5_000

    def test_empty_title_on_untitled_page(self, tmp_path):
        out = str(tmp_path / "out.png")
        mock_sync, mock_page = self._make_playwright_mock("")
        mock_page.title.return_value = ""

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            title, _ = take_full_screenshot("https://example.com", out)

        assert title == ""

    def test_custom_viewport_width_forwarded(self, tmp_path):
        """v2.0: non-preset widths (e.g. 1600) should work."""
        out = str(tmp_path / "out.png")
        mock_sync, mock_page = self._make_playwright_mock()
        # mock_sync() returns the context-manager mock; __enter__ returns pw
        mock_pw = mock_sync.return_value.__enter__.return_value
        mock_browser = mock_pw.chromium.launch.return_value

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_screenshot("https://example.com", out, 1600)

        # Verify the viewport was set to 1600
        ctx_call = mock_browser.new_context.call_args
        assert ctx_call[1]["viewport"]["width"] == 1600


# ── CLI argument validation ──────────────────────────────────────────────────

class TestCliWidthValidation:
    """v2.0: --width accepts any int in [320, 7680], rejects out-of-range."""

    def test_accepts_non_preset_width(self):
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_take, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-w", "1600"]):
            main()
        mock_take.assert_called_once()
        assert mock_take.call_args[0][2] == 1600

    def test_accepts_boundary_min(self):
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_take, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-w", "320"]):
            main()
        assert mock_take.call_args[0][2] == 320

    def test_accepts_boundary_max(self):
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_take, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-w", "7680"]):
            main()
        assert mock_take.call_args[0][2] == 7680

    def test_rejects_below_minimum(self):
        from htmlrf.screenshot import main
        import sys
        with patch.object(sys, "argv", ["htmlrf", "https://example.com", "-w", "100"]), \
             pytest.raises(SystemExit):
            main()

    def test_rejects_above_maximum(self):
        from htmlrf.screenshot import main
        import sys
        with patch.object(sys, "argv", ["htmlrf", "https://example.com", "-w", "10000"]), \
             pytest.raises(SystemExit):
            main()


# ── take_full_pdf (mocked Playwright) ─────────────────────────────────────────

class TestTakeFullPdf:
    """Mirrors TestTakeFullScreenshot but for take_full_pdf."""

    def _make_playwright_mock(self, page_title: str = "Test Page"):
        """Return a nested mock that satisfies sync_playwright for PDF calls."""
        mock_page = MagicMock()
        mock_page.title.return_value = page_title
        mock_page.goto.return_value  = None
        mock_page.evaluate.return_value = None
        mock_page.wait_for_function.return_value = None
        mock_page.screenshot.return_value = None
        mock_page.pdf.return_value = None
        mock_page.emulate_media.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_browser.close.return_value = None

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_pw.__enter__ = MagicMock(return_value=mock_pw)
        mock_pw.__exit__  = MagicMock(return_value=False)

        mock_sync = MagicMock(return_value=mock_pw)
        return mock_sync, mock_page

    def test_returns_title_and_path(self, tmp_path):
        out = str(tmp_path / "out.pdf")
        mock_sync, mock_page = self._make_playwright_mock("Hello PDF")

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            title, path = take_full_pdf("https://example.com", out)

        assert title == "Hello PDF"
        assert path  == out

    def test_callable_output_receives_page_title(self, tmp_path):
        received = []

        def resolver(title: str) -> str:
            received.append(title)
            return str(tmp_path / f"{title}.pdf")

        mock_sync, _ = self._make_playwright_mock("My PDF Page")
        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            title, path = take_full_pdf("https://example.com", resolver)

        assert received == ["My PDF Page"]
        assert path.endswith("My PDF Page.pdf")

    def test_calls_page_pdf_not_screenshot(self, tmp_path):
        """PDF function must call page.pdf(), never page.screenshot()."""
        out = str(tmp_path / "out.pdf")
        mock_sync, mock_page = self._make_playwright_mock()

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_pdf("https://example.com", out)

        assert mock_page.pdf.called,        "page.pdf() should be called for PDF export"
        assert not mock_page.screenshot.called, "page.screenshot() must NOT be called for PDF export"

    def test_pdf_format_forwarded(self, tmp_path):
        """pdf_format parameter must be passed to page.pdf(format=...)."""
        out = str(tmp_path / "out.pdf")
        mock_sync, mock_page = self._make_playwright_mock()

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_pdf("https://example.com", out, pdf_format="Letter")

        call_kwargs = mock_page.pdf.call_args[1]
        assert call_kwargs.get("format") == "Letter"

    def test_emulate_media_screen_called(self, tmp_path):
        """emulate_media('screen') must be called so PDF matches the PNG visually."""
        out = str(tmp_path / "out.pdf")
        mock_sync, mock_page = self._make_playwright_mock()

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_pdf("https://example.com", out)

        mock_page.emulate_media.assert_called_once_with(media="screen")

    def test_local_html_uses_file_uri(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>test</p>")
        out = str(tmp_path / "out.pdf")

        mock_sync, mock_page = self._make_playwright_mock()
        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_pdf(str(f), out)

        nav_url = mock_page.goto.call_args[0][0]
        assert nav_url.startswith("file:///"), (
            f"Expected file:/// URI, got: {nav_url}"
        )

    def test_default_format_is_a4(self, tmp_path):
        out = str(tmp_path / "out.pdf")
        mock_sync, mock_page = self._make_playwright_mock()

        with patch("htmlrf.screenshot.sync_playwright", mock_sync):
            take_full_pdf("https://example.com", out)

        call_kwargs = mock_page.pdf.call_args[1]
        assert call_kwargs.get("format") == "A4"


# ── CLI format dispatch ────────────────────────────────────────────────────────

class TestCliFormatDispatch:
    """CLI auto-detects PNG vs PDF from output file extension."""

    def test_png_extension_calls_screenshot(self):
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_png, \
             patch("htmlrf.screenshot.take_full_pdf") as mock_pdf, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-o", "out.png"]):
            main()
        mock_png.assert_called_once()
        mock_pdf.assert_not_called()

    def test_pdf_extension_calls_pdf(self):
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_png, \
             patch("htmlrf.screenshot.take_full_pdf") as mock_pdf, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-o", "out.pdf"]):
            main()
        mock_pdf.assert_called_once()
        mock_png.assert_not_called()

    def test_other_extension_defaults_to_screenshot(self):
        """Any extension other than .pdf routes to take_full_screenshot."""
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_png, \
             patch("htmlrf.screenshot.take_full_pdf") as mock_pdf, \
             patch.object(sys, "argv", ["htmlrf", "https://example.com", "-o", "out.jpg"]):
            main()
        mock_png.assert_called_once()
        mock_pdf.assert_not_called()

    def test_format_flag_forwarded_to_pdf(self):
        """--format Letter must reach take_full_pdf as pdf_format='Letter'."""
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_pdf") as mock_pdf, \
             patch.object(sys, "argv", [
                 "htmlrf", "https://example.com", "-o", "out.pdf", "--format", "Letter"
             ]):
            main()
        call_kwargs = mock_pdf.call_args[1]
        assert call_kwargs.get("pdf_format") == "Letter"

    def test_format_flag_ignored_for_png(self):
        """--format A4 with .png output should not cause an error."""
        from htmlrf.screenshot import main
        import sys
        with patch("htmlrf.screenshot.take_full_screenshot") as mock_png, \
             patch("htmlrf.screenshot.take_full_pdf"), \
             patch.object(sys, "argv", [
                 "htmlrf", "https://example.com", "-o", "out.png", "--format", "A4"
             ]):
            main()
        mock_png.assert_called_once()
