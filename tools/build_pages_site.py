#!/usr/bin/env python3
"""Prepare the static files deployed as the AluDIY Blender extension repository."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
_VERSIONED_PROGRESS = re.compile(
    r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-[A-Za-z0-9.]+)?\.html$"
)


@dataclass(frozen=True, slots=True)
class SiteArtifacts:
    package: Path
    progress_index: Path
    checksums: Path


def latest_progress_page(progress_dir: Path) -> Path:
    candidates: list[tuple[tuple[int, int, int], Path]] = []
    for path in progress_dir.glob("v*.html"):
        match = _VERSIONED_PROGRESS.fullmatch(path.name)
        if match is None:
            continue
        version = tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
        candidates.append((version, path))
    if not candidates:
        raise FileNotFoundError(f"No versioned progress dashboard found in {progress_dir}")
    return max(candidates, key=lambda item: (item[0], item[1].name))[1]


def prepare_pages_site(package: Path, progress_page: Path, output_dir: Path) -> SiteArtifacts:
    if not package.is_file():
        raise FileNotFoundError(package)
    if not progress_page.is_file():
        raise FileNotFoundError(progress_page)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    copied_package = output_dir / package.name
    shutil.copy2(package, copied_package)

    progress_index = output_dir / "progress" / "index.html"
    progress_index.parent.mkdir(parents=True)
    shutil.copy2(progress_page, progress_index)

    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    digest = hashlib.sha256(copied_package.read_bytes()).hexdigest()
    checksums = output_dir / "SHA256SUMS.txt"
    checksums.write_text(f"{digest}  {copied_package.name}\n", encoding="utf-8")
    return SiteArtifacts(copied_package, progress_index, checksums)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--progress-dir", type=Path, default=ROOT / "docs" / "progress")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    progress_page = args.progress or latest_progress_page(args.progress_dir)
    artifacts = prepare_pages_site(args.package, progress_page, args.output)
    print(artifacts.package)
    print(artifacts.progress_index)
    print(artifacts.checksums)


if __name__ == "__main__":
    main()
