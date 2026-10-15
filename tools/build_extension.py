#!/usr/bin/env python3
"""Build deterministic Blender extension and acceptance example artifacts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from aludiy_core.cutlist import write_cutlist_csv  # noqa: E402
from aludiy_core.io import create_sample_frame, save_project  # noqa: E402
from tools.release_meta import extension_package_name  # noqa: E402

EXTENSION = ROOT / "extension" / "aludiy_designer"
DIST = ROOT / "dist"
MANIFEST = EXTENSION / "blender_manifest.toml"
PACKAGE = DIST / extension_package_name(MANIFEST)


def _include(path: Path) -> bool:
    relative_parts = path.relative_to(EXTENSION).parts
    return (
        path.is_file()
        and "__pycache__" not in relative_parts
        and not path.name.endswith((".pyc", ".pyo", ".zip"))
    )


def _write_deterministic(archive: ZipFile, source: Path, archive_name: str) -> None:
    info = ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, source.read_bytes())


def build_examples() -> None:
    examples = ROOT / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")
    save_project(project, examples / "sample_frame.aludiy.json")
    write_cutlist_csv(project, examples / "sample_frame_cutlist.csv")


def build_package() -> Path:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_core_into_extension.py")],
        cwd=ROOT,
        check=True,
    )
    build_examples()
    DIST.mkdir(parents=True, exist_ok=True)
    PACKAGE.unlink(missing_ok=True)
    files = sorted(path for path in EXTENSION.rglob("*") if _include(path))
    with ZipFile(PACKAGE, "w") as archive:
        for path in files:
            _write_deterministic(archive, path, path.relative_to(EXTENSION).as_posix())
    return PACKAGE


def main() -> None:
    package = build_package()
    print(package)


if __name__ == "__main__":
    main()
