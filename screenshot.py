#!/usr/bin/env python3
"""
screenshot.py — Full-page HTML/URL to PNG screenshotter (CLI entry point).

How to test:
    python screenshot.py https://example.com -o out.png
    python screenshot.py "C:\\path\\to\\file.html" -o out.png --width 1440

Core function take_full_screenshot() is imported by the GUI as well.
"""

import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def take_full_screenshot(
    input_source: str,
    output_png: str,
    viewport_width: int = 1920,
) -> None:
    """
    Render input_source to a full-page PNG using headless Chromium.

    Args:
        input_source: A URL (http/https) or absolute path to a local .html file.
        output_png:   Destination PNG file path (parent directories are created).
        viewport_width: Browser viewport width in pixels (height is fixed at 1080
                        — Playwright expands it automatically for full-page capture).

    Raises:
        Any Playwright exception propagates to the caller (GUI catches them).
    """
    Path(output_png).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Headless Chromium — identical rendering engine to Google Chrome.
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
                # Local file → convert to file:// URL so Playwright can load it.
                file_url = f"file://{Path(input_source).resolve().as_posix()}"
                print(f"→ Loading local file: {file_url}")
                page.goto(file_url, wait_until="networkidle", timeout=30_000)
            else:
                print(f"→ Loading URL: {input_source}")
                page.goto(input_source, wait_until="networkidle", timeout=30_000)
        except PlaywrightTimeout:
            # Partial loads are still worth screenshotting — warn but continue.
            print("⚠  Page load timed out; capturing what rendered so far…")

        # Scroll to the bottom so lazy-loaded images and JS finalise layout.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)  # 500 ms settle time for final JS reflows

        # full_page=True captures the entire scrollable document height.
        page.screenshot(path=output_png, full_page=True)
        print(f"✓ Screenshot saved: {output_png}")

        browser.close()


def main() -> None:
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
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=1920,
        choices=[1280, 1440, 1920, 2560],
        metavar="{1280,1440,1920,2560}",
        help="Viewport width in pixels (default: 1920)",
    )
    args = parser.parse_args()
    take_full_screenshot(args.input, args.output, args.width)


if __name__ == "__main__":
    main()
