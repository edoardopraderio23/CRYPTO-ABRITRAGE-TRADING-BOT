"""Pytest root configuration.

Adds the repository root to `sys.path` so tests can import the
`src.*` packages directly. Without this, `from src.sentinel.allocator
import allocate` would fail with ModuleNotFoundError because Python's
default search path does not include the repo root when pytest is
invoked.

Once `pyproject.toml` is added (with a `[tool.pytest.ini_options]
pythonpath = ["."]` entry), this file can be removed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
