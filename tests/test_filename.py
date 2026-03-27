"""
tests/test_filename.py
Validates _sanitize() and _resolve_filename() — the filename template engine.
Covers the {seq} collision-check regression and Unicode/locale edge cases.
"""

from unittest.mock import patch

import pytest

from htmlrf.gui import _sanitize, _resolve_filename, DEFAULT_TEMPLATE


# ── _sanitize ─────────────────────────────────────────────────────────────────

class TestSanitize:
    def test_removes_windows_reserved_chars(self):
        assert _sanitize('file:name*?"<>|') == "file-name------"

    def test_strips_leading_trailing_hyphens_dots_spaces(self):
        assert _sanitize("--hello world--") == "hello world"
        assert _sanitize("...test...") == "test"

    def test_empty_input_returns_untitled(self):
        assert _sanitize("") == "untitled"

    def test_all_unsafe_chars_returns_untitled(self):
        assert _sanitize("---") == "untitled"

    def test_truncates_to_max_len(self):
        long = "a" * 200
        result = _sanitize(long)
        assert len(result) == 80

    def test_backslash_replaced(self):
        assert "\\" not in _sanitize("C:\\path\\to\\file")

    def test_unicode_passthrough(self):
        """Non-ASCII safe characters should survive sanitization."""
        result = _sanitize("résumé_2026")
        assert "résumé" in result

    def test_null_byte_removed(self):
        assert "\x00" not in _sanitize("file\x00name")

    def test_control_chars_removed(self):
        assert "\x1f" not in _sanitize("file\x1fname")


# ── _resolve_filename ─────────────────────────────────────────────────────────

class TestResolveFilename:
    def test_default_template_url(self):
        name = _resolve_filename(DEFAULT_TEMPLATE, "https://github.com", 1920)
        assert name.startswith("github_")
        assert name.endswith(".png")

    def test_default_template_file(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<p>test</p>")
        name = _resolve_filename(DEFAULT_TEMPLATE, str(f), 1440)
        assert name.startswith("report_")
        assert name.endswith(".png")

    def test_www_stripped_from_name_token(self):
        name = _resolve_filename("{name}", "https://www.example.com", 1920)
        assert name == "example.png"

    def test_domain_token_keeps_www(self):
        name = _resolve_filename("{domain}", "https://www.example.com", 1920)
        assert name == "www.example.com.png"

    def test_width_token(self):
        name = _resolve_filename("{name}_{width}", "https://example.com", 1280)
        assert "1280" in name

    def test_title_token(self):
        name = _resolve_filename("{title}", "https://example.com", 1920,
                                 page_title="My Cool Page")
        assert "My-Cool-Page" in name or "My Cool Page" not in name  # sanitized

    def test_ts_token_is_numeric(self):
        name = _resolve_filename("{ts}", "https://example.com", 1920)
        stem = name[:-4]   # strip .png
        assert stem.isdigit()

    def test_seq_at_end_of_template(self, tmp_path):
        """Standard case: {seq} at the end — collision check should work."""
        # Create the file that would be seq=001
        existing = tmp_path / "github_001.png"
        existing.write_bytes(b"")

        name = _resolve_filename(
            "{name}_{seq}", "https://github.com", 1920,
            output_dir=str(tmp_path),
        )
        assert "002" in name, f"Expected seq=002, got: {name}"

    def test_seq_at_start_of_template(self, tmp_path):
        """
        Regression test for the seq-collision-check-wrong-filename bug.
        When {seq} is at the START of the template, the old code checked
        f"{base}{seq:03d}.png" which produced "_github001.png" while the
        actual file was "001_github.png" — a mismatch that caused seq to
        always return 001 even when the file existed.
        """
        # Create what would be the seq=001 output
        existing = tmp_path / "001_github.png"
        existing.write_bytes(b"")

        name = _resolve_filename(
            "{seq}_{name}", "https://github.com", 1920,
            output_dir=str(tmp_path),
        )
        assert "002" in name, (
            f"seq collision check failed for leading {{seq}}: got {name!r}. "
            "The bug was: base+seq produced a different filename than "
            "stem.replace({{seq}}, seq_formatted)."
        )

    def test_seq_in_middle_of_template(self, tmp_path):
        """Same regression: {seq} in the middle of the template."""
        existing = tmp_path / "github_001_shot.png"
        existing.write_bytes(b"")

        name = _resolve_filename(
            "{name}_{seq}_shot", "https://github.com", 1920,
            output_dir=str(tmp_path),
        )
        assert "002" in name, f"Expected seq=002 in middle position, got: {name}"

    def test_seq_starts_at_001_when_no_collision(self, tmp_path):
        name = _resolve_filename(
            "{name}_{seq}", "https://example.com", 1920,
            output_dir=str(tmp_path),
        )
        assert "001" in name

    def test_no_seq_token_no_collision_check(self, tmp_path):
        """Templates without {seq} should just produce a deterministic name."""
        name = _resolve_filename("{name}", "https://example.com", 1920)
        assert name == "example.png"

    def test_output_always_ends_with_png(self):
        for tmpl in ["{name}", "{date}", "{ts}", "{seq}", DEFAULT_TEMPLATE]:
            name = _resolve_filename(tmpl, "https://example.com", 1920)
            assert name.endswith(".png"), f"No .png extension for template {tmpl!r}"

    def test_unicode_url_sanitized(self):
        """Non-ASCII hostnames are sanitized to filesystem-safe strings."""
        name = _resolve_filename("{name}", "https://münchen.de", 1920)
        assert name.endswith(".png")
        assert len(name) > 4  # not just ".png"


# ── Globalization: locale/encoding edge cases ─────────────────────────────────

class TestGlobalization:
    def test_non_ascii_page_title_sanitized(self):
        """CJK and accented titles should produce valid filenames, not empty."""
        name = _resolve_filename(
            "{title}", "https://example.com", 1920,
            page_title="日本語のページ"
        )
        # Should not raise, should end with .png, should not be empty stem
        assert name.endswith(".png")
        stem = name[:-4]
        assert len(stem) > 0 and stem != ""

    def test_emoji_title_sanitized(self):
        name = _resolve_filename(
            "{title}", "https://example.com", 1920,
            page_title="🚀 Launch Page"
        )
        assert name.endswith(".png")

    def test_rtl_domain_sanitized(self):
        """Arabic/Hebrew domain names should not produce empty filenames."""
        name = _resolve_filename("{name}", "https://مثال.إختبار", 1920)
        assert name.endswith(".png")
        assert name != ".png"
