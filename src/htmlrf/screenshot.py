#!/usr/bin/env python3
"""
screenshot.py — Full-page HTML/URL to PNG screenshotter (CLI entry point).

How to test:
    python screenshot.py https://example.com -o out.png
    python screenshot.py "C:\\path\\to\\file.html" -o out.png --width 1440

Core function take_full_screenshot() is imported by the GUI as well.
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

        try:
            if os.path.isfile(input_source) and input_source.lower().endswith(
                (".html", ".htm")
            ):
                # CHANGED: use Path.as_uri() instead of f"file://{path.as_posix()}"
                # WHY: BUG FIX — on Windows, as_posix() gives "C:/path/file.html" so
                #      the manual f-string produced "file://C:/..." (missing leading /)
                #      while the correct URI is "file:///C:/...".  Path.as_uri() is
                #      platform-correct on all OSes.
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
        # CHANGED: replace unconditional 500 ms sleep with a shorter settle wait
        # after confirming readyState, falling back to a fixed 300 ms cap.
        # WHY: fast local pages paid the full 500 ms penalty unconditionally;
        #      checking readyState gives an early exit on already-settled pages.
        try:
            page.wait_for_function(
                "document.readyState === 'complete'", timeout=300
            )
        except PlaywrightTimeout:
            pass  # page already timed out once; capture whatever we have

        # Resolve the output path — may depend on the page title.
        page_title = page.title() or ""
        if callable(output_png):
            final_path = output_png(page_title)
        else:
            final_path = output_png

        Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=final_path, full_page=True)
        _log.info("Screenshot saved: %s", final_path)

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
        prog="screenshot",
        description="Full-page HTML/URL → PNG screenshot utility (scroll-captured)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  screenshot.py https://example.com -o example.png\n"
            "  screenshot.py report.html -o report.png --width 1440\n"
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
    args = parser.parse_args()

    if not (320 <= args.width <= 7680):
        parser.error(f"--width must be between 320 and 7680 (got {args.width})")

    take_full_screenshot(args.input, args.output, args.width, timeout_ms=args.timeout)


if __name__ == "__main__":
    main()
