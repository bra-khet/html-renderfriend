# pyproject.toml Templates

Copy-paste-ready templates for each backend. Fill in the bracketed placeholders.

## Table of Contents

1. [Pure Python CLI with Hatchling](#hatchling-cli)
2. [Pure Python CLI with Setuptools](#setuptools-cli)
3. [Pure Python Library with Flit-core](#flit-core-library)
4. [GUI Application with Hatchling](#hatchling-gui)
5. [Rust Extension with Maturin](#maturin-rust)
6. [C Extension with Meson-Python](#meson-python-c)
7. [Legacy Migration Stub](#legacy-stub)

---

## Hatchling CLI

The recommended template for most new projects. Uses dynamic versioning from a source file.

**Directory structure:**
```
[project-name]/
├── src/
│   └── [import_name]/
│       ├── __init__.py
│       ├── __about__.py          # contains __version__ = "1.0.0"
│       └── cli.py
├── tests/
│   └── test_cli.py
├── pyproject.toml
├── README.md
└── LICENSE
```

**pyproject.toml:**
```toml
[build-system]
requires = ["hatchling >= 1.26"]
build-backend = "hatchling.build"

[project]
name = "[project-name]"
dynamic = ["version"]
description = "[One-line description]"
readme = "README.md"
requires-python = ">= 3.10"
license = {text = "MIT"}
authors = [{name = "[Author Name]"}]
keywords = ["[keyword1]", "[keyword2]"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "click >= 8.1",
    "rich >= 13.0",
]

[project.scripts]
[cli-command] = "[import_name].cli:main"

[project.urls]
Homepage = "https://github.com/[user]/[project-name]"
Issues = "https://github.com/[user]/[project-name]/issues"

[tool.hatch.version]
path = "src/[import_name]/__about__.py"

[dependency-groups]
dev = ["pytest >= 8.0", "ruff >= 0.4"]
```

**src/[import_name]/__about__.py:**
```python
__version__ = "1.0.0"
```

**src/[import_name]/__init__.py:**
```python
from .__about__ import __version__
```

**src/[import_name]/cli.py:**
```python
import click

@click.command()
@click.version_option()
def main():
    """[Description of what the CLI does]."""
    click.echo("Hello from [project-name]!")

if __name__ == "__main__":
    main()
```

---

## Setuptools CLI

For modernizing existing projects or when the team prefers setuptools.

**pyproject.toml:**
```toml
[build-system]
requires = ["setuptools >= 77.0.3", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "[project-name]"
version = "[version]"
description = "[One-line description]"
readme = "README.md"
requires-python = ">= 3.10"
license = {text = "MIT"}
authors = [{name = "[Author Name]"}]
dependencies = [
    "[dep1] >= [x.y]",
    "[dep2] >= [a.b]",
]

[project.scripts]
[cli-command] = "[import_name].[module]:main"

[project.urls]
Homepage = "[url]"

[tool.setuptools.packages.find]
where = ["src"]
```

For dynamic versioning with setuptools:
```toml
[project]
name = "[project-name]"
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "[import_name].__version__"}
```

---

## Flit-core Library

Minimal, zero-config. Best for single-module libraries.

**pyproject.toml:**
```toml
[build-system]
requires = ["flit_core >= 3.12.0, < 4"]
build-backend = "flit_core.buildapi"

[project]
name = "[project-name]"
version = "[version]"
description = "[One-line description]"
readme = "README.md"
requires-python = ">= 3.10"
license = {text = "MIT"}
authors = [{name = "[Author Name]", email = "[email]"}]
dependencies = []
```

Flit reads version from `__version__` in the package's `__init__.py` if not specified.

---

## Hatchling GUI

For desktop GUI applications (tkinter, CustomTkinter, PyQt, etc.).

**pyproject.toml:**
```toml
[build-system]
requires = ["hatchling >= 1.26"]
build-backend = "hatchling.build"

[project]
name = "[project-name]"
version = "[version]"
description = "[One-line description]"
readme = "README.md"
requires-python = ">= 3.10"
license = {text = "MIT"}
authors = [{name = "[Author Name]"}]
dependencies = [
    "customtkinter >= 5.0",
]

[project.gui-scripts]
[gui-command] = "[import_name].app:main"

[project.scripts]
[cli-command] = "[import_name].cli:main"

[project.urls]
Homepage = "[url]"

[dependency-groups]
dev = ["pytest >= 8.0"]
```

**src/[import_name]/app.py:**
```python
import customtkinter as ctk

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("[App Title]")
        # ... build your UI ...

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
```

---

## Maturin Rust

For Python packages with Rust extensions using PyO3.

**pyproject.toml:**
```toml
[build-system]
requires = ["maturin >= 1.0, < 2.0"]
build-backend = "maturin"

[project]
name = "[project-name]"
version = "[version]"
description = "[One-line description]"
requires-python = ">= 3.10"
license = {text = "MIT"}

[tool.maturin]
features = ["pyo3/extension-module"]
```

Requires a `Cargo.toml` at the project root and a `src/lib.rs` with PyO3 bindings.

---

## Meson-Python C

For C/C++/Fortran extensions using the Meson build system.

**pyproject.toml:**
```toml
[build-system]
requires = ["meson-python >= 0.13.0", "meson >= 1.0.0"]
build-backend = "mesonpy"

[project]
name = "[project-name]"
version = "[version]"
description = "[One-line description]"
requires-python = ">= 3.9"
license = {text = "MIT"}
```

Requires a `meson.build` file. For cross-platform binary wheels, use `cibuildwheel`
in CI.

---

## Legacy Migration Stub

When an external CI system or tool absolutely requires a `setup.py` to exist, keep this
minimal stub alongside your `pyproject.toml`. All actual metadata lives in `pyproject.toml`:

**setup.py:**
```python
import setuptools
setuptools.setup()
```

This file should be the ONLY concession to legacy tooling. Remove it as soon as the
blocking tool is updated.
