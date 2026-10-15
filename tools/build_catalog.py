#!/usr/bin/env python3
"""Compile catalog source JSON files to a deterministic local SQLite catalog."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aludiy_core.catalog import compile_catalog  # noqa: E402


def main() -> None:
    source = ROOT / "catalog" / "profiles"
    destination = ROOT / "catalog" / "build" / "profile_catalog.sqlite"
    result = compile_catalog(source, destination)
    print(result)


if __name__ == "__main__":
    main()
