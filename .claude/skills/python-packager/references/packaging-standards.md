# Python Packaging Standards Reference

This reference covers the PEP standards, build backend details, advanced packaging topics,
and CI/CD publishing workflows. Read this when the SKILL.md core workflow needs more depth.

## Table of Contents

1. [PEP Standards Map](#pep-standards-map)
2. [Build Backend Deep Dive](#build-backend-deep-dive)
3. [Dynamic Metadata Configuration](#dynamic-metadata-configuration)
4. [Dependency Management: Libraries vs Applications](#dependency-management)
5. [PEP 735 Dependency Groups](#pep-735-dependency-groups)
6. [Namespace Packages (PEP 420)](#namespace-packages)
7. [Plugin Discovery via Entry Points](#plugin-discovery)
8. [Editable Installs (PEP 660)](#editable-installs)
9. [Binary Extensions](#binary-extensions)
10. [Trusted Publishing CI/CD](#trusted-publishing)
11. [PEP 639 Licensing](#pep-639-licensing)
12. [Version Specifiers (PEP 440)](#version-specifiers)
13. [Security and Deprecated Tooling](#security-and-deprecations)

---

## PEP Standards Map

These are the governing standards. When in doubt, the PEP is the authority.

| PEP | What it standardizes |
|---|---|
| **PEP 440** | Version identification and dependency specifiers (`>=`, `~=`, `!=`, etc.) |
| **PEP 517/518** | `[build-system]` table in `pyproject.toml` — decouples frontend from backend |
| **PEP 621** | `[project]` table — standardized, declarative core metadata |
| **PEP 639** | Modern licensing via SPDX expressions and `license-files` globs |
| **PEP 660** | Wheel-based editable installs (`pip install -e .`) |
| **PEP 735** | `[dependency-groups]` for non-production deps (test, lint, docs) |
| **PEP 751** | `pylock.toml` — interoperable lockfile specification |
| **PEP 772** | Packaging Governance Council (organizational, not technical) |

---

## Build Backend Deep Dive

### Hatchling (recommended default)

```toml
[build-system]
requires = ["hatchling >= 1.26"]
build-backend = "hatchling.build"
```

Strengths: dynamic versioning from source files, plugin ecosystem, environment management
via `hatch`. Supports `[tool.hatch.build]` for fine-grained inclusion/exclusion.

### Setuptools (legacy modernization)

```toml
[build-system]
requires = ["setuptools >= 77.0.3", "wheel"]
build-backend = "setuptools.build_meta"
```

Use when: modernizing an existing `setup.py` project, basic C extensions, complex
programmatic build requirements. Supports `[tool.setuptools.packages.find]` for
auto-discovery and `[tool.setuptools.dynamic]` for version extraction.

### Flit-core (minimal)

```toml
[build-system]
requires = ["flit_core >= 3.12.0, < 4"]
build-backend = "flit_core.buildapi"
```

Enforces strict simplicity. No plugins, no dynamic metadata beyond version from
`__version__`. Best for single-module packages.

### PDM-Backend

```toml
[build-system]
requires = ["pdm-backend >= 2.4.0"]
build-backend = "pdm.backend"
```

Modern, PEP 621-compliant. Pairs with PDM workflow manager.

### uv-build

```toml
[build-system]
requires = ["uv_build >= 0.10.10, < 0.11.0"]
build-backend = "uv_build"
```

For projects already in the uv ecosystem. Fast, Rust-powered.

### Meson-Python (C/C++/Fortran)

```toml
[build-system]
requires = ["meson-python >= 0.13.0", "meson >= 1.0.0"]
build-backend = "mesonpy"
```

Bridges the Meson build system to Python wheel format. Use for complex native extensions.

### Maturin (Rust)

```toml
[build-system]
requires = ["maturin >= 1.0, < 2.0"]
build-backend = "maturin"
```

Definitive backend for Rust extensions via PyO3/Cargo.

---

## Dynamic Metadata Configuration

When a field (typically `version`) is computed at build time rather than hardcoded:

1. Declare it in the `dynamic` array: `dynamic = ["version"]`
2. Configure the backend-specific extraction in `[tool.*]`

**Hatchling** — reads from a source file:
```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/my_package/__about__.py"
```

Where `__about__.py` contains: `__version__ = "1.2.3"`

**Setuptools** — reads an attribute at build time:
```toml
[project]
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "my_package.__version__"}
```

The `dynamic` array and the `[tool.*]` configuration must be perfectly synchronized.
Forgetting to list a field in `dynamic` while configuring it in `[tool.*]` causes
PEP 621 schema validation failures.

---

## Dependency Management

### Libraries: Abstract Dependencies

Libraries specify broad ranges so pip can resolve conflicts across all packages in
the user's environment:

```toml
dependencies = [
    "requests >= 2.25",
    "click >= 8.0, < 9.0",
    "numpy >= 1.21",
]
```

Never pin exact versions in a library — this forces every downstream consumer to use
that exact version, creating dependency conflicts.

### Applications: Concrete Dependencies

Applications need reproducible deployments. Use a workflow tool to generate lockfiles:

- **uv**: `uv lock` → `uv.lock`
- **PDM**: `pdm lock` → `pdm.lock`
- **pip-tools**: `pip-compile` → `requirements.txt` (with hashes)
- **Poetry**: `poetry lock` → `poetry.lock`
- **Standard**: PEP 751 `pylock.toml` (emerging standard)

The lockfile pins every transitive dependency with exact versions and optionally
cryptographic hashes, ensuring identical environments across dev/staging/production.

### Optional Dependencies (Extras)

For features that aren't always needed:

```toml
[project.optional-dependencies]
gui = ["customtkinter >= 5.0"]
export = ["pandas >= 2.0", "openpyxl >= 3.1"]
```

Users install with: `pip install my-package[gui]` or `pip install my-package[gui,export]`

---

## PEP 735 Dependency Groups

Development-only dependencies (testing, linting, docs) should NOT go in
`[project.optional-dependencies]` because those get published in package metadata.
PEP 735 provides `[dependency-groups]`:

```toml
[dependency-groups]
test = ["pytest >= 8.0", "pytest-cov >= 5.0"]
lint = ["ruff >= 0.4", "mypy >= 1.10"]
docs = ["sphinx >= 7.0", "sphinx-rtd-theme >= 2.0"]
dev = [{include-group = "test"}, {include-group = "lint"}]
```

Build backends must NOT include these in distribution metadata — they're purely for
development workflow tooling.

---

## Namespace Packages

Namespace packages let multiple distributions share a top-level import path:

```
company-telemetry/src/company/telemetry/...
company-database/src/company/database/...
```

Critical rule: the shared namespace directory (`company/`) must have **NO `__init__.py`**.
An `__init__.py` tells Python it's a regular package, breaking namespace discovery.

Setuptools configuration for namespace packages:
```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["company.telemetry*"]
```

---

## Plugin Discovery

For plugin architectures (like pytest plugins, Sphinx extensions):

**Plugin publisher** declares an entry point:
```toml
[project.entry-points."myapp.plugins"]
awesome-feature = "awesome_plugin.core:AwesomePlugin"
```

**Host application** discovers plugins at runtime:
```python
from importlib.metadata import entry_points

plugins = entry_points(group="myapp.plugins")
for plugin in plugins:
    cls = plugin.load()
    # cls is now the AwesomePlugin class
```

---

## Editable Installs

PEP 660 standardizes editable installs via the wheel format:

```bash
pip install -e .
```

This creates import hooks so Python loads code directly from your source tree.
Changes to `.py` files take effect immediately without reinstalling.

Setuptools offers strict mode (`--config-settings editable_mode=strict`) which
hides newly added files until reinstall — useful for catching missing files in
your distribution manifest before publishing.

---

## Binary Extensions

### C/C++ with Meson-Python

Requires a `meson.build` file alongside `pyproject.toml`. The Meson build system
handles compilation, and `meson-python` bridges the output into a wheel.

### Rust with Maturin

Requires a `Cargo.toml` alongside `pyproject.toml`. Maturin compiles the Rust code
via Cargo and packages the resulting `.so`/`.pyd` into a wheel.

### Cross-Platform Wheels

For binary extensions, use **cibuildwheel** in CI to build wheels for all platforms:
- manylinux (various glibc versions)
- macOS (x86_64 and arm64)
- Windows (amd64)

The sdist serves as fallback for platforms without a pre-built wheel.

---

## Trusted Publishing

Modern PyPI publishing uses OIDC (OpenID Connect) instead of API tokens.

### Setup (one-time)

1. On PyPI, go to your project → Publishing → Add a new publisher
2. Enter: GitHub repo owner, repo name, workflow filename, environment name

### GitHub Actions Workflow

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

permissions:
  id-token: write    # Required for OIDC token acquisition

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: pip install build
      - run: python -m build

      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi     # Must match what you registered on PyPI
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - uses: pypa/gh-action-pypi-publish@release/v1
        # No secrets needed — OIDC handles authentication
        # Automatically generates PEP 740 provenance attestations
```

Always test on TestPyPI first by adding `repository-url: https://test.pypi.org/legacy/`
to the publish action.

---

## PEP 639 Licensing

Modern licensing uses SPDX expressions:

```toml
license = {text = "MIT"}
license-files = ["LICENSE*", "NOTICE*"]
```

For dual licensing: `license = {text = "MIT OR Apache-2.0"}`

Do NOT use the old `License ::` classifiers — they're deprecated.

---

## Version Specifiers (PEP 440)

| Specifier | Meaning | Example |
|---|---|---|
| `>=` | Minimum version | `requests >= 2.25` |
| `~=` | Compatible release | `~= 1.4.2` means `>= 1.4.2, < 1.5.0` |
| `!=` | Exclude version | `!= 1.5.0` |
| `<` | Upper bound | `< 2.0` |
| `==` | Exact pin | `== 1.4.2` (avoid in libraries) |

Environment markers for conditional deps:
```toml
dependencies = [
    "pywin32 >= 300; os_name == 'nt'",
    "uvloop >= 0.19; sys_platform == 'linux'",
]
```

---

## Security and Deprecations

### Absolutely Prohibited (never generate these)

- `python setup.py install`
- `python setup.py develop`
- `python setup.py sdist bdist_wheel`
- `distutils` imports
- `easy_install`
- `setup_requires` in `setup.py`
- Long-lived PyPI API tokens in CI (use Trusted Publishing)

### Security Best Practices

- Use `permissions: id-token: write` for OIDC in GitHub Actions
- Pin CI action versions with SHA hashes, not tags
- Upload to TestPyPI before production PyPI
- Enable 2FA on PyPI account
- Use `--require-hashes` with pip for supply-chain security in deployments
