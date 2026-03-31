---
name: run-tests
description: "Run the html-renderfriend test suite (all tests, single file, or single class)"
---

# Run Tests

## Steps

1. Confirm the venv is active:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

2. Choose scope:
   - All tests: `pytest`
   - Single file: `pytest tests/test_screenshot.py -v`
   - Single class: `pytest -k "TestResolveFilename"`
   - Single test: `pytest tests/test_filename.py::TestSanitize::test_removes_windows_reserved_chars`

3. For GUI tests (`tests/test_gui.py`): they skip automatically when no display is available
   (controlled by the `display_available` session fixture). No action needed on CI.

4. On failure: check which class failed. The `{seq}` collision regression tests in
   `TestResolveFilename` are the most sensitive — they cover 3 position variants of `{seq}` in a template.
