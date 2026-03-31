#!/usr/bin/env python3
"""
screenshot.py — Full-page HTML/URL to PNG or PDF renderer (CLI entry point).

How to test:
    python screenshot.py https://example.com -o out.png
    python screenshot.py "C:\\path\\to\\file.html" -o out.png --width 1440
    python screenshot.py https://example.com -o out.pdf --format Letter

Core functions take_full_screenshot() and take_full_pdf() are imported by the GUI.
"""

import argparse
import logging
import os
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# CHANGED: use module-level logger instead of bare print()
# WHY: print() is silently swallowed in --windowed PyInstaller builds; logging
#      lets callers (GUI, tests) route messages to their own handlers.
_log = logging.getLogger(__name__)


def _resolve_url(raw: str) -> tuple[str, bool]:
    """
    Normalise a user-supplied source string.

    Returns:
        (resolved, was_upgraded) where was_upgraded is True when https:// was
        prepended automatically.  Local file paths and already-schemed strings
        pass through unchanged.
    """
    if os.path.isfile(raw):
        return raw, False
    if raw.startswith(("http://", "https://", "file://")):
        return raw, False
    return f"https://{raw}", True


# CHANGED: extracted shared navigation/settle logic into _prepare_page()
# WHY: take_full_screenshot and take_full_pdf use identical page-load choreography;
#      a single helper keeps both functions in sync without code duplication.
def _prepare_page(page, input_source: str, timeout_ms: int) -> str:
    """
    Navigate to input_source, scroll to bottom, settle, and return the page title.

    Mutates `page` in place.  Called by both take_full_screenshot and take_full_pdf
    so that the browser setup and output-capture logic remain the only differences
    between the two functions.

    Args:
        page:         A Playwright Page object already attached to a browser context.
        input_source: A fully-resolved URL or local file path (already normalised by
                      _resolve_url — bare hostnames must be upgraded before calling).
        timeout_ms:   Navigation timeout in milliseconds.

    Returns:
        page_title — empty string when the page has no <title> tag.
    """
    try:
        if os.path.isfile(input_source) and input_source.lower().endswith(
            (".html", ".htm")
        ):
            # BUG FIX: windows-file-uri-missing-slash
            # Fix: replaced f"file://{path.as_posix()}" with Path.as_uri()
            file_url = Path(input_source).resolve().as_uri()
            _log.info("Loading local file: %s", file_url)
            page.goto(file_url, wait_until="networkidle", timeout=timeout_ms)
        else:
            _log.info("Loading URL: %s", input_source)
            page.goto(input_source, wait_until="networkidle", timeout=timeout_ms)
    except PlaywrightTimeout:
        _log.warning("Page load timed out; capturing what rendered so far")

    # Scroll to the bottom so lazy-loaded images and JS finalise layout.
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    try:
        page.wait_for_function(
            "document.readyState === 'complete'", timeout=300
        )
    except PlaywrightTimeout:
        pass  # page already timed out once; capture whatever we have

    return page.title() or ""


def take_full_screenshot(
    input_source: str,
    output_png: str | Callable[[str], str],
    viewport_width: int = 1920,
    *,
    timeout_ms: int = 30_000,
) -> tuple[str, str]:
    """
    Render input_source to a full-page PNG using headless Chromium.

    Args:
        input_source:   A URL (http/https) or absolute path to a local .html file.
                        Bare hostnames (e.g. "example.com") are auto-upgraded to
                        https:// via _resolve_url.
        output_png:     Destination PNG file path, OR a callable(page_title) -> path
                        so the caller can embed the page title in the filename.
        viewport_width: Browser viewport width in pixels (height is fixed at 1080;
                        Playwright expands it for full-page capture).
        timeout_ms:     Navigation timeout in milliseconds (default 30 000).
                        Keyword-only to prevent accidental positional misuse.

    Returns:
        (page_title, final_output_path)
        page_title is '' when the page has no <title> tag.

    Raises:
        Any Playwright exception propagates to the caller (GUI catches them).
    """
    # Normalise bare hostnames at the CLI entry point as well.
    input_source, _ = _resolve_url(input_source)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": 1080},
            device_scale_factor=2.0,   # Retina-quality output (2× pixel density)
        )
        page = context.new_page()

        # CHANGED: replaced inline navigation/settle block with _prepare_page()
        # WHY: identical logic now shared with take_full_pdf via the shared helper.
        page_title = _prepare_page(page, input_source, timeout_ms)
        if callable(output_png):
            final_path = output_png(page_title)
        else:
            final_path = output_png

        Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=final_path, full_page=True)
        _log.info("Screenshot saved: %s", final_path)

        browser.close()

    return page_title, final_path


# CHANGED: new PDF export function sharing _prepare_page() with take_full_screenshot
# WHY: PDF rendering reuses identical browser/page setup; only the output call differs.
def take_full_pdf(
    input_source: str,
    output_pdf: str | Callable[[str], str],
    viewport_width: int = 1920,
    *,
    timeout_ms: int = 30_000,
    pdf_format: str = "A4",
) -> tuple[str, str]:
    """
    Render input_source to a full-page PDF using headless Chromium.

    Args:
        input_source:   A URL (http/https) or absolute path to a local .html file.
                        Bare hostnames are auto-upgraded to https:// via _resolve_url.
        output_pdf:     Destination PDF file path, OR a callable(page_title) -> path
                        for title-based naming (same pattern as take_full_screenshot).
        viewport_width: Browser viewport width in pixels (default 1920).
        timeout_ms:     Navigation timeout in milliseconds (default 30 000).
        pdf_format:     PDF paper size — "A4", "Letter", "Legal", or "Tabloid".
                        Named pdf_format to avoid shadowing the Python builtin `format`.

    Returns:
        (page_title, final_output_path)

    Raises:
        Any Playwright exception propagates to the caller (GUI catches them).
    """
    input_source, _ = _resolve_url(input_source)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": 1080},
            # CHANGED: no device_scale_factor for PDF
            # WHY: device_scale_factor affects raster rendering only; PDF output
            #      is vector-based so this setting has no effect on the result.
        )
        page = context.new_page()

        page_title = _prepare_page(page, input_source, timeout_ms)

        # CHANGED: emulate screen media before pdf() call
        # WHY: Playwright defaults to @media print, which can suppress backgrounds,
        #      alter fonts, or collapse layout elements that look correct in a PNG.
        #      emulate_media("screen") makes the PDF visually match the screenshot.
        page.emulate_media(media="screen")

        if callable(output_pdf):
            final_path = output_pdf(page_title)
        else:
            final_path = output_pdf

        Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        page.pdf(
            path=final_path,
            format=pdf_format,
            print_background=True,
            prefer_css_page_size=False,
        )
        _log.info("PDF saved: %s", final_path)

        browser.close()

    return page_title, final_path


def main() -> None:
    # CHANGED: configure logging for the CLI so _log calls produce visible output
    # WHY: without basicConfig the root logger has no handlers and all messages
    #      are silently discarded when running as a CLI script.
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="htmlrf",
        description="Full-page HTML/URL → PNG or PDF renderer (scroll-captured)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  htmlrf https://example.com -o example.png\n"
            "  htmlrf report.html -o report.png --width 1440\n"
            "  htmlrf https://example.com -o report.pdf\n"
            "  htmlrf report.html -o report.pdf --format Letter\n"
        ),
    )
    parser.add_argument(
        "input",
        help="URL (http/https) or path to a local .html / .htm file",
    )
    parser.add_argument(
        "-o", "--output",
        default="screenshot.png",
        help="Output PNG path (default: screenshot.png in current directory)",
    )
    # CHANGED: accept any integer width instead of a fixed choices list
    # WHY: v2.0 — users need arbitrary widths (e.g. 1600, 3840) for custom viewports
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=1920,
        metavar="PX",
        help="Viewport width in pixels, 320–7680 (default: 1920)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30_000,
        metavar="MS",
        help="Navigation timeout in milliseconds (default: 30000)",
    )
    # CHANGED: add --format flag and auto-detect output type from extension
    # WHY: "htmlrf page.html -o report.pdf" should just work; extension-based
    #      dispatch is the least-surprise CLI UX. --format overrides PDF paper size.
    parser.add_argument(
        "--format",
        default=None,
        choices=["A4", "Letter", "Legal", "Tabloid"],
        metavar="SIZE",
        help=(
            "PDF paper size when output is .pdf: A4 (default), Letter, Legal, Tabloid. "
            "Ignored for PNG output."
        ),
    )
    args = parser.parse_args()

    if not (320 <= args.width <= 7680):
        parser.error(f"--width must be between 320 and 7680 (got {args.width})")

    if Path(args.output).suffix.lower() == ".pdf":
        take_full_pdf(
            args.input, args.output, args.width,
            timeout_ms=args.timeout,
            pdf_format=args.format or "A4",
        )
    else:
        take_full_screenshot(args.input, args.output, args.width, timeout_ms=args.timeout)


if __name__ == "__main__":
    main()
