from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tomllib
from zipfile import ZipFile

import pytest

from tools.release_meta import extension_package_name

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "extension" / "aludiy_designer" / "blender_manifest.toml"
PACKAGE = ROOT / "dist" / extension_package_name(MANIFEST)


@pytest.fixture(scope="module", autouse=True)
def _build_extension_package() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_extension.py")],
        cwd=ROOT,
        check=True,
    )


def test_extension_zip_has_blender_root_layout_and_runtime_resources() -> None:
    assert PACKAGE.is_file()
    with ZipFile(PACKAGE) as archive:
        names = archive.namelist()
        assert "blender_manifest.toml" in names
        assert "__init__.py" in names
        assert "resources/profile_catalog.sqlite" in names
        assert "vendor/aludiy_core/model.py" in names
        assert "vendor/aludiy_core/units.py" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert not any(name.startswith("tests/") for name in names)
        manifest = tomllib.loads(archive.read("blender_manifest.toml").decode("utf-8"))
        assert manifest["version"] == "0.1.17"
        assert manifest["blender_version_min"] == "5.2.0"


def test_extension_zip_entries_are_deterministically_sorted() -> None:
    with ZipFile(PACKAGE) as archive:
        assert archive.namelist() == sorted(archive.namelist())
