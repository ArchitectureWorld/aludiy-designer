#!/usr/bin/env python3
"""Vendor the tested pure-Python core and compiled catalog into the extension."""

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CORE = ROOT / "src" / "aludiy_core"
EXTENSION = ROOT / "extension" / "aludiy_designer"
VENDOR_ROOT = EXTENSION / "vendor"
VENDOR_CORE = VENDOR_ROOT / "aludiy_core"
RESOURCES = EXTENSION / "resources"

sys.path.insert(0, str(ROOT / "src"))
from aludiy_core.catalog import compile_catalog  # noqa: E402


def main() -> None:
    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
    (VENDOR_ROOT / "__init__.py").write_text(
        '"""Vendored runtime dependencies for the Blender extension."""\n',
        encoding="utf-8",
    )
    if VENDOR_CORE.exists():
        shutil.rmtree(VENDOR_CORE)
    shutil.copytree(
        SOURCE_CORE,
        VENDOR_CORE,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    RESOURCES.mkdir(parents=True, exist_ok=True)
    compile_catalog(
        ROOT / "catalog" / "profiles",
        RESOURCES / "profile_catalog.sqlite",
    )
    print(f"Vendored core: {VENDOR_CORE}")
    print(f"Compiled catalog: {RESOURCES / 'profile_catalog.sqlite'}")


if __name__ == "__main__":
    main()
